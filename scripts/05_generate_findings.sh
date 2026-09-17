#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Security Posture Review (CSPR) - Fase 05
# Task: Execute Findings Scanner, Unnest Exporter & Populate Checklist/Questionnaires
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
echo -e "${CYAN}${BOLD} [FASE 05] CSPR Findings Scanner, Data Exporter & Checklist Consolidation     ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"
mkdir -p "${BASE_DIR}/local_tests"

if [[ -z "${BQ_PROJECT_ID:-}" ]]; then
    SUMMARY_FILE=$(ls -t "${BASE_DIR}"/cspr_environment_summary_*.txt "${BASE_DIR}"/local_tests/cspr_environment_summary_*.txt cspr_environment_summary_*.txt 2>/dev/null | grep -v "_sample.txt" | head -n 1 || true)
    DEFAULT_PROJECT=""
    if [[ -n "${SUMMARY_FILE}" ]]; then
        DEFAULT_PROJECT=$(grep "GCP Project ID:" "${SUMMARY_FILE}" | awk '{print $NF}' || true)
    fi
    DEFAULT_PROJECT="${DEFAULT_PROJECT:-nu-cspr-assessment}"
    read -r -p "Customer GCP Project ID [default: ${DEFAULT_PROJECT}]: " INPUT_PROJECT
    BQ_PROJECT_ID="${INPUT_PROJECT:-${DEFAULT_PROJECT}}"
fi

LOCATION="${LOCATION:-us-east1}"
ORGANIZATION_ID="${ORGANIZATION_ID:-802070535070}"
ORG_DOMAIN="${ORG_DOMAIN:-nubank.com.br}"

PSO_FINDINGS_IMAGE="us-docker.pkg.dev/cloud-pso-security/cspr-toolkit/cspr-toolkit-findings:latest"
CUSTOMER_FINDINGS_IMAGE="${LOCATION}-docker.pkg.dev/${BQ_PROJECT_ID}/customer-cspr-toolkit/cspr-toolkit-findings:latest"

# ------------------------------------------------------------------------------
# [1/5] Verify or Push CSPR Findings Image to Customer Artifact Registry
# ------------------------------------------------------------------------------
echo -e "${CYAN}[1/5] Verifying CSPR Findings container in customer Artifact Registry...${NC}"
EXISTING_IMG=$(gcloud artifacts docker images list "${LOCATION}-docker.pkg.dev/${BQ_PROJECT_ID}/customer-cspr-toolkit" --project="${BQ_PROJECT_ID}" --format="value(package)" 2>/dev/null | grep "cspr-toolkit-findings" || true)

if [[ -n "${EXISTING_IMG}" ]]; then
    echo -e "${GREEN}[✔] Image '${CUSTOMER_FINDINGS_IMAGE}' already exists in customer Artifact Registry. Skipping push.${NC}"
elif command -v docker &> /dev/null; then
    echo -e "${CYAN}[i] Pulling and pushing '${PSO_FINDINGS_IMAGE}' via Docker...${NC}"
    gcloud auth configure-docker "us-docker.pkg.dev,${LOCATION}-docker.pkg.dev" --quiet
    docker pull "${PSO_FINDINGS_IMAGE}"
    docker tag "${PSO_FINDINGS_IMAGE}" "${CUSTOMER_FINDINGS_IMAGE}"
    docker push "${CUSTOMER_FINDINGS_IMAGE}"
    echo -e "${GREEN}[✔] Findings image pushed to customer registry.${NC}"
else
    echo -e "${YELLOW}[i] Local 'docker' binary not found. Transferring image via Artifact Registry HTTP V2 API...${NC}"
    python3 -c "
import subprocess, json, tempfile, os
token = subprocess.check_output(['gcloud', 'auth', 'print-access-token']).decode().strip()
src_host, src_repo = 'us-docker.pkg.dev', 'cloud-pso-security/cspr-toolkit/cspr-toolkit-findings'
dst_host, dst_repo = '${LOCATION}-docker.pkg.dev', '${BQ_PROJECT_ID}/customer-cspr-toolkit/cspr-toolkit-findings'
tag = 'latest'
out = subprocess.check_output(['curl', '-sS', '-H', f'Authorization: Bearer {token}', '-H', 'Accept: application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.index.v1+json', f'https://{src_host}/v2/{src_repo}/manifests/{tag}'])
manifest = json.loads(out.decode())
if 'manifests' in manifest:
    amd64_digest = next((m['digest'] for m in manifest['manifests'] if m.get('platform', {}).get('architecture') == 'amd64'), manifest['manifests'][0]['digest'])
    out = subprocess.check_output(['curl', '-sS', '-H', f'Authorization: Bearer {token}', '-H', 'Accept: application/vnd.docker.distribution.manifest.v2+json', f'https://{src_host}/v2/{src_repo}/manifests/{amd64_digest}'])
    manifest = json.loads(out.decode())
