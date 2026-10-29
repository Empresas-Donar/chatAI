#!/usr/bin/env bash
# Deploy the harvest-quality Cloud Run Job and the Chile Scheduler.
# Does not touch the chatai service. Secrets come from the environment
# and are passed as job env vars. The deploy account cannot enable APIs.
set -euo pipefail

PROJECT=integraciones-484915
REGION=southamerica-west1
SCHEDULER_REGION=southamerica-east1
JOB=harvest-quality
SCHEDULER=harvest-quality-hourly
IMAGE=southamerica-west1-docker.pkg.dev/integraciones-484915/integraciones/harvest-quality:${IMAGE_TAG:?IMAGE_TAG is required}
RUNTIME_SA=github-actions-deploy@integraciones-484915.iam.gserviceaccount.com
RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/${JOB}:run"
ENV_FILE=/tmp/harvest-quality-env.yaml

if [ -z "${HARVEST_QUALITY_SESSION:-}" ] || [ -z "${DATABASE_URL:-}" ]; then
  echo "HARVEST_QUALITY_SESSION or DATABASE_URL is empty" >&2
  exit 1
fi

python3 - << 'PY'
import json
import os
from pathlib import Path

path = Path("/tmp/harvest-quality-env.yaml")
values = {
    "DATABASE_URL": os.environ["DATABASE_URL"],
    "HARVEST_QUALITY_SESSION": os.environ["HARVEST_QUALITY_SESSION"],
}
path.write_text("".join(f"{key}: {json.dumps(value)}\n" for key, value in values.items()))
PY

gcloud run jobs deploy "${JOB}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --service-account="${RUNTIME_SA}" \
  --env-vars-file="${ENV_FILE}" \
  --memory=2Gi \
  --cpu=2 \
  --task-timeout=900 \
  --max-retries=0 \
  --quiet

rm -f "${ENV_FILE}"

gcloud run jobs add-iam-policy-binding "${JOB}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/run.invoker \
  --quiet >/dev/null

scheduler_args=(
  --project="${PROJECT}"
  --location="${SCHEDULER_REGION}"
  --schedule="0 8-21 * * *"
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
