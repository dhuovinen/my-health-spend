# CareBack (code name MHS; formerly My Health Spend, ADR-060)

Reconciles provider bills, insurer EOBs and HSA payments per visit to find billing errors and overpayment. **Durable tier** (docs/DECISIONS.md ADR-020): read `docs/VISION.md`, `docs/ARCHITECTURE.md` and `docs/ROADMAP.md` before structural work, and record irreversible choices as an ADR in `docs/DECISIONS.md` first.

**Current phase:** Release 1, phase 1.6 (acceptance) next. On `main` (2026-10-18, tag `r2-early`): phases 1.1 to 1.5 and the local build of 1.3; phase 1.5 added home in the ADR-023 order with visit cards, the visit page in five sections, the Household page and view switch, and the phone layout with a bottom bar. Members sign in with MFA (recovery codes for a lost phone or password); upload or forward by email provider statements, EOBs (PDF or photo), HSA exports and insurer claims exports; Tesseract OCR and Presidio run in the app tier, the worker extracts fields (layout rules, or Claude per household with dates shifted, PRV-05); the member reviews and confirms; phase 1.4 matches lines, checks the three money identities with the $1.00 tolerance and gives each visit one of nine statuses. Export and delete, an access log and Google Cloud adapters (tested against emulators, DEPLOYMENT.md) are built. ADR-031 to ADR-044 are accepted. Still to come in 1.3: the staging project (needs the Google Cloud account; the step-by-step guide and scripts are in `docs/GCP_SETUP.md` and `tools/gcp/`, tested only with `--dry-run`) and the 95% accuracy target on the held-out corpus (the layout rules score 80% classification and 61.5% amounts; Claude extraction is the plan, not yet measured, needs an API key). Release 2 disputes (DSP-01, DSP-02, DSP-04, DSP-05, DSP-07; ADR-042) and the HSA and tax group (TAX-01 to TAX-04, TAX-06 to TAX-10; ADR-043, the `/tax` page on both apps) are merged ahead of Release 2, with false-positive tracking (PLT-02, ADR-044: members mark a closed finding real or wrong; `/accuracy` and `mhs-admin false-positives`). Merged into `main` on 2026-11-20 (PR #1; ADR-050 to ADR-058), with staging live at https://carebackhealth.com (myhealthspend.com and healthcareback.com forward there, 2026-11-25): REC-06 cost sharing against the plan and REC-09 claim codes, ING-06 learning from corrections, MAT-08 EOB versions, ALC-05 secondary insurance, ALC-08 refunds to the HSA, the Plan ahead page (PRE-01 to PRE-07 without PRE-03), the insurer connection (ING-09, fake payer only), onboarding (UX-09), consent, the privacy notice and the breach plan (CMP-01 to CMP-03, drafts for the attorney). Also on that branch (2026-11-19, ADR-056): REC-15, the plan's terms read from the household's own EOBs. On `feat/social-signup` (2026-11-21, ADR-059 proposed): PRV-13, sign-up with Google or Microsoft behind an owner toggle that starts off.

## How to run

Release 0 app (FastAPI + SQLite, Python 3.12 via uv), registered in `~/Projects/app-registry` on port 3062:

```bash
uv run mhs
```

Open http://127.0.0.1:3062. It binds to 127.0.0.1 only (no login; real health data). Env vars: `MHS_DATA_DIR` (default `data/`), `MHS_PORT` (default 3062).

Release 1 stack (Docker Compose; app on http://127.0.0.1:3063, registered in app-registry as `my-health-spend-r1`). The first run generates passwords and key files into the `secrets` volume:

```bash
docker compose up --build
```

```bash
docker compose exec app mhs-admin create-household "Household name"
```

```bash
docker compose exec -it app mhs-admin add-member --household <household-id> --email you@example.com --name "Your name"
```

The second command prints, once, an authenticator secret and a single-use link (`/enrol/<token>`, 15 minutes) that shows it as a QR code to scan; sign in with email, password and the 6-digit code. For a demo, one command does all of that plus Settings (household member, 2026 plan, HSA) and prints a generated password; then upload the four files in `samples/demo/` and follow `docs/DEMO.md` (rerunnable; new password and code each time):

```bash
docker compose exec app mhs-admin demo-setup
```

Regenerate the synthetic demo pack (committed) after changing its text: `uv run tools/make_demo_pack.py`. Load the made-up sample into a household (or upload an ingest file on the Import page):

```bash
docker compose exec app mhs-admin import --household <household-id> /srv/mhs/samples/example-ingest.json --yes
```

 Full suite against the stack (unit, integration and stack tests, through the `capture` proxy):

```bash
docker compose --profile test run --rm tests
```

Upload documents on the Uploads page (bills, statements, EOBs as PDF or photo; HSA CSV/XLS/XLSX; insurer claims CSV); each document shows "Review" once the worker has read it. The compose app runs Tesseract OCR (`MHS_OCR_ENGINE`) and the Presidio scrubber (`MHS_SCRUBBER`). Claude extraction is off: turn it on per household (it needs a worker with `MHS_EXTRACTOR=claude`, an API key and an egress proxy; SETUP.md "AI extraction"):

```bash
docker compose exec app mhs-admin ai-extraction --household <household-id> on
```

 The user scenarios and how to try each by hand are in `docs/TESTING.md` ("User scenarios"). A full walk through the app as a member, on staging or locally, with importable data (`samples/walkthrough/`, made by `uv run tools/make_walkthrough_sample.py`, on top of `demo-setup`), is `docs/USER_TEST_GUIDE.md`; `tests/test_walkthrough_sample.py` keeps its expected results true. Vault backup and restore (passphrase prompted, or `MHS_BACKUP_PASSPHRASE`) are in `docs/SETUP.md`. Wipe the local stack, data included: `docker compose --profile test down -v`.

A three-person synthetic household (Household page, view switch, a six-line visit) for trying the pages: point `MHS_DATA_DIR` at a scratch folder and import `samples/household-ingest.json` (regenerate with `uv run tools/make_household_sample.py`). The layout tests at 375 and 1280 px drive headless Chromium (`uv run playwright install chromium` once; they skip without it):

```bash
uv run pytest tests/test_ux_layout.py
```

Plan ahead (PRE, ADR-053) is at `/plan` on both apps. The insurer connection (ING-09, ADR-054) is off until `MHS_FHIR_PAYERS` names a payer (SETUP.md "Insurer connection"); consent is at `/consent` and its requirement is an admin-screen toggle (SETUP.md "Consent and the privacy notice"). To try the pages without touching `data/`, the `mhs-scratch` entry in `.claude/launch.json` runs Release 0 on the git-ignored `scratch-data/` folder (import a sample into it first).

False-positive rate of findings (PLT-02, ADR-044): members say "real problem" or "wrong" when closing a finding and see the rate on Finding accuracy; the owner's report, counts only, over every household (`--household`, `--release` optional):

```bash
docker compose exec app mhs-admin false-positives --from 2026-10-01 --to 2026-10-31
```

The test harness runs the made-up data in `samples/harness/` (README there) through the real app in six new households (each family from its CSV rows, from its PDFs and from invoices and exports together; the PDFs are generated from the CSV by `tools/make_harness_pdfs.py`), with no person reviewing, compares the results with the CSV's answers and writes `harness-output/` (git-ignored; `results.png`, `report.html` with logins). `uv run tools/run_harness.py login <email>` prints a member's password and current sign-in code. Exit code 0 means the run finished; add `--strict` to fail on a mismatch:

```bash
uv run tools/run_harness.py
```

REC-14's test plan, data and checker are in `samples/rec14/` (`TEST_PLAN.md`); this imports the data into a running stack, reads the pages and writes `harness-output/rec14/` (`uv run tools/run_rec14_check.py login` prints the login):

```bash
uv run tools/run_rec14_check.py
```

Extraction accuracy on the synthetic corpus (development set `tests/corpus`, held-out set `tests/corpus-holdout`; regenerate with `uv run python tools/make_corpus.py`; add `--extractor claude` with an API key to measure Claude):

```bash
uv run python tools/extraction_accuracy.py tests/corpus-holdout
```

Tests and coverage (the Release 1 tests start a throwaway Postgres container, so Docker must be running; they skip without it):

```bash
uv run pytest
```

```bash
uv run --with pytest-cov pytest --cov=mhs
```

Build an ingest file from real source files, then import it on the Import page by path:

```bash
uv run tools/build_ingest.py --settings data/settings.json --claims data/source/2026-10-09/claims.csv --hsa data/source/2026-10-09/TransactionHistory.xls --statements data/source/2026-10-09/patient-statements --out data/ingest-2026.json
```

First-time setup and the converter's warnings are in `docs/SETUP.md`. Everything the owner sets up outside the code (Google Cloud, OAuth clients, Anthropic, insurer registrations, the BAA and the launch gate), in order, is the checklist in `docs/OWNER_SETUP.md`.

## Gotchas

- The product is CareBack (ADR-060); code, package and infrastructure names stay `mhs`. `tests/test_brand_name.py` fails if "My Health $pend" or "My Health Spend" appears anywhere under `src/`.
- **UX and design work uses the `impeccable` skill** (`/impeccable`, in `.claude/skills/impeccable`, with its agents in `.claude/agents/impeccable-*.md`; pbakaus/impeccable, Apache 2.0, version in `SOURCE`). That means any page, template, `style.css`/`landing.css` change, landing or deck design, or a UX review: start with `/impeccable critique`, `audit`, `polish` or the command that fits, and `/impeccable` alone lists them. The project's rules win over its defaults: `docs/UI_GUIDE.md` is the brief (tokens, Manrope and DM Sans, the red pen, findings language, no promised savings), templates stay CSP-clean, phone rules (ADR-041) and `tests/test_ux_layout.py` still apply, and `core/` never changes to suit the UI. App pages are its "Operate" mode (precision and restraint); the landing page is "Persuade". Not set up, on purpose: its hooks (they run a downloaded engine after every edit) and `live` mode (it can start an agent with permissions bypassed). Its launcher downloads that engine on first use; until the owner allows it, the skill's "launcher unavailable" path applies (read PRODUCT.md and DESIGN.md directly). `PRODUCT.md` (root, written by `/impeccable init` on 2026-11-25) is the product record design work starts from: the household's bill manager at a desktop, WCAG 2.2 AA. `DESIGN.md` (root, `/impeccable document`, 2026-11-25: "The Advocate's Desk", components confident and firm) records the incumbent system from UI_GUIDE.md and the stylesheets, with dark values, ramps and component snippets in `.impeccable/design.json`; UI_GUIDE.md stays the brand standard, so change it first and re-run `/impeccable document`.
- Brand and UI standard: `docs/UI_GUIDE.md`. The app is on it, with Manrope and DM Sans self-hosted in `web/static/fonts/`; new visual work follows the guide. DM Sans has no tabular digits, so figures that must line up use `.num` (Manrope).
- `data/` holds the owner's real health data and is git-ignored. Never import test files into it, never commit it, and don't read the source PDFs or statements unless the owner asks. To try the app, point `MHS_DATA_DIR` at a scratch folder and import `samples/example-ingest.json`.
- Money is integer cents everywhere inside the app (`src/mhs/data/money.py`); ingest files use dollars.
- `src/mhs/core/` is pure functions: no database or web imports, and never changed to suit the UI. `reconcile.py` builds the report (claims per visit, allocation, checks, settlement, the nine statuses); `lines.py` holds the identities, ALC-01 buckets, line pairing and duplicates; `matching.py` the MAT-05 scores; `edits.py` the member's decisions as record changes. `TOLERANCE` in `lines.py` is ADR-015's $1.00.
- The member's reconciliation decisions are saved on the records they change, through `save_record` in `web/pages.py` (validated, marked as member edits): a payment's `allocations`, a document's `visit_id` and `match`, a visit's `payment_path`, `dispute`, `closed_findings` and `documents`. The waiting threshold is a `preference` record (`data/repository.py`) that imports never touch. Findings are matched to closed ones by check code and amount, so a changed amount reopens it.
- Edits made in the app (Settings, provider notes, deletes) are marked in the `owner_edits` table and survive re-import unless the owner ticks "Replace my edits" (ADR-011). Save through `Store.upsert(..., edited=True)` / `Store.delete(..., edited=True)` from any new in-app write path.
- Settings edits are also written to `data/settings.json`, which the converter reads, so in-app changes flow into the next ingest file.
- Release 1 code: adapters in `data/` (db, records, household_store, queue, objects, keys, migrate); upload pipeline in `ingest/` (values, hsa, claims, text, scrub, extract, resolve, worker, OCR stub) with routes in `web/household/intake.py`; vault service in `vault/`, application tier in `web/household/`, stack settings in `stack.py`. The Release 0 pages live once in `web/pages.py` and are mounted by both apps through a `PagesHost`; change a page there, never per app. Templates must stay CSP-clean: no inline `style=`, `<script>` or `on*=` handlers (use `style.css` classes and `static/app.js`), and every post form starts with `{{ csrf_input() }}`. Each tier uses its own Postgres role; household tables have row-level security, so always go through `HouseholdRecords` / `db.tx(household_id)`. Add schema changes as a new numbered file in `src/mhs/data/migrations/`.
- If `docker pull` or a build hangs on `docker-credential-desktop`, run it with a config that has no credential store: `DOCKER_CONFIG=<dir with {} config.json and a cli-plugins symlink to ~/.docker/cli-plugins>`.
- AI requests must stay pseudonymized: identifiers become tokens in the app tier and dates are shifted per person in the worker (`ingest/dates.py`, PRV-05) right before the call; anything new sent to the AI goes through both. Real household data still needs the production project and the data-processing agreement (ADR-028) before AI extraction is turned on.
- Upload rule: identifiers are scrubbed in the application tier (`ingest/scrub.py`, vault tokens) before anything is queued; the worker never sees raw document text, and the Claude extractor (`ingest/ai.py`) sends only that scrubbed text. OCR (`ingest/ocr.py`) also runs in the app tier. Keep it that way. Test documents come from `tests/pdfs.py` (`make_pdf`, `make_image`, `make_scanned_pdf`); never use real documents. AI tests use recorded responses in `tests/fixtures/ai` (no key, no network); `capture` serves the same recordings to `worker-ai` on the stack.
- Tesseract isn't installed locally, so OCR tests skip under `uv run pytest`; they run in the compose `tests` container. Presidio loads spaCy `en_core_web_md` (a uv dependency) once per process.
- The compose project is named `mhs` in every checkout, and images are tagged `mhs:dev` / `mhs:test`: running the stack from a worktree replaces the main checkout's containers. Use `docker compose -p <other-name>` with an override that changes the image tags and drops the published port to test a worktree beside a running stack.
- Phones (ADR-041): at 860px and narrower the top nav is hidden and the pages are in `nav.tabbar`; every control is at least 44px tall. A new standalone link (not inside a sentence) needs a class the phone rule covers (`a.back`, `.page-head a`, `td > a`, or `btn`), or `tests/test_ux_layout.py` flags it. Add new pages to its `PAGES` list.
- The household view's member is in the `mhs_view` cookie (`VIEW_COOKIE` in `web/pages.py`); Home, Visits and Household read it through `view_of()`.
- Dispute cases live on the visit record (`visit.cases`, ADR-042) and their contact log on `provider_note` records with a `case_id`. Letters are drafted in the application tier when the member asks (`web/letters.py`, identifiers from `PagesHost.identifiers`) and are never stored, queued, logged with their text or sent; keep it that way.
- HSA and tax (ADR-043): the logic is `core/tax.py` (pure); IRS limits and the Publication 502 categories are dated JSON in `src/mhs/data/reference/`, never constants in code; add a year or a category version there in the yearly review. Tags and advice are possibilities: every block that suggests an action prints `core.tax.DISCLAIMER` (CMP-04). The routes are in `web/tax_pages.py`, mounted by `add_pages`. Try it with `samples/tax-ingest.json` (`uv run tools/make_tax_sample.py` rewrites it).
- Visits are rows (`visit_row` in `_macros.html`), not cards (ADR-046). REC-14 flags (`core/repeats.py`) have the check result `flag`, never `fail`, so they can't change a visit's status or dollars at stake. Charges over time (UX-11) is `core/charges.py` and `/charges`, drawn as SVG by the template.
- Landing page (ADR-047): `templates/landing.html`, `static/landing.css` and `static/landing.js`, standalone from `base.html` and `style.css`. On Release 1, `/` shows it to anyone without a session (the `SignInRequired` handler in `web/household/app.py`), so test "needs sign-in" against `/visits`, not `/`. Release 0 keeps Home at `/`; both apps serve the page at `/welcome`. On Cloud Run, `MHS_REDIRECT_OTHER_HOSTS=1` forwards every host but `MHS_PUBLIC_URL`'s to it (ADR-058), and `/auth` (the old Lovable sign-in) goes to `/signin`. It reads no household data. Its FAQ and "Sign in" link follow `signup_open` (ADR-059). `dhuovinen/health-reconciler` (Lovable) is no longer the source for it.
- Sign-up (PRV-13, ADR-059, `docs/SIGN_UP_REQUIREMENTS.md`): `web/household/signup.py` (`/signup`, `/terms`), called from the social callback for an unlinked account. Off until an owner opens it on the admin screen (`allow_signup`, only while `require_consent` is on). Creates a household and a member with no password (`password_hash` NULL): anywhere a password is asked for, `confirmed()` in `app.py` takes the code instead, or a sign-in within 10 minutes when the code is off; such a member can't unlink their last provider. Verified emails only (`oidc.email_verified`: Google `email_verified`, Microsoft consumer tenant or `xms_edov`); Apple is sign-in only (`SignInProvider.signup=False`). Tests: `tests/test_r1_signup.py`, TC-PRV-13-10 in `tests/test_ux_layout.py`.
- Social sign-in (PRV-12, ADR-048): `web/household/oidc.py` (the flow), `social.py` (routes), `Accounts` identity methods. Off until `MHS_GOOGLE_CLIENT_ID`/`_SECRET`, the Microsoft pair or the four `MHS_APPLE_` settings are set (SETUP.md "Social sign-in"). Apple (ADR-057) is asked for no scope so it comes back with a GET, skips PKCE, and gets a client secret signed per request (`oidc.client_secret`); it can't be tried on localhost. Linked by provider and subject, never email, and a social account never creates a member. The session cookie is `SameSite=Strict`, so it isn't sent on the way back from a provider: the callback shows the next page itself, never redirects to a page that needs the session. Tests use `tests/fake_oidc.py`; a browser test must put it on a different host from the app (`localhost` vs `127.0.0.1`). With the code off (ADR-049), the callback signs the member in and shows a link to Home.
- Admin screen (PLT-09, ADR-049): `web/household/admin_screen.py` at `/admin`, owners only (`app.members.is_owner`, `mhs-admin owner`) in a session that entered a code, 404 for anyone else; it shows counts and settings, never household data. Service toggles are `app.service_settings` through `features.py` (`Features.set` logs `setting_<name>_on/off`); the code starts required (`DEFAULTS`). `needs_code()` in `app.py` decides per sign-in: owners always. Turning the code on deletes sessions with `code_passed` false. Add a new toggle to `Features` and the screen, not an env var.
- REC-06 (`core/costshare.py`, ADR-050) replays a plan year's claims in EOB-date order; its differences are `flag`s until the plan has `terms_confirmed`, then `fail`s. Claim codes are dated data in `data/reference/claim_codes.json` (our own wording), loaded into `Dataset.claim_codes` by `load_dataset`.
- REC-15 (`core/plan_inference.py`, ADR-056) reads a plan's terms from its primary, current EOBs on every report (`Report.plan_terms`), and stores nothing. A term is `known` only when at least 3 EOBs agree, and they are at least 80% of the EOBs that show it. Only a known term fills an empty entered term (REC-06 then stays a `flag`), and the claim being checked is left out of that inference. A difference from an entered term is a `terms-<term>` flag (kind `terms_mismatch`) on the visit whose EOB made the term known. Coverage's "Use this" only fills the form (`?use=`); the member saves.
- EOB versions (MAT-08, ADR-052) are never overwritten: a corrected EOB is a new document `<id>-v2` with `version_of`; `claim_versions()` in `reconcile.py` picks the current one, and a version of an EOB with `member_edited` waits for the member's `version_choice`. A plan with `coverage_order` secondary makes its EOBs the second step on the visit (ALC-05), not another claim.
- Insurance plans are shown and edited on the Coverage page (`/coverage`, `templates/coverage.html`, the editor in `_plan_editor.html`); the form still posts to `/settings/plans/...`, which redirects back to Coverage, and Settings only lists the plans.
- Planned visits (`planned: true`, ADR-053) are left out of `build_report` until a document is linked to them; `core/estimate.py` lists them.
- The insurer connection (`ingest/fhir.py`, `web/household/connect.py`) never stores a payer token or the payer's patient id; tests use `httpx.MockTransport` through `connect.TRANSPORT`. Consent (`web/household/consent.py`) is checked at upload, forwarded email, import and insurer pull through `collect_for`/`may_collect`; add any new way data comes in there.
- Web tests run on the real date; a test that needs the sample's waiting period (its derm visit, 2026-09-28, waits 30 days) pins the day with the `sample_day` fixture in `tests/test_r1_reconcile_pages.py`.
- Unit tests pin "today" (`TODAY = date(2026, 10, 9)` in `tests/test_reconcile.py`); web tests run on the real date, so don't assert exact day counts there.