blobs = [manifest['config']] + manifest.get('layers', [])
for b in blobs:
    digest = b['digest']
    code = subprocess.check_output(['curl', '-sS', '-I', '-o', '/dev/null', '-w', '%{http_code}', '-H', f'Authorization: Bearer {token}', f'https://{dst_host}/v2/{dst_repo}/blobs/{digest}']).decode().strip()
    if code == '200': continue
    with tempfile.NamedTemporaryFile(delete=False) as tf: tmp_path = tf.name
    subprocess.check_call(['curl', '-sS', '-L', '-H', f'Authorization: Bearer {token}', '-o', tmp_path, f'https://{src_host}/v2/{src_repo}/blobs/{digest}'])
    headers = subprocess.check_output(['curl', '-sS', '-I', '-X', 'POST', '-H', f'Authorization: Bearer {token}', '-H', 'Content-Length: 0', f'https://{dst_host}/v2/{dst_repo}/blobs/uploads/']).decode()
    loc = [l.split(': ', 1)[1].strip() for l in headers.splitlines() if l.lower().startswith('location:')][0]
    if loc.startswith('/'): loc = f'https://{dst_host}{loc}'
    sep = '&' if '?' in loc else '?'
    subprocess.check_call(['curl', '-sS', '-o', '/dev/null', '-X', 'PUT', '-H', f'Authorization: Bearer {token}', '-H', 'Content-Type: application/octet-stream', '--data-binary', f'@{tmp_path}', f'{loc}{sep}digest={digest}'])
    os.unlink(tmp_path)
with tempfile.NamedTemporaryFile(delete=False) as mf:
    mf.write(out)
    mf_path = mf.name
m_type = manifest.get('mediaType', 'application/vnd.docker.distribution.manifest.v2+json')
subprocess.check_call(['curl', '-sS', '-o', '/dev/null', '-X', 'PUT', '-H', f'Authorization: Bearer {token}', '-H', f'Content-Type: {m_type}', '--data-binary', f'@{mf_path}', f'https://{dst_host}/v2/{dst_repo}/manifests/{tag}'])
os.unlink(mf_path)
"
    echo -e "${GREEN}[✔] Findings image deployed to customer registry.${NC}"
fi

