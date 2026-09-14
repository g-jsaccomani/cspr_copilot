#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Security Posture Review (CSPR) - Fase 04
# Task: Validate BigQuery Datasets and Ingestion Telemetry (CAI, Policy, Rec)
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
echo -e "${CYAN}${BOLD} [FASE 04] BigQuery Datasets & Telemetry Validation                           ${NC}"
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

echo ""
echo -e "Querying BigQuery datasets in project: ${BOLD}${BQ_PROJECT_ID}${NC}..."
BQ_ERR=$(mktemp)
if ! DATASETS=$(bq ls --project_id="${BQ_PROJECT_ID}" --format=prettyjson 2>"${BQ_ERR}"); then
    echo ""
    echo -e "${RED}[✘] Failed to query BigQuery in project '${BQ_PROJECT_ID}'.${NC}"
    echo -e "${YELLOW}Details:${NC}"
    cat "${BQ_ERR}"
    rm -f "${BQ_ERR}"
    echo ""
    echo -e "${CYAN}Tip:${NC} Make sure you are authenticated with the target customer GCP account (${BOLD}gcloud auth login${NC}) or run inside Cloud Shell."
    exit 1
fi
rm -f "${BQ_ERR}"

check_dataset() {
    local DATASET_NAME="$1"
    local DESCRIPTION="$2"
    local IS_ASYNC="$3"
    
    echo -n " • Checking dataset '${DATASET_NAME}' (${DESCRIPTION})... "
    if echo "${DATASETS}" | grep -q "\"${DATASET_NAME}\""; then
        local SUMMARY
        SUMMARY=$(bq query --nouse_legacy_sql --format=csv --quiet \
            "SELECT COUNT(1), IFNULL(SUM(row_count),0), ROUND(IFNULL(SUM(size_bytes),0)/1073741824, 2) FROM \`${BQ_PROJECT_ID}.${DATASET_NAME}.__TABLES__\`" 2>/dev/null | tail -n 1 || true)
        local T_COUNT=$(echo "${SUMMARY}" | cut -d',' -f1)
        local R_COUNT=$(echo "${SUMMARY}" | cut -d',' -f2)
        local GB_SIZE=$(echo "${SUMMARY}" | cut -d',' -f3)
        echo -e "${GREEN}[✔] Present (${T_COUNT:-0} tables | ${R_COUNT:-0} total rows | ${GB_SIZE:-0} GB)${NC}"
    else
        if [[ "${IS_ASYNC}" == "true" ]]; then
            echo -e "${YELLOW}[⏳] Pending Ingestion (48h-72h window)${NC}"
        else
            echo -e "${RED}[✗] Not found (or Job still running)${NC}"
        fi
    fi
}

echo ""
echo -e "${BOLD}--- Cloud Run Collector Job Status ---${NC}"
gcloud run jobs executions list --job=cspr-prereq-job --region="${LOCATION:-us-east1}" --project="${BQ_PROJECT_ID}" --limit=5 2>/dev/null || echo "  (Could not list Cloud Run Job executions)"

echo ""
echo -e "${BOLD}--- BigQuery Datasets Verification (Exact Counts) ---${NC}"
check_dataset "cspr_cai" "Cloud Asset Inventory" "false"
check_dataset "cspr_policy" "Organization Policies & Key Analyzer" "false"
check_dataset "cspr_rec" "Security & IAM Recommenders" "true"
check_dataset "cspr_finding" "CSPR Findings (Scanner Output)" "true"
check_dataset "cspr_ci" "Cloud Identity (Optional)" "true"

echo ""
echo -e "${BOLD}--- Table Rows Verification ---${NC}"

check_table_rows() {
    local DATASET="$1"
    local TABLE="$2"
    local QUERY="SELECT count(1) FROM \`${BQ_PROJECT_ID}.${DATASET}.${TABLE}\`"
    
    local COUNT
    COUNT=$(bq query --nouse_legacy_sql --format=csv --quiet "${QUERY}" 2>/dev/null | tail -n 1 || true)
    if [[ -n "${COUNT}" && "${COUNT}" =~ ^[0-9]+$ ]]; then
        echo -e " • ${DATASET}.${TABLE}: ${GREEN}${COUNT} rows${NC}"
    else
        echo -e " • ${DATASET}.${TABLE}: ${YELLOW}(Table not ready or empty)${NC}"
    fi
}

