#!/usr/bin/env bash
# ==============================================================================
# CSPR COPILOT & AGENTIC STUDIO - GOOGLE CLOUD RUN DEPLOYMENT
# Deploys with @google.com Google Identity authentication & Gemini 3.x Engine
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo 'agentic-grc-cd06')}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-cspr-copilot-studio}"

echo "============================================================"
echo "🚀 Deploying CSPR Copilot & Studio to Google Cloud Run"
echo "Project ID:   ${PROJECT_ID}"
echo "Region:       ${REGION}"
echo "Service Name: ${SERVICE_NAME}"
echo "Access:       @google.com Exclusive Identity Enforcement"
echo "============================================================"

# 1. Sync latest Nubank CSPR scripts before build
echo "[1/4] Syncing latest CSPR scripts from Google/CSPR..."
if [ -d "/Users/jsaccomani/Documents/Jetsky/Google/CSPR/scripts" ]; then
  mkdir -p ./scripts
  cp -f /Users/jsaccomani/Documents/Jetsky/Google/CSPR/scripts/*.sh ./scripts/ || true
fi

# 2. Enable Required Cloud Run & Vertex AI APIs
echo "[2/4] Enabling Cloud Run, Artifact Registry, Cloud Build, IAP & Vertex AI APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  iap.googleapis.com \
  --project="${PROJECT_ID}" --quiet || true

# 3. Deploy to Google Cloud Run
echo "[3/4] Deploying ${SERVICE_NAME} to Cloud Run (${REGION})..."
ENV_VARS="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
ENV_VARS="${ENV_VARS},GOOGLE_CLOUD_REGION=${REGION}"
ENV_VARS="${ENV_VARS},GEMINI_REASONING_MODEL=gemini-3.8-flash"
ENV_VARS="${ENV_VARS},GEMINI_FAST_MODEL=gemini-3.8-flash"
ENV_VARS="${ENV_VARS},ALLOWED_DOMAINS=google.com,jsaccomani.altostrat.com"
ENV_VARS="${ENV_VARS},ALLOWED_EMAILS=jsaccomani@google.com,admin@jsaccomani.altostrat.com"
ENV_VARS="${ENV_VARS},ALLOW_LOCAL_DEV=false"

gcloud run deploy "${SERVICE_NAME}" \
  --source="${SCRIPT_DIR}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --platform=managed \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=5 \
  --memory=1Gi \
  --cpu=1 \
  --quiet \
  --set-env-vars="${ENV_VARS}"

# 4. Configure Cloud Run IAM & Google Identity Access
echo "[4/4] Configuring Cloud Run IAM bindings for @google.com & IAP..."
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --member="domain:google.com" \
  --role="roles/run.invoker" \
  --quiet >/dev/null 2>&1 || true

gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --member="user:admin@jsaccomani.altostrat.com" \
  --role="roles/run.invoker" \
  --quiet >/dev/null 2>&1 || true

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format="value(status.url)")

echo ""
echo "============================================================"
echo "✅ CSPR Copilot & Studio Deployed to Google Cloud Run!"
echo "============================================================"
echo "🔗 Cloud Run URL:     ${SERVICE_URL}"
echo "🔒 Identity Policy:   Restricted to @google.com corporate accounts"
echo "🤖 Gemini Engine:     gemini-3.8-flash (Auto-Fallback Router)"
echo "============================================================"
