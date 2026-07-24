# Contributing

Thanks for helping build trueset. This project is small on purpose -- the core
`Backend` protocol is the moat and should stay tiny.

## Setup

```bash
git clone <your-fork-url>
cd trueset
pip install -e ".[dev,sql]"
pytest -q
```

## Before opening a PR

- `pytest -q` passes (currently 25 tests).
- `ruff check .` is clean.
- New checks or backends include tests. A new backend MUST include a
  cross-engine parity test (see `tests/test_duckdb.py`) asserting it agrees with
  pandas on the example suites.

## Design rules

1. Checks talk only to the `Backend` protocol -- never import pandas/duckdb in a
   check.
2. AI may author checks, but only deterministic, registry-validated checks run
   against data. No LLM in the pass/fail path.
3. Keep the `Backend` protocol minimal; only add a primitive if several checks
   share it.

## License

This project is Apache-2.0. By contributing you agree your contributions are
licensed under Apache-2.0.
