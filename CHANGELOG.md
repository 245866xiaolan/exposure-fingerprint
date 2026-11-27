# Changelog

## v0.4.0 — 2026-11-26
- `tools/rdb_stream_extract.py`：从 `SCAN+DUMP` 快照离线还原 Stream
  （DUMP 载荷解析、6 种长度编码、LZF 解压、listpack 明文抽取）
- `tools/service_value_probe.py`：服务价值打分（Redis DBSIZE / ES 文档数 /
  Memcached slab / Docker 容器数）
- `docs/rdb-stream-parsing.md`：离线还原原理与踩坑记录
- README 新增「配套工具」章节

## v0.3.1 — 2026-11-21
- L3 temporal sampling (`--temporal`, default interval 45 s)
- rule distillation (`--emit-rules`), 19 rules in `rules/rules.yaml`
- precision 0.86 -> 0.94 on the labelled subset

## v0.3.0 — 2026-11-14
- L2 structural grouping by service-specific identity tuple
- per-service benchmarks

## v0.2.0 — 2026-11-02
- L1 static rules, CLI, JSONL in/out

## v0.1.0 — 2026-10-26
- initial collection harness
