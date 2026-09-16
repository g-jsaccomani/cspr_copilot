"""FastAPI Server for CSPR Copilot & Agentic Studio (Gemini 3.x Multi-Model Platform)."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from agentic_studio.core.auth import get_verified_google_user
from agentic_studio.core.cspr_engine import CSPREngine
from agentic_studio.core.customer_store import CustomerStore, get_customer_store
from agentic_studio.core.model_router import ModelRouter
from agentic_studio.core.report_exporter import (
    export_customer_report_csv,
    export_customer_report_docx,
    export_customer_report_pdf,
)

app = FastAPI(
    title="CSPR Copilot & Agentic Studio",
    version="3.3.3",
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
customer_store = get_customer_store()
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


class ExportReportRequest(BaseModel):
    format: str = "pdf"


class UserPreferencesRequest(BaseModel):
    active_customer_id: Optional[str] = None
    active_conversation_id: Optional[str] = None
    preferred_model: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None
    google_oauth_client_id: Optional[str] = None


@app.get("/healthz")
@app.get("/api/v1/health")
def healthz() -> Dict[str, Any]:
    """Cloud Run liveness and readiness probe with multi-instance storage health check."""
    storage_health = customer_store.get_storage_health()
    return {
        "status": storage_health.get("status", "healthy"),
        "service": "cspr-copilot-studio",
        "storage_health": storage_health,
    }


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
    """Returns the verified @google.com user context and OAuth configuration."""
    from agentic_studio.core.auth import ALLOWED_DOMAINS, ALLOWED_EMAILS
    session = customer_store.get_user_session(user.get("email", "jsaccomani@google.com")) or {}
    client_id = (
        session.get("google_oauth_client_id")
        or os.getenv("GOOGLE_OAUTH_CLIENT_ID", "32555940559.apps.googleusercontent.com")
    )
    return {
        "authenticated": True,
        "user": user,
        "google_oauth_client_id": client_id,
        "allowed_domains": ALLOWED_DOMAINS,
        "allowed_emails": ALLOWED_EMAILS,
    }


@app.post("/api/v1/user/preferences")
def update_user_preferences(
    req: UserPreferencesRequest,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Persists user session preferences (active customer, conversation, model, custom OAuth client ID) in Cloud Firestore."""
    updated_payload = dict(user)
    if req.active_customer_id is not None:
        updated_payload["active_customer_id"] = req.active_customer_id
    if req.active_conversation_id is not None:
        updated_payload["active_conversation_id"] = req.active_conversation_id
    if req.preferred_model is not None:
        updated_payload["preferred_model"] = req.preferred_model
    if req.name is not None:
        updated_payload["name"] = req.name
    if req.picture is not None:
        updated_payload["picture"] = req.picture
    if req.google_oauth_client_id is not None:
        updated_payload["google_oauth_client_id"] = req.google_oauth_client_id.strip()
    saved = customer_store.save_user_session(updated_payload)
    return {
        "status": "saved",
        "session": saved,
        "google_oauth_client_id": saved.get("google_oauth_client_id"),
    }


