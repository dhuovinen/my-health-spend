# Deployment (Google Cloud, staging first)

The plan for the staging project (phase 1.3) and production (phase 1.6), ADR-030 and ADR-036. The code is ready for it: the four adapters switch by environment variable and were tested against emulators and fakes. Nothing below has been run against a real project yet.

## What the owner sets up first

These need your Google account and decisions; nothing in the repository can do them.

1. **Two projects:** `mhs-staging` (synthetic data only) and later `mhs-production`. Separate billing alerts on each.
2. **The BAA** (production, before any real data): accept Google Cloud's Business Associate Addendum in the console, and confirm that every service below is on Google's HIPAA covered-products list (ADR-030 notes Cloud KMS needs checking).
3. **Region:** one US region for everything (for example `us-east4`), and the Document AI location `us`.
4. **A Document AI Enterprise OCR processor** in each project; its resource name goes in `MHS_DOCAI_PROCESSOR`.
5. **An Anthropic API key** under a data-processing agreement (ADR-028), only if AI extraction will be turned on; it goes in Secret Manager, never in the repository.

## Services

| Local (compose) | Google Cloud | Notes |
| --- | --- | --- |
| `app` | Cloud Run service, public over HTTPS, `MHS_COOKIE_SECURE=1`, `MHS_PUBLIC_URL=https://…` | The only public entry point |
| `vault` | Cloud Run service, internal ingress only, reachable from `app` | Own service account and KMS key |
| `worker` | Cloud Run worker pool (or a job on a schedule) with no egress | Rules extraction |
| `worker-ai` | Cloud Run worker pool whose only egress is the Anthropic API (a proxy or a NAT rule) | Only if AI extraction is on (ADR-034) |
| `migrate` | Cloud Run job, run before each deploy | Holds the admin password; nothing else does |
| `setup` | Not used | Secret Manager and KMS replace the generated secrets volume |
| `postgres` | Cloud SQL for PostgreSQL 17, private IP, automated backups, point-in-time recovery | Roles `mhs_app`, `mhs_worker`, `mhs_vault` as locally (ADR-031) |
| originals volume | Cloud Storage bucket per environment, uniform access, no public access, versioning on | `MHS_OBJECT_STORE=gcs`, `MHS_GCS_BUCKET` |
| key files | Cloud KMS key ring per environment with two symmetric keys: `app` and `vault` | `MHS_KEYS=kms`, `MHS_KMS_KEY` per service |
| Tesseract | Document AI Enterprise OCR | `MHS_OCR_ENGINE=documentai`, `MHS_DOCAI_PROCESSOR` |

## Inbound email (ADR-039)

Forwarded bills need an inbound-mail service (for example a mail provider's inbound route) on a domain with an MX record, posting the raw message to the app with its sender checks (SPF, DKIM, DMARC) passed; locally the `mail` container stands in for it. This needs an account and the domain, so it comes with staging.

## Identities and access

| Service account | Can |
| --- | --- |
| `mhs-app` | Cloud SQL client; read and write the bucket; encrypt and decrypt with the `app` key; call Document AI; read its secrets |
| `mhs-vault` | Cloud SQL client; encrypt and decrypt with the `vault` key; read its secrets |
| `mhs-worker` | Cloud SQL client only (no bucket, no keys: TC-PRV-06-3) |
| `mhs-worker-ai` | As `mhs-worker`, plus read the Anthropic key secret |
| `mhs-migrate` | Cloud SQL client; read the admin password secret |

## Secrets (Secret Manager)

Database passwords for each role and the admin, the vault service token, and the Anthropic key if used. Each service reads only its own, mounted as files and given to the app as `MHS_…_FILE` variables, as the compose stack does today.

## Environment variables per service

| Variable | app | vault | worker | worker-ai |
| --- | --- | --- | --- | --- |
| `MHS_DB_HOST`, `MHS_DB_NAME`, `MHS_DB_USER`, `MHS_DB_PASSWORD_FILE` | yes | yes | yes | yes |
| `MHS_OBJECT_STORE=gcs`, `MHS_GCS_BUCKET` | yes | | | |
| `MHS_KEYS=kms`, `MHS_KMS_KEY` | `…/cryptoKeys/app` | `…/cryptoKeys/vault` | | |
| `MHS_OCR_ENGINE=documentai`, `MHS_DOCAI_PROCESSOR` | yes | | | |
| `MHS_SCRUBBER=presidio` | yes | | | |
| `MHS_VAULT_URL`, `MHS_VAULT_TOKEN_FILE` | yes | yes | | |
| `MHS_EXTRACTOR=claude`, `MHS_ANTHROPIC_API_KEY_FILE`, `MHS_AI_PROXY` | | | | yes |
| `MHS_COOKIE_SECURE=1`, `MHS_PUBLIC_URL` | yes | | | |

## Moving the key files to KMS

Each household's data key is stored wrapped by the service's key-encryption key. Switching a service from its key file to KMS means rewrapping: unwrap each household key with the file, wrap it with KMS, in one migration step run by the service itself. Staging starts empty, so it starts on KMS directly; the rewrap tool is needed only if a local database is ever moved up, which ARCHITECTURE.md rules out for real data.

## Staging checks (phase 1.3 exit)

1. Deploy, run `migrate`, create a synthetic household with `mhs-admin` (as a Cloud Run job).
2. Run the compose suite against staging where it applies, and the extraction corpus through Document AI (`tools/extraction_accuracy.py`).
3. Restore drill: vault backup and Cloud SQL point-in-time restore into a fresh project (TC-PRV-07-1).
4. Capture the AI worker's egress through a proxy and search it for the seeded identifiers (TC-PLT-04-1).
