#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Security Posture Review (CSPR) - Fase 05
# Task: Execute Findings Scanner & Prepare Review Checklist / Looker Studio
# Author: Joabson Saccomani (jsaccomani@google.com)
# ==============================================================================
set -euo pipefail

# ANSI Color Codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} [FASE 05] CSPR Findings Scanner & Checklist Preparation                      ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"

if [[ -z "${BQ_PROJECT_ID:-}" ]]; then
    SUMMARY_FILE=$(ls -t "${BASE_DIR}"/cspr_environment_summary_*.txt "${BASE_DIR}"/local_tests/cspr_environment_summary_*.txt cspr_environment_summary_*.txt 2>/dev/null | head -n 1 || true)
    DEFAULT_PROJECT=""
    if [[ -n "${SUMMARY_FILE}" ]]; then
        DEFAULT_PROJECT=$(grep "GCP Project ID:" "${SUMMARY_FILE}" | awk '{print $NF}' || true)
    fi
    if [[ -n "${DEFAULT_PROJECT}" ]]; then
        read -r -p "Customer GCP Project ID [default: ${DEFAULT_PROJECT}]: " INPUT_PROJECT
        BQ_PROJECT_ID="${INPUT_PROJECT:-${DEFAULT_PROJECT}}"
    else
        read -r -p "Enter Customer GCP Project ID: " BQ_PROJECT_ID
    fi
fi

LOCATION="${LOCATION:-us-east1}"
PSO_FINDINGS_IMAGE="us-docker.pkg.dev/cloud-pso-security/cspr-toolkit/cspr-toolkit-findings:latest"
CUSTOMER_FINDINGS_IMAGE="${LOCATION}-docker.pkg.dev/${BQ_PROJECT_ID}/customer-cspr-toolkit/cspr-toolkit-findings:latest"

# 1. Push Findings Image
echo -e "${CYAN}[1/4] Pushing CSPR Findings container to customer Artifact Registry...${NC}"
gcloud auth configure-docker "us-docker.pkg.dev,${LOCATION}-docker.pkg.dev" --quiet
docker pull "${PSO_FINDINGS_IMAGE}"
docker tag "${PSO_FINDINGS_IMAGE}" "${CUSTOMER_FINDINGS_IMAGE}"
docker push "${CUSTOMER_FINDINGS_IMAGE}"
echo -e "${GREEN}[✔] Findings image deployed to customer registry.${NC}"

# 2. Deploy Cloud Run Job for Findings
echo -e "${CYAN}[2/4] Deploying Findings Cloud Run Job (cspr-findings-job)...${NC}"
PROCESSED_FINDINGS_YAML="${BASE_DIR}/local_tests/cloudrun-findings-processed-${BQ_PROJECT_ID}.yaml"
TEMPLATE_FINDINGS_FILE="${BASE_DIR}/templates/cloudrun-findings-job.template.yaml"
ORGANIZATION_ID="${ORGANIZATION_ID:-802070535070}"
ORG_DOMAIN="${ORG_DOMAIN:-customer-domain.com}"

sed -e "s/\${BQ_PROJECT_ID}/${BQ_PROJECT_ID}/g" \
    -e "s/\${LOCATION}/${LOCATION}/g" \
    -e "s/\${ORGANIZATION_ID}/${ORGANIZATION_ID}/g" \
    -e "s/\${ORG_DOMAIN}/${ORG_DOMAIN}/g" \
    "${TEMPLATE_FINDINGS_FILE}" > "${PROCESSED_FINDINGS_YAML}"

gcloud run jobs replace "${PROCESSED_FINDINGS_YAML}" \
    --project="${BQ_PROJECT_ID}" \
    --region="${LOCATION}"
echo -e "${GREEN}[✔] Findings job definition registered.${NC}"

# 2.5 Check and trigger Recommendations Export Transfer Run if cspr_rec is empty
REC_TABLES=$(bq ls --project_id="${BQ_PROJECT_ID}" cspr_rec 2>/dev/null | grep -E "TABLE|VIEW" | wc -l | tr -d ' ' || true)
if [[ "${REC_TABLES:-0}" -eq 0 ]]; then
    TRANSFER_CFG=$(bq ls --transfer_config --transfer_location="${LOCATION}" --project_id="${BQ_PROJECT_ID}" 2>/dev/null | grep "Recommendations_Export_Job" | awk '{print $1}' | head -n 1 || true)
    if [[ -n "${TRANSFER_CFG}" ]]; then
        echo -e "${YELLOW}[!] Dataset 'cspr_rec' is currently empty. Triggering immediate on-demand run of Recommendations_Export_Job...${NC}"
        bq mk --transfer_run --run_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${TRANSFER_CFG}" >/dev/null 2>&1 || true
    fi
fi

# 3. Trigger Findings Job
echo -e "${CYAN}[3/4] Executing Findings Job in Cloud Run...${NC}"
echo "Analyzing BigQuery datasets (cspr_cai, cspr_policy, cspr_rec) and generating findings..."
gcloud run jobs execute cspr-findings-job \
    --region="${LOCATION}" \
    --project="${BQ_PROJECT_ID}" \
    --wait

echo -e "${GREEN}[✔] Findings scan complete!${NC}"

# 4. Export Findings to CSV
echo -e "${CYAN}[4/4] Exporting consolidated findings to CSV...${NC}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_CSV="${BASE_DIR}/local_tests/cspr_findings_${BQ_PROJECT_ID}_${TIMESTAMP}.csv"

SQL_QUERY="SELECT * FROM \`${BQ_PROJECT_ID}.cspr_finding.findings_summary\`"
bq query --use_legacy_sql=false --format=csv --max_rows=100000 "${SQL_QUERY}" > "${OUTPUT_CSV}" 2>/dev/null || {
    # Fallback to any table in cspr_finding
    FIRST_TABLE=$(bq ls --project_id="${BQ_PROJECT_ID}" cspr_finding 2>/dev/null | grep -E "TABLE|VIEW" | head -n 1 | awk '{print $1}' || true)
    if [[ -n "${FIRST_TABLE}" ]]; then
        bq query --use_legacy_sql=false --format=csv --max_rows=100000 "SELECT * FROM \`${BQ_PROJECT_ID}.cspr_finding.${FIRST_TABLE}\`" > "${OUTPUT_CSV}"
    fi
}

echo ""
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD} [✔] CSPR FINDINGS GENERATION COMPLETED SUCCESSFULLY!${NC}"
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
if [[ -f "${OUTPUT_CSV}" && -s "${OUTPUT_CSV}" ]]; then
    ROWS_COUNT=$(wc -l < "${OUTPUT_CSV}" | tr -d ' ')
    echo -e " • Exported Findings File: ${BOLD}${OUTPUT_CSV}${NC} (${ROWS_COUNT} rows)"
fi
echo ""
echo -e "${BLUE}${BOLD}Next Actions for Discovery Workshops (Week 3):${NC}"
echo -e " 1. Import ${BOLD}$(basename "${OUTPUT_CSV}")${NC} into the Google Cloud CSPR Review Checklist Template."
echo -e " 2. Open Google Looker Studio and refresh data source connected to ${BOLD}${BQ_PROJECT_ID}.cspr_finding${NC}."
echo -e " 3. Consolidate architecture priorities for the upcoming customer discovery workshops!"
echo ""
