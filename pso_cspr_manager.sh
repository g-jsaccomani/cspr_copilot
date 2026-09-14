#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Security Posture Review (CSPR) - Master Execution Manager
# Orchestrator for All Phases (01_setup -> 05_findings)
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find summary file (excluding sample/template files)
SUMMARY_FILE=$(ls -t "${SCRIPT_DIR}"/cspr_environment_summary_*.txt "${SCRIPT_DIR}"/local_tests/cspr_environment_summary_*.txt 2>/dev/null | grep -v "_sample.txt" | head -n 1 || true)
DEFAULT_PROJECT=""
DEFAULT_ORG=""
DEFAULT_LOCATION="us-east1"
DEFAULT_REVIEWER="jsaccomani@google.com"

if [[ -n "${SUMMARY_FILE}" ]]; then
    DEFAULT_PROJECT=$(grep "GCP Project ID:" "${SUMMARY_FILE}" | awk '{print $NF}' || true)
    DEFAULT_ORG=$(grep "Organization ID:" "${SUMMARY_FILE}" | awk '{print $NF}' || true)
    DEFAULT_LOCATION=$(grep "Primary Region:" "${SUMMARY_FILE}" | awk '{print $NF}' || echo "us-east1")
fi
ACTIVE_GCLOUD_PROJ=$(gcloud config get-value project 2>/dev/null || true)
if [[ -n "${ACTIVE_GCLOUD_PROJ}" && "${ACTIVE_GCLOUD_PROJ}" != "(unset)" ]]; then
    DEFAULT_PROJECT="${DEFAULT_PROJECT:-${ACTIVE_GCLOUD_PROJ}}"
fi
DEFAULT_PROJECT="${DEFAULT_PROJECT:-target-gcp-project}"
DEFAULT_ORG="${DEFAULT_ORG:-802070535070}"

export BQ_PROJECT_ID="${BQ_PROJECT_ID:-${DEFAULT_PROJECT}}"
export ORGANIZATION_ID="${ORGANIZATION_ID:-${DEFAULT_ORG}}"
export LOCATION="${LOCATION:-${DEFAULT_LOCATION}}"
export GCP_GROUP_EMAIL_ADDRESS="${GCP_GROUP_EMAIL_ADDRESS:-${DEFAULT_REVIEWER}}"

print_header() {
    clear 2>/dev/null || true
    echo -e "${BLUE}${BOLD}==============================================================================${NC}"
    echo -e "${BLUE}${BOLD}     Google Cloud Security Posture Review (CSPR) - Execution Manager          ${NC}"
    echo -e "${BLUE}${BOLD}==============================================================================${NC}"
    echo -e " Active Account:       ${GREEN}$(gcloud config get-value account 2>/dev/null || echo 'Not authenticated')${NC}"
    echo -e " Target Customer Proj: ${GREEN}${BQ_PROJECT_ID:-'(Not configured)'}${NC}"
    echo -e " Organization ID:      ${GREEN}${ORGANIZATION_ID:-'(Not configured)'}${NC}"
    echo -e " Region / Location:    ${GREEN}${LOCATION}${NC}"
    echo -e " Reviewer Identity:    ${GREEN}${GCP_GROUP_EMAIL_ADDRESS}${NC}"
    echo -e "------------------------------------------------------------------------------"
}

