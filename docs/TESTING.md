# Testing

The strategy in brief. Test cases for every requirement, the open conflicts and the traceability matrix are in [TEST_PLAN.md](TEST_PLAN.md).

## How to run

```bash
uv run pytest
```

The Release 1 tests (marked `postgres`) need a Postgres server: `MHS_TEST_DATABASE_ADMIN_URL`, or Docker running, in which case the session starts a throwaway `postgres:17-alpine` container. Without either they skip. Full suite against the running stack, including the `stack` tests through the `capture` proxy:

```bash
docker compose --profile test run --rm tests
```

```bash
uv run --with pytest-cov pytest --cov=mhs
```

## Current state (2026-10-16, phase 1.1)

| Measure | Value |
| --- | --- |
| Automated tests | 95: 32 Release 0, 60 Release 1 (`tests/test_r1_*.py`), 3 stack (`tests/stack/`); all passing on the compose stack |
| Coverage, `core/` | 96% (target ≥ 80%) |
| Coverage, `data/` | 89 to 100% per module |
| Coverage, `web/household/app.py` and `auth.py` | 96%, 98% |
| Coverage, total | 88% (`mhs-admin` and process entry points are run in the stack, not under coverage) |

Release 1 test cases covered in phase 1.1:

| Case | Test |
| --- | --- |
| TC-PRV-11-1 password alone reaches no data | `test_r1_auth.py::test_tc_prv_11_1_*`, `stack/test_stack.py` |
| TC-PRV-11-2 two-household isolation (records, files, jobs, vault entries; database row-level security) | `test_r1_isolation.py`, `test_r1_database.py::test_row_level_security_*` |
| TC-PRV-11-3 sign-out and idle timeout | `test_r1_auth.py::test_tc_prv_11_3_*` |
| TC-PRV-06-2 unreadable without the key | `test_r1_encryption.py`, `stack/test_stack.py::test_originals_volume_holds_only_ciphertext` |
| TC-PRV-06-3 back-end tier can't decrypt or read the vault | `test_r1_database.py::test_worker_role_*`, `test_r1_encryption.py::test_tc_prv_06_3_*` |
| TC-PRV-07-1 restore onto a fresh server; TC-PRV-07-2 wrong passphrase | `test_r1_backup.py` (including the scripted `mhs-vault` commands) |
| TC-PRV-08-3 CSP; TC-PRV-08-1 (partial) first-party traffic only | `test_r1_csp.py`, `stack/test_stack.py::test_captured_traffic_stays_first_party` |
| TC-PLT-06-2 CI on every change | `.github/workflows/ci.yml` (runs once the repo is on GitHub) |

Not yet: TC-PRV-06-1 (TLS; staging), TC-PRV-07-3 (self-service MFA recovery; `mhs-admin reset-mfa` meanwhile), TC-PRV-08-2 (no analytics events exist).

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

## Release 1 test environment

Defined 2026-10-16; built in phase 1.1. Environments and adapters are in [ARCHITECTURE.md](ARCHITECTURE.md#environments).

### Local (every change)

| Piece | How |
| --- | --- |
| Stack | `docker compose --profile test up`: `app`, `worker`, `vault`, `postgres`, plus `capture` |
| Database | Fresh Postgres database and tier roles per test session; tables truncated before each test (the app's own pooled transactions can't be wrapped in one rollback) |
| Outside services | AI extraction mocked with recorded responses; OCR is Tesseract; keys from a throwaway key file |
| Outbound capture | `capture` is an intercepting proxy (mitmproxy) on the app → worker → AI path. PRV and PLT-04 tests seed the identifier set, run a workflow, then search every captured payload |
| Isolation | Tests create two households and assert neither can read the other's records, files or vault entries (TC-PRV-11-*) |
| Data | `samples/`, synthetic builders, the extraction corpus and the identifier seed set; the redacted scenario library once it exists. Never the real `data/` folder |
| Commands | `uv run pytest` for unit and integration tests; `docker compose --profile test run --rm tests` for the full suite against the stack |
| CI | The same compose file in CI on every change; merge blocked on failure (PLT-06) |

### Staging (per release and on demand)

| Run | What it proves |
| --- | --- |
| OCR accuracy | The extraction corpus through Document AI meets the 95% target before confirmation (PLT-02, TC-PLT-02-1) |
| Cloud integration | The same suite with the Cloud SQL, Cloud Storage and Cloud KMS adapters |
| Restore drill | Vault and database restored from backup into a fresh staging project (TC-PRV-07-1) |
| Performance | 50 typical uploads, p95 machine time under 60 seconds (TC-PLT-05-1) |
| Outbound capture | Traffic from Cloud Run to the AI service captured through a proxy egress; no identifiers (TC-PLT-04-1) |

### Production

No test data and no test runs. Health checks, audit logs and the owner's acceptance in phase 1.6.

## Release 1 additions

| Need | Phase |
| --- | --- |
| Docker Compose stack, CI, household isolation tests | 1.1 |
| Release 0 regression suite (TEST_PLAN Appendix A) run against the stack | 1.2 |
| Extraction corpus with ground truth (≥ 5 documents per type), identifier seed set, capture tests | 1.3 |
| Staging project and the OCR accuracy run | 1.3 |
| Redacted real-world scenario per REC rule | 1.4 |
| Restore drill and performance run in staging | 1.6 |
