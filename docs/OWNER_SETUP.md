# Owner setup checklist

Everything you, the owner, have to set up outside the code: accounts, registrations, keys, settings and reviews. Work through it top to bottom and tick each box. Each step says what it unlocks, roughly how long it takes, and where the detail lives, so this page stays a checklist and the detailed guides stay the source:

- [GCP_SETUP.md](GCP_SETUP.md): the Google Cloud staging project, command by command.
- [SETUP.md](SETUP.md): running locally, and the settings for each optional feature.
- [DEPLOYMENT.md](DEPLOYMENT.md): what runs where in Google Cloud.

**Rules for the whole checklist**

- Never put a secret (password, API key, client secret) in a file that git tracks, in a chat, or in an email. Secrets go in the git-ignored `.env` locally, and in Secret Manager in Google Cloud.
- **Staging gets synthetic data only.** Your real health data waits for the production project and the BAA (Stage 5).
- Write each value you collect into the worksheet at the end, except secrets: for those, note only where you stored them.

## Stage 0: what you need first (about 15 minutes)

- [ ] **Docker Desktop** running, and **uv** installed (`brew install uv`).
- [ ] The local stack starts and you can sign in: `docker compose up --build`, then `docker compose exec app mhs-admin demo-setup` (SETUP.md "Release 1 stack").
- [ ] **Make yourself the service owner,** so you can open the admin screen at `/admin` (sign in again afterwards):
  ```bash
  docker compose exec app mhs-admin owner --email you@example.com on
  ```
- [ ] **GitHub:** the repository already has a remote and `.github/workflows/ci.yml`. Push the branch and check that the Actions tab shows a green run. If Actions is off for the repository, turn it on under Settings > Actions.

## Stage 1: Google Cloud account (about 30 minutes; unlocks Stage 2)

Do GCP_SETUP.md **Part A**, steps 1 to 5. In short:

- [ ] Sign in at console.cloud.google.com with the Google account that will own the service. A personal Gmail account works; a Google Workspace account is better if you'll have a business entity later, since the BAA and the billing then belong to the business.
- [ ] **Billing account** with a payment method. Note the billing account id (Billing > Account management).
- [ ] **Budget alert** for the project: about $50 a month, with alerts at 50%, 90% and 100%.
- [ ] **gcloud** installed and signed in twice (`gcloud auth login`, then `gcloud auth application-default login`).
- [ ] **Staging project** created with a unique id (for example `mhs-staging-48213`) and linked to billing.

## Stage 2: the staging project (about 1 hour, mostly waiting; unlocks Stages 3 and 4)

Do GCP_SETUP.md **Parts B to E**. Try each script with `--dry-run` first.

- [ ] `tools/gcp/setup.sh`: APIs, network, bucket, keys, service accounts, secrets, Cloud SQL (about 10 minutes), Artifact Registry, Document AI.
- [ ] `tools/gcp/deploy.sh`: builds the committed code, migrates, deploys the vault, app and worker. Note the app's address (`https://mhs-app-….run.app`).
- [ ] `tools/gcp/admin.sh demo-setup`: a synthetic household. Sign in at the app's address and upload `samples/demo/` (DEMO.md).
- [ ] `tools/gcp/check.sh`, then the manual checks in GCP_SETUP.md Part E, including the restore drill.
- [ ] Pause the worker when you aren't testing, so it doesn't cost about $50 a month: `WORKER_INSTANCES=0 PROJECT_ID=… tools/gcp/deploy.sh worker`.

Read GCP_SETUP.md's **open items** before starting. Two of them affect the steps below: AI extraction (item 6) and forwarded email (item 7) can't run on Cloud Run yet.

## Stage 3: optional features (each one is independent; do only the ones you want)

Each feature is off until it's configured. Set it up locally first, then on staging.

### 3a. Sign in with Google, Microsoft or Apple (about 30 minutes each)

What it gives you: members sign in with a Google, Microsoft or Apple account instead of a password. The authenticator code still applies while it's required.

