# Benchmarks (v0.3.1)

Evaluation set: 7,148 records collected over 6 rounds, 611 manually labelled.

## Overall

| Config | Precision | Recall | F1 | Throughput |
|---|---|---|---|---|
| L1 only | 0.71 | 0.88 | 0.78 | 41k rec/s |
| L1+L2 | 0.86 | 0.90 | 0.88 | 38k rec/s |
| L1+L2+L3 | **0.94** | **0.93** | **0.93** | 1.1k rec/s (temporal bound) |

## Per service (L1+L2+L3)

| Service | n | Precision | Recall | Dominant signal |
|---|---|---|---|---|
| Redis | 402 | 0.95 | 0.94 | shared dir, trap directory |
| Memcached | 118 | 0.99 | 0.97 | frozen pid/uptime |
| Elasticsearch | 61 | 0.91 | 0.90 | shared cluster+node name |
| Web | 30 | 0.88 | 0.86 | identical body for all paths |

## Error analysis

False positives (n=9): production Redis clusters that legitimately share
`dir=/data`, and three hosts behind one reverse proxy.

False negatives (n=7): decoys with randomised `pid` and a synthesised uptime
increment. These defeated L2 and L3; L1 caught four on version inconsistency.

## Reproduce

```bash
python3 analyze.py data/sample_hits.jsonl
python3 tests/test_rules.py
```
