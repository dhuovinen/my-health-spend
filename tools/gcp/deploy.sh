#!/usr/bin/env bash
# Build the image and deploy the Release 1 services to Cloud Run (docs/GCP_SETUP.md part C). Safe to rerun:
# the image is built only if its tag isn't in Artifact Registry, and each deploy replaces the service's
# configuration with the one below.
#
#   PROJECT_ID=<id> tools/gcp/deploy.sh [--dry-run] [--with-ai] [part ...]
#
# Parts, in order: image migrate vault app worker admin (default: all), plus worker-ai with --with-ai.
# TAG (default: the commit at HEAD) picks the image; PUBLIC_URL overrides the app's run.app address.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TAG="${TAG:-$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD)}"
IMAGE="$(image_base):$TAG"
ALL_PARTS=(image migrate vault app worker admin)
WITH_AI=0

# Secret files: Cloud Run mounts each secret in its own folder.
DB_PASSWORD_FILE=/secrets/db/password
VAULT_TOKEN_FILE=/secrets/vault-token/token
MEMBER_PASSWORD_FILE=/secrets/member/password

VPC=(--network="$NETWORK" --subnet="$SUBNET" --vpc-egress=all-traffic)
NO_EGRESS=(--network-tags="$NO_EGRESS_TAG")

# Values looked up once, before any part runs, so a missing resource stops the deploy instead of an empty setting.
lookups() {
  SQL_IP="$(sql_private_ip)"
  [[ -n "$SQL_IP" ]] || die "no Cloud SQL instance $SQL_INSTANCE: run tools/gcp/setup.sh first"
  DOCAI_PROCESSOR="$(docai_processor)"
  [[ -n "$DOCAI_PROCESSOR" ]] || die "no Document AI processor $DOCAI_NAME: run tools/gcp/setup.sh docai"
  APP_URL="${PUBLIC_URL:-$(service_url mhs-app)}"
  VAULT_URL="$(service_url mhs-vault)"
}

db_env() {  # role
  printf 'MHS_DB_HOST=%s,MHS_DB_NAME=%s,MHS_DB_USER=%s,MHS_DB_PASSWORD_FILE=%s' \
    "$SQL_IP" "$DB_NAME" "$1" "$DB_PASSWORD_FILE"
}

# What the app and the mhs-admin job share: database, KMS app key, bucket, Document AI, Presidio, public URL.
app_env() {
  printf '%s,MHS_KEYS=kms,MHS_KMS_KEY=%s,MHS_OBJECT_STORE=gcs,MHS_GCS_BUCKET=%s' \
    "$(db_env mhs_app)" "$(kms_key app)" "$BUCKET"
  printf ',MHS_OCR_ENGINE=documentai,MHS_DOCAI_PROCESSOR=%s,MHS_SCRUBBER=presidio' "$DOCAI_PROCESSOR"
  printf ',MHS_COOKIE_SECURE=1,MHS_PUBLIC_URL=%s' "$APP_URL"
}

image() {
  step "Build and push the image: $IMAGE"
  if exists gcloud artifacts docker images describe "$IMAGE" "${P[@]}"; then
    note "Already in Artifact Registry; not rebuilt."
    return
  fi
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)" ]]; then
    note "Uncommitted changes are not in the image: it is built from the commit at HEAD."
  fi
  run gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet
  # The build context is `git archive HEAD`: committed files only, so data/ (git-ignored) can never get in.
  if [[ "$DRY_RUN" == 1 ]]; then
    printf '+ git archive --format=tar HEAD | docker buildx build --platform=linux/amd64 --target=runtime'
    printf ' --tag=%s --push -\n' "$IMAGE"
  else
    git -C "$REPO_ROOT" archive --format=tar HEAD \
      | docker buildx build --platform=linux/amd64 --target=runtime --tag="$IMAGE" --push -
  fi
}

migrate() {
  step "Migrate job (creates the roles, applies migrations), then run it"
  run gcloud run jobs deploy mhs-migrate --image="$IMAGE" --region="$REGION" "${P[@]}" \
    --service-account="$(sa_email mhs-migrate)" --command=mhs-stack --args=migrate \
    "${VPC[@]}" "${NO_EGRESS[@]}" --cpu=1 --memory=512Mi --tasks=1 --max-retries=0 --task-timeout=600 \
    --set-env-vars="MHS_DB_HOST=$SQL_IP,MHS_DB_NAME=$DB_NAME,MHS_DB_ADMIN_USER=postgres,\
MHS_DB_ADMIN_PASSWORD_FILE=/secrets/admin/password,MHS_DB_APP_PASSWORD_FILE=/secrets/app/password,\
MHS_DB_WORKER_PASSWORD_FILE=/secrets/worker/password,MHS_DB_VAULT_PASSWORD_FILE=/secrets/vault/password" \
    --set-secrets="/secrets/admin/password=mhs-db-admin-password:latest,\
/secrets/app/password=mhs-db-app-password:latest,/secrets/worker/password=mhs-db-worker-password:latest,\
/secrets/vault/password=mhs-db-vault-password:latest"
  run gcloud run jobs execute mhs-migrate --region="$REGION" --wait "${P[@]}"
}

