"""Comprehensive Automated QA & Reliability Suite for CSPR Copilot & Agentic Studio.

Covers:
1. Customer Workspace Lifecycle & Multi-Conversation Isolation (Scenario 1)
2. Customer Library Ingestion & Source-Attributed Copilot Chat [fonte: <título>] (Scenario 2 & Task 2)
3. CSPR 6-Phase Catalog (`01, 01.1, 02, 03, 04, 05`) & Dry-Run Validation (Scenario 3)
4. User Session Preferences & Multi-Process Durability (Scenario 4)
5. Executive Report Export: PDF, DOCX (OOXML), and CSV Structured Findings (Task 1)
6. Multi-Instance Cloud Run (`K_SERVICE`) Storage Health Warning (Task 3)
7. ModelRouter Dependency Injection Seam & Optional Live Gemini Smoke Test (Task 4)
"""

import csv
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Ensure local isolated storage during test runs
os.environ.setdefault("FORCE_LOCAL_STORAGE", "true")
os.environ.setdefault("CSPR_TEST_FORCE_OFFLINE", "true")

from agentic_studio.api.server import app, customer_store, model_router
from agentic_studio.core.cspr_engine import CSPR_PHASES, CSPREngine
from agentic_studio.core.customer_store import CustomerStore, get_customer_store
from agentic_studio.core.model_router import ModelRouter


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Provides a FastAPI TestClient bound to an isolated temporary CustomerStore."""
    monkeypatch.setenv("FORCE_LOCAL_STORAGE", "true")
    monkeypatch.setenv("CSPR_TEST_FORCE_OFFLINE", "true")
    test_storage = tmp_path / "test_workspaces.json"
    isolated_store = CustomerStore(storage_path=test_storage)
    monkeypatch.setattr("agentic_studio.api.server.customer_store", isolated_store)
    monkeypatch.setattr("agentic_studio.core.customer_store._singleton_instance", isolated_store)
    return TestClient(app)


# ==============================================================================
# SCENARIO 1: Customer Workspace & Multi-Conversation Lifecycle (Tests 1 - 6)
# ==============================================================================


def test_01_healthz_endpoint_returns_healthy(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "cspr-copilot-studio"
    assert "storage_health" in data


def test_02_list_customers_returns_default_seed_workspace(client: TestClient) -> None:
    resp = client.get("/api/v1/customers")
    assert resp.status_code == 200
    customers = resp.json()
    assert isinstance(customers, list)
    assert len(customers) >= 1
    assert "customer_id" in customers[0]
    assert "name" in customers[0]


def test_03_create_customer_workspace(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/customers",
        json={
            "name": "Nubank Financial Posture",
            "gcp_project_id": "nu-cspr-assessment-01",
            "org_id": "112233445566",
            "description": "Revisão CSPR dedicada Nubank.",
        },
    )
    assert resp.status_code == 200
    cust = resp.json()
    assert cust["name"] == "Nubank Financial Posture"
    assert cust["gcp_project_id"] == "nu-cspr-assessment-01"
    assert cust["org_id"] == "112233445566"
    assert cust["library"] == []


def test_04_create_customer_rejects_empty_name(client: TestClient) -> None:
    resp = client.post("/api/v1/customers", json={"name": "   "})
    assert resp.status_code == 400


def test_05_create_and_list_conversations_filtered_by_customer(client: TestClient) -> None:
    cust_a = client.post("/api/v1/customers", json={"name": "Customer Alpha", "gcp_project_id": "alpha-01"}).json()
    cust_b = client.post("/api/v1/customers", json={"name": "Customer Beta", "gcp_project_id": "beta-01"}).json()

    conv_a1 = client.post(
        "/api/v1/conversations",
        json={"customer_id": cust_a["customer_id"], "title": "Alpha Thread 1"},
    ).json()
    conv_a2 = client.post(
        "/api/v1/conversations",
        json={"customer_id": cust_a["customer_id"], "title": "Alpha Thread 2"},
    ).json()
    conv_b1 = client.post(
        "/api/v1/conversations",
        json={"customer_id": cust_b["customer_id"], "title": "Beta Thread 1"},
    ).json()

    list_a = client.get("/api/v1/conversations", params={"customer_id": cust_a["customer_id"]}).json()
    list_b = client.get("/api/v1/conversations", params={"customer_id": cust_b["customer_id"]}).json()

    a_ids = {c["conversation_id"] for c in list_a}
    b_ids = {c["conversation_id"] for c in list_b}

    assert conv_a1["conversation_id"] in a_ids
    assert conv_a2["conversation_id"] in a_ids
    assert conv_b1["conversation_id"] not in a_ids
    assert conv_b1["conversation_id"] in b_ids


def test_06_create_conversation_for_nonexistent_customer_returns_404(client: TestClient) -> None:
    resp = client.post("/api/v1/conversations", json={"customer_id": "cust-does-not-exist", "title": "Invalid"})
    assert resp.status_code == 404


# ==============================================================================
# SCENARIO 2: Customer Library Ingestion & Context-Aware Copilot Chat (Tests 7 - 12)
# ==============================================================================


def test_07_add_library_item_to_customer(client: TestClient) -> None:
    cust = client.post("/api/v1/customers", json={"name": "Retail Corp", "gcp_project_id": "retail-cspr"}).json()
    resp = client.post(
        f"/api/v1/customers/{cust['customer_id']}/library",
        json={
            "title": "01_setup_cspr_prereqs.sh",
            "item_type": "script",
            "summary": "Habilita as 7 APIs do CSPR e cria Service Account cspr-prereq-cloudrun-sa.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["item"]["title"] == "01_setup_cspr_prereqs.sh"
    assert len(data["customer"]["library"]) == 1


def test_08_add_library_item_to_missing_customer_returns_404(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/customers/cust-unknown-999/library",
        json={"title": "doc.txt", "item_type": "document", "summary": "Sample"},
    )
    assert resp.status_code == 404


def test_09_copilot_chat_creates_conversation_and_returns_diagnostic(client: TestClient) -> None:
    cust = client.post("/api/v1/customers", json={"name": "Bank Corp", "gcp_project_id": "bank-cspr"}).json()
    resp = client.post(
        "/api/v1/copilot/chat",
        json={
            "customer_id": cust["customer_id"],
            "message": "Recebi o erro UREQ_PROJECT_BILLING_NOT_FOUND ao ativar APIs de billing",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "UREQ_PROJECT_BILLING_NOT_FOUND" in data["response"]
    assert "gcloud billing projects link" in data["response"]
    assert data["conversation"]["customer_id"] == cust["customer_id"]
    assert len(data["conversation"]["messages"]) == 2


def test_10_copilot_chat_cites_library_sources_with_fonte_tag(client: TestClient) -> None:
    """Verifies Task 2: Copilot responses cite customer library sources with [fonte: <título do item>]."""
    cust = client.post("/api/v1/customers", json={"name": "InsurTech LATAM", "gcp_project_id": "insur-cspr"}).json()
    client.post(
        f"/api/v1/customers/{cust['customer_id']}/library",
        json={
            "title": "iam_org_policy_audit_2026.log",
            "item_type": "log",
            "summary": "Violação constraints/iam.allowedPolicyMemberDomains na conta cspr-prereq-cloudrun-sa.",
        },
    )

    resp = client.post(
        "/api/v1/copilot/chat",
        json={
            "customer_id": cust["customer_id"],
            "message": "Como remediar o erro de IAM permission allowedPolicyMemberDomains encontrado no log?",
        },
    )
    assert resp.status_code == 200
    text = resp.json()["response"]
    assert "[fonte: iam_org_policy_audit_2026.log]" in text


def test_11_copilot_chat_strictly_isolates_customer_libraries(client: TestClient) -> None:
    cust_alpha = client.post("/api/v1/customers", json={"name": "Alpha Private", "gcp_project_id": "alpha-p"}).json()
    cust_beta = client.post("/api/v1/customers", json={"name": "Beta Public", "gcp_project_id": "beta-p"}).json()

    client.post(
        f"/api/v1/customers/{cust_alpha['customer_id']}/library",
        json={
            "title": "SECRET_ALPHA_CREDENTIALS_LOG.txt",
            "item_type": "log",
            "summary": "Confidential IAM bindings for Alpha.",
        },
    )

    # Chat under Beta should never cite Alpha's library file
    resp_beta = client.post(
        "/api/v1/copilot/chat",
        json={
            "customer_id": cust_beta["customer_id"],
            "message": "Quais as orientações para Terraform e Pulumi?",
        },
    )
    assert resp_beta.status_code == 200
    assert "SECRET_ALPHA_CREDENTIALS_LOG.txt" not in resp_beta.json()["response"]


def test_12_copilot_chat_with_missing_customer_returns_404(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/copilot/chat",
        json={"customer_id": "cust-nonexistent-00", "message": "Hello"},
    )
    assert resp.status_code == 404


# ==============================================================================
# SCENARIO 3: CSPR 6-Phase Catalog (`01, 01.1, 02, 03, 04, 05`) & Dry-Run (Tests 13 - 19)
# ==============================================================================


def test_13_status_endpoint_lists_all_six_official_phases(client: TestClient) -> None:
    resp = client.get("/api/v1/status")
    assert resp.status_code == 200
    data = resp.json()
    phases = data["phases"]
    assert len(phases) == 6
    codes = [p["code"] for p in phases]
    assert codes == ["01", "01.1", "02", "03", "04", "05"]


@pytest.mark.parametrize("phase_code", ["01", "01.1", "02", "03", "04", "05"])
def test_14_to_19_dry_run_all_six_phases_pass_bash_syntax_and_sha256(
    client: TestClient, phase_code: str
) -> None:
    resp = client.post(f"/api/v1/phases/{phase_code}/dry-run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["syntax_valid"] is True
    assert len(data["sha256"]) == 12
    assert data["lines"] > 0


# ==============================================================================
# SCENARIO 4: User Preferences, Auth & Multi-Process Durability (Tests 20 - 24)
# ==============================================================================


def test_20_auth_me_returns_verified_google_user(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert data["user"]["email"].endswith("@google.com")


def test_21_update_and_read_back_user_preferences(client: TestClient) -> None:
    cust = client.post("/api/v1/customers", json={"name": "Pref Customer", "gcp_project_id": "pref-proj"}).json()
    resp = client.post(
        "/api/v1/user/preferences",
        json={
            "active_customer_id": cust["customer_id"],
            "preferred_model": "gemini-3.1-pro-preview",
            "name": "Joabson Saccomani (PSO)",
        },
    )
    assert resp.status_code == 200
    saved = resp.json()["session"]
    assert saved["active_customer_id"] == cust["customer_id"]
    assert saved["preferred_model"] == "gemini-3.1-pro-preview"


def test_22_switch_active_gemini_model(client: TestClient) -> None:
    resp = client.post("/api/v1/models/select", json={"model_id": "gemini-3.7-flash"})
    assert resp.status_code == 200
    assert resp.json()["active_model"] == "gemini-3.7-flash"


def test_23_sync_upstream_scripts_endpoint(client: TestClient) -> None:
    resp = client.post("/api/v1/sync-upstream")
    assert resp.status_code == 200
    data = resp.json()
    assert "sync_result" in data
    assert len(data["phases"]) == 6


def test_24_persistence_survives_simulated_process_restart(tmp_path: Path) -> None:
    storage_file = tmp_path / "persistent_workspaces.json"
    store1 = CustomerStore(storage_path=storage_file)
    created = store1.create_customer(
        name="Durable FinTech",
        gcp_project_id="durable-fintech-prod",
        org_id="998877665544",
    )
    store1.add_library_item(
        customer_id=created["customer_id"],
        title="05_generate_findings.sh",
        item_type="script",
        content_or_summary="Gera achados em cspr_finding",
    )

    # Instantiate a second store pointing to the same file (simulating container restart)
    store2 = CustomerStore(storage_path=storage_file)
    reloaded = store2.get_customer(created["customer_id"])
    assert reloaded is not None
    assert reloaded["name"] == "Durable FinTech"
    assert len(reloaded["library"]) == 1
    assert reloaded["library"][0]["title"] == "05_generate_findings.sh"


# ==============================================================================
# TASK 1: Executive Report Export (PDF / DOCX / CSV) (Tests 25 - 28)
# ==============================================================================


def test_25_export_customer_report_pdf(client: TestClient) -> None:
    cust = client.post("/api/v1/customers", json={"name": "Acme Cloud PDF", "gcp_project_id": "acme-pdf-01"}).json()
    client.post(
        f"/api/v1/customers/{cust['customer_id']}/library",
        json={
            "title": "04_validate_bigquery.sh",
            "item_type": "script",
            "summary": "Valida ingestão nos 5 datasets BigQuery do CSPR.",
        },
    )

    resp = client.post(
        f"/api/v1/customers/{cust['customer_id']}/reports/export",
        json={"format": "pdf"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "CSPR_Executive_Report_" in resp.headers.get("content-disposition", "")
    assert resp.content.startswith(b"%PDF-1.")


def test_26_export_customer_report_docx_matches_runbook_structure(client: TestClient) -> None:
    from docx import Document

    cust = client.post("/api/v1/customers", json={"name": "Acme Cloud DOCX", "gcp_project_id": "acme-docx-01"}).json()
    client.post(
        f"/api/v1/customers/{cust['customer_id']}/library",
        json={
            "title": "cspr_finding_high_risk.json",
            "item_type": "finding",
            "summary": "Achados críticos de IAM e Cloud Storage.",
        },
    )

    resp = client.post(
        f"/api/v1/customers/{cust['customer_id']}/reports/export",
        json={"format": "docx"},
    )
    assert resp.status_code == 200
    assert "officedocument.wordprocessingml.document" in resp.headers["content-type"]
    # Validate OOXML ZIP signature
    assert resp.content.startswith(b"PK\x03\x04")

    doc = Document(io.BytesIO(resp.content))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Google Cloud PSO — Cloud Security Posture Review (CSPR)" in full_text
    assert "Acme Cloud DOCX" in full_text
    assert "[fonte: cspr_finding_high_risk.json]" in full_text


def test_27_export_customer_report_csv_exports_structured_findings(client: TestClient) -> None:
    cust = client.post("/api/v1/customers", json={"name": "Acme Cloud CSV", "gcp_project_id": "acme-csv-01"}).json()
    structured_findings = json.dumps(
        [
            {
                "finding_id": "CSPR-CUSTOM-777",
                "dataset": "cspr_finding",
                "control_id": "cspr_ci.iam_no_public_buckets",
                "severity": "CRITICAL",
                "category": "Storage Public Exposure",
                "resource": "gs://acme-public-bucket",
                "status": "NON_COMPLIANT",
                "remediation": "Remove allUsers from bucket IAM policy immediately.",
            }
        ]
    )
    client.post(
        f"/api/v1/customers/{cust['customer_id']}/library",
        json={
            "title": "custom_findings.json",
            "item_type": "finding",
            "summary": structured_findings,
        },
    )

    resp = client.post(
        f"/api/v1/customers/{cust['customer_id']}/reports/export",
        json={"format": "csv"},
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]

    reader = list(csv.DictReader(io.StringIO(resp.text)))
    finding_ids = {r["finding_id"] for r in reader}
    assert "CSPR-CUSTOM-777" in finding_ids
    custom_row = next(r for r in reader if r["finding_id"] == "CSPR-CUSTOM-777")
    assert custom_row["severity"] == "CRITICAL"
    assert custom_row["dataset"] == "cspr_finding"
    assert custom_row["source"] == "custom_findings.json"


def test_28_export_customer_report_invalid_format_returns_400(client: TestClient) -> None:
    cust = client.post("/api/v1/customers", json={"name": "Invalid Format Cust"}).json()
    resp = client.post(
        f"/api/v1/customers/{cust['customer_id']}/reports/export",
        json={"format": "xlsx"},
    )
    assert resp.status_code == 400


# ==============================================================================
# TASK 3: Multi-Instance Cloud Run Storage Health Warning (Test 29)
# ==============================================================================


def test_29_multi_instance_cloud_run_storage_health_alerts_without_firestore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Alerts when K_SERVICE is set (Cloud Run) without Firestore initialized."""
    monkeypatch.setenv("K_SERVICE", "cspr-copilot-cloud-run")
    monkeypatch.setenv("FORCE_LOCAL_STORAGE", "false")
    monkeypatch.setattr("agentic_studio.core.customer_store.get_firestore_client", lambda: None)

    store = CustomerStore(storage_path=tmp_path / "cloudrun_ephemeral.json")
    health = store.get_storage_health()
    assert health["cloud_run_detected"] is True
    assert health["firestore_connected"] is False
    assert health["multi_instance_safe"] is False
    assert health["status"] == "degraded"
    assert "K_SERVICE is set" in health["warning"]


