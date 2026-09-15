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

    def __init__(self) -> None:
        self.project_id: str = os.getenv("GOOGLE_CLOUD_PROJECT", "security-agentic-c84c3d")
        self.location: str = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        self.primary_model: str = os.getenv("GEMINI_REASONING_MODEL", "gemini-3.8-flash")
        self.fast_model: str = os.getenv("GEMINI_FAST_MODEL", "gemini-3.8-flash")
        self.fallback_chain: List[str] = self._build_fallback_chain()
        self._client: Any = None
        self._init_client()

    def _build_fallback_chain(self) -> List[str]:
        seen = set()
        chain: List[str] = []
        for model in [self.primary_model] + DEFAULT_REASONING_MODELS:
            if model not in seen:
                seen.add(model)
                chain.append(model)
        return chain

    def _init_client(self) -> None:
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
            "sdk_ready": self._client is not None,
        }

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        preferred_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes prompt against preferred model or falls back across Gemini 3.x chain."""
        candidate_models = []
        if preferred_model:
            candidate_models.append(preferred_model)
        for m in self.fallback_chain:
            if m not in candidate_models:
                candidate_models.append(m)

        last_error: Optional[str] = None
        if self._client is not None:
            for model_id in candidate_models:
                try:
                    from google.genai import types
                    config = types.GenerateContentConfig(
                        temperature=0.2,
                        system_instruction=system_instruction,
                    )
                    response = self._client.models.generate_content(
                        model=model_id,
                        contents=prompt,
                        config=config,
                    )
                    return {
                        "model_used": model_id,
                        "fallback_triggered": model_id != candidate_models[0],
                        "response": response.text or "",
                        "status": "ok",
                    }
                except Exception as exc:
                    last_error = f"{model_id}: {exc}"
                    logger.warning("Model %s failed (%s), trying next in fallback chain...", model_id, exc)

        # Deterministic CSPR domain fallback if offline or ADC expired
        return {
            "model_used": f"{candidate_models[0]} (CSPR Domain Heuristic Engine)",
            "fallback_triggered": True,
            "last_api_notice": last_error or "ADC credentials not active in local shell",
            "response": self._offline_cspr_diagnostic(prompt),
            "status": "domain_fallback",
        }

    def _offline_cspr_diagnostic(self, prompt: str) -> str:
        """Provides immediate deterministic CSPR field guidance aligned with the Google Cloud PSO CSPR Toolkit."""
        p_lower = prompt.lower()
        if "billing" in p_lower or "ureq_project_billing_not_found" in p_lower:
            return (
                "### Diagnóstico CSPR_copilot — Faturamento / Billing (`UREQ_PROJECT_BILLING_NOT_FOUND`)\n"
                "- **Causa Raiz:** O projeto dedicado do CSPR (ex: `nu-cspr-assessment`) foi criado sem conta de faturamento vinculada, bloqueando a ativação das 7 APIs obrigatórias (`cloudasset`, `bigquery`, `run`, `artifactregistry`, `policyanalyzer`, `recommender`, `serviceusage`).\n"
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
            )
        if "terraform" in p_lower or "pulumi" in p_lower or "nubank" in p_lower or "iac" in p_lower:
            return (
                "### Diagnóstico CSPR_copilot — Governança IaC Corporativa (Terraform / Pulumi Bypass)\n"
                "- **Contexto:** Em clientes com pipeline estrita de IaC (ex: Nubank), a criação direta de folders (`google-cspr-nubank`) e projetos (`nu-cspr-assessment`) via `gcloud` no `setup_cspr_prereqs.sh` deve ser **pulada**.\n"
                "- **Workflow Recomendado:**\n"
                "  1. Injete `SKIP_PROJECT_CREATION=true`, `BQ_PROJECT_ID=\"nu-cspr-assessment\"`, `LOCATION=\"us-east1\"`.\n"
                "  2. Provisione via Terraform/Pulumi os 5 datasets BigQuery organizacionais: `cspr_cai`, `cspr_policy`, `cspr_rec`, `cspr_finding` e `cspr_ci`.\n"
                "  3. Crie a Service Account `cspr-prereq-cloudrun-sa` com bindings IAM no nível da Organização (`roles/cloudasset.viewer`, `roles/policyanalyzer.activityAnalysisViewer`, `roles/recommender.viewer`, `roles/bigquery.dataEditor`)."
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
            )
        return (
            "### CSPR_copilot — Senior GCP Security Architect & Lead CSPR Assessor\n"
            "- **Domínio Completo:** 7 APIs CSPR (`cloudasset`, `bigquery`, `run`, `artifactregistry`, `policyanalyzer`, `recommender`, `serviceusage`), Artifact Registry (`customer-cspr-toolkit`), Cloud Run Job (`cspr-prereq-job`), SA (`cspr-prereq-cloudrun-sa`), e os 5 Datasets BigQuery (`cspr_cai`, `cspr_policy`, `cspr_rec`, `cspr_finding`, `cspr_ci`).\n"
            "- **Pronto para Ação:** Cole um log de erro (`UREQ_PROJECT_BILLING_NOT_FOUND`, IAM, Docker, Cloud Run Job) ou solicite a customização de scripts/Terraform para o Customer ativo."
        )