- [ ] **Google:** console.cloud.google.com, project `mhs-staging`, > Google Auth Platform (older consoles: APIs & Services > OAuth consent screen).
  1. Get started (Project configuration): App Information (name "My Health Spend", support email), Audience **External**, Contact Information, Finish, Create. The first Create can fail with "create failed"; running it again worked (2026-11-19).
  2. Branding > Authorized domains: `myhealthspend.com` (verified in Search Console, GCP_SETUP.md Part F).
  3. Audience: leave it in **Testing** and add your Google account under Test users. Only test users can sign in until the app is published, and nothing needs Google's review until then.
  4. Data Access: nothing to add; the app asks only for `openid` and `email`, which need no review.
  5. Clients > Create client > Web application. Authorized redirect URIs: `https://app.myhealthspend.com/signin/with/google/callback` and `https://myhealthspend.com/signin/with/google/callback` (both, so moving the main address later needs no change here), plus `http://localhost:3063/signin/with/google/callback` on a separate local client if you want it. No JavaScript origins.
  6. Copy the client ID and secret into Secret Manager (below).
  - **Still to do on Google's branding page before publishing** (Testing mode works without them):
    - [ ] **Contact addresses.** The support email and developer contact email are set to a personal address for now. Change both to a `myhealthspend.com` address. The support email must be your Google account's address or a Google Group you manage, so it needs a group (or Google Workspace) for `myhealthspend.com`; the developer contact can be any address.
    - [ ] **Logo.** A square image, 120 × 120 px, PNG or JPG, under 1 MB. Uploading one means Google must verify the brand before members see it, so add it when you're ready to publish. The brand mark exists only as the website's PNG and the app's `favicon.svg` (UI_GUIDE.md); a 120 px export is needed.
    - [ ] **App domain.** Application home page `https://myhealthspend.com`; privacy policy `https://myhealthspend.com/privacy-notice` (the app's page; it is still a draft for the attorney, Stage 5); terms of service `https://myhealthspend.com/terms` (the app's page since PRV-13; a draft for the attorney too). Use these once `myhealthspend.com` is served by the app (the switch after sign-in works); until then they point at the old Hostinger site.
    - [ ] Then publish (Audience > Publish app) and ask for brand verification (Verification Center). This is the "Google OAuth app verification" in Stage 5.
- [ ] **Microsoft:** entra.microsoft.com > App registrations > New registration.
  1. Supported accounts: accounts in any organizational directory and personal Microsoft accounts.
  2. Redirect URI: Web, `https://app.myhealthspend.com/signin/with/microsoft/callback`; then under Authentication add `https://myhealthspend.com/signin/with/microsoft/callback`. For local use, `http://localhost:3063/signin/with/microsoft/callback` (Microsoft accepts plain `http` only for `localhost`). If Entra says your account can't register apps, it has no directory: a free Azure account creates one.
  3. Certificates & secrets > New client secret. Copy the Application (client) ID and the secret's value.
  4. Only if work and school accounts should be able to **sign up** (PRV-13): Token configuration > Add optional claim > ID > `xms_edov`. Without it only personal Microsoft accounts can sign up, because Microsoft doesn't vouch for a work account's email (ADR-059). Linking and signing in work either way.
- [ ] **Apple** (ADR-057; needs the paid Apple Developer Program, and a real HTTPS domain, so staging only: do Stage 4 first): developer.apple.com > Certificates, Identifiers & Profiles.
  1. Identifiers > App IDs: register one (for example `com.myhealthspend.app`) with "Sign in with Apple" ticked.
  2. Identifiers > Services IDs: register one (for example `com.myhealthspend.web`). This is the client ID. Tick "Sign in with Apple", Configure: primary App ID from step 1, "Domains and Subdomains" `app.myhealthspend.com`, "Return URLs" `https://app.myhealthspend.com/signin/with/apple/callback`. Apple accepts neither `localhost` nor plain `http`.
  3. Keys: create a key with "Sign in with Apple" ticked, linked to the App ID. Download the `.p8` file (only once) and note its Key ID. Your Team ID is under Membership details.
  4. No scopes to choose: the app asks Apple for none, so members aren't asked to share or hide their email.
- [ ] **Locally:** add these lines to `.env` beside `compose.yaml`, then restart with `docker compose up -d app`:
  ```bash
  MHS_PUBLIC_URL=http://localhost:3063
  MHS_GOOGLE_CLIENT_ID=…
  MHS_GOOGLE_CLIENT_SECRET=…
  ```
  Open the app at `http://localhost:3063` (not 127.0.0.1), sign in with your password, and link the account on your Account page.
- [ ] **On staging:** put each value in Secret Manager under the name below (client IDs too, so a deploy never needs them typed again), grant the app access, and deploy the app. `deploy.sh` turns on each provider whose secrets are all there and says which.

  | Provider | Secrets |
  | --- | --- |
  | Google | `mhs-google-client-id`, `mhs-google-client-secret` |
  | Microsoft | `mhs-microsoft-client-id`, `mhs-microsoft-client-secret` |
  | Apple | `mhs-apple-client-id` (the Services ID), `mhs-apple-team-id`, `mhs-apple-key-id`, `mhs-apple-private-key` (the `.p8` file) |

  Each one like this; it reads what you paste, then press Ctrl-D (a line break at the end is ignored):
  ```bash
  gcloud secrets create mhs-google-client-id --data-file=- --replication-policy=user-managed --locations=us-east4 --project=$PROJECT_ID
  ```
  Apple's key from its file:
  ```bash
  gcloud secrets create mhs-apple-private-key --data-file=AuthKey_<key id>.p8 --replication-policy=user-managed --locations=us-east4 --project=$PROJECT_ID
  ```
  Then grant them to the app and deploy it (with your domain, Stage 4):
  ```bash
  PROJECT_ID=$PROJECT_ID tools/gcp/setup.sh secrets
  ```
  ```bash
  PUBLIC_URL=https://app.myhealthspend.com PROJECT_ID=$PROJECT_ID tools/gcp/deploy.sh app
  ```
  To change a value later, add a version (`gcloud secrets versions add <name> --data-file=-`) and deploy the app again.
