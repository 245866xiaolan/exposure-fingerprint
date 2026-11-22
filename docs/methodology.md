# Methodology

## Problem statement

Exposure triage at scale is a precision problem, not a discovery problem.
Port scanners give us 10k candidate endpoints per round; the analyst's budget is
roughly 200. Every false positive costs review time, every false negative costs a
missed lead. Single-shot banners sit at ~0.71 precision on our labelled subset.

## Layers

### L1 — static

Cheap, parallel, no state. Banner regexes, version bounds, directory layout,
service-specific probe replies. Catches naive decoys and misconfigured hosts.
Known weakness: modern decoys answer plausibly.

### L2 — structural

A decoy fleet is built from one image. That image has one process table.
Consequently `pid`, `run_id`, `cluster_name`, `node_name` and even the serving
directory repeat across hosts that should be independent.

We group records by a service-specific identity tuple and flag any group with
`len(group) > 1` for identity fields that must be unique per process.

Implementation detail: identity tuples are normalised (sorted, truncated to 120
bytes) so cosmetic banner padding does not defeat grouping.

### L3 — temporal

State that must be monotonic is the strongest cheap signal available:
`uptime_in_seconds`, `keyspace` counters, `stats uptime`.

Two samples separated by 45 s: if the counter does not advance, the endpoint is
replaying a captured response. A frozen counter is deterministic evidence; it does
not depend on heuristics or version knowledge.

Cost: one extra round-trip plus the interval. We run L3 only on records that
survived L1/L2 as `REVIEW`, which keeps wall-clock overhead near zero relative to
scan time.

## Rule distillation

Once a judgement pattern stabilises, it is written into `rules/rules.yaml` and the
model is removed from that path. The pipeline keeps two execution modes:

- **model-assisted** — for new service types and ambiguous records
- **rule-only** — for everything distilled, running at line rate

`analyze.py --emit-rules` writes a candidate rule file from a labelled batch;
review is manual.

## Evaluation

Labelled subset: 611 records across Redis (402), Memcached (118), Elasticsearch
(61), Web (30). Labels were assigned by two reviewers with adjudication on
disagreement (kappa 0.91).

Metrics are computed per-class and macro-averaged; see `docs/benchmarks.md`.

## Limitations

1. L3 requires the endpoint to expose a monotonic counter. Services without one
   fall back to L2 and are reported as `REVIEW` rather than guessed.
2. A sufficiently patient adversary can clone images with randomised identities.
   L3 still catches them unless the counter is synthesised to advance.
3. Cross-host grouping requires a batch of records; single-record judgement is
   weaker by construction.
