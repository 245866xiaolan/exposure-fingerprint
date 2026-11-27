#!/usr/bin/env python3
"""
rdb_stream_extract.py — 离线从 Redis/Valkey 的 DUMP 快照里还原 Stream 内容

用途
    SCAN + DUMP 导出的键值快照（JSONL：{"k": b64(key), "d": b64(dump)}）在
    服务端关闭之后仍然可读。Stream 类型（RDB type 15/19/21）内部是 listpack，
    当条目较大时整块被 LZF 压缩 —— 直接 grep 明文会漏掉大部分内容。

    本脚本做三件事：
      1) 解析 DUMP 载荷头，取出 Stream 的 listpack 数量与逐条 [key][listpack]
      2) 对 0xC3 标记的字符串做 LZF 解压
      3) 在解压后的明文里按用户给定的正则抽取（默认演示：抓取请求头里的鉴权字段）

用法
    python3 rdb_stream_extract.py snapshot.jsonl.gz \
        --pattern 'X-Auth-Token:\s*([A-Za-z0-9+/=_\-\.]{20,200})' \
        --out tokens.csv

设计要点
    - 只读、纯标准库，不需要 redis-server
    - 不做 listpack 元素边界解析：解压后直接正则，既快又不受编码差异影响
    - 统计输出按命中次数排序，便于先看“重复度最高”的长会话
"""

import argparse
import base64
import csv
import gzip
import json
import re
import sys
import collections

# ---------------------------------------------------------------- LZF

def lzf_decompress(data: bytes, expected: int) -> bytes:
    """Redis 的 LZF 实现（字面量段 + 回溯引用）。expected 仅用于校验。"""
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        ctrl = data[i]
        i += 1
        if ctrl < 32:                       # 字面量段
            ln = ctrl + 1
            out += data[i:i + ln]
            i += ln
        else:                               # 回溯引用
            ln = ctrl >> 5
            if ln == 7:
                ln += data[i]
                i += 1
            ref = len(out) - ((ctrl & 0x1F) << 8) - data[i] - 1
            i += 1
            ln += 2
            for _ in range(ln):
                out.append(out[ref])
                ref += 1
    return bytes(out)


# ---------------------------------------------------------------- RDB reader

class RdbReader:
    """最小实现：只认长度编码与字符串，够读 Stream 的 listpack 表。"""

    def __init__(self, buf: bytes):
        self.b = buf
        self.p = 0

    def u8(self) -> int:
        v = self.b[self.p]
        self.p += 1
        return v

    def take(self, n: int) -> bytes:
        v = self.b[self.p:self.p + n]
        self.p += n
        return v

    def length(self):
        b = self.u8()
        if b < 0x40:                       # 6 位
            return b
        if b < 0x80:                       # 14 位
            return ((b & 0x3F) << 8) | self.u8()
        if b < 0xC0:                       # 32 位大端
            return int.from_bytes(self.take(4), "big")
        t = b & 0x3F
        if t == 0:
            return int.from_bytes(self.take(1), "little", signed=True)
        if t == 1:
            return int.from_bytes(self.take(2), "little", signed=True)
        if t == 2:
            return int.from_bytes(self.take(4), "little", signed=True)
        if t == 3:                         # LZF
            clen = self.length()
            ulen = self.length()
            return lzf_decompress(self.take(clen), ulen)
        raise ValueError(f"unknown string encoding 0x{b:02x}")

    def string(self):
        n = self.length()
        if isinstance(n, bytes):
            return n
        return self.take(n)


STREAM_TYPES = (15, 19, 21)                # listpacks / listpacks_2 / listpacks_3


def iter_listpacks(dump: bytes):
    """返回 Stream 对象里所有 listpack 的字节串（已解压）。"""
    r = RdbReader(dump)
    typ = r.u8()
    if typ not in STREAM_TYPES:
        return
    count = r.length()
    if not isinstance(count, int):
        return
    for _ in range(count):
        _lpkey = r.string()
        lp = r.string()
        if isinstance(lp, bytes):
            yield lp


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", help="JSONL(.gz)：每行 {\"k\": b64, \"d\": b64}")
    ap.add_argument("--pattern", required=True, help="在 listpack 明文上执行的正则（第 1 组为抽取值）")
    ap.add_argument("--key-suffix", default="_request_log",
                   help="只处理键名以该后缀结尾的键（默认 _request_log）")
    ap.add_argument("--context", type=int, default=400, help="命中点前后保留的上下文字节数")
    ap.add_argument("--out", default="extracted.csv")
    args = ap.parse_args()

    rx = re.compile(args.pattern.encode())
    ua_rx = re.compile(rb"User-Agent:\s*([^\r\n]{0,120})")
    ip_rx = re.compile(rb"X-Forwarded-For:\s*([^\r\n]{0,80})")
    host_rx = re.compile(rb"Host:\s*([^\r\n]{0,80})")

    hits = []
    streams = 0
    opener = gzip.open if args.snapshot.endswith(".gz") else open
    with opener(args.snapshot, "rb") as f:
        for line in f:
            rec = json.loads(line)
            key = base64.b64decode(rec["k"])
            if not key.endswith(args.key_suffix.encode()):
                continue
            streams += 1
            dump = base64.b64decode(rec["d"])
            for lp in iter_listpacks(dump):
                for m in rx.finditer(lp):
                    ctx = lp[max(0, m.start() - args.context): m.start() + args.context]
                    ua = ua_rx.search(ctx)
                    ip = ip_rx.search(ctx)
                    host = host_rx.search(ctx)
                    hits.append({
                        "stream": key.decode("utf-8", "ignore"),
                        "value": m.group(1).decode("utf-8", "ignore"),
                        "host": host.group(1).decode() if host else "",
                        "ua": (ua.group(1).decode() if ua else "")[:80],
                        "ip": (ip.group(1).decode() if ip else "")[:60],
                    })

    uniq = collections.OrderedDict()
    for h in hits:
        u = uniq.setdefault(h["value"], {"count": 0, "streams": set(), **h})
        u["count"] += 1
        u["streams"].add(h["stream"])

    print(f"streams scanned : {streams}")
    print(f"matches         : {len(hits)}")
    print(f"unique values   : {len(uniq)}")
    if uniq:
        top = sorted(uniq.values(), key=lambda x: -x["count"])[:5]
        print("top repeats     : " + ", ".join(str(t["count"]) for t in top))

    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["value", "count", "streams", "host", "ua", "ip"])
        for u in sorted(uniq.values(), key=lambda x: -x["count"]):
            w.writerow([u["value"], u["count"], "|".join(sorted(u["streams"])), u["host"], u["ua"], u["ip"]])
    print(f"written         : {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
