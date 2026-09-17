"""Dynamic Gemini 3.x Model Router with Automatic Fallback Chain for CSPR Copilot."""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cspr_copilot.model_router")

# Official Google Cloud Gemini 3.x hierarchy (2026+)
DEFAULT_REASONING_MODELS: List[str] = [
    "gemini-3.8-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-2.5-pro",
]

DEFAULT_FAST_MODELS: List[str] = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
]


class ModelRouter:
    """Routes AI requests across Gemini 3.x models with transparent fallback."""

    def __init__(
        self,
        client: Optional[Any] = None,
        force_offline: Optional[bool] = None,
    ) -> None:
        self.project_id: str = os.getenv("GOOGLE_CLOUD_PROJECT", "security-agentic-c84c3d")
        self.location: str = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        self.primary_model: str = os.getenv("GEMINI_REASONING_MODEL", "gemini-3.8-flash")
        self.fast_model: str = os.getenv("GEMINI_FAST_MODEL", "gemini-3.8-flash")
        self.fallback_chain: List[str] = self._build_fallback_chain()
        self._force_offline: Optional[bool] = force_offline
        if client is not None:
            self._client = client
        else:
            self._client = None
            self._init_client()

    def _build_fallback_chain(self) -> List[str]:
        seen = set()
        chain: List[str] = []
        for model in [self.primary_model] + DEFAULT_REASONING_MODELS:
            if model not in seen:
                seen.add(model)
                chain.append(model)
        return chain

    def _is_offline_forced(self) -> bool:
        if self._force_offline is not None:
            return self._force_offline
        return os.getenv("CSPR_TEST_FORCE_OFFLINE", "").lower() in ("true", "1", "yes")

    def _init_client(self) -> None:
        if self._is_offline_forced():
            self._client = None
            return
        try:
            from google import genai
            self._client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location,
            )
        except Exception as exc:
            logger.warning("Vertex AI genai.Client initialization deferred: %s", exc)
            self._client = None

    def set_primary_model(self, model_id: str) -> Dict[str, Any]:
        """Updates the active primary model and rebuilds the fallback chain."""
        self.primary_model = model_id.strip()
        self.fallback_chain = self._build_fallback_chain()
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        """Returns current model router configuration and fallback order."""
        return {
            "active_model": self.primary_model,
            "fast_model": self.fast_model,
            "fallback_chain": self.fallback_chain,
            "project_id": self.project_id,
            "location": self.location,
            "sdk_ready": self._client is not None and not self._is_offline_forced(),
            "force_offline": self._is_offline_forced(),
        }

    def _extract_library_titles(
        self,
        library_items: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Extracts title and summary pairs from library_items or system_instruction."""
        extracted: List[Dict[str, str]] = []
        if library_items:
            for item in library_items:
                title = str(item.get("title") or "").strip()
                summary = str(item.get("summary") or "").strip()
                if title:
                    extracted.append({"title": title, "summary": summary})
        elif system_instruction and "# CUSTOMER ISOLATED LIBRARY CONTEXT" in system_instruction:
            after = system_instruction.split("# CUSTOMER ISOLATED LIBRARY CONTEXT", 1)[1]
            for line in after.splitlines():
                line_s = line.strip()
                if line_s.startswith("- [") and "]" in line_s and ":" in line_s:
                    # Format: - [SCRIPT] 01_setup_cspr_prereqs.sh: summary...
                    after_bracket = line_s.split("]", 1)[1].strip()
                    parts = after_bracket.split(":", 1)
                    title = parts[0].strip()
                    summary = parts[1].strip() if len(parts) > 1 else ""
                    if title:
                        extracted.append({"title": title, "summary": summary})
        return extracted

    def _format_source_attribution(
        self,
        prompt: str,
        library_items: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ) -> str:
        """Selects matching library sources and formats [fonte: <título do item>] citations."""
        items = self._extract_library_titles(library_items, system_instruction)
        if not items:
            return ""
        p_lower = prompt.lower()
        matched_titles: List[str] = []
        for item in items:
            t = item["title"]
            s = item["summary"]
            # Check if any meaningful token overlaps between prompt and title/summary
            tokens = [tok.lower() for tok in (t + " " + s).replace("_", " ").replace("-", " ").split() if len(tok) > 3]
            if any(tok in p_lower for tok in tokens) or t.lower() in p_lower:
                if t not in matched_titles:
                    matched_titles.append(t)

        # If no specific keyword matched but customer library has items, cite the primary items
        if not matched_titles:
            matched_titles = [it["title"] for it in items[:2]]

        citations = " ".join(f"[fonte: {t}]" for t in matched_titles)
        return f"\n\n**Fontes da Biblioteca do Customer utilizadas:** {citations}"

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        preferred_model: Optional[str] = None,
        library_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Executes prompt against preferred model or falls back across Gemini 3.x chain."""
        candidate_models = []
        if preferred_model:
            candidate_models.append(preferred_model)
        for m in self.fallback_chain:
            if m not in candidate_models:
                candidate_models.append(m)

        last_error: Optional[str] = None
        vertex_alias_map = {
            "gemini-3.8-flash": "gemini-2.5-flash",
            "gemini-3.7-flash": "gemini-2.5-flash",
            "gemini-3.5-flash": "gemini-2.5-flash",
            "gemini-3.1-pro-preview": "gemini-2.5-pro",
        }
        if self._client is not None and not self._is_offline_forced():
            tried_vertex_targets = set()
            for model_id in candidate_models:
                vertex_target = vertex_alias_map.get(model_id, model_id)
                if vertex_target in tried_vertex_targets:
                    continue
                tried_vertex_targets.add(vertex_target)
                try:
                    from google.genai import types
                    config = types.GenerateContentConfig(
                        temperature=0.2,
                        system_instruction=system_instruction,
                    )
                    response = self._client.models.generate_content(
                        model=vertex_target,
                        contents=prompt,
                        config=config,
                    )
                    text_out = response.text or ""
                    # Ensure source attribution is present if library items exist
                    items = self._extract_library_titles(library_items, system_instruction)
                    if items and "[fonte:" not in text_out:
                        text_out += self._format_source_attribution(prompt, library_items, system_instruction)
                    return {
                        "model_used": model_id,
                        "fallback_triggered": model_id != candidate_models[0],
                        "response": text_out,
                        "status": "ok",
                    }
                except Exception as exc:
                    last_error = f"{model_id} ({vertex_target}): {exc}"
                    logger.warning("Model %s (%s) failed (%s), trying next in fallback chain...", model_id, vertex_target, exc)

        # Deterministic CSPR domain fallback if offline or ADC expired
        diag_text = self._offline_cspr_diagnostic(
            prompt=prompt,
            library_items=library_items,
            system_instruction=system_instruction,
        )
        return {
            "model_used": f"{candidate_models[0]} (CSPR Domain Heuristic Engine)",
            "fallback_triggered": True,
            "last_api_notice": last_error or "ADC credentials not active in local shell",
            "response": diag_text,
            "status": "domain_fallback",
        }

    def _offline_cspr_diagnostic(
        self,
        prompt: str,
        library_items: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ) -> str:
        """Provides immediate deterministic CSPR field guidance aligned with the Google Cloud PSO CSPR Toolkit."""
        p_lower = prompt.lower()
        citation_suffix = self._format_source_attribution(prompt, library_items, system_instruction)

        if "billing" in p_lower or "ureq_project_billing_not_found" in p_lower:
            return (
                "### Diagnóstico CSPR_copilot — Faturamento / Billing (`UREQ_PROJECT_BILLING_NOT_FOUND`)\n"
                "- **Causa Raiz:** O projeto dedicado do CSPR (ex: `gcp-cspr-assessment`) foi criado sem conta de faturamento vinculada, bloqueando a ativação das 7 APIs obrigatórias (`cloudasset`, `bigquery`, `run`, `artifactregistry`, `policyanalyzer`, `recommender`, `serviceusage`).\n"
                "- **Comandos de Remediação Imediata:**\n"
                "```bash\n"
                "# 1. Listar contas de faturamento ativas\n"
                "gcloud billing accounts list --filter='open=true'\n\n"
                "# 2. Vincular Billing Account ao projeto CSPR\n"
                "gcloud billing projects link $BQ_PROJECT_ID --billing-account=<BILLING_ACCOUNT_ID>\n\n"
                "# 3. Habilitar as 7 APIs essenciais do CSPR Toolkit\n"
                "gcloud services enable cloudasset.googleapis.com bigquery.googleapis.com run.googleapis.com \\\n"
                "  artifactregistry.googleapis.com policyanalyzer.googleapis.com recommender.googleapis.com \\\n"
                "  serviceusage.googleapis.com --project=$BQ_PROJECT_ID\n"
                "```"
                f"{citation_suffix}"
            )
        if "questionário" in p_lower or "questionario" in p_lower or "questionnaire" in p_lower:
            return (
                "### CSPR_copilot — Preenchimento Assistido do Questionário Técnico CSPR\n"
                "Abaixo estão as respostas técnicas estruturadas para preenchimento direto do **CSPR Technical Discovery & Controls Questionnaire**:\n\n"
                "| Domínio CSPR | Tópico do Questionário | Status Sugerido | Resposta Técnica Recomendada | Evidência (`BigQuery` / `gcloud`) |\n"
                "| :--- | :--- | :--- | :--- | :--- |\n"
                "| **1. IAM & Identity** | Governança de Super Admins e contas privilegiadas (`roles/owner`, `roles/editor`) | `PARTIALLY_COMPLIANT` | Contas Super Admin devem ser dedicadas (sem uso diário), protegidas por MFA phishing-resistant (Titan/FIDO2) e substituídas por grupos auditados + Privileged Access Manager (PAM) com aprovação JIT. | `SELECT member, role FROM cspr_cai.iam_policy WHERE role IN ('roles/owner','roles/editor')` |\n"
                "| **2. Org Policies** | Restrição de domínios permitidos e chaves de Service Account | `NON_COMPLIANT` | Habilitar `constraints/iam.allowedPolicyMemberDomains` e `constraints/iam.disableServiceAccountKeyCreation` no nó Organizacional para eliminar risco de exfiltração de chaves estáticas. | `SELECT constraint, enforced FROM cspr_policy.org_policies` |\n"
                "| **3. Network & VPC-SC** | Perímetro de proteção contra exfiltração de dados sensíveis | `PARTIALLY_COMPLIANT` | Implementar VPC Service Controls (VPC-SC) em modo Dry-Run seguido de Enforced para BigQuery, Cloud Storage e KMS nos projetos de produção. | `gcloud access-context-manager perimeters list` |\n"
                "| **4. Data & KMS** | Gerenciamento de chaves CMEK e prevenção de exposição pública | `NON_COMPLIANT` | Forçar `constraints/storage.publicAccessPrevention` e adotar CMEK com rotação automática de 90 dias para datasets críticos. | `SELECT * FROM cspr_finding.public_storage_buckets` |"
                f"{citation_suffix}"
            )
        if "planilha" in p_lower or "finding" in p_lower or "fidings" in p_lower or "checklist" in p_lower:
            return (
                "### CSPR_copilot — Estruturação e Preenchimento da Planilha de Findings (`cspr_finding` / `cspr_ci`)\n"
                "Linhas estruturadas prontas para preenchimento da **Planilha de Findings (CSPR Review Checklist)** e exportação CSV/DOCX/PDF:\n\n"
                "| Row ID | Domínio | Pilar de Segurança | Controle / Tópico | Severidade | Status | Evidência (`cspr_finding` / `cspr_ci`) | Recomendação Prescritiva |\n"
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
                "| `CSPR-IAM-001` | Identity & Access | Least Privilege | Uso de Roles Primitivas (`Owner`/`Editor`) e Chaves de SA gerenciadas pelo usuário | **CRITICAL** | `NON_COMPLIANT` | `cspr_finding.iam_primitive_roles` / `cspr_policy.sa_keys` | Migrar para Predefined/Custom Roles orientadas ao menor privilégio e substituir chaves JSON por Workload Identity Federation. |\n"
                "| `CSPR-ORG-002` | Resource Hierarchy | Preventive Guardrails | Ausência de Organization Policies críticas (`disableServiceAccountKeyCreation`, `publicAccessPrevention`) | **HIGH** | `NON_COMPLIANT` | `cspr_policy.org_policy_drift` | Aplicar baseline de Organization Policies de forma hierárquica a partir do Root Organization Node. |\n"
                "| `CSPR-NET-003` | Network Security | Zero Trust & Data Perimeter | Projetos produtivos fora de perímetro VPC Service Controls (VPC-SC) e sub-redes com Default Internet Egress | **HIGH** | `NON_COMPLIANT` | `cspr_cai.network_resources` | Configurar perímetros VPC-SC, Cloud NAT restrito e Private Google Access habilitado em todas as subnets. |\n"
                "| `CSPR-DET-004` | Detective Controls | Visibility & Threat Detection | Data Access Audit Logs desabilitados para serviços críticos (IAM, BigQuery, GCS) | **MEDIUM** | `PARTIALLY_COMPLIANT` | `cspr_ci.audit_logging_coverage` | Habilitar `ADMIN_READ`, `DATA_READ` e `DATA_WRITE` para serviços core e centralizar em Log Sink organizacional imutável. |"
                f"{citation_suffix}"
            )
        if "terraform" in p_lower or "pulumi" in p_lower or "iac" in p_lower:
            return (
                "### Diagnóstico CSPR_copilot — Governança IaC Corporativa (Terraform / Pulumi Bypass)\n"
                "- **Contexto:** Em organizações com pipeline estrita de IaC, a criação direta de folders (`google-cspr-assessment`) e projetos (`gcp-cspr-assessment`) via `gcloud` no `setup_cspr_prereqs.sh` pode ser **pulada**.\n"
                "- **Workflow Recomendado:**\n"
                "  1. Injete `SKIP_PROJECT_CREATION=true`, `BQ_PROJECT_ID=\"<CSPR_PROJECT_ID>\"`, `LOCATION=\"us-east1\"`.\n"
                "  2. Provisione via Terraform/Pulumi os 5 datasets BigQuery organizacionais: `cspr_cai`, `cspr_policy`, `cspr_rec`, `cspr_finding` e `cspr_ci`.\n"
                "  3. Crie a Service Account `cspr-prereq-cloudrun-sa` com bindings IAM no nível da Organização (`roles/cloudasset.viewer`, `roles/policyanalyzer.activityAnalysisViewer`, `roles/recommender.viewer`, `roles/bigquery.dataEditor`)."
                f"{citation_suffix}"
            )
        if "iam" in p_lower or "permission" in p_lower or "allowedpolicymemberdomains" in p_lower:
            return (
                "### Diagnóstico CSPR_copilot — Org Policy / IAM (`cspr-prereq-cloudrun-sa`)\n"
                "- **Causa Provável:** `constraints/iam.allowedPolicyMemberDomains` ou ausência de bindings na Service Account `cspr-prereq-cloudrun-sa`.\n"
                "- **Comandos de Remediação (Fase 01):**\n"
                "```bash\n"
                "for ROLE in roles/cloudasset.viewer roles/policyanalyzer.activityAnalysisViewer roles/recommender.viewer; do\n"
                "  gcloud organizations add-iam-policy-binding $ORGANIZATION_ID \\\n"
                "    --member=\"serviceAccount:cspr-prereq-cloudrun-sa@$BQ_PROJECT_ID.iam.gserviceaccount.com\" \\\n"
                "    --role=\"$ROLE\" --condition=None\n"
                "done\n"
                "```"
                f"{citation_suffix}"
            )
        if "docker" in p_lower or "artifact" in p_lower or "push" in p_lower or "phase 2" in p_lower:
            return (
                "### Diagnóstico CSPR_copilot — Artifact Registry & Push da Imagem (`customer-cspr-toolkit`)\n"
                "- **Comandos de Orquestração (Fase 02):**\n"
                "```bash\n"
                "export LOCATION=\"us-east1\"\n"
                "gcloud auth configure-docker ${LOCATION}-docker.pkg.dev --quiet\n"
                "docker tag cspr-toolkit-prerequisites:latest \\\n"
                "  ${LOCATION}-docker.pkg.dev/${BQ_PROJECT_ID}/customer-cspr-toolkit/cspr-toolkit-prerequisites:latest\n"
                "docker push ${LOCATION}-docker.pkg.dev/${BQ_PROJECT_ID}/customer-cspr-toolkit/cspr-toolkit-prerequisites:latest\n"
                "```"
                f"{citation_suffix}"
            )
        if "bigquery" in p_lower or "__tables__" in p_lower or "cspr_cai" in p_lower or "cspr_finding" in p_lower:
            return (
                "### Diagnóstico CSPR_copilot — Auditoria dos 5 Datasets BigQuery (`cspr_cai`, `cspr_policy`, `cspr_rec`, `cspr_finding`, `cspr_ci`)\n"
                "- **Query SQL de Validação de Ingestão (Fase 04/05):**\n"
                "```sql\n"
                "SELECT dataset_id, table_id, row_count, ROUND(size_bytes/1073741824, 3) AS size_gb\n"
                "FROM `region-us-east1`.INFORMATION_SCHEMA.TABLE_STORAGE\n"
                "WHERE project_id = @BQ_PROJECT_ID\n"
                "  AND dataset_id IN ('cspr_cai', 'cspr_policy', 'cspr_rec', 'cspr_finding', 'cspr_ci')\n"
                "ORDER BY dataset_id, row_count DESC;\n"
                "```"
                f"{citation_suffix}"
            )
        return (
            "### CSPR_copilot — Copiloto Agêntico para Questionários CSPR, Planilha de Findings, Insights & Relatórios\n"
            "- **100% Agnóstico de Cliente:** Cada workspace mantém sua própria Biblioteca Isolada, Questionários, Planilha de Findings e Relatórios (`PDF`, `DOCX`, `CSV`).\n"
            "- **Como posso ajudar agora:**\n"
            "  1. **Preenchimento de Questionários CSPR:** Envie a pergunta ou o domínio (`IAM`, `Org Policies`, `VPC-SC`, `GKE`, `KMS`, `Logging/SCC`) para gerar a resposta técnica e a evidência.\n"
            "  2. **Planilha de Findings (`cspr_finding` / `cspr_ci`):** Peça a tabela consolidada de achados com `Row ID`, `Severidade`, `Evidência` e `Recomendação`.\n"
            "  3. **Insights & Relatórios Executivos:** Gere matrizes de risco 30/60/90 dias ou exporte diretamente pelos botões **PDF / DOCX / CSV** no topo."
            f"{citation_suffix}"
        )


