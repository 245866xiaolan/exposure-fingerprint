<div align="center">

# exposure-fingerprint

**把"暴露面里哪些是饵"这件事，从人工肉眼变成一条流水线。**

Layered triage for exposure surface — telling real services from high-interaction decoys at 10k records per round.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)]()
[![precision](https://img.shields.io/badge/precision-0.94-brightgreen.svg)]()
[![rules](https://img.shields.io/badge/rules-19-orange.svg)](rules/rules.yaml)
[![records](https://img.shields.io/badge/evaluated-7148-lightgrey.svg)](docs/benchmarks.md)

</div>

---

## TL;DR

| 指标 | 单指纹基线 | 本工程 |
|---|---:|---:|
| 判定准确率（precision） | 0.71 | **0.94** |
| 召回（recall） | 0.88 | **0.93** |
| F1 | 0.78 | **0.93** |
| 每轮处理量 | — | **7,148 条** |
| 人工复核需求 | ~40% | **<3%** |

> 一个 10,000 条规模的批次，人工判定约 2.5 人日；
> 用这条流水线，复核量降到 300 条以内，**判定时间从人日级压到分钟级**。

---

## 一、问题：饵比鱼多

过去两年，诱饵生态完成了一次升级。今天一个假 Redis 会回 `+PONG`、
会给出格式正确的 `INFO`、会摆出一个看起来像生产环境的目录结构；
一个假 Docker 会给出版本号正常的 `/info`；
一个假 Web 服务会对任意路径返回同一段"泄露的 shadow"——里面还贴心地写着 `uid=0(root)`。

**这类东西的问题不在"看不出来"，而在"看不完"。**

- 一轮采集 7,000–10,000 条端点，人工复核预算通常只有 200 条；
- 漏判一个饵 = 分析师浪费半天；
- 误判一个真目标 = 丢掉一条真实线索；
- 两边都贵，所以只能靠"经验"——而经验不可复制。

---

## 二、洞察：饵是复制出来的，真机是长出来的

诱饵农场有一个天生的破绽：**它们来自同一份镜像。**

同一份镜像意味着同一个进程表：

```
10.0.0.11:11211   STAT pid 2080   STAT uptime 3151236
10.0.0.42:11211   STAT pid 2080   STAT uptime 3151236
10.0.0.77:11211   STAT pid 2080   STAT uptime 3151236
```

**三台机器，一个进程身份。真实环境永远不会这样。**

第二个破绽更致命：**状态必须单调。**

真机的 `uptime_in_seconds` 一定在涨；快照、录像、回放不会。
隔 45 秒采两次，数字不动 —— 这是确定性证据，不依赖任何特征库、不依赖版本知识。

**这两条，几乎没人做。** 绝大多数工具还停留在 banner 正则。

---

## 三、方法：三层递进

```
┌─────────────────────────────────────────────────────────────┐
│  L1  静态指纹     banner / version / 目录 / 服务探测应答      │
│      O(1)/条，41k rec/s                                      │
│      ↓ 命中率 ~30%                                          │
│  L2  跨机结构     pid / run_id / cluster_name / dir 重复     │
│      O(n)，38k rec/s，专杀克隆农场                            │
│      ↓ 命中率 ~70%                                          │
│  L3  时序验证     两次采样，uptime 不前进即判饵               │
│      只对 REVIEW 样本执行，墙钟成本 ≈ 0                       │
│      ↓ 命中率 ~90%                                          │
└─────────────────────────────────────────────────────────────┘
```

**L3 是分水岭。** 我们花了一周才想明白：
与其让模型去"理解"一个服务像不像真的，不如让它去看**一个必须变化的数字变没变**。

---

## 四、结果

标注集 611 条（双人标注，分歧仲裁，κ = 0.91），评测集 7,148 条：

| Config | Precision | Recall | F1 | Throughput |
|---|---:|---:|---:|---:|
| L1 | 0.71 | 0.88 | 0.78 | 41k rec/s |
| L1+L2 | 0.86 | 0.90 | 0.88 | 38k rec/s |
| **L1+L2+L3** | **0.94** | **0.93** | **0.93** | 1.1k rec/s |

分服务：Redis 0.95 / Memcached 0.99 / Elasticsearch 0.91 / Web 0.88。
误差归因（9 个 FP、7 个 FN）写在 [`docs/benchmarks.md`](docs/benchmarks.md)，
**包括我们打不过的那一类：随机化 pid、并伪造 uptime 递增的诱饵。**
诚实写下来，比藏着有用。

---

## 五、为什么它值得被支持

1. **方法可复用**：三层结构不绑定任何具体服务，新增一种服务只需要补身份元组。
2. **规则可脱钩**：判据稳定后 `--emit-rules` 蒸馏成 YAML，生产线交给脚本，模型只做疑难裁决。
3. **产出可复现**：样本、脚本、评测脚本全在这，任何人可以本地跑一遍对账。
4. **下一步明确**：TLS 握手熵作为 L1.5、自适应采样（L2 结论明确就跳过 L3）、脱敏语料开源。

> 现阶段这套流水线正在跑真实批次：每轮 7,000 条抽样进模型做三分类，
> 结果回灌做规则蒸馏。**模型调用额度是目前唯一的瓶颈**——
> 判据、代码、样本、评测都已完成，缺的是把它跑满一轮的量。

---

## 六、快速开始

```bash
git clone https://github.com/245866xiaolan/exposure-fingerprint.git
cd exposure-fingerprint
python3 analyze.py data/sample_hits.jsonl
```

```
records 23 | real 12 | decoy 6 | review 5

IP                PORT   SERVICE     VERDICT  WHY
192.0.2.40        11211  MEMCACHED   DECOY    cross-host fingerprint x3
192.0.2.60        9200   ES          DECOY    cross-host fingerprint x2
198.51.100.31     6379   REDIS       DECOY    trap directory /etc
```

时序模式：

```bash
python3 analyze.py data/sample_hits.jsonl --temporal --interval 45
```

规则蒸馏：

```bash
python3 analyze.py data/sample_hits.jsonl --emit-rules
```

---

## 七、规则集（19 条）

四个家族，全部机器可读（[`rules/rules.yaml`](rules/rules.yaml)）：

| 家族 | 代表规则 | 置信度 |
|---|---|---|
| `structural/*` | 跨机 pid/uptime 重复、共享 ES cluster+node | 0.90–0.98 |
| `temporal/*` | uptime 不前进、keyspace 非单调、回放窗口 | 0.88–0.96 |
| `protocol/*` | RESP 帧不合规、INFO 字段不可能、DBSIZE 与 keyspace 不一致 | 0.70–0.85 |
| `content/*` | 诱饵目录、假 shadow 泄露、全路径同响应、Docker 指纹克隆 | 0.87–0.95 |

---

## 八、路线图

- [x] L1/L2 流水线 + CLI
- [x] L3 时序采样
- [x] 规则蒸馏（`--emit-rules`）
- [ ] TLS 握手熵（L1.5）
- [ ] 自适应采样：L2 结论明确则跳过 L3
- [ ] 脱敏语料 + 评测脚本开源

## 九、引用

```bibtex
@misc{exposure-fingerprint,
  title  = {exposure-fingerprint: layered triage for exposure surface},
  author = {245866xiaolan},
  year   = {2026},
  note   = {v0.3.1}
}
```

## 十、许可

MIT — 见 [LICENSE](LICENSE)。
