#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Security Posture Review (CSPR) - Monitoramento de Status
# Task: Verificar status de execução do Findings Scanner (Cloud Run Jobs, Docker, BigQuery)
# Author: Joabson Saccomani (jsaccomani@google.com)
# ==============================================================================
set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

BQ_PROJECT_ID="${BQ_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo 'target-gcp-project')}"
LOCATION="${LOCATION:-us-east1}"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} [STATUS] Diagnóstico em Tempo Real do CSPR Findings (${BQ_PROJECT_ID})      ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# 1. Processos locais / Docker no Cloud Shell
echo -e "\n${BLUE}${BOLD}[1/4] Processos Locais / Containers no Cloud Shell:${NC}"
ps aux | grep -E "05_generate_findings|cspr-toolkit-findings|gcloud run jobs execute" | grep -v grep || echo -e "  ${YELLOW}Nenhum processo bash/gcloud local do Findings em primeiro plano neste shell.${NC}"
if command -v docker &>/dev/null; then
    docker ps --filter "ancestor=us-docker.pkg.dev/cloud-pso-security/cspr-toolkit/cspr-toolkit-findings" --format "table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.RunningFor}}" 2>/dev/null || true
fi

# 2. Status dos Cloud Run Jobs (cspr-findings-job e cspr-prereq-job)
echo -e "\n${BLUE}${BOLD}[2/4] Execuções do Cloud Run Job (cspr-findings-job / cspr-prereq-job) em ${LOCATION}:${NC}"
gcloud run jobs executions list \
    --job=cspr-findings-job \
    --project="${BQ_PROJECT_ID}" \
    --region="${LOCATION}" \
    --limit=5 2>/dev/null || echo -e "  ${YELLOW}Job 'cspr-findings-job' ainda não encontrado em ${LOCATION} (ou rodando em outra região).${NC}"

gcloud run jobs executions list \
    --job=cspr-prereq-job \
    --project="${BQ_PROJECT_ID}" \
    --region="${LOCATION}" \
    --limit=3 2>/dev/null || true

# 3. Últimos logs do cspr-findings-job no Cloud Logging
echo -e "\n${BLUE}${BOLD}[3/4] Últimas 20 linhas de Log do 'cspr-findings-job' (Cloud Logging):${NC}"
gcloud logging read \
    "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"cspr-findings-job\"" \
    --project="${BQ_PROJECT_ID}" \
    --limit=20 \
    --format="table(timestamp, severity, textPayload)" 2>/dev/null || echo -e "  ${YELLOW}Sem logs recentes para cspr-findings-job.${NC}"

# 4. Contagem de linhas populadas no BigQuery (cspr_finding e cspr_ci)
echo -e "\n${BLUE}${BOLD}[4/4] Status das Tabelas de Findings no BigQuery (${BQ_PROJECT_ID}):${NC}"
bq query --nouse_legacy_sql --project_id="${BQ_PROJECT_ID}" --format=pretty "
SELECT
  dataset_id,
  table_id,
  row_count,
  ROUND(size_bytes / 1024, 2) AS size_kb,
  TIMESTAMP_MILLIS(last_modified_time) AS last_updated_utc
FROM \`${BQ_PROJECT_ID}.cspr_finding.__TABLES__\`
UNION ALL
SELECT
  dataset_id,
  table_id,
  row_count,
  ROUND(size_bytes / 1024, 2) AS size_kb,
  TIMESTAMP_MILLIS(last_modified_time) AS last_updated_utc
FROM \`${BQ_PROJECT_ID}.cspr_ci.__TABLES__\`
ORDER BY dataset_id, table_id;
" 2>/dev/null || echo -e "  ${YELLOW}Tabelas cspr_finding / cspr_ci ainda não populadas ou sem permissão de leitura.${NC}"

echo -e "\n${GREEN}${BOLD}[✔] Verificação de status concluída.${NC}"
