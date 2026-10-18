#!/usr/bin/env bash
# Delete what setup.sh and deploy.sh created (docs/GCP_SETUP.md part F). Asks you to type the project id first.
# Everything in the bucket and the database goes with it, permanently: staging holds synthetic data only.
#
#   PROJECT_ID=<id> tools/gcp/teardown.sh [--dry-run]                    resources one by one; the project stays
#   PROJECT_ID=<id> tools/gcp/teardown.sh [--dry-run] --delete-project   the whole project (30 days to undo)
#
# Cloud KMS never deletes key rings or keys: their key versions are destroyed instead, which stops their cost.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

parse_common "$@"
DELETE_PROJECT=0
for a in "${ARGS[@]+"${ARGS[@]}"}"; do
  case "$a" in
    --delete-project) DELETE_PROJECT=1 ;;
    *) die "unknown flag $a" ;;
  esac
done

if [[ "$DRY_RUN" != 1 ]]; then
  if [[ "$DELETE_PROJECT" == 1 ]]; then
    printf 'This shuts down the whole project %s and everything in it.\n' "$PROJECT_ID"
  else
    printf 'This deletes the My Health Spend services, database, bucket, secrets, image repository, Document AI\n'
    printf 'processor, service accounts and network in %s, and destroys its KMS key versions.\n' "$PROJECT_ID"
  fi
  read -r -p "Type the project id to go ahead: " answer
  [[ "$answer" == "$PROJECT_ID" ]] || die "not confirmed; nothing was deleted"
fi

if [[ "$DELETE_PROJECT" == 1 ]]; then
  step "Shut down the project (restorable for 30 days with gcloud projects undelete)"
  run gcloud projects delete "$PROJECT_ID" --quiet
  exit 0
fi

step "Cloud Run worker pools, services and jobs"
for pool in mhs-worker mhs-worker-ai; do
  if_present gcloud run worker-pools describe "$pool" --region="$REGION" "${P[@]}" -- \
      gcloud run worker-pools delete "$pool" --region="$REGION" --quiet "${P[@]}"
done
for service in mhs-app mhs-vault; do
  if_present gcloud run services describe "$service" --region="$REGION" "${P[@]}" -- \
      gcloud run services delete "$service" --region="$REGION" --quiet "${P[@]}"
done
for job in mhs-migrate mhs-admin; do
  if_present gcloud run jobs describe "$job" --region="$REGION" "${P[@]}" -- \
      gcloud run jobs delete "$job" --region="$REGION" --quiet "${P[@]}"
done

step "Cloud SQL instance (its backups go with it)"
if present gcloud sql instances describe "$SQL_INSTANCE" "${P[@]}"; then
  run gcloud sql instances patch "$SQL_INSTANCE" --no-deletion-protection --quiet "${P[@]}"
  run gcloud sql instances delete "$SQL_INSTANCE" --quiet "${P[@]}"
fi

step "Bucket, every object version included"
if_present gcloud storage buckets describe "gs://$BUCKET" "${P[@]}" -- \
    gcloud storage rm --recursive --all-versions "gs://$BUCKET" "${P[@]}"

step "Secrets"
for name in "${GENERATED_SECRETS[@]}" "$AI_KEY_SECRET"; do
  if_present gcloud secrets describe "$name" "${P[@]}" -- \
      gcloud secrets delete "$name" --quiet "${P[@]}"
done

step "Artifact Registry repository and its images"
if_present gcloud artifacts repositories describe "$REPO" --location="$REGION" "${P[@]}" -- \
    gcloud artifacts repositories delete "$REPO" --location="$REGION" --quiet "${P[@]}"

step "Document AI processor"
processor="$(docai_processor)"
if [[ -n "$processor" ]]; then
  run docai_curl -X DELETE "https://$DOCAI_LOCATION-documentai.googleapis.com/v1/$processor"
fi

step "Service accounts"
for sa in "${SERVICE_ACCOUNTS[@]}"; do
  if_present gcloud iam service-accounts describe "$(sa_email "$sa")" "${P[@]}" -- \
      gcloud iam service-accounts delete "$(sa_email "$sa")" --quiet "${P[@]}"
done

step "Network: firewall rules, the Cloud SQL peering, the reserved range, subnet and VPC"
for rule in mhs-allow-sql-egress mhs-deny-egress; do
  if_present gcloud compute firewall-rules describe "$rule" "${P[@]}" -- \
      gcloud compute firewall-rules delete "$rule" --quiet "${P[@]}"
done
# Google can take a while to release the peering after the Cloud SQL instance is gone; rerun this script later
# if this step fails.
if [[ "$DRY_RUN" == 1 ]] \
   || has_output gcloud services vpc-peerings list --network="$NETWORK" "${P[@]}" --format='value(peering)'; then
  run gcloud services vpc-peerings delete --service=servicenetworking.googleapis.com --network="$NETWORK" \
    --quiet "${P[@]}" || note "The peering is still in use; rerun teardown in an hour for the network."
fi
if_present gcloud compute addresses describe "$PSA_RANGE" --global "${P[@]}" -- \
    gcloud compute addresses delete "$PSA_RANGE" --global --quiet "${P[@]}"
if_present gcloud compute networks subnets describe "$SUBNET" --region="$REGION" "${P[@]}" -- \
    gcloud compute networks subnets delete "$SUBNET" --region="$REGION" --quiet "${P[@]}"
if_present gcloud compute networks describe "$NETWORK" "${P[@]}" -- \
    gcloud compute networks delete "$NETWORK" --quiet "${P[@]}"

step "KMS: destroy the app and vault key versions (the key ring and key names stay; Cloud KMS never deletes them)"
for key in app vault; do
  versions="$(lookup "${key}_KEY_VERSION" gcloud kms keys versions list --key="$key" --keyring="$KEYRING" \
    --location="$REGION" --filter='state=ENABLED OR state=DISABLED' --format='value(name.basename())' "${P[@]}" \
    2>/dev/null || true)"
  for version in $versions; do
    run gcloud kms keys versions destroy "$version" --key="$key" --keyring="$KEYRING" --location="$REGION" \
      --quiet "${P[@]}"
  done
done

step "Done. The project itself, its billing link and budget alerts are still there (docs/GCP_SETUP.md part F)."