# ==============================================================================
# TASK 4: ModelRouter Dependency Injection Seam & Live Gemini Smoke Test (Tests 30 - 31)
# ==============================================================================


def test_30_model_router_dependency_injection_seam_invokes_sdk_and_appends_source_citation() -> None:
    """Verifies ModelRouter DI seam invokes real SDK path when a client is injected and appends [fonte: <title>]."""
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.text = "Para resolver a falha de billing, vincule a conta de faturamento com gcloud billing projects link."
    fake_client.models.generate_content.return_value = fake_response

    router = ModelRouter(client=fake_client, force_offline=False)
    result = router.generate(
        prompt="Analise o erro de billing no script de pré-requisitos",
        system_instruction="# CUSTOMER ISOLATED LIBRARY CONTEXT\n- [SCRIPT] 01_setup_cspr_prereqs.sh: Configura APIs e billing.",
        preferred_model="gemini-3.8-flash",
    )

    assert result["status"] == "ok"
    assert result["model_used"] == "gemini-3.8-flash"
    assert fake_client.models.generate_content.called
    assert "[fonte: 01_setup_cspr_prereqs.sh]" in result["response"]


def test_31_real_gemini_smoke_when_adc_available() -> None:
    """Optional smoke test against live Vertex AI Gemini API when ADC is present and offline mode is not forced."""
    if os.getenv("CSPR_TEST_FORCE_OFFLINE", "true").lower() in ("true", "1", "yes"):
        pytest.skip("Skipping live Gemini smoke test because CSPR_TEST_FORCE_OFFLINE=true (default CI mode).")

    router = ModelRouter(force_offline=False)
    if router._client is None:
        pytest.skip("Skipping live Gemini smoke test because Google Cloud ADC credentials are not active.")

    res = router.generate(
        prompt="Em uma frase curta, qual é o objetivo do dataset cspr_finding no BigQuery?",
        system_instruction="Você é o CSPR_copilot.",
        preferred_model="gemini-3.8-flash",
    )
    assert res["status"] in ("ok", "domain_fallback")
    assert len(res["response"]) > 10