- [ ] On the admin screen, check that the provider shows as on.
- [ ] **Sign-up (PRV-13, ADR-059), only once the launch gate below is passed:** the Google consent screen must be published (Audience > Publish app), or only test users get through. Then on the admin screen turn on "Consent before collection", then "Open sign-up". Keep sign-up closed on staging except to try it: staging holds made-up data only.

### 3b. AI reading with Claude (about 30 minutes, plus the agreement)

What it gives you: Claude reads documents instead of the layout rules, which get about 61.5% of amounts right on the held-out test set. The text Claude sees has names and ID numbers replaced by tokens, and dates shifted.

- [ ] **Anthropic account:** console.anthropic.com. Create an organization, add billing and set a monthly spend limit (Settings > Limits).
- [ ] **Data terms (ADR-028):** read Anthropic's commercial terms and data processing addendum, and confirm that API data isn't used for training. If you want it, ask Anthropic about zero data retention. Keep a copy of what you agreed to.
- [ ] **API key:** Settings > API keys > Create key, named for the environment (for example `mhs-local`). Copy it once.
- [ ] **Measure it first, with synthetic documents only:**
  ```bash
  MHS_ANTHROPIC_API_KEY=… uv run python tools/extraction_accuracy.py tests/corpus-holdout --extractor claude
  ```
  The target is 95% (PLT-02). Write the result into TESTING.md.
- [ ] **Locally:** SETUP.md "AI extraction". It needs a worker with `MHS_EXTRACTOR=claude`, the key, and an egress proxy, then the per-household switch: `mhs-admin ai-extraction --household <id> on`.
- [ ] **On staging:** blocked until the egress proxy exists (GCP_SETUP.md open item 6). You can already store the key with GCP_SETUP.md step B10.

### 3c. Connect an insurer (about 1 hour for the Medicare sandbox; weeks for a commercial insurer)

What it gives you: claims arrive from the insurer instead of photographed EOBs (ADR-054). **This has only been tested against a fake insurer.** The first real connection may show that the code needs small changes, for example in the scopes it asks for.