check_table_rows "cspr_cai" "iam_policy"
check_table_rows "cspr_cai" "org_policy"
check_table_rows "cspr_cai" "resource_cloudresourcemanager_googleapis_com_Project"
check_table_rows "cspr_cai" "kubernetes"
check_table_rows "cspr_cai" "os_inventory"
check_table_rows "cspr_policy" "policyanalyzer_orgpolicy_analysis"
check_table_rows "cspr_policy" "policyanalyzer_UnusedServiceAccountKey"
check_table_rows "cspr_rec" "recommendations_export"
check_table_rows "cspr_rec" "insights_export"

echo ""
echo -e "${BOLD}--- Complete BigQuery Table & Row Audit (INFORMATION_SCHEMA) ---${NC}"
for DS in cspr_cai cspr_policy cspr_rec cspr_finding cspr_ci; do
    echo -e "${CYAN}[Dataset: ${DS}]${NC}"
    bq query --nouse_legacy_sql --format=pretty --project_id="${BQ_PROJECT_ID}" \
        "SELECT table_id, row_count, ROUND(size_bytes/1048576, 2) AS size_mb FROM \`${BQ_PROJECT_ID}.${DS}.__TABLES__\` ORDER BY row_count DESC LIMIT 15" 2>/dev/null || echo "  (No tables found in ${DS})"
done

echo ""
echo -e "${BOLD}--- BigQuery Data Transfer (Recommendations Export) ---${NC}"
TRANSFER_LOCATION="${LOCATION:-us-east1}"
TRANSFER_INFO=$(bq ls --transfer_config --transfer_location="${TRANSFER_LOCATION}" --project_id="${BQ_PROJECT_ID}" 2>/dev/null | grep "Recommendations_Export_Job" || true)
if [[ -n "${TRANSFER_INFO}" ]]; then
    TRANSFER_ID=$(echo "${TRANSFER_INFO}" | awk '{print $1}')
    echo -e " • Recommendations_Export_Job: ${GREEN}[✔] Registered & Active (${TRANSFER_LOCATION})${NC}"
    echo -e " • Config Resource Name:       ${TRANSFER_ID}"
    LATEST_RUN=$(bq ls --transfer_run --transfer_location="${TRANSFER_LOCATION}" "${TRANSFER_ID}" 2>/dev/null | grep "cspr_rec" | head -n 1 || true)
    if [[ -n "${LATEST_RUN}" ]]; then
        RUN_STATE=$(echo "${LATEST_RUN}" | awk '{print $(NF-1)}')
        echo -e " • Latest Transfer Run State:  ${CYAN}${RUN_STATE}${NC}"
    fi
    REC_COUNT=$(bq ls --project_id="${BQ_PROJECT_ID}" cspr_rec 2>/dev/null | grep -E "TABLE|VIEW" | wc -l | tr -d ' ' || true)
    if [[ "${REC_COUNT:-0}" -eq 0 ]]; then
        echo -e " • ${YELLOW}[Action] Ensuring BigQuery Data Transfer Service Agent IAM permissions...${NC}"
        PROJECT_NUMBER=$(gcloud projects describe "${BQ_PROJECT_ID}" --format="value(projectNumber)" 2>/dev/null || true)
        ACTIVE_USER=$(gcloud config get-value account 2>/dev/null || true)
        if [[ -n "${PROJECT_NUMBER}" ]]; then
            gcloud iam service-accounts add-iam-policy-binding "cspr-prereq-cloudrun-sa@${BQ_PROJECT_ID}.iam.gserviceaccount.com" \
              --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-bigquerydatatransfer.iam.gserviceaccount.com" \
              --role="roles/iam.serviceAccountTokenCreator" \
              --project="${BQ_PROJECT_ID}" --quiet >/dev/null 2>&1 || true
        fi
        if [[ -n "${ACTIVE_USER}" ]]; then
            gcloud projects add-iam-policy-binding "${BQ_PROJECT_ID}" \
              --member="user:${ACTIVE_USER}" \
              --role="roles/bigquery.admin" --quiet >/dev/null 2>&1 || true
        fi
        echo -e " • ${YELLOW}[Action] Triggering immediate on-demand run of Recommendations_Export_Job...${NC}"
        bq mk --transfer_run --run_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${TRANSFER_ID}" || true
    fi
else
    echo -e " • Recommendations_Export_Job: ${YELLOW}[!] Not found in ${TRANSFER_LOCATION}${NC}"
fi

echo ""
echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${YELLOW}${BOLD} ⚠️  CRITICAL TELEMETRY INGESTION WINDOW (48 - 72h):${NC}"
echo -e " Cloud Asset Inventory (cspr_cai) and Org Policies (cspr_policy) populate immediately."
echo -e " Google Cloud Recommenders and Insights (cspr_rec) require 48 to 72 hours for complete"
echo -e " historical consolidation into BigQuery per Google Cloud architecture."
echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo ""
