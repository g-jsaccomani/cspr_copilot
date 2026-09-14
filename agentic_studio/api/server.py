"""FastAPI Server for CSPR Copilot & Agentic Studio (Gemini 3.x Multi-Model Platform)."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from agentic_studio.core.auth import get_verified_google_user
from agentic_studio.core.cspr_engine import CSPREngine
from agentic_studio.core.customer_store import CustomerStore
from agentic_studio.core.model_router import ModelRouter

app = FastAPI(
    title="CSPR Copilot & Agentic Studio",
    version="3.2.0",
    description="Customer-Agnostic AI Cloud Security Posture Review Platform powered by Gemini 3.x (@google.com Exclusive)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

model_router = ModelRouter()
cspr_engine = CSPREngine()
customer_store = CustomerStore()
UI_HTML_PATH = Path(__file__).resolve().parents[1] / "ui" / "index.html"


class ModelSelectRequest(BaseModel):
    model_id: str


class CreateCustomerRequest(BaseModel):
    name: str
    gcp_project_id: Optional[str] = ""
    org_id: Optional[str] = ""
    description: Optional[str] = ""


class AddLibraryItemRequest(BaseModel):
    title: str
    item_type: Optional[str] = "document"
    summary: str


class CreateConversationRequest(BaseModel):
    customer_id: str
    title: Optional[str] = "Nova conversa"


class CopilotChatRequest(BaseModel):
    message: str
    customer_id: str
    conversation_id: Optional[str] = None
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
    """Returns full Studio status including Gemini 3.x router, Customer workspaces, and CSPR phases."""
    customers = customer_store.list_customers()
    return {
        "platform": "CSPR Copilot & Agentic Studio",
        "version": "3.2.0",
        "authenticated_user": user,
        "model_router": model_router.get_status(),
        "phases": cspr_engine.get_phases_status(),
        "customers": customers,
        "conversations": customer_store.list_conversations(),
    }


@app.get("/api/v1/customers")
def list_customers(
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> List[Dict[str, Any]]:
    """Lists all isolated Customer Workspaces."""
    return customer_store.list_customers()


@app.post("/api/v1/customers")
def create_customer(
    req: CreateCustomerRequest,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Creates a strictly isolated Customer Workspace & Library."""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="O nome do Customer é obrigatório.")
    return customer_store.create_customer(
        name=req.name,
        gcp_project_id=req.gcp_project_id or "",
        org_id=req.org_id or "",
        description=req.description or "",
    )


@app.post("/api/v1/customers/{customer_id}/library")
def add_customer_library_item(
    customer_id: str,
    req: AddLibraryItemRequest,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Adds an isolated file/script/log item to a specific Customer's library."""
    try:
        item = customer_store.add_library_item(
            customer_id=customer_id,
            title=req.title,
            item_type=req.item_type or "document",
            content_or_summary=req.summary,
        )
        return {"status": "ok", "item": item, "customer": customer_store.get_customer(customer_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/conversations")
def list_conversations(
    customer_id: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> List[Dict[str, Any]]:
    """Lists conversations, optionally filtered by isolated Customer ID."""
    return customer_store.list_conversations(customer_id=customer_id)


@app.post("/api/v1/conversations")
def create_conversation(
    req: CreateConversationRequest,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Creates a new conversation strictly bound to a Customer Workspace."""
    try:
        return customer_store.create_conversation(
            customer_id=req.customer_id,
            title=req.title or "Nova conversa",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/v1/models/select")
def set_active_model(
    req: ModelSelectRequest,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Switches the primary Gemini 3.x model used by CSPR Copilot."""
    if not req.model_id.strip():
        raise HTTPException(status_code=400, detail="model_id cannot be empty")
    return model_router.set_primary_model(req.model_id)


@app.post("/api/v1/sync-upstream")
def sync_scripts_from_upstream(
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Synchronizes the 6 CSPR bash scripts from Upstream CSPR Engine into cspr_copilot."""
    result = cspr_engine.sync_from_upstream()
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
    """Executes AI chat strictly isolated within the active Customer Workspace & Conversation."""
    customer = customer_store.get_customer(req.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer workspace {req.customer_id} not found.")

    conv = None
    if req.conversation_id:
        conv = customer_store.get_conversation(req.conversation_id)
    if not conv or conv.get("customer_id") != req.customer_id:
        conv = customer_store.create_conversation(customer_id=req.customer_id, title=req.message[:48])

    customer_store.append_message(
        conversation_id=conv["conversation_id"],
        role="user",
        content=req.message,
        model_used=req.preferred_model or model_router.primary_model,
    )

    library_context = "\n".join(
        f"- [{item['type'].upper()}] {item['title']}: {item['summary']}"
        for item in customer.get("library", [])
    ) or "Nenhum arquivo extra anexado à biblioteca deste Customer ainda."

    system_instruction = (
        f"You are CSPR Copilot, assisting Google Cloud Security Architect {user['email']} (@google.com). "
        f"CRITICAL ISOLATION RULE: You are operating strictly inside Customer Workspace '{customer['name']}' "
        f"(GCP Project: {customer['gcp_project_id']}, Org ID: {customer['org_id']}). "
        "NEVER mix or reference data from any other customer.\n"
        f"Customer Isolated Library Context:\n{library_context}\n\n"
        "You specialize in Google Cloud Security Posture Review (CSPR) field execution across all 6 phases "
        "(01_setup_cspr_prereqs.sh, 01.1_cloudshell_push_image.sh, 02_push_scanner_image.sh, "
        "03_deploy_and_run_job.sh, 04_validate_bigquery.sh, 05_generate_findings.sh). "
        "Provide exact root-cause diagnosis and ready-to-run gcloud commands."
    )
    full_prompt = req.message
    if req.phase_context:
        full_prompt = f"[Phase Context: {req.phase_context}]\n\n{req.message}"

    result = model_router.generate(
        prompt=full_prompt,
        system_instruction=system_instruction,
        preferred_model=req.preferred_model,
    )

    updated_conv = customer_store.append_message(
        conversation_id=conv["conversation_id"],
        role="assistant",
        content=result["response"],
        model_used=result["model_used"],
    )

    return {
        **result,
        "conversation": updated_conv,
        "customer": customer,
    }
