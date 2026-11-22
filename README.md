# exposure-fingerprint

**A layered fingerprinting toolkit for large-scale exposure surface triage — telling real services from high-interaction decoys.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)]()
[![status](https://img.shields.io/badge/status-active-brightgreen.svg)]()
[![rules](https://img.shields.io/badge/rules-19-orange.svg)](rules/rules.yaml)

---

## Why

Single-shot banners are no longer enough. Over the last two years the decoy ecosystem has
matured to the point where a fake Redis will answer `PING` with `+PONG`, report a plausible
`INFO` block, and even expose a directory layout that looks like a production install.

At 10k records per round, human review does not scale, and FP/FN costs are asymmetric:
a missed decoy wastes an analyst-day, a false positive burns a valid lead.

This toolkit implements a **three-layer judgement pipeline** that raised our precision on a
7,000-record evaluation set from 0.71 (banner-only) to 0.94.

---

## Method

| Layer | Signal | Cost | Catches |
|---|---|---|---|
| L1 static | banner, version, directory, service-specific probes | O(1)/record | naive decoys |
| L2 structural | cross-host fingerprint duplication (pid / run_id / uptime / dir) | O(n) | cloned images |
| L3 temporal | two-sample time delta on uptime / keyspace counters | 20–60 s | frozen or replayed state |

Layer 3 is what most pipelines miss. A real process increments `uptime_in_seconds`;
a snapshot does not.

### Cross-host duplication

Cloned decoy fleets reuse one image, therefore one `pid` and one `uptime`:

```
10.0.0.11:11211  STAT pid 2080  STAT uptime 3151236
10.0.0.42:11211  STAT pid 2080  STAT uptime 3151236
10.0.0.77:11211  STAT pid 2080  STAT uptime 3151236
```

Three hosts, one process identity. Real fleets never do this.

---

## Results (v0.3.1)

Evaluation set: 7,148 records, 611 manually labelled.

| Config | Precision | Recall | F1 |
|---|---|---|---|
| banner + version | 0.71 | 0.88 | 0.78 |
| + structural (L2) | 0.86 | 0.90 | 0.88 |
| + temporal (L3) | **0.94** | **0.93** | **0.93** |

Per-service breakdown available in [`docs/benchmarks.md`](docs/benchmarks.md).

---

## Quick start

```bash
git clone https://github.com/<you>/exposure-fingerprint.git
cd exposure-fingerprint
python3 analyze.py data/sample_hits.jsonl
```

Output:

```
records 1481 | real 903 | decoy 561 | review 17
precision 0.94 recall 0.93 (labelled subset)
```

### Two-sample mode (layer 3)

```bash
python3 analyze.py data/sample_hits.jsonl --temporal --interval 45
```

### Rule output

```bash
python3 analyze.py data/sample_hits.jsonl --emit-rules
```

Emits a distilled `rules.yaml` you can run without any model in the loop.

---

## Rules

19 rules across four families (`rules/rules.yaml`):

- `structural/*` — duplicate fingerprints, reused directory layouts
- `temporal/*`  — frozen counters, non-monotonic uptime
- `protocol/*`  — inconsistent RESP framing, impossible INFO fields
- `content/*`   — decoy-specific artifacts

---

## Roadmap

- [x] L1/L2 pipeline, CLI
- [x] temporal sampling
- [x] rule distillation
- [ ] TLS handshake entropy as L1.5 signal
- [ ] adaptive sampling (skip L3 when L2 is conclusive)
- [ ] labelled corpus release (sanitised)

## Citation

```
@misc{exposure-fingerprint,
  title  = {exposure-fingerprint: layered triage for exposure surface},
  year   = {2026},
  note   = {v0.3.1}
}
```

## License

MIT — see [LICENSE](LICENSE).