- [ ] **Practice on the CMS Blue Button 2.0 sandbox,** which serves synthetic Medicare claims:
  1. Create a developer account in the Blue Button 2.0 developer sandbox (CMS's site for Blue Button developers).
  2. Register an application. Redirect URI: `http://localhost:3063/connect/bluebutton/callback` for local, and the staging address with the same path.
  3. Note the client ID and secret, and one of the sandbox's synthetic test users.
  4. Copy the FHIR base, authorize and token addresses from CMS's current documentation into the worksheet; don't assume them.
- [ ] **Configure it** in `.env` (one line; SETUP.md "Insurer connection"):
  ```bash
  MHS_FHIR_PAYERS='[{"name": "bluebutton", "label": "Medicare (sandbox)", "fhir_base": "<FHIR base>", "authorize_url": "<authorize URL>", "token_url": "<token URL>", "client_id": "<client id>"}]'
  MHS_FHIR_BLUEBUTTON_SECRET=<client secret>
  ```
  Restart the app. Add a plan for the claims' year in Settings, then go to Uploads > "Connect your insurer".
- [ ] **Commercial insurers:** every CMS-regulated plan publishes a Patient Access API, but each one has its own developer portal, registration and review. Find it on the insurer's website (search for "Patient Access API" or "interoperability"). Expect a review of the app and of its privacy notice, which is another reason for Stage 5's attorney review.

### 3d. Forwarding bills by email (blocked)

Locally the `mail` container already takes forwarded email (ADR-039). Elsewhere it needs a domain you own, MX records, an inbound-mail provider and an HTTP endpoint the app doesn't have yet (GCP_SETUP.md open item 7). Nothing to set up until that's built.

## Stage 4: a domain name (optional for staging, recommended for production; about 1 hour plus DNS time)

What it gives you: a stable address instead of the `run.app` one. That address goes into every OAuth and insurer redirect URI, so set the domain up before you register production clients.

- [ ] `myhealthspend.com` is registered, with its DNS at Hostinger; the landing page stays there.
- [ ] Point `app.myhealthspend.com` at the app: GCP_SETUP.md Part F, step by step (domain proof, mapping, the `CNAME` at Hostinger, the certificate). A load balancer replaces the mapping for production.
- [ ] Deploy with `PUBLIC_URL=https://app.myhealthspend.com`, and add the new redirect URIs to each OAuth client, Apple's Services ID and each insurer registration.
- [ ] Point the landing page's "Sign in" at `https://app.myhealthspend.com/signin`.

## Stage 5: production and the launch gate (before any real data, and before anyone else uses it)

**Your own household's real data needs:**

- [ ] A **production project**, set up like staging with GCP_SETUP.md. The scripts refuse a project id containing `prod` unless you set `MHS_ALLOW_PRODUCTION=1`.
- [ ] **The Google Cloud BAA:** accept Google Cloud's Business Associate Addendum for the account, following Google's HIPAA compliance page, and keep a copy. Check every service in DEPLOYMENT.md against Google's HIPAA covered-products list (Cloud KMS is the one ADR-030 says to check).
- [ ] **Anthropic data terms** in place before AI reading is turned on for real data (ADR-028).
- [ ] The restore drill done on production (TC-PRV-07-1).
- [ ] The **vault backup passphrase** chosen and stored somewhere safe and offline (SETUP.md "Back up and restore the vault").

**Inviting anyone outside your household also needs** (the launch gate, ROADMAP.md):

- [ ] A **healthcare privacy attorney** reviews the privacy notice (`/privacy-notice`), the Terms of Service (`/terms`), the consent page (`/consent`) and `docs/BREACH_RESPONSE.md`, and confirms what the FTC Health Breach Notification Rule and Washington's My Health My Data Act require of you. Update all three with their changes, then remove "draft".
- [ ] A **tabletop exercise** of the breach plan (TC-CMP-01-2).
- [ ] **Turn on "Consent before collection"** on the admin screen.
- [ ] Decide whether the authenticator code must stay on for other households (ADR-049); the recommendation is yes.
- [ ] **Google OAuth app verification** and Microsoft publisher verification, if social sign-in is on. Apple has no review for web sign-in, but its button wording rules apply.
- [ ] Production registrations with each insurer you connect.

## Stage 6: the acceptance month (phase 1.6)

- [ ] Load a month of your household's real visits into production.
- [ ] Close every finding as "real problem" or "wrong".
- [ ] Run the false-positive report for that month (target: 5% or less):
  ```bash
  docker compose exec app mhs-admin false-positives --from <first day> --to <last day>
  ```
  On Cloud Run, run it as the admin job (GCP_SETUP.md Part D).

## Worksheet

Write the values here, or in a private note if you'd rather not commit them. Secrets go only where the last column says.

| Value | Where you get it | Where it goes | Yours |
| --- | --- | --- | --- |
| Billing account id | Cloud console > Billing | `gcloud billing projects link` | |
| Staging project id | You choose it | `PROJECT_ID=` for every script | |
| Region | `us-east4` unless you choose otherwise | `REGION=` | |
| Staging app address | Printed by `deploy.sh` | OAuth and insurer redirect URIs | |
| Google client ID | APIs & Services > Credentials | `MHS_GOOGLE_CLIENT_ID` | |
| Google client secret (secret) | Same | `.env`, or Secret Manager `mhs-google-client-secret` (the ID in `mhs-google-client-id`) | stored in: |
| Microsoft client ID | Entra > App registrations | `MHS_MICROSOFT_CLIENT_ID` | |
| Microsoft client secret (secret) | Certificates & secrets | `.env`, or Secret Manager `mhs-microsoft-client-secret` (the ID in `mhs-microsoft-client-id`) | stored in: |
| Apple Services ID, Team ID, Key ID | developer.apple.com > Identifiers, Membership, Keys | Secret Manager `mhs-apple-client-id`, `mhs-apple-team-id`, `mhs-apple-key-id` | |
| Apple private key `.p8` (secret) | developer.apple.com > Keys (downloaded once) | Secret Manager `mhs-apple-private-key` | stored in: |
| Anthropic API key (secret) | console.anthropic.com > API keys | `.env` locally; Secret Manager `mhs-anthropic-api-key` | stored in: |
| Insurer FHIR base, authorize and token URLs | The insurer's developer documentation | `MHS_FHIR_PAYERS` | |
| Insurer client ID | The insurer's developer portal | `MHS_FHIR_PAYERS` | |
| Insurer client secret (secret) | Same | `MHS_FHIR_<NAME>_SECRET` | stored in: |
| Domain | `myhealthspend.com` (Hostinger); the app at `app.myhealthspend.com` | `PUBLIC_URL` | |
| Vault backup passphrase (secret) | You choose it | Prompted at backup time; kept offline | stored in: |