# ==============================================================================
# SCENARIO 5: Customer Workspace Deletion & Cascade (Patch v3.3.1)
# ==============================================================================


class TestScenario5CustomerDeletion:
    """Verifies DELETE /api/v1/customers/{customer_id} cascade deletion and auto-reseed."""

    def test_delete_customer_cascades_conversations(self, client: TestClient) -> None:
        cust = client.post(
            "/api/v1/customers",
            json={"name": "Ephemeral Client", "gcp_project_id": "ephem-01"},
        ).json()
        cid = cust["customer_id"]

        conv1 = client.post(
            "/api/v1/conversations",
            json={"customer_id": cid, "title": "Conv 1"},
        ).json()
        conv2 = client.post(
            "/api/v1/conversations",
            json={"customer_id": cid, "title": "Conv 2"},
        ).json()

        resp = client.delete(f"/api/v1/customers/{cid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        assert data["deleted_customer_id"] == cid
        assert set(data["deleted_conversation_ids"]) == {conv1["conversation_id"], conv2["conversation_id"]}

        remaining_convs = client.get("/api/v1/conversations", params={"customer_id": cid}).json()
        assert remaining_convs == []

    def test_delete_unknown_customer_returns_404(self, client: TestClient) -> None:
        resp = client.delete("/api/v1/customers/cust-does-not-exist-404")
        assert resp.status_code == 404

    def test_deleting_last_customer_reseeds_default_workspace(self, client: TestClient) -> None:
        all_customers = client.get("/api/v1/customers").json()
        # Delete all existing customers except the last one
        for c in all_customers[:-1]:
            client.delete(f"/api/v1/customers/{c['customer_id']}")

        last_customer_id = all_customers[-1]["customer_id"]
        resp = client.delete(f"/api/v1/customers/{last_customer_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recreated_default_workspace"] is True
        assert len(data["customers"]) >= 1
        assert data["customers"][0]["customer_id"] == "cust-workspace-01"

    def test_auth_rejects_unauthorized_domain_with_403(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/auth/me",
            headers={"X-Goog-Authenticated-User-Email": "accounts.google.com:attacker@evil-domain.com"},
        )
        assert resp.status_code == 403
        assert "Acesso bloqueado" in resp.json()["detail"]

    def test_update_user_preferences_saves_custom_google_oauth_client_id(self, client: TestClient) -> None:
        custom_client_id = "1234567890-customclientid.apps.googleusercontent.com"
        resp = client.post(
            "/api/v1/user/preferences",
            json={"google_oauth_client_id": custom_client_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["google_oauth_client_id"] == custom_client_id

        me_resp = client.get("/api/v1/auth/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["google_oauth_client_id"] == custom_client_id


# ==============================================================================
# PATCH v3.3.3 REGRESSION: Shared CustomerStore Singleton Across Auth & API (Test 32)
# ==============================================================================


def test_32_auth_session_hydration_shares_the_same_singleton_as_api_endpoints(
    client: TestClient,
) -> None:
    """Verifies Patch v3.3.3: get_verified_google_user() in auth.py shares the exact same
    CustomerStore singleton instance as API endpoints in server.py, preventing active_customer_id
    from reverting to 'cust-workspace-01' after selecting a new customer or deleting the default workspace.
    """
    import agentic_studio.api.server as srv

    assert get_customer_store() is srv.customer_store

    new_cust = client.post(
        "/api/v1/customers",
        json={
            "name": "Itaú Unibanco CSPR",
            "gcp_project_id": "itau-cspr-prod-01",
            "org_id": "554433221100",
        },
    ).json()
    new_cid = new_cust["customer_id"]

    # Select the newly created customer as active in user preferences
    pref_resp = client.post(
        "/api/v1/user/preferences",
        json={"active_customer_id": new_cid},
    )
    assert pref_resp.status_code == 200
    assert pref_resp.json()["session"]["active_customer_id"] == new_cid

    # Subsequent authenticated requests must hydrate the exact same active_customer_id (not 'cust-workspace-01')
    me_resp = client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["active_customer_id"] == new_cid

    # Even if 'cust-workspace-01' is deleted, active_customer_id remains the selected customer
    client.delete("/api/v1/customers/cust-workspace-01")
    status_resp = client.get("/api/v1/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["authenticated_user"]["active_customer_id"] == new_cid
    assert client.get("/api/v1/customers").json()[0]["customer_id"] == new_cid

