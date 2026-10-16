# Testing

The strategy in brief. Test cases for every requirement, the open conflicts and the traceability matrix are in [TEST_PLAN.md](TEST_PLAN.md).

## How to run

```bash
uv run pytest
```

```bash
uv run --with pytest-cov pytest --cov=mhs
```

## Current state (2026-10-15)

| Measure | Value |
| --- | --- |
| Automated tests | 32, all passing |
| Coverage, `core/` | 96% (target ≥ 80%) |
| Coverage, `data/` | 89 to 100% per module |
| Coverage, `web/app.py` | 78% |
| Coverage, total | 90% |

## Levels

| Level | Where | Covers |
| --- | --- | --- |
| Unit | `tests/test_reconcile.py`: synthetic datasets built with `base()`, `eob()`, `pay()`, `visit()`; "today" pinned | Core rules: checks, statuses, allocation, ledgers, HSA flags, limits |
| Integration | `tests/test_importer.py`, `tests/test_web.py`: temp data folder, `fastapi.testclient.TestClient` | Import validation and upsert, owner-edit protection, pages, forms |
| End-to-end | Browser against `uv run mhs` with `MHS_DATA_DIR` on a scratch folder | Screens and flows |
| Security and privacy (Release 1) | Intercepting proxy between tiers, seeded identifiers, storage inspection | PRV, PLT-04 |
| Performance (Release 1) | Timed runs on the scenario library | PLT-05 |
| Review | Checklists | CMP, PLT-06 coverage |

## Rules

- Tests run alongside implementation. A task isn't done until `uv run pytest` is green.
- `src/mhs/core/` keeps unit coverage ≥ 80%.
- Never use the real `data/` folder in tests; fixtures use `samples/example-ingest.json` or synthetic data. Real-world scenarios enter the scenario library only after redaction (PLT-06).
- Assertions on money use integer cents.
- No secrets or environment-specific values in tests.

## Release 1 additions

| Need | Phase |
| --- | --- |
| CI running the suite and the scenario library on every change | 1.1 |
| Server test environment: application tier, back-end tier, identity vault, proxy between tiers | 1.1 |
| Household isolation tests (TC-PRV-11-*) | 1.1 |
| Release 0 regression suite (TEST_PLAN Appendix A) run against the server | 1.2 |
| Extraction corpus with ground truth, ≥ 5 documents per type | 1.3 |
| Identifier seed set and outbound-capture tests | 1.3 |
| Redacted real-world scenario per REC rule | 1.4 |