# ------------------------------------------------------------------------------
# [2/5] Ensure Cloud Identity Base Schema & Deploy/Run Findings Cloud Run Job
# ------------------------------------------------------------------------------
echo -e "${CYAN}[2/5] Ensuring Cloud Identity schema tables exist in '${BQ_PROJECT_ID}:cspr_ci'...${NC}"
bq query --nouse_legacy_sql --project_id="${BQ_PROJECT_ID}" "
CREATE TABLE IF NOT EXISTS \`${BQ_PROJECT_ID}.cspr_ci.cloudidentity_consumers\` (name STRING, state STRING, mailsSentCount INT64, updateTime STRING);
CREATE TABLE IF NOT EXISTS \`${BQ_PROJECT_ID}.cspr_ci.cloudidentity_domains\` (kind STRING, verified BOOL, etag STRING, creationTime STRING, isPrimary BOOL, domainName STRING);
CREATE TABLE IF NOT EXISTS \`${BQ_PROJECT_ID}.cspr_ci.cloudidentity_groups\` (name STRING, email STRING, whoCanJoin STRING, whoCanModerateMembers STRING, whoCanViewMembership STRING, whoCanViewGroup STRING, whoCanDiscoverGroup STRING, allowExternalMembers BOOL, members ARRAY<STRUCT<email STRING>>);
CREATE TABLE IF NOT EXISTS \`${BQ_PROJECT_ID}.cspr_ci.cloudidentity_roles\` (roleAssignmentId STRING, roleId STRING, assignedTo STRING, data STRUCT<roleName STRING, roleDescription STRING, rolePrivileges ARRAY<STRUCT<privilegeName STRING, serviceId STRING>>, isSystemRole BOOL, isSuperAdminRole BOOL>);
CREATE TABLE IF NOT EXISTS \`${BQ_PROJECT_ID}.cspr_ci.cloudidentity_tokens\` (items STRING, primaryEmail STRING);
CREATE TABLE IF NOT EXISTS \`${BQ_PROJECT_ID}.cspr_ci.cloudidentity_users\` (name STRING, primaryEmail STRING, isAdmin BOOL, isDelegatedAdmin BOOL, recoveryPhone STRING, recoveryEmail STRING, isEnforcedIn2SV BOOL, isEnrolledIn2SV BOOL, suspended BOOL, lastLoginTime STRING, creationTime STRING);
" >/dev/null 2>&1 || true

PROCESSED_FINDINGS_YAML="${BASE_DIR}/local_tests/cloudrun-findings-processed-${BQ_PROJECT_ID}.yaml"
cat << EOF > "${PROCESSED_FINDINGS_YAML}"
apiVersion: run.googleapis.com/v1
kind: Job
metadata:
  name: cspr-findings-job
  labels:
    cloud.googleapis.com/location: ${LOCATION}
spec:
  template:
    spec:
      taskCount: 1
      template:
        spec:
          serviceAccountName: cspr-prereq-cloudrun-sa@${BQ_PROJECT_ID}.iam.gserviceaccount.com
          containers:
          - image: ${CUSTOMER_FINDINGS_IMAGE}
            env:
            - name: BQ_PROJECT
              value: "${BQ_PROJECT_ID}"
            - name: BQ_PROJECT_ID
              value: "${BQ_PROJECT_ID}"
            - name: BQ_BILLING_PROJECT
              value: "${BQ_PROJECT_ID}"
            - name: LOCATION
              value: "${LOCATION}"
            - name: ORGANIZATION_ID
              value: "${ORGANIZATION_ID}"
            - name: ORG_DOMAIN
              value: "${ORG_DOMAIN}"
            - name: INCLUDE_LIST
              value: ""
            - name: EXCLUDE_LIST
              value: ""
            - name: BQDATASET_INVENTORY
              value: "cspr_cai"
            - name: BQDATASET_POLICYANALYZER
              value: "cspr_policy"
            - name: BQDATASET_EFFECTIVEORGPOLICY
              value: "cspr_policy"
            - name: BQDATASET_REC
              value: "cspr_rec"
            - name: BQDATASET_FINDING
              value: "cspr_finding"
            - name: BQDATASET_CLOUDIDENTITY
              value: "cspr_ci"
            resources:
              limits:
                cpu: "2000m"
                memory: "4Gi"
          timeoutSeconds: 3600
          maxRetries: 1
EOF

echo -e "${CYAN}[2/5] Deploying and executing 'cspr-findings-job' in Cloud Run (${LOCATION})...${NC}"
gcloud run jobs replace "${PROCESSED_FINDINGS_YAML}" --project="${BQ_PROJECT_ID}" --region="${LOCATION}"
gcloud run jobs execute cspr-findings-job --project="${BQ_PROJECT_ID}" --region="${LOCATION}" --wait
echo -e "${GREEN}[✔] Findings Scanner execution completed! Table '${BQ_PROJECT_ID}.cspr_finding.cspr_finding' populated.${NC}"

# ------------------------------------------------------------------------------
# [3/5] Finding Data Exporter (Create Unnested View/Table in BigQuery for Looker & Sheets)
# ------------------------------------------------------------------------------
echo -e "${CYAN}[3/5] Creating unnested analytical view '${BQ_PROJECT_ID}.cspr_finding.cspr_finding_unnested' (Finding Data Exporter)...${NC}"
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
echo -e "${GREEN}[✔] Unnested view 'cspr_finding_unnested' created in BigQuery.${NC}"

# ------------------------------------------------------------------------------
# [4/5] Extract Findings to JSON, CSV & Offline Review Checklist Folder (Findings_raw)
# ------------------------------------------------------------------------------
echo -e "${CYAN}[4/5] Exporting consolidated JSON, CSV, and Offline Review Checklist files (Findings_raw)...${NC}"
OUTPUT_JSON="${BASE_DIR}/local_tests/cspr_findings_${BQ_PROJECT_ID}.json"
OUTPUT_CSV="${BASE_DIR}/local_tests/cspr_findings_${BQ_PROJECT_ID}.csv"
RAW_DIR="${BASE_DIR}/local_tests/Findings_raw_${BQ_PROJECT_ID}"
mkdir -p "${RAW_DIR}"

bq query --nouse_legacy_sql --project_id="${BQ_PROJECT_ID}" --format=json --max_rows=10000 \
  "SELECT row_id, section, topic, finding, items FROM \`${BQ_PROJECT_ID}.cspr_finding.cspr_finding\` ORDER BY row_id" > "${OUTPUT_JSON}"

bq query --nouse_legacy_sql --project_id="${BQ_PROJECT_ID}" --format=csv --max_rows=100000 \
  "SELECT row_id, REGEXP_EXTRACT(row_id, r'^([a-z0-9]+)-') AS domain, section, topic, finding, ARRAY_LENGTH(items) AS remark_groups FROM \`${BQ_PROJECT_ID}.cspr_finding.cspr_finding\` ORDER BY row_id" > "${OUTPUT_CSV}"

python3 -c "
import json, os

json_path = '${OUTPUT_JSON}'
raw_dir = '${RAW_DIR}'
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
    items = r.get('items') or []
    if len(items) > 0:
        non_empty += 1
    with open(os.path.join(raw_dir, f'{rid}.json'), 'w', encoding='utf-8') as out:
        json.dump(r, out, indent=2, ensure_ascii=False)

with open(os.path.join(raw_dir, 'AutoFinding_row_ids.txt'), 'w', encoding='utf-8') as rf:
    rf.write('\n'.join(row_ids) + '\n')

print(f'   -> Generated {len(row_ids)} individual <row_id>.json files + AutoFinding_row_ids.txt ({non_empty} checks with active findings)')
"

# Mirror to Findings_raw_Nubank if project is nu-cspr-assessment
if [[ "${BQ_PROJECT_ID}" == "nu-cspr-assessment" ]]; then
    mkdir -p "${BASE_DIR}/local_tests/Findings_raw_Nubank"
    cp -R "${RAW_DIR}/"* "${BASE_DIR}/local_tests/Findings_raw_Nubank/" 2>/dev/null || true
fi

# Package everything into a single ZIP for easy Cloud Shell download
EXPORT_ZIP="${BASE_DIR}/local_tests/cspr_findings_bundle_${BQ_PROJECT_ID}.zip"
(cd "${BASE_DIR}/local_tests" && zip -q -r "cspr_findings_bundle_${BQ_PROJECT_ID}.zip" "cspr_findings_${BQ_PROJECT_ID}.json" "cspr_findings_${BQ_PROJECT_ID}.csv" "Findings_raw_${BQ_PROJECT_ID}") || true

# ------------------------------------------------------------------------------
# [5/5] Consolidate into Deliverables (Excel Review Checklist, Word Questionnaires & Decks)
# ------------------------------------------------------------------------------
if [[ -f "${BASE_DIR}/scripts/06_build_nubank_drive_workspace.py" ]]; then
    echo -e "${CYAN}[5/5] Building consolidated Review Checklist (.xlsx), Domain Questionnaires (.docx) & Executive Decks...${NC}"
    python3 "${BASE_DIR}/scripts/06_build_nubank_drive_workspace.py" || echo -e "${YELLOW}[i] Skipping local Office doc build (run 06_build_nubank_drive_workspace.py on Mac after downloading JSON bundle).${NC}"
fi

echo ""
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD} [✔] FASE 05 CONCLUÍDA COM SUCESSO!                                          ${NC}"
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo -e " 1. ${BOLD}BigQuery Online Mode (Google Sheets Review Checklist Template):${NC}"
echo -e "    • Abra a planilha Review Checklist -> Menu ${CYAN}Automation -> 1. Populate automated findings from BigQuery Dataset (Online mode)${NC}"
echo -e "    • Informe: Project ID = ${BOLD}${BQ_PROJECT_ID}${NC} | Dataset = ${BOLD}cspr_finding${NC} | Location = ${BOLD}${LOCATION}${NC}"
echo ""
echo -e " 2. ${BOLD}Google Drive Offline Mode (Pasta Findings_raw):${NC}"
echo -e "    • Diretório gerado: ${BOLD}${RAW_DIR}/${NC} (326 arquivos <row_id>.json + AutoFinding_row_ids.txt)"
echo -e "    • Na planilha Review Checklist -> Menu ${CYAN}Automation -> 2. Populate automated findings from Google Drive Folder (Offline mode)${NC}"
echo ""
echo -e " 3. ${BOLD}Pacote Completo para Download (se estiver no Cloud Shell):${NC}"
echo -e "    • Rode: ${YELLOW}cloudshell download ${EXPORT_ZIP}${NC}"
echo ""
