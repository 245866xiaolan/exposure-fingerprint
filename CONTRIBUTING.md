# Contributing

Thanks for taking a look. Scope is intentionally narrow.

## What is welcome
- new decoy signatures (with a minimal reproducible record)
- corrections to existing rules where a real service is misclassified
- benchmark additions (service type + labelled batch)

## What is not
- bundled sample data containing real third-party addresses
- rules that require active exploitation to evaluate

## Pull requests
1. add a record to `data/sample_hits.jsonl` that reproduces the case
2. add a rule under the matching family in `rules/rules.yaml`
3. run `python tests/test_rules.py`
4. describe the FP/FN impact in the PR body
