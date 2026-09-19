#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Security Posture Review (CSPR) - Fase 08 (Exportação Imediata)
# Task: Exportar Findings já existentes no BigQuery (JSON, CSV, Findings_raw, ZIP & Deliverables)
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"
mkdir -p "${BASE_DIR}/local_tests"

BQ_PROJECT_ID="${BQ_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo 'nu-cspr-assessment')}"
LOCATION="${LOCATION:-us-east1}"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} [EXPORT] Extração de Findings Existentes no BigQuery (${BQ_PROJECT_ID})     ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

ROW_COUNT=$(bq query --nouse_legacy_sql --project_id="${BQ_PROJECT_ID}" --format=csv --quiet \
  "SELECT COUNT(*) FROM \`${BQ_PROJECT_ID}.cspr_finding.cspr_finding\`" 2>/dev/null | tail -n 1 | tr -d '[:space:]' || echo "0")

if [[ "${ROW_COUNT}" == "0" || -z "${ROW_COUNT}" ]]; then
    echo -e "${YELLOW}[i] A tabela '${BQ_PROJECT_ID}.cspr_finding.cspr_finding' ainda possui 0 linhas.${NC}"
    echo -e "    Aguarde o job assíncrono ('cspr-findings-job') popular os primeiros dados (monitore pela Opção 9) e rode novamente."
    exit 0
fi

echo -e "${GREEN}[✔] Encontrados ${BOLD}${ROW_COUNT}${NC}${GREEN} registros populados em '${BQ_PROJECT_ID}.cspr_finding.cspr_finding'! Iniciando exportação...${NC}"

