#!/usr/bin/env bash
# Create the staging project's resources (docs/GCP_SETUP.md part B). Safe to rerun: each resource is created only
# if it isn't there yet. Needs the owner's part A first (project, billing, `gcloud auth login`).
#
#   PROJECT_ID=<id> tools/gcp/setup.sh [--dry-run] [step ...]
#
# Steps, in order: apis network bucket kms accounts secrets sql registry docai (default: all).
set -euo pipefail
source "$(dirname "$0")/lib.sh"

ALL_STEPS=(apis network bucket kms accounts secrets sql registry docai)

apis() {
  step "Enable the APIs"
  run gcloud services enable "${APIS[@]}" "${P[@]}"
}

network() {
  step "VPC, subnet for Cloud Run, private services access for Cloud SQL, egress firewall"
  exists gcloud compute networks describe "$NETWORK" "${P[@]}" \
    || run gcloud compute networks create "$NETWORK" --subnet-mode=custom "${P[@]}"
  exists gcloud compute networks subnets describe "$SUBNET" --region="$REGION" "${P[@]}" \
    || run gcloud compute networks subnets create "$SUBNET" --network="$NETWORK" --region="$REGION" \
         --range="$SUBNET_RANGE" --enable-private-ip-google-access "${P[@]}"
  exists gcloud compute addresses describe "$PSA_RANGE" --global "${P[@]}" \
    || run gcloud compute addresses create "$PSA_RANGE" --global --purpose=VPC_PEERING \
         --addresses="$PSA_ADDRESS" --prefix-length="$PSA_PREFIX" --network="$NETWORK" "${P[@]}"
  has_output gcloud services vpc-peerings list --network="$NETWORK" "${P[@]}" --format='value(peering)' \
    || run gcloud services vpc-peerings connect --service=servicenetworking.googleapis.com \
         --ranges="$PSA_RANGE" --network="$NETWORK" "${P[@]}"
  # No Cloud NAT: nothing on this network reaches the internet. Services tagged mhs-no-egress (worker, migrate)
  # also can't reach Google APIs; they reach Cloud SQL and nothing else (TC-PRV-06-3).
  exists gcloud compute firewall-rules describe mhs-allow-sql-egress "${P[@]}" \
    || run gcloud compute firewall-rules create mhs-allow-sql-egress --network="$NETWORK" --direction=EGRESS \
         --action=ALLOW --rules=tcp:5432 --destination-ranges="$PSA_ADDRESS/$PSA_PREFIX" \
         --target-tags="$NO_EGRESS_TAG" --priority=1000 "${P[@]}"
  exists gcloud compute firewall-rules describe mhs-deny-egress "${P[@]}" \
    || run gcloud compute firewall-rules create mhs-deny-egress --network="$NETWORK" --direction=EGRESS \
         --action=DENY --rules=all --destination-ranges=0.0.0.0/0 \
         --target-tags="$NO_EGRESS_TAG" --priority=65000 "${P[@]}"
}

sql() {
  step "Cloud SQL for PostgreSQL 17: private IP only, TLS required, backups and point-in-time recovery"
  note "Creating the instance takes about ten minutes."
  exists gcloud sql instances describe "$SQL_INSTANCE" "${P[@]}" \
    || run gcloud sql instances create "$SQL_INSTANCE" --database-version=POSTGRES_17 --edition=ENTERPRISE \
         --tier="$SQL_TIER" --region="$REGION" --availability-type=ZONAL \
         --storage-type=SSD --storage-size=10GB --storage-auto-increase \
         --network="projects/$PROJECT_ID/global/networks/$NETWORK" --allocated-ip-range-name="$PSA_RANGE" \
         --no-assign-ip --ssl-mode=ENCRYPTED_ONLY \
         --backup-start-time=07:00 --retained-backups-count=7 \
         --enable-point-in-time-recovery --retained-transaction-log-days=7 \
         --deletion-protection "${P[@]}"
  exists gcloud sql databases describe "$DB_NAME" --instance="$SQL_INSTANCE" "${P[@]}" \
    || run gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE" "${P[@]}"
  # The admin password lives in Secret Manager (the secrets step); set it on the built-in `postgres` user, which
  # the migrate job uses (MHS_DB_ADMIN_USER). Rerunning sets the same value again.
  if [[ "$DRY_RUN" == 1 ]] || has_output gcloud secrets versions list mhs-db-admin-password "${P[@]}" \
       --filter=state=enabled --format='value(name)'; then
    run gcloud sql users set-password postgres --instance="$SQL_INSTANCE" \
      --password="$(secret_value mhs-db-admin-password)" "${P[@]}"
  else
    note "No admin password yet: run the secrets step, then this one again."
  fi
}

bucket() {
  step "Cloud Storage bucket for originals: uniform access, no public access, versioning"
  exists gcloud storage buckets describe "gs://$BUCKET" "${P[@]}" \
    || run gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --default-storage-class=STANDARD \
         --uniform-bucket-level-access --public-access-prevention "${P[@]}"
  run gcloud storage buckets update "gs://$BUCKET" --versioning "${P[@]}"
}