@app.get("/api/v1/status")
def get_platform_status(
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Returns full Studio status including Gemini 3.x router, Customer workspaces, and CSPR phases."""
    customers = customer_store.list_customers()
    storage_health = customer_store.get_storage_health()
    return {
        "platform": "CSPR Copilot & Agentic Studio",
        "version": "3.3.3",
        "authenticated_user": user,
        "model_router": model_router.get_status(),
        "storage_health": storage_health,
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


@app.delete("/api/v1/customers/{customer_id}")
def delete_customer(
    customer_id: str,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Deletes a Customer Workspace, cascades all conversations, and reseeds if last."""
    try:
        result = customer_store.delete_customer(customer_id)
        return {
            "status": "deleted",
            **result,
            "customers": customer_store.list_customers(),
            "conversations": customer_store.list_conversations(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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


@app.get("/api/v1/cloud/inspect")
def inspect_live_cloud_posture(
    project_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Runs live read-only GCP inspection for CSPR readiness (7 APIs, IAM policy, Service Account)."""
    from agentic_studio.core.cloud_inspector import inspect_cspr_project_posture
    target_project = project_id
    if not target_project and customer_id:
        c = customer_store.get_customer(customer_id)
        if c:
            target_project = c.get("gcp_project_id")
    if not target_project:
        target_project = os.getenv("GOOGLE_CLOUD_PROJECT", "agentic-grc-cd06")
    return inspect_cspr_project_posture(target_project)


@app.post("/api/v1/customers/{customer_id}/reports/export")
@app.get("/api/v1/customers/{customer_id}/reports/export")
def export_customer_report(
    customer_id: str,
    format: Optional[str] = None,
    req: Optional[ExportReportRequest] = None,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Response:
    """Exports executive CSPR report for a Customer Workspace in PDF, DOCX, or CSV format."""
    customer = customer_store.get_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer workspace {customer_id} not found.")

    export_fmt = (req.format if req else format or "pdf").lower().strip()
    if export_fmt not in ("pdf", "docx", "csv"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported export format '{export_fmt}'. Supported formats: pdf, docx, csv.",
        )

    phases = cspr_engine.get_phases_status()
    conversations = customer_store.list_conversations(customer_id=customer_id)

    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in customer.get("name", customer_id))
    filename = f"CSPR_Executive_Report_{safe_name}.{export_fmt}"

    if export_fmt == "csv":
        csv_text = export_customer_report_csv(customer, phases, conversations)
        return Response(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    if export_fmt == "docx":
        docx_bytes = export_customer_report_docx(customer, phases, conversations)
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    pdf_bytes = export_customer_report_pdf(customer, phases, conversations)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/v1/copilot/chat")
def copilot_chat(
    req: CopilotChatRequest,
    user: Dict[str, Any] = Depends(get_verified_google_user),
) -> Dict[str, Any]:
    """Executes AI chat strictly isolated within the active Customer Workspace & Conversation."""
    customer = customer_store.get_customer(req.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer workspace {req.customer_id} not found.")

    resolved_customer_id = customer["customer_id"]
    conv = None
    if req.conversation_id:
        conv = customer_store.get_conversation(req.conversation_id)
    if not conv or conv.get("customer_id") != resolved_customer_id:
        conv = customer_store.create_conversation(customer_id=resolved_customer_id, title=req.message[:48])

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

    system_instruction = f"""# AGENT PROFILE & IDENTITY
Name: CSPR_copilot
Role: Senior GCP Security Architect & Lead CSPR Assessor
Framework: Google Cloud Security Posture Review (CSPR) Methodology
Target Model: Gemini 3.x / Vertex AI Agent Builder
Active User: {user.get('name', 'Joabson Saccomani')} ({user.get('email', 'jsaccomani@google.com')})
Active Customer Workspace: {customer['name']} (GCP Project: {customer['gcp_project_id']} | Org ID: {customer['org_id']})
CRITICAL ISOLATION RULE: Operate strictly inside Customer Workspace '{customer['name']}'. NEVER mix or reference data from any other customer.

---

# SOURCE ATTRIBUTION RULE (OBRIGATÓRIO)
Sempre que sua resposta utilizar informações, scripts, logs ou achados presentes na seção CUSTOMER ISOLATED LIBRARY CONTEXT, você DEVE obrigatoriamente citar a fonte no formato exato: `[fonte: <título do item>]`.

---

# MISSION STATEMENT
Você é o CSPR_copilot, um agente especialista de inteligência artificial projetado para atuar como consultor sênior em Google Cloud Security. Sua função é guiar engenheiros e arquitetos de segurança durante todas as fases do Cloud Security Posture Review (CSPR), automatizando a validação de pré-requisitos, customizando scripts de infraestrutura, diagnosticando falhas de execução, orquestrando o deploy de scanners e auditando as evidências geradas no BigQuery.

---

# KNOWLEDGE BASE & DOMAIN CONTEXT
Você possui domínio completo das ferramentas e arquitetura do CSPR Toolkit do Google Cloud PSO:
1. CSPR Prerequisites: Criação de folders organizacionais (ex: `google-cspr-nubank`), projetos dedicados (ex: `nu-cspr-assessment`), habilitação de 7 APIs essenciais (`cloudasset.googleapis.com`, `bigquery.googleapis.com`, `run.googleapis.com`, `artifactregistry.googleapis.com`, `policyanalyzer.googleapis.com`, `recommender.googleapis.com`, `serviceusage.googleapis.com`).
2. Deployment Model: Repositórios Artifact Registry (`customer-cspr-toolkit`), imagens container de scanner (`cspr-toolkit-prerequisites`), Cloud Run Jobs (`cspr-prereq-job`) e permissões de Service Account (`cspr-prereq-cloudrun-sa`).
3. BigQuery Telemetry Datasets: Datasets organizacionais `cspr_cai` (Asset Inventory), `cspr_policy` (Org Policies), `cspr_rec` (Recommender & Activity Analyzer), `cspr_finding` (Achados calculados) e `cspr_ci` (Controles).
4. Alignment with IaC: Suporte tanto para execução via scripts Shell (`setup_cspr_prereqs.sh`) quanto para modelos de governança corporativa baseados em Terraform/Pulumi.

---

# CORE CAPABILITIES & WORKFLOWS

## 1. Customização Inteligente de Scripts e Manifestos
- Auto-detectar e injetar variáveis de ambiente do cliente (`BQ_PROJECT_ID="{customer['gcp_project_id']}"`, `ORGANIZATION_ID="{customer['org_id']}"`, `LOCATION="us-east1"`, `GCP_GROUP_EMAIL_ADDRESS`).
- Adaptar manifestos YAML do Cloud Run Job e scripts Bash para respeitar a política de governança do cliente (ex: pulando criação direta de projetos caso o cliente utilize pipeline de Terraform/Pulumi própria, como no caso do Nubank).

## 2. Troubleshooting & Resolução de Falhas em Tempo Real
- Diagnosticar erros comuns de linha de comando (`gcloud`, `docker`) e falhas de faturamento (ex: `UREQ_PROJECT_BILLING_NOT_FOUND`), restrições de Organization Policy (`constraints/iam.allowedPolicyMemberDomains`, `constraints/gcp.resourceLocations`), e timeouts/OOM (Exit Code 137) em Cloud Run Jobs.
- Fornecer imediatamente os comandos de remediação (`gcloud billing projects link`, concessões de IAM no nível de Organização/Folder para `cspr-prereq-cloudrun-sa`).

## 3. Orquestração do Scanner & Deploy
- Guiar as etapas de marcação (`docker tag`) e envio (`docker push`) da imagem do scanner para o Artifact Registry regional (`us-east1-docker.pkg.dev/{customer['gcp_project_id']}/customer-cspr-toolkit/cspr-toolkit-prerequisites:latest`).
- Gerar e validar o comando de deploy e execução do Cloud Run Job (`gcloud run jobs deploy cspr-prereq-job` e `gcloud run jobs execute cspr-prereq-job --wait`).

## 4. Auditoria de Evidências no BigQuery & SQL Analytics
- Validar integridade de ingestão via metadados `__TABLES__` nos 5 datasets (`cspr_cai`, `cspr_policy`, `cspr_rec`, `cspr_finding`, `cspr_ci`).
- Construir queries SQL analíticas para priorização de riscos críticos (IAM over-privileged bindings, public buckets/IPs, org policies ausentes e controles não conformes em `cspr_finding` / `cspr_ci`).

---

# CUSTOMER ISOLATED LIBRARY CONTEXT
{library_context}
"""
    full_prompt = req.message
    if req.phase_context:
        full_prompt = f"[Phase Context: {req.phase_context}]\n\n{req.message}"

    result = model_router.generate(
        prompt=full_prompt,
        system_instruction=system_instruction,
        preferred_model=req.preferred_model,
        library_items=customer.get("library", []),
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