# 1. Create Unnested View
echo -e "${CYAN}[1/3] Atualizando view analítica '${BQ_PROJECT_ID}.cspr_finding.cspr_finding_unnested'...${NC}"
bq query --nouse_legacy_sql --project_id="${BQ_PROJECT_ID}" "
CREATE OR REPLACE VIEW \`${BQ_PROJECT_ID}.cspr_finding.cspr_finding_unnested\` AS
SELECT
  f.row_id,
  REGEXP_EXTRACT(f.row_id, r'^([a-z0-9]+)-') AS domain,
  f.section,
  f.topic,
  f.finding AS finding_title,
  ARRAY_LENGTH(f.items) AS remark_groups_count,
  grp.remark AS evidence_remark,
  ARRAY_LENGTH(grp.items) AS affected_resources_in_group,
  TO_JSON_STRING(res) AS affected_resource_json,
  grp.query AS bq_finding_query
FROM \`${BQ_PROJECT_ID}.cspr_finding.cspr_finding\` AS f
LEFT JOIN UNNEST(f.items) AS grp
LEFT JOIN UNNEST(grp.items) AS res;
" >/dev/null 2>&1 || true
echo -e "${GREEN}[✔] View 'cspr_finding_unnested' pronta no BigQuery.${NC}"

# 2. Extract JSON, CSV & Offline Review Checklist Folder (Findings_raw)
echo -e "${CYAN}[2/3] Exportando JSON, CSV e pasta Offline Review Checklist (Findings_raw)...${NC}"
OUTPUT_JSON="${BASE_DIR}/local_tests/cspr_findings_${BQ_PROJECT_ID}.json"
OUTPUT_CSV="${BASE_DIR}/local_tests/cspr_findings_${BQ_PROJECT_ID}.csv"
RAW_DIR="${BASE_DIR}/local_tests/Findings_raw_${BQ_PROJECT_ID}"
mkdir -p "${RAW_DIR}"

bq query --nouse_legacy_sql --project_id="${BQ_PROJECT_ID}" --format=json --max_rows=10000 \
  "SELECT row_id, section, topic, finding, sql_script, items FROM \`${BQ_PROJECT_ID}.cspr_finding.cspr_finding\` ORDER BY row_id" > "${OUTPUT_JSON}"

bq query --nouse_legacy_sql --project_id="${BQ_PROJECT_ID}" --format=csv --max_rows=100000 \
  "SELECT row_id, REGEXP_EXTRACT(row_id, r'^([a-z0-9]+)-') AS domain, section, topic, finding, ARRAY_LENGTH(items) AS remark_groups FROM \`${BQ_PROJECT_ID}.cspr_finding.cspr_finding\` ORDER BY row_id" > "${OUTPUT_CSV}"

python3 -c "
import json, os, shutil

json_path = '${OUTPUT_JSON}'
raw_dir = '${RAW_DIR}'
if os.path.exists(raw_dir):
    shutil.rmtree(raw_dir)
os.makedirs(raw_dir, exist_ok=True)

with open(json_path, 'r', encoding='utf-8') as f:
    rows = json.load(f)

row_ids = []
non_empty = 0
for r in rows:
    rid = r.get('row_id', '').strip()
    if not rid:
        continue
    row_ids.append(rid)
    dom = rid.split('-')[0]
    dom_dir = os.path.join(raw_dir, dom)
    os.makedirs(dom_dir, exist_ok=True)
    items = r.get('items') or []
    if any(len(g.get('names') or []) > 0 for g in items):
        non_empty += 1
    payload = {
        'finding': r.get('finding', ''),
        'items': items,
    }
    with open(os.path.join(dom_dir, f'{rid}.json'), 'w', encoding='utf-8') as out:
        json.dump(payload, out, indent=4, ensure_ascii=False)

with open(os.path.join(raw_dir, 'AutoFinding_row_ids.txt'), 'w', encoding='utf-8') as rf:
    rf.write('\n'.join(row_ids) + '\n')

print(f'   -> Gerados {len(row_ids)} arquivos <domain>/<row_id>.json + AutoFinding_row_ids.txt ({non_empty} regras com recursos afetados)')
"

if [[ "${BQ_PROJECT_ID}" == "nu-cspr-assessment" ]]; then
    rm -rf "${BASE_DIR}/local_tests/Findings_raw_Nubank"
    mkdir -p "${BASE_DIR}/local_tests/Findings_raw_Nubank"
    cp -R "${RAW_DIR}/"* "${BASE_DIR}/local_tests/Findings_raw_Nubank/" 2>/dev/null || true
fi

EXPORT_ZIP="${BASE_DIR}/local_tests/cspr_findings_bundle_${BQ_PROJECT_ID}.zip"
(cd "${BASE_DIR}/local_tests" && zip -q -r "cspr_findings_bundle_${BQ_PROJECT_ID}.zip" "cspr_findings_${BQ_PROJECT_ID}.json" "cspr_findings_${BQ_PROJECT_ID}.csv" "Findings_raw_${BQ_PROJECT_ID}") || true

# 3. Populate Native Google Workspace (.gsheet, .gdoc, .gslides) in Google Drive
if [[ -f "${BASE_DIR}/scripts/09_populate_native_google_workspace.py" ]]; then
    echo -e "${CYAN}[3/3] Populando planilha nativa Google Sheets (.gsheet) & clonando templates (.gdoc/.gsheet/.gslides) no Google Drive...${NC}"
    python3 "${BASE_DIR}/scripts/09_populate_native_google_workspace.py" "${CSPR_SPREADSHEET_ID:-1r7-DA8FZtJ1TDzDLAA_7TiQnXxlj7GxiZIyUeUi8iYc}" "${OUTPUT_JSON}" \
      || echo -e "${YELLOW}[i] Para popular a planilha .gsheet via API, rode a Opção 11 no menu (autoriza escopos Google Drive/Sheets).${NC}"
fi

echo ""
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD} [✔] EXPORTAÇÃO DE FINDINGS (${ROW_COUNT} REGRAS) CONCLUÍDA!                 ${NC}"
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo -e " • ${BOLD}JSON Consolidado:${NC} ${OUTPUT_JSON}"
echo -e " • ${BOLD}CSV Consolidado:${NC}  ${OUTPUT_CSV}"
echo -e " • ${BOLD}Pasta Findings_raw:${NC} ${RAW_DIR}/"
echo -e " • ${BOLD}Pacote ZIP p/ Download no Cloud Shell:${NC}"
echo -e "   ${YELLOW}cloudshell download ${EXPORT_ZIP}${NC}"
echo ""
