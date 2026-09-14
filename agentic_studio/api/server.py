"""FastAPI Server for CSPR Copilot & Agentic Studio (Gemini 3.x Multi-Model Platform)."""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from agentic_studio.core.auth import get_verified_google_user
from agentic_studio.core.cspr_engine import CSPREngine
from agentic_studio.core.model_router import ModelRouter

app = FastAPI(
    title="CSPR Copilot & Agentic Studio",
    version="3.1.0",
    description="AI-assisted Cloud Security Posture Review Platform powered by Gemini 3.x (@google.com Exclusive)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

model_router = ModelRouter()
cspr_engine = CSPREngine()
UI_HTML_PATH = Path(__file__).resolve().parents[1] / "ui" / "index.html"


class ModelSelectRequest(BaseModel):
    model_id: str


class CopilotChatRequest(BaseModel):
    message: str
    preferred_model: Optional[str] = None
    phase_context: Optional[str] = None


@app.get("/healthz")
@app.get("/api/v1/health")
def healthz() -> Dict[str, str]:
    """Cloud Run liveness and readiness probe."""
    return {"status": "healthy", "service": "cspr-copilot-studio"}


@app.get("/", response_class=HTMLResponse)
def serve_studio_ui() -> str:
    """Serves the CSPR Copilot & Agentic Studio web dashboard."""
    if UI_HTML_PATH.exists():
        return UI_HTML_PATH.read_text(encoding="utf-8")
    return "<h1>CSPR Copilot Studio UI not found</h1>"


@app.get("/api/v1/auth/me")
def get_current_user_identity(
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Returns the verified @google.com user context."""
    return {
        "authenticated": True,
        "user": user,
        "google_oauth_client_id": os.getenv(
            "GOOGLE_OAUTH_CLIENT_ID",
            "32555940559.apps.googleusercontent.com",
        ),
    }


@app.get("/api/v1/status")
def get_platform_status(
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Returns full Studio status including Gemini 3.x router and CSPR phases sync status."""
    return {
        "platform": "CSPR Copilot & Agentic Studio",
        "version": "3.1.0",
        "authenticated_user": user,
        "model_router": model_router.get_status(),
        "phases": cspr_engine.get_phases_status(),
    }


@app.post("/api/v1/models/select")
def set_active_model(
    req: ModelSelectRequest,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Switches the primary Gemini 3.x model used by CSPR Copilot."""
    if not req.model_id.strip():
        raise HTTPException(status_code=400, detail="model_id cannot be empty")
    return model_router.set_primary_model(req.model_id)


@app.post("/api/v1/sync-from-nubank")
def sync_scripts_from_nubank(
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Synchronizes the 6 CSPR bash scripts from Google/CSPR (Nubank base) into cspr_copilot."""
    result = cspr_engine.sync_from_nubank()
    return {
        "sync_result": result,
        "phases": cspr_engine.get_phases_status(),
    }


@app.post("/api/v1/phases/{phase_code}/dry-run")
def dry_run_phase(
    phase_code: str,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Validates bash syntax and metadata for a specific CSPR phase script."""
    return cspr_engine.dry_run_phase(phase_code)


@app.post("/api/v1/copilot/chat")
def copilot_chat(
    req: CopilotChatRequest,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Analyzes CSPR logs, GCP IAM/Org Policy errors, and recommends gcloud remediations."""
    system_instruction = (
        f"You are CSPR Copilot, assisting Google Cloud Security Architect {user['email']} (@google.com). "
        "You specialize in Google Cloud Security Posture Review (CSPR) field execution across all 6 phases "
        "(01_setup_cspr_prereqs.sh, 01.1_cloudshell_push_image.sh, 02_push_scanner_image.sh, "
        "03_deploy_and_run_job.sh, 04_validate_bigquery.sh, 05_generate_findings.sh). "
        "When given real-world customer errors (such as Nubank GCP Org Policies, VPC-SC, Cloud Run Job OOM/timeouts, "
        "or BigQuery __TABLES__ verification issues), provide exact root-cause diagnosis and ready-to-run gcloud commands."
    )
    full_prompt = req.message
    if req.phase_context:
        full_prompt = f"[Phase Context: {req.phase_context}]\n\n{req.message}"

    result = model_router.generate(
        prompt=full_prompt,
        system_instruction=system_instruction,
        preferred_model=req.preferred_model,
    )
    return result