show_menu() {
    print_header
    echo -e "${BOLD}Selecione a fase ou ação a executar:${NC}"
    echo ""
    echo -e "  ${CYAN}1)${NC} ${BOLD}[Fase 01 - Setup]${NC}      Executar Script de Setup de Pré-requisitos (Cliente / Local)"
    echo -e "  ${CYAN}2)${NC} ${BOLD}[Fase 02 - Push]${NC}       Push da Imagem Scanner para Artifact Registry do Cliente"
    echo -e "  ${CYAN}3)${NC} ${BOLD}[Fase 03 - Deploy]${NC}     Deploy e Execução do Cloud Run Job (Coleta de Telemetria)"
    echo -e "  ${CYAN}4)${NC} ${BOLD}[Fase 04 - Validação]${NC}  Validar Datasets e Tabelas no BigQuery (CAI, Policy, Rec)"
    echo -e "  ${CYAN}5)${NC} ${BOLD}[Fase 05 - Findings]${NC}   Executar Findings Scanner e Exportar para Checklist/Looker"
    echo -e "  ${CYAN}6)${NC} ${BOLD}[Pipeline Completo]${NC}    Executar Fases 02 -> 04 Sequencialmente"
    echo -e "  ${CYAN}7)${NC} Configurar / Alternar Projeto Alvo"
    echo -e "  ${CYAN}8)${NC} Visualizar Relatório de Resumo de Setup do Cliente"
    echo -e "  ${RED}0)${NC} Sair"
    echo ""
    read -r -p "Escolha uma opção [0-8]: " OPTION
}

configure_project() {
    echo ""
    read -r -p "Enter Customer GCP Project ID [current: ${BQ_PROJECT_ID}]: " INPUT_PROJECT
    BQ_PROJECT_ID="${INPUT_PROJECT:-${BQ_PROJECT_ID}}"
    read -r -p "Enter Customer Organization ID [current: ${ORGANIZATION_ID}]: " INPUT_ORG
    ORGANIZATION_ID="${INPUT_ORG:-${ORGANIZATION_ID}}"
    read -r -p "Enter Region [current: ${LOCATION}]: " INPUT_LOC
    LOCATION="${INPUT_LOC:-${LOCATION}}"
    export BQ_PROJECT_ID ORGANIZATION_ID LOCATION
}

while true; do
    show_menu
    case "${OPTION}" in
        1)
            bash "${SCRIPT_DIR}/scripts/01_setup_cspr_prereqs.sh"
            read -r -p "Pressione [Enter] para voltar ao menu..."
            ;;
        2)
            bash "${SCRIPT_DIR}/scripts/02_push_scanner_image.sh"
            read -r -p "Pressione [Enter] para voltar ao menu..."
            ;;
        3)
            bash "${SCRIPT_DIR}/scripts/03_deploy_and_run_job.sh"
            read -r -p "Pressione [Enter] para voltar ao menu..."
            ;;
        4)
            bash "${SCRIPT_DIR}/scripts/04_validate_bigquery.sh"
            read -r -p "Pressione [Enter] para voltar ao menu..."
            ;;
        5)
            bash "${SCRIPT_DIR}/scripts/05_generate_findings.sh"
            read -r -p "Pressione [Enter] para voltar ao menu..."
            ;;
        6)
            echo -e "${CYAN}${BOLD}Disparando Pipeline Fases 02 -> 04...${NC}"
            bash "${SCRIPT_DIR}/scripts/02_push_scanner_image.sh"
            bash "${SCRIPT_DIR}/scripts/03_deploy_and_run_job.sh"
            bash "${SCRIPT_DIR}/scripts/04_validate_bigquery.sh"
            echo -e "${GREEN}${BOLD}[✔] Pipeline concluído com sucesso!${NC}"
            read -r -p "Pressione [Enter] para voltar ao menu..."
            ;;
        7)
            configure_project
            ;;
        8)
            if [[ -n "${SUMMARY_FILE}" && -f "${SUMMARY_FILE}" ]]; then
                echo ""
                cat "${SUMMARY_FILE}"
            else
                echo -e "${YELLOW}Nenhum relatório cspr_environment_summary encontrado.${NC}"
            fi
            read -r -p "Pressione [Enter] para voltar ao menu..."
            ;;
        0)
            echo "Saindo do CSPR Manager."
            exit 0
            ;;
        *)
            echo -e "${RED}Opção inválida.${NC}"
            sleep 1
            ;;
    esac
done