vault() {
  step "Vault service: internal ingress only, reached by the app through the VPC"
  # Cloud Run's IAM check would claim the Authorization header the vault token travels in, so the check is off
  # and the vault's own token is the lock; ingress=internal keeps the internet out (docs/GCP_SETUP.md, open items).
  run gcloud run deploy mhs-vault --image="$IMAGE" --region="$REGION" "${P[@]}" \
    --service-account="$(sa_email mhs-vault)" --command=mhs-vault --args=serve --port="$VAULT_PORT" \
    --ingress=internal --no-invoker-iam-check "${VPC[@]}" \
    --cpu=1 --memory=512Mi --min-instances=0 --max-instances=2 \
    --set-env-vars="MHS_HOST=0.0.0.0,MHS_VAULT_PORT=$VAULT_PORT,$(db_env mhs_vault),\
MHS_VAULT_TOKEN_FILE=$VAULT_TOKEN_FILE,MHS_KEYS=kms,MHS_KMS_KEY=$(kms_key vault)" \
    --set-secrets="$DB_PASSWORD_FILE=mhs-db-vault-password:latest,$VAULT_TOKEN_FILE=mhs-vault-token:latest"
}

app() {
  step "App service: public over HTTPS"
  # uvicorn is started directly so it trusts Cloud Run's X-Forwarded-Proto: the app's same-origin check on posts
  # compares the browser's https:// origin with the request's own scheme (docs/GCP_SETUP.md, open items).
  run gcloud run deploy mhs-app --image="$IMAGE" --region="$REGION" "${P[@]}" \
    --service-account="$(sa_email mhs-app)" --command=uvicorn \
    --args="mhs.web.household.app:app_from_env,--factory,--host=0.0.0.0,--port=$APP_PORT,--proxy-headers,\
--forwarded-allow-ips=*,--no-server-header" \
    --port="$APP_PORT" --ingress=all --allow-unauthenticated "${VPC[@]}" \
    --cpu=1 --memory=2Gi --cpu-boost --min-instances=0 --max-instances=2 --concurrency=20 --timeout=300 \
    --set-env-vars="$(app_env),MHS_VAULT_URL=$VAULT_URL,MHS_VAULT_TOKEN_FILE=$VAULT_TOKEN_FILE" \
    --set-secrets="$DB_PASSWORD_FILE=mhs-db-app-password:latest,$VAULT_TOKEN_FILE=mhs-vault-token:latest"
}

worker() {
  step "Worker pool: layout-rules extraction, Cloud SQL and no other egress ($WORKER_INSTANCES instance(s))"
  run gcloud run worker-pools deploy mhs-worker --image="$IMAGE" --region="$REGION" "${P[@]}" \
    --service-account="$(sa_email mhs-worker)" --command=mhs-worker \
    "${VPC[@]}" "${NO_EGRESS[@]}" --cpu=1 --memory=1Gi --instances="$WORKER_INSTANCES" \
    --set-env-vars="$(db_env mhs_worker),MHS_EXTRACTOR=rules" \
    --set-secrets="$DB_PASSWORD_FILE=mhs-db-worker-password:latest"
}

worker-ai() {
  step "AI worker pool: Claude extraction, out through the egress proxy only"
  [[ -n "${MHS_AI_PROXY:-}" ]] \
    || die "--with-ai needs MHS_AI_PROXY: the egress proxy that only lets the Anthropic API through (open item)"
  run gcloud run worker-pools deploy mhs-worker-ai --image="$IMAGE" --region="$REGION" "${P[@]}" \
    --service-account="$(sa_email mhs-worker-ai)" --command=mhs-worker \
    "${VPC[@]}" --cpu=1 --memory=1Gi --instances=1 \
    --set-env-vars="$(db_env mhs_worker),MHS_EXTRACTOR=claude,\
MHS_ANTHROPIC_API_KEY_FILE=/secrets/anthropic/key,MHS_AI_PROXY=$MHS_AI_PROXY" \
    --set-secrets="$DB_PASSWORD_FILE=mhs-db-worker-password:latest,/secrets/anthropic/key=$AI_KEY_SECRET:latest"
}

admin() {
  step "mhs-admin job (create-household, add-member, demo-setup, import); run it with tools/gcp/admin.sh"
  # Runs as mhs-app with the app's settings. `sh -c` lets add-member read its password from a mounted secret,
  # since a job has no terminal or stdin.
  run gcloud run jobs deploy mhs-admin --image="$IMAGE" --region="$REGION" "${P[@]}" \
    --service-account="$(sa_email mhs-app)" --command=sh --args='^|^-c|exec mhs-admin "$@"|mhs-admin|--help' \
    "${VPC[@]}" --cpu=1 --memory=2Gi --tasks=1 --max-retries=0 --task-timeout=600 \
    --set-env-vars="$(app_env)" \
    --set-secrets="$DB_PASSWORD_FILE=mhs-db-app-password:latest,$MEMBER_PASSWORD_FILE=mhs-member-password:latest"
}

parse_common "$@"
parts=()
for a in "${ARGS[@]+"${ARGS[@]}"}"; do
  case "$a" in
    --with-ai) WITH_AI=1 ;;
    image|migrate|vault|app|worker|admin|worker-ai) parts+=("$a") ;;
    *) die "unknown part or flag $a (parts: ${ALL_PARTS[*]} worker-ai)" ;;
  esac
done
if [[ ${#parts[@]} -eq 0 ]]; then
  parts=("${ALL_PARTS[@]}")
  [[ "$WITH_AI" == 0 ]] || parts+=(worker-ai)
fi
[[ " ${parts[*]} " == " image " ]] || lookups
for part in "${parts[@]}"; do
  "$part"
done
step "Done. The app is at ${APP_URL:-${PUBLIC_URL:-$(service_url mhs-app)}}; next, tools/gcp/admin.sh demo-setup."
