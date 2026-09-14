#!/usr/bin/env bash
# ==============================================================================
# CSPR COPILOT & AGENTIC STUDIO — END-TO-END GCP CLOUD RUN DEPLOYMENT
# Provisions Cloud Firestore persistence, Model Armor, IAM identities, and deploys
# ==============================================================================
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-agentic-grc-cd06}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-cspr-copilot-studio}"
MODEL_ARMOR_TEMPLATE="${MODEL_ARMOR_TEMPLATE:-cspr-safety-baseline}"

echo "============================================================"
echo "🚀 Deploying CSPR Copilot & Studio to Google Cloud Run"
echo "Project ID:   ${PROJECT_ID}"
echo "Region:       ${REGION}"
echo "Service Name: ${SERVICE_NAME}"
echo "Persistence:  Google Cloud Firestore (Native Mode) + SQLite"
echo "Access:       @google.com Exclusive Identity Enforcement"
echo "============================================================"

# 1. Sync latest CSPR scripts from Upstream
echo "[1/5] Syncing latest CSPR scripts from Upstream CSPR Engine..."
if [ -f "scripts/sync_cspr_upstream.py" ]; then
  python3 scripts/sync_cspr_upstream.py
elif [ -f "sync_cspr_upstream.py" ]; then
  python3 sync_cspr_upstream.py
fi

# 2. Enable Required Google Cloud APIs (Idempotent)
echo "[2/5] Enabling Cloud Run, Firestore, Model Armor, IAP & Vertex AI APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  modelarmor.googleapis.com \
  iap.googleapis.com \
  aiplatform.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  --project="${PROJECT_ID}" --quiet || true

# Ensure Firestore (Native mode) default database exists for durable persistence across Cloud Run restarts
echo "[2b/5] Verifying Cloud Firestore (Native mode) Database..."
if ! gcloud firestore databases describe --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "[INFO] Creating Firestore (default) database in ${REGION}..."
  gcloud firestore databases create --location="${REGION}" --project="${PROJECT_ID}" --quiet || true
else
  echo "[PASS] Firestore database already exists."
fi

# 3. Configure Model Armor Safety Template (Idempotent)
echo "[3/5] Verifying Model Armor Safety Template (${MODEL_ARMOR_TEMPLATE})..."
if gcloud model-armor templates describe "${MODEL_ARMOR_TEMPLATE}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "[PASS] Model Armor template '${MODEL_ARMOR_TEMPLATE}' already exists."
else
  gcloud model-armor templates create "${MODEL_ARMOR_TEMPLATE}" \
    --location="${REGION}" \
    --rai-settings-filters='[{"filterType":"HATE_SPEECH","confidenceLevel":"MEDIUM_AND_ABOVE"}]' \
    --pi-and-jailbreak-filter-settings-enforcement=enabled \
    --pi-and-jailbreak-filter-settings-confidence-level=medium-and-above \
    --malicious-uri-filter-settings-enforcement=enabled \
    --project="${PROJECT_ID}" >/dev/null 2>&1 || true
fi

# 4. Configure Service Identities & IAM Roles (Idempotent)
echo "[4/5] Configuring Service Identities and Cloud Run IAM bindings..."
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
gcloud beta services identity create --service=aiplatform.googleapis.com --project="${PROJECT_ID}" --quiet >/dev/null 2>&1 || true
gcloud beta services identity create --service=iap.googleapis.com --project="${PROJECT_ID}" --quiet >/dev/null 2>&1 || true

COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for r in "roles/datastore.user" "roles/aiplatform.user" "roles/modelarmor.user" "roles/storage.admin" "roles/logging.logWriter"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="${r}" \
    --condition=None --quiet >/dev/null 2>&1 || true
done

# 5. Deploy to Cloud Run with Firestore & Vertex AI Environment
echo "[5/5] Deploying ${SERVICE_NAME} to Cloud Run (${REGION})..."
ENV_VARS="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
ENV_VARS="${ENV_VARS},GOOGLE_CLOUD_LOCATION=${REGION}"
ENV_VARS="${ENV_VARS},GOOGLE_GENAI_USE_VERTEXAI=true"
ENV_VARS="${ENV_VARS},GEMINI_MODEL_ID=gemini-3.8-flash"
ENV_VARS="${ENV_VARS},ENABLE_FIRESTORE=true"
ENV_VARS="${ENV_VARS},FIRESTORE_DATABASE=(default)"
ENV_VARS="${ENV_VARS},DEFAULT_GOOGLE_USER=jsaccomani@google.com"
ENV_VARS="${ENV_VARS},DEFAULT_GOOGLE_NAME=Joabson Saccomani"
ENV_VARS="${ENV_VARS},ALLOWED_DOMAINS=google.com,jsaccomani.altostrat.com"
ENV_VARS="${ENV_VARS},GOOGLE_IAP_AUDIENCE=/projects/${PROJECT_NUMBER}/locations/${REGION}/services/${SERVICE_NAME}"

gcloud run deploy "${SERVICE_NAME}" \
  --source=. \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --platform=managed \
  --allow-unauthenticated \
  --min-instances=1 \
  --memory=2Gi \
  --cpu=2 \
  --quiet \
  --set-env-vars="${ENV_VARS}"

gcloud beta run services update "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --no-iap \
  --quiet >/dev/null 2>&1 || true

gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --quiet >/dev/null 2>&1 || true

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format="value(status.url)")

echo ""
echo "============================================================"
echo "✅ CSPR Copilot & Studio Deployed to Google Cloud Run!"
echo "============================================================"
echo "🔗 Cloud Run URL:     ${SERVICE_URL}"
echo "💾 Persistence:       Cloud Firestore (cspr_* collections)"
echo "🔒 Identity Policy:   Restricted to @google.com corporate accounts"
echo "🤖 Gemini Engine:     gemini-3.8-flash (Auto-Fallback Router)"
echo "============================================================"
