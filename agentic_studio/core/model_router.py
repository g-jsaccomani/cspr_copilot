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
        """Provides immediate deterministic CSPR field guidance when Vertex AI ADC is offline."""
        p_lower = prompt.lower()
        if "iam" in p_lower or "permission" in p_lower or "allowedpolicymemberdomains" in p_lower:
            return (
                "### Diagnóstico CSPR — Org Policy / IAM\n"
                "- **Causa Provável:** `constraints/iam.allowedPolicyMemberDomains` ou ausência de `roles/cloudasset.viewer` / `roles/bigquery.dataEditor` na Service Account do Cloud Run Job.\n"
                "- **Ação Recomendada (Fase 01):**\n"
                "  1. Verifique se a Service Account pertence ao mesmo Customer ID da Org.\n"
                "  2. Execute `./scripts/01_setup_cspr_prereqs.sh` com `--project <PROJECT_ID>` para revalidar bindings IAM."
            )
        if "cloud run" in p_lower or "job" in p_lower or "timeout" in p_lower or "phase 3" in p_lower:
            return (
                "### Diagnóstico CSPR — Cloud Run Job (Fase 02 / 03)\n"
                "- **Causa Provável:** Timeout ou limite de memória no job de processamento (`03_run_cspr_processing.sh`).\n"
                "- **Ação Recomendada:**\n"
                "  1. Verifique os logs reais da execução com `gcloud run jobs executions list --region=<REGION>`.\n"
                "  2. Aumente `--memory=4Gi --task-timeout=3600s` caso o volume exportado pelo Cloud Asset Inventory exceda 500k recursos."
            )
        if "bigquery" in p_lower or "__tables__" in p_lower or "phase 4" in p_lower:
            return (
                "### Diagnóstico CSPR — Verificação BigQuery (Fase 04)\n"
                "- **Ação Recomendada:** Execute `./scripts/04_verify_cspr_results.sh` para consultar a metadados `__TABLES__` e validar contagem exata de linhas e GB ingeridos por tabela CSPR."
            )
        return (
            "### CSPR Copilot & Studio (Gemini 3.x Engine)\n"
            "- Pipeline pronto para validar Fases 01 a 05.\n"
            "- Cole qualquer log de erro real do ambiente GCP do cliente para diagnóstico imediato com recomendação de comando `gcloud`."
        )
