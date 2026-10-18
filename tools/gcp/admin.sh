#!/usr/bin/env bash
# Run an `mhs-admin` command as the Cloud Run job that tools/gcp/deploy.sh created, and show its output
# (docs/GCP_SETUP.md part D). Staging only: synthetic households.
#
#   PROJECT_ID=<id> tools/gcp/admin.sh [--dry-run] demo-setup
#   PROJECT_ID=<id> tools/gcp/admin.sh [--dry-run] create-household "Example household"
#   PROJECT_ID=<id> tools/gcp/admin.sh [--dry-run] add-member --household <id> --email a@example.com --name "A Member"
#   PROJECT_ID=<id> tools/gcp/admin.sh [--dry-run] import --household <id> /srv/mhs/samples/example-ingest.json --yes
#
# add-member gets a new random password in the mhs-member-password secret (a job has no terminal to type one);
# read it on your own terminal with the command the script prints.
#
# The job's output, including any authenticator secret, enrolment link or demo password, is in Cloud Logging
# for the project (30 days); see "Open items" in docs/GCP_SETUP.md.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

parse_common "$@"
set -- "${ARGS[@]+"${ARGS[@]}"}"
[[ $# -gt 0 ]] || die "name an mhs-admin command: demo-setup, create-household, add-member, import, reset-mfa, ai-extraction"
for a in "$@"; do
  [[ "$a" != *"|"* ]] || die "arguments can't contain |"
done

script='exec mhs-admin "$@"'
if [[ "$1" == add-member ]]; then
  step "New password for the member, into Secret Manager (not shown)"
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '+ openssl rand -base64 18 | gcloud secrets versions add mhs-member-password --data-file=- --project=%s\n' \
      "$PROJECT_ID"
  else
    openssl rand -base64 18 | tr -d '\n' \
      | gcloud secrets versions add mhs-member-password --data-file=- "${P[@]}" --format=none
  fi
  script='exec mhs-admin "$@" --password-stdin < /secrets/member/password'
fi

joined="-c|$script|mhs-admin"
for a in "$@"; do
  joined+="|$a"
done

step "Run mhs-admin $1"
if [[ "$DRY_RUN" == 1 ]]; then
  run gcloud run jobs execute mhs-admin --region="$REGION" --wait --args="^|^$joined" \
    --format='value(metadata.name)' "${P[@]}"
  execution='<EXECUTION>'
else
  execution="$(gcloud run jobs execute mhs-admin --region="$REGION" --wait --args="^|^$joined" \
    --format='value(metadata.name)' "${P[@]}")" || {
    note "The job failed. Its output:"
    gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="mhs-admin"' \
      --order=asc --freshness=10m --format='value(textPayload)' "${P[@]}"
    exit 1
  }
fi

step "Output of $execution"
filter="resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"mhs-admin\" AND \
labels.\"run.googleapis.com/execution_name\"=\"$execution\""
if [[ "$DRY_RUN" == 1 ]]; then
  run gcloud logging read "$filter" --order=asc --freshness=1h --format='value(textPayload)' "${P[@]}"
else
  for _ in 1 2 3 4 5 6; do  # logs arrive a few seconds after the job ends
    out="$(gcloud logging read "$filter" --order=asc --freshness=1h --format='value(textPayload)' "${P[@]}")"
    [[ -z "$out" ]] || break
    sleep 5
  done
  printf '%s\n' "${out:-(no output yet: run the gcloud logging read command above again in a minute)}"
fi

if [[ "$1" == add-member ]]; then
  note "The member's password, on your own terminal only:"
  note "  gcloud secrets versions access latest --secret=mhs-member-password --project=$PROJECT_ID"
fi