kms() {
  step "Cloud KMS key ring with the app and vault keys"
  exists gcloud kms keyrings describe "$KEYRING" --location="$REGION" "${P[@]}" \
    || run gcloud kms keyrings create "$KEYRING" --location="$REGION" "${P[@]}"
  for key in app vault; do
    exists gcloud kms keys describe "$key" --keyring="$KEYRING" --location="$REGION" "${P[@]}" \
      || run gcloud kms keys create "$key" --keyring="$KEYRING" --location="$REGION" --purpose=encryption \
           --protection-level=software "${P[@]}"
  done
}

bind_project() {  # service account, role
  run gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$(sa_email "$1")" \
    --role="$2" --condition=None --format=none
}

bind_secret() {  # secret, service account
  run gcloud secrets add-iam-policy-binding "$1" --member="serviceAccount:$(sa_email "$2")" \
    --role=roles/secretmanager.secretAccessor --format=none "${P[@]}"
}

accounts() {
  step "Service accounts and their roles (DEPLOYMENT.md \"Identities and access\")"
  for sa in "${SERVICE_ACCOUNTS[@]}"; do
    exists gcloud iam service-accounts describe "$(sa_email "$sa")" "${P[@]}" \
      || run gcloud iam service-accounts create "$sa" --display-name="MHS ${sa#mhs-}" "${P[@]}"
  done
  for sa in "${SERVICE_ACCOUNTS[@]}"; do
    bind_project "$sa" roles/cloudsql.client
  done
  run gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$(sa_email mhs-app)" \
    --role=roles/storage.objectUser --format=none "${P[@]}"
  for key in app vault; do
    run gcloud kms keys add-iam-policy-binding "$key" --keyring="$KEYRING" --location="$REGION" \
      --member="serviceAccount:$(sa_email "mhs-$key")" --role=roles/cloudkms.cryptoKeyEncrypterDecrypter \
      --format=none "${P[@]}"
  done
  bind_project mhs-app roles/documentai.apiUser
  note "Secret access is granted per secret in the secrets step."
}

# A new random value, straight from openssl into Secret Manager: never on screen, in a file or in an argument.
add_generated_version() {
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '+ openssl rand -hex 32 | gcloud secrets versions add %s --data-file=- --project=%s\n' "$1" "$PROJECT_ID"
  else
    openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add "$1" --data-file=- "${P[@]}" --format=none
  fi
}

secrets() {
  step "Secret Manager: generated database passwords, the vault token and a staging member password"
  for name in "${GENERATED_SECRETS[@]}"; do
    exists gcloud secrets describe "$name" "${P[@]}" \
      || run gcloud secrets create "$name" --replication-policy=user-managed --locations="$REGION" "${P[@]}"
    has_output gcloud secrets versions list "$name" --filter=state=enabled --format='value(name)' "${P[@]}" \
      || add_generated_version "$name"
  done
  # Each service reads only its own (migrate sets the role passwords, so it reads all of them).
  bind_secret mhs-db-admin-password mhs-migrate
  for role in app worker vault; do
    bind_secret "mhs-db-$role-password" mhs-migrate
  done
  bind_secret mhs-db-app-password mhs-app
  bind_secret mhs-vault-token mhs-app
  bind_secret mhs-member-password mhs-app       # the mhs-admin job runs as mhs-app (add-member)
  bind_secret mhs-db-vault-password mhs-vault
  bind_secret mhs-vault-token mhs-vault
  bind_secret mhs-db-worker-password mhs-worker
  bind_secret mhs-db-worker-password mhs-worker-ai
  if exists gcloud secrets describe "$AI_KEY_SECRET" "${P[@]}"; then
    bind_secret "$AI_KEY_SECRET" mhs-worker-ai
  else
    note "No $AI_KEY_SECRET secret: fine unless AI extraction will be turned on (docs/GCP_SETUP.md step B11)."
  fi
}

registry() {
  step "Artifact Registry repository for the image"
  exists gcloud artifacts repositories describe "$REPO" --location="$REGION" "${P[@]}" \
    || run gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" \
         --description="My Health Spend images" "${P[@]}"
}

docai() {
  step "Document AI Enterprise OCR processor ($DOCAI_LOCATION)"
  if [[ -n "$(docai_processor)" && "$DRY_RUN" != 1 ]]; then
    note "Processor $DOCAI_NAME exists: $(docai_processor)"
  else
    run docai_curl -X POST -H 'Content-Type: application/json' \
      -d "{\"type\": \"OCR_PROCESSOR\", \"displayName\": \"$DOCAI_NAME\"}" "$(docai_endpoint)"
  fi
}

parse_common "$@"
steps=("${ARGS[@]+"${ARGS[@]}"}")
[[ ${#steps[@]} -gt 0 ]] || steps=("${ALL_STEPS[@]}")
for s in "${steps[@]}"; do
  [[ " ${ALL_STEPS[*]} " == *" $s "* ]] || die "unknown step $s (steps: ${ALL_STEPS[*]})"
done
for s in "${steps[@]}"; do
  "$s"
done
step "Done. Next: tools/gcp/deploy.sh (docs/GCP_SETUP.md part C)."
