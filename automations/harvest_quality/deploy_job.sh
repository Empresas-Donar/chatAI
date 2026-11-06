#!/usr/bin/env bash
# Deploy the harvest-quality Cloud Run Job.
# Does not touch the chatai service or Cloud Scheduler. The hourly job
# harvest-quality-hourly already exists in southamerica-east1 and is
# managed from the donar gcloud configuration. This account cannot
# create or update Scheduler jobs.
set -euo pipefail

PROJECT=integraciones-484915
REGION=southamerica-west1
JOB=harvest-quality
IMAGE=southamerica-west1-docker.pkg.dev/integraciones-484915/integraciones/harvest-quality:${IMAGE_TAG:?IMAGE_TAG is required}
RUNTIME_SA=github-actions-deploy@integraciones-484915.iam.gserviceaccount.com
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
    "TZ": "America/Santiago",
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
  --task-timeout=1800 \
  --max-retries=0 \
  --quiet

# Isla de Maipo uses the same image and session. It stays out until
# config/reports/isla.yaml has a webhook URL, not the workflow editor.
ISLA_JOB=harvest-quality-isla
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ISLA_URL="$(
  python3 - "$ROOT_DIR" << 'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1], "config", "reports", "isla.yaml").read_text(encoding="utf-8")
url = ""
for line in text.splitlines():
    if line.startswith("production_url:"):
        url = line.split(":", 1)[1].strip().strip("\"'")
        break
print(url)
PY
)"

if [[ "${ISLA_URL}" == https://*"/webhook/"* && "${ISLA_URL}" != *"/workflow/"* ]]; then
  gcloud run jobs deploy "${ISLA_JOB}" \
    --project="${PROJECT}" \
    --region="${REGION}" \
    --image="${IMAGE}" \
    --command=python \
    --args=-m,harvest_quality,run,isla \
    --service-account="${RUNTIME_SA}" \
    --env-vars-file="${ENV_FILE}" \
    --memory=2Gi \
    --cpu=2 \
    --task-timeout=1800 \
    --max-retries=0 \
    --quiet
else
  echo "Isla webhook is not set; harvest-quality-isla was not deployed"
fi

rm -f "${ENV_FILE}"

gcloud run jobs add-iam-policy-binding "${JOB}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/run.invoker \
  --quiet >/dev/null

if [[ "${ISLA_URL}" == https://*"/webhook/"* && "${ISLA_URL}" != *"/workflow/"* ]]; then
  gcloud run jobs add-iam-policy-binding "${ISLA_JOB}" \
    --project="${PROJECT}" \
    --region="${REGION}" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role=roles/run.invoker \
    --quiet >/dev/null
fi
