#!/usr/bin/env bash
# Deploy the harvest-quality Cloud Run Job and the Chile Scheduler.
# Does not touch the chatai service. HARVEST_QUALITY_SESSION must be set.
set -euo pipefail

PROJECT=integraciones-484915
REGION=southamerica-west1
SCHEDULER_REGION=southamerica-east1
JOB=harvest-quality
SCHEDULER=harvest-quality-hourly
IMAGE=southamerica-west1-docker.pkg.dev/integraciones-484915/integraciones/harvest-quality:${IMAGE_TAG:?IMAGE_TAG is required}
RUNTIME_SA=github-actions-deploy@integraciones-484915.iam.gserviceaccount.com
RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/${JOB}:run"

if [ -z "${HARVEST_QUALITY_SESSION:-}" ]; then
  echo "HARVEST_QUALITY_SESSION is empty" >&2
  exit 1
fi

gcloud services enable cloudscheduler.googleapis.com secretmanager.googleapis.com \
  --project="${PROJECT}"

if ! gcloud secrets describe HARVEST_QUALITY_SESSION --project="${PROJECT}" >/dev/null 2>&1; then
  gcloud secrets create HARVEST_QUALITY_SESSION \
    --project="${PROJECT}" \
    --replication-policy=automatic
fi
printf '%s' "${HARVEST_QUALITY_SESSION}" | gcloud secrets versions add HARVEST_QUALITY_SESSION \
  --project="${PROJECT}" \
  --data-file=-

for secret in DATABASE_URL HARVEST_QUALITY_SESSION; do
  gcloud secrets add-iam-policy-binding "${secret}" \
    --project="${PROJECT}" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role=roles/secretmanager.secretAccessor \
    --quiet >/dev/null
done

gcloud run jobs deploy "${JOB}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --service-account="${RUNTIME_SA}" \
  --set-secrets="DATABASE_URL=DATABASE_URL:latest,HARVEST_QUALITY_SESSION=HARVEST_QUALITY_SESSION:latest" \
  --memory=2Gi \
  --cpu=2 \
  --task-timeout=900 \
  --max-retries=0 \
  --quiet

gcloud run jobs add-iam-policy-binding "${JOB}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/run.invoker \
  --quiet >/dev/null

scheduler_args=(
  --project="${PROJECT}"
  --location="${SCHEDULER_REGION}"
  --schedule="0 8-20 * * *"
  --time-zone="America/Santiago"
  --uri="${RUN_URI}"
  --http-method=POST
  --oauth-service-account-email="${RUNTIME_SA}"
)

if gcloud scheduler jobs describe "${SCHEDULER}" --project="${PROJECT}" --location="${SCHEDULER_REGION}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${SCHEDULER}" "${scheduler_args[@]}" --quiet
else
  gcloud scheduler jobs create http "${SCHEDULER}" "${scheduler_args[@]}" --quiet
fi
