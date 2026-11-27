# 离线还原 Redis Stream：DUMP 载荷、LZF 与 listpack

> 场景：目标在采集之后关闭了服务端（端口消失、容器被重建），
> 但你手里已有 `SCAN + DUMP` 导出的键值快照。
> 本文说明如何在不启动 redis-server 的前提下，把 Stream 里的内容原样还原出来。

---

## 1. 为什么不能直接 grep

Stream 的条目存放在 **listpack** 里。当单个 listpack 超过阈值（默认 1 KB 左右）
或压缩率满足条件时，RDB 会把整块 listpack 用 **LZF** 压缩再写入。
于是快照里保存的是压缩后的字节，明文关键词（字段名、请求头）在不解压的情况下不可见。

实测差异：

| 手段 | 覆盖范围 |
|---|---|
| 直接对快照二进制 grep | 只能命中「未被压缩」的小条目，通常不足 10% |
| 解压后抽取 | 10 条流全部命中，条数提升 30 倍以上 |

---

## 2. DUMP 载荷结构

`DUMP key` 返回的是**单个对象的序列化值**，不是完整 RDB 文件：

```
[type 1B][object payload …][rdbver 2B LE][crc64 8B]
```

Stream 的类型字节有三代：

| type | 版本 | 说明 |
|---|---|---|
| 15 | RDB 5+ | `STREAM_LISTPACKS` |
| 19 | RDB 9+ | `STREAM_LISTPACKS_2`（增加 first_id / max_deleted_entry_id / entries_added） |
| 21 | RDB 10+ | `STREAM_LISTPACKS_3`（增加 consumer group 的 PEL 计数） |

三代的**开头完全一致**：

```
listpack_count : length
repeat listpack_count times:
    listpack_key  : string      # 该块覆盖的 ID 区间，如 "1699999999999-0"
    listpack_data : string      # 可能被 LZF 压缩
```

因此只读这一段就能拿到全部内容，后面的 length / last_id / groups 结构可以完全跳过。

---

## 3. 长度编码（必须精确实现）

```
0x00–0x3F   6 位长度，值即长度
0x40–0x7F   14 位长度 ((b & 0x3F) << 8) | next
0x80–0xBF   32 位长度，后接 4 字节大端
0xC0|0x00   int8
0xC0|0x01   int16（小端）
0xC0|0x02   int32（小端）
0xC0|0x03   LZF：clen(length) + ulen(length) + payload(clen 字节)
```

> **常见踩坑**：把 32 位分支错写成 `((b & 0x3F) << 24) | …`。
> `0x80` 的低 6 位是 0，真实长度在随后的 4 个字节里；
> 写错会导致 LZF 解压时回溯引用越界（`IndexError`）。

---

## 4. LZF 解压

Redis 的 LZF 是一种极简 LZ77 变体，控制字节分两种：

```
ctrl < 32   ：字面量段，复制 ctrl+1 字节
ctrl >= 32  ：回溯引用
              len = ctrl >> 5 ，若 len == 7 再读 1 字节累加
              ref = out_len - ((ctrl & 0x1F) << 8) - 1
              ref -= 下一个字节
              复制 len + 2 字节
```

完整实现约 25 行，见 `tools/rdb_stream_extract.py` 的 `lzf_decompress()`。

---

## 5. listpack 不必逐元素解析

listpack 的内部结构为：`header(6B) + entries + 0xFF`，每个 entry 有
`encoding + data + backlen`，类型包括 7/13 位整数、6/12/32 位字符串等。

但在**取证场景**下不需要还原元素边界：

1. 解压后的 listpack 里，字段值就是原始明文字节；
2. 用正则直接在整块字节上匹配目标串（例如 `X-Auth-Token:\s*(\S{20,200})`）；
3. 命中点前后各取 400 字节作为上下文，即可同时提取 `Host` / `User-Agent` / `X-Forwarded-For`。

好处：不依赖对方使用的 listpack 编码组合（不同版本有 intset / quicklist / listpack 差异），
也不会因为某个 entry 编码分支没实现而中断。

---

## 6. 输出与判读

`tools/rdb_stream_extract.py` 输出三列统计：

```
streams scanned : 处理的 Stream 数量
matches         : 正则命中总次数（含重复）
unique values   : 去重后的值数量
```

再用 `value` 的出现次数排序：

- **高频值**：长期在线的会话，说明令牌在请求过程中被持续续期（滑动过期）；
- **低频值**：新登录或短会话；
- **同一值横跨多个 Stream**：同一凭据在不同租户流里复用，是横向影响的直接证据。

---

## 7. 复用建议

```bash
# 1) 抽某个字段
python3 tools/rdb_stream_extract.py snapshot.jsonl.gz \
    --pattern 'X-Auth-Token:\s*([A-Za-z0-9+/=_\-\.]{20,200})'

# 2) 抽所有内网地址
python3 tools/rdb_stream_extract.py snapshot.jsonl.gz \
    --pattern '(?:10|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.[0-9.]+'

# 3) 抽 OAuth 响应体里的 token（脱敏通常只处理请求头，响应体是完整的）
python3 tools/rdb_stream_extract.py snapshot.jsonl.gz \
    --pattern '"access_token":"([^"]+)"'
```

---

## 8. 免责声明

本文与配套脚本仅用于**自有环境**的数据恢复、或已获书面授权的评估。
请勿用于未授权系统。
