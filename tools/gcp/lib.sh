# shellcheck shell=bash disable=SC2034  # settings used by the scripts that source this file
# Shared settings and helpers for the tools/gcp scripts (docs/GCP_SETUP.md). Sourced, not run.
#
# Every Google Cloud call goes through `run`, `exists` or `lookup`, so `--dry-run` prints each command and runs
# none of them: no network, no credentials, and lookups print placeholders such as <SQL_PRIVATE_IP>.

# Settings; override any of them in the environment.
: "${PROJECT_ID:?Set PROJECT_ID to the staging project id (docs/GCP_SETUP.md step 4)}"
REGION="${REGION:-us-east4}"
DOCAI_LOCATION="${DOCAI_LOCATION:-us}"            # Document AI runs in `us` or `eu`, not in a region
SQL_TIER="${SQL_TIER:-db-f1-micro}"               # the smallest shared-core tier (Enterprise edition)
WORKER_INSTANCES="${WORKER_INSTANCES:-1}"         # 0 pauses the worker (and its cost)

NETWORK=mhs-vpc
SUBNET=mhs-run
SUBNET_RANGE=10.8.0.0/24                          # Cloud Run Direct VPC egress addresses
PSA_RANGE=mhs-psa                                 # private services access range, peered with Cloud SQL
PSA_ADDRESS=10.10.0.0
PSA_PREFIX=20
NO_EGRESS_TAG=mhs-no-egress                       # worker and migrate: Cloud SQL and nothing else
SQL_INSTANCE=mhs-pg
DB_NAME=mhs
BUCKET="${PROJECT_ID}-originals"
KEYRING=mhs
REPO=mhs
DOCAI_NAME=mhs-ocr
APP_PORT=3063                                     # src/mhs/stack.py APP_PORT
VAULT_PORT=8100                                   # src/mhs/stack.py VAULT_PORT

SERVICE_ACCOUNTS=(mhs-app mhs-vault mhs-worker mhs-worker-ai mhs-migrate)
GENERATED_SECRETS=(mhs-db-admin-password mhs-db-app-password mhs-db-worker-password mhs-db-vault-password
                   mhs-vault-token mhs-member-password)
AI_KEY_SECRET=mhs-anthropic-api-key               # added by the owner, only if AI extraction is turned on

APIS=(run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com cloudkms.googleapis.com
      storage.googleapis.com documentai.googleapis.com artifactregistry.googleapis.com
      servicenetworking.googleapis.com compute.googleapis.com logging.googleapis.com)

export CLOUDSDK_CORE_DISABLE_PROMPTS=1            # the scripts ask their own questions
DRY_RUN="${DRY_RUN:-0}"
P=(--project="$PROJECT_ID")

sa_email() { printf '%s@%s.iam.gserviceaccount.com' "$1" "$PROJECT_ID"; }
kms_key() { printf 'projects/%s/locations/%s/keyRings/%s/cryptoKeys/%s' "$PROJECT_ID" "$REGION" "$KEYRING" "$1"; }
image_base() { printf '%s-docker.pkg.dev/%s/%s/mhs' "$REGION" "$PROJECT_ID" "$REPO"; }

step() { printf '\n== %s\n' "$*"; }
note() { printf '   %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# A command as it would be typed: plain words as they are, anything else in single quotes.
show() {
  local a out=""
  for a in "$@"; do
    if [[ "$a" =~ ^[A-Za-z0-9_@%+=:,./-]+$ ]]; then
      out+=" $a"
    else
      out+=" '${a//\'/\'\\\'\'}'"
    fi
  done
  printf '%s\n' "${out# }"
}

# Run a command, or print it under --dry-run.
run() {
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '+ '; show "$@"
  else
    "$@"
  fi
}

# True if a describe/list command succeeds. Under --dry-run nothing exists, so every create is printed.
exists() {
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '? '; show "$@"
    return 1
  fi
  "$@" >/dev/null 2>&1
}

# Print a command's output, or <PLACEHOLDER> under --dry-run.
lookup() {
  local placeholder="$1"; shift
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '<%s>' "$placeholder"
  else
    "$@"
  fi
}

# Parse the flags every script takes; the rest are left in ARGS.
parse_common() {
  ARGS=()
  for a in "$@"; do
    case "$a" in
      --dry-run) DRY_RUN=1 ;;
      *) ARGS+=("$a") ;;
    esac
  done
  if [[ "$PROJECT_ID" == *prod* && "${MHS_ALLOW_PRODUCTION:-0}" != 1 ]]; then
    die "these scripts set up staging (synthetic data only); production needs the BAA first (docs/GCP_SETUP.md)"
  fi
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '# dry run: project %s, region %s; nothing is run\n' "$PROJECT_ID" "$REGION"
  fi
}

# --- values other scripts look up --------------------------------------------------------------

project_number() {
  lookup PROJECT_NUMBER gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)'
}

# Cloud Run's deterministic URL for a service: https://<service>-<project number>.<region>.run.app
service_url() {
  printf 'https://%s-%s.%s.run.app' "$1" "$(project_number)" "$REGION"
}

sql_private_ip() {
  lookup SQL_PRIVATE_IP gcloud sql instances describe "$SQL_INSTANCE" "${P[@]}" \
    --format='value(ipAddresses[0].ipAddress)'
}

docai_endpoint() {
  printf 'https://%s-documentai.googleapis.com/v1/projects/%s/locations/%s/processors' \
    "$DOCAI_LOCATION" "$PROJECT_ID" "$DOCAI_LOCATION"
}

# Call the Document AI REST API (gcloud has no processor commands). The access token goes in a header file
# descriptor, never on the command line.
docai_curl() {
  curl -sS --fail-with-body -H "X-Goog-User-Project: $PROJECT_ID" \
    -H @<(printf 'Authorization: Bearer %s\n' "$(gcloud auth print-access-token)") "$@"
}

# The OCR processor's resource name (projects/<number>/locations/us/processors/<id>), or nothing.
docai_processor() {
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '<DOCAI_PROCESSOR>'
    return
  fi
  docai_curl "$(docai_endpoint)" | python3 -c '
import json, sys
for p in json.load(sys.stdin).get("processors", []):
    if p.get("displayName") == sys.argv[1]:
        print(p["name"], end="")
        break
' "$DOCAI_NAME"
}

# True if a list command prints anything. Under --dry-run, false.
has_output() {
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '? '; show "$@"
    return 1
  fi
  [[ -n "$("$@" 2>/dev/null)" ]]
}

# A secret's latest value, for a command that has to take it as an argument. Never printed.
secret_value() {
  lookup "SECRET $1" gcloud secrets versions access latest --secret="$1" "${P[@]}"
}

# True if a describe command succeeds. Under --dry-run everything is present, so every delete is printed.
present() {
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '? '; show "$@"
    return 0
  fi
  "$@" >/dev/null 2>&1
}

# if_present <describe command ...> -- <delete command ...>
if_present() {
  local check=()
  while [[ "$1" != -- ]]; do check+=("$1"); shift; done
  shift
  if present "${check[@]}"; then
    run "$@"
  fi
}
