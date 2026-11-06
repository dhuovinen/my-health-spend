#!/usr/bin/env bash
# The automatic part of "Is it working?" in docs/GCP_SETUP.md: the app answers, the vault and the database
# can't be reached from the internet, the bucket is locked down, and the worker holds no bucket or key access.
#
#   PROJECT_ID=<id> tools/gcp/check.sh [--dry-run]
set -euo pipefail
source "$(dirname "$0")/lib.sh"

parse_common "$@"
failures=0

# check <description> <expected output> <command ...>: pass if the command prints exactly the expected text.
check() {
  local what="$1" want="$2" got; shift 2
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '+ '; show "$@"
    printf '    expect: %s\n' "$want"
    return
  fi
  got="$("$@" 2>/dev/null || true)"
  if [[ "$got" == "$want" ]]; then
    printf 'ok    %s\n' "$what"
  else
    printf 'FAIL  %s: expected %q, got %q\n' "$what" "$want" "$got"
    failures=$((failures + 1))
  fi
}

http_status() {  # url
  curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$1"
}

# Prints "refused" unless the URL answers 200 (Cloud Run answers 404 for internal-only services).
refused() {  # url
  if [[ "$(http_status "$1")" == 200 ]]; then echo answered; else echo refused; fi
}

# One field of a Cloud Run service's JSON description, by a Python expression on `s`.
service_field() {  # service, expression
  gcloud run services describe "$1" --region="$REGION" "${P[@]}" --format=json \
    | python3 -c 'import json, sys; s = json.load(sys.stdin); print(eval(sys.argv[1]))' "$2"
}

# Prints "none" if the service account is missing from the IAM policy the command prints, "found" if it's there.
absent_from() {  # service account, command ...
  local member policy; member="serviceAccount:$(sa_email "$1")"; shift
  policy="$("$@" --format=json)" || { echo "error reading the policy"; return; }
  if grep -q "\"$member\"" <<<"$policy"; then echo found; else echo none; fi
}

APP_URL="${PUBLIC_URL:-$(service_url mhs-app)}"
VAULT_URL="$(service_url mhs-vault)"

step "Staging checks for $PROJECT_ID"
check "the app answers /health over HTTPS" 200 http_status "$APP_URL/health"
check "the vault is not reachable from the internet" refused refused "$VAULT_URL/health"
check "Cloud SQL has no public IP" False \
  gcloud sql instances describe "$SQL_INSTANCE" --format='value(settings.ipConfiguration.ipv4Enabled)' "${P[@]}"
check "Cloud SQL backups and point-in-time recovery are on" $'True\tTrue' \
  gcloud sql instances describe "$SQL_INSTANCE" "${P[@]}" \
  --format='value(settings.backupConfiguration.enabled,settings.backupConfiguration.pointInTimeRecoveryEnabled)'
check "the bucket has public access prevention" enforced \
  gcloud storage buckets describe "gs://$BUCKET" --format='value(public_access_prevention)' "${P[@]}"
check "the bucket has uniform access and versioning" $'True\tTrue' \
  gcloud storage buckets describe "gs://$BUCKET" "${P[@]}" \
  --format='value(uniform_bucket_level_access,versioning_enabled)'
check "the worker can't read the bucket (TC-PRV-06-3)" none \
  absent_from mhs-worker gcloud storage buckets get-iam-policy "gs://$BUCKET" "${P[@]}"
for key in app vault; do
  check "the worker can't use the $key key (TC-PRV-06-3)" none \
    absent_from mhs-worker gcloud kms keys get-iam-policy "$key" --keyring="$KEYRING" --location="$REGION" "${P[@]}"
done
check "the vault service has internal ingress" internal \
  service_field mhs-vault 's["metadata"]["annotations"]["run.googleapis.com/ingress"]'
check "the app sets secure cookies" 1 \
  service_field mhs-app '{e["name"]: e.get("value") for e in s["spec"]["template"]["spec"]["containers"][0]["env"]}["MHS_COOKIE_SECURE"]'

if [[ "$DRY_RUN" != 1 ]]; then
  if [[ "$failures" -gt 0 ]]; then
    die "$failures check(s) failed"
  fi
  step "All checks passed. The manual checks are in docs/GCP_SETUP.md \"Is it working?\"."
fi
