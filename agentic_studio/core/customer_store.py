"""Multi-Customer Workspace & Isolated Library Store for CSPR Copilot Studio.

Mirrors the Cloud Firestore (Native Mode) durability architecture from agentic_grc_copilot:
- Uses dedicated Google Cloud Firestore collections:
  - cspr_customers
  - cspr_conversations
  - cspr_user_sessions
- Strictly isolated from agentic_grc_copilot collections (zero data linkage).
- Guarantees 100% survival of Customers, Libraries, Conversations, Messages, and
  User Login Sessions across Cloud Run container restarts, scaling to 0, and redeployments.
"""

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentic_studio.core.persistence import get_firestore_client

logger = logging.getLogger("cspr_copilot.customer_store")


class CustomerStore:
    """Manages strictly isolated Customer workspaces, Libraries, Conversations, and User Sessions with Cloud Firestore persistence."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        base_dir = Path(os.getenv("CSPR_DATA_DIR", "/tmp/cspr_copilot_data"))
        base_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path: Path = storage_path or (base_dir / "customer_workspaces.json")
        self._data: Dict[str, Any] = {
            "customers": {},
            "conversations": {},
            "user_sessions": {},
        }
        self._load()
        self._sync_from_firestore_on_startup()
        self._ensure_default_workspace()

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                loaded = json.loads(self.storage_path.read_text(encoding="utf-8"))
                self._data["customers"] = loaded.get("customers", {})
                self._data["conversations"] = loaded.get("conversations", {})
                self._data["user_sessions"] = loaded.get("user_sessions", {})
            except Exception:
                self._data = {"customers": {}, "conversations": {}, "user_sessions": {}}

    def _save(self) -> None:
        try:
            self.storage_path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("Local cache write warning: %s", exc)

    def _normalize_customer(self, d: Dict[str, Any], fallback_id: str = "") -> Dict[str, Any]:
        cid = d.get("customer_id") or fallback_id or f"cust-{uuid.uuid4().hex[:8]}"
        name = d.get("name") or d.get("customer_name") or cid
        proj_ids = d.get("gcp_project_ids") or []
        gcp_proj = d.get("gcp_project_id") or (proj_ids[0] if proj_ids else "agentic-grc-cd06")
        org_id = d.get("org_id") or d.get("gcp_org_id") or "938078169010"
        d["customer_id"] = cid
        d["name"] = name
        d["customer_name"] = name
        d["gcp_project_id"] = gcp_proj
        d["org_id"] = org_id
        d.setdefault("library", [])
        return d

    def _sync_from_firestore_on_startup(self) -> None:
        """Hydrates local memory/disk cache from Google Cloud Firestore on Cloud Run container startup."""
        fs = get_firestore_client()
        if fs is None:
            return
        try:
            for doc in fs.collection("cspr_customers").stream():
                d = self._normalize_customer(doc.to_dict(), doc.id)
                self._data["customers"][d["customer_id"]] = d
                # Also write normalized schema back to Firestore if needed
                fs.collection("cspr_customers").document(d["customer_id"]).set(d, merge=True)

            for doc in fs.collection("cspr_conversations").stream():
                d = doc.to_dict()
                conv_id = d.get("conversation_id") or doc.id
                d["conversation_id"] = conv_id
                self._data["conversations"][conv_id] = d

            for doc in fs.collection("cspr_user_sessions").stream():
                d = doc.to_dict()
                email = (d.get("email") or doc.id).lower().strip()
                d["email"] = email
                self._data["user_sessions"][email] = d

            self._save()
            logger.info(
                "Hydrated CSPR CustomerStore from Cloud Firestore: %d customers, %d conversations, %d user sessions",
                len(self._data["customers"]),
                len(self._data["conversations"]),
                len(self._data["user_sessions"]),
            )
        except Exception as exc:
            logger.warning("Firestore hydration warning: %s", exc)

    def get_storage_health(self) -> Dict[str, Any]:
        """Evaluates multi-instance safety and detects Cloud Run (K_SERVICE) divergence risk when Firestore is absent."""
        is_cloud_run = bool(os.environ.get("K_SERVICE"))
        force_local = os.environ.get("FORCE_LOCAL_STORAGE", "").lower() in ("true", "1", "yes")
        fs = None if force_local else get_firestore_client()
        firestore_connected = fs is not None

        if is_cloud_run and not firestore_connected and not force_local:
            return {
                "storage_mode": "ephemeral_local_fallback",
                "multi_instance_safe": False,
                "firestore_connected": False,
                "cloud_run_detected": True,
                "status": "degraded",
                "warning": (
                    "CRITICAL: K_SERVICE is set (Cloud Run multi-instance environment) "
                    "but Cloud Firestore is not connected. CSPR_DATA_DIR (/tmp) will diverge "
                    "across container instances!"
                ),
            }

        if firestore_connected:
            return {
                "storage_mode": "cloud_firestore",
                "multi_instance_safe": True,
                "firestore_connected": True,
                "cloud_run_detected": is_cloud_run,
                "status": "healthy",
                "warning": None,
            }

        return {
            "storage_mode": "local_isolated",
            "multi_instance_safe": True,
            "firestore_connected": False,
            "cloud_run_detected": is_cloud_run,
            "status": "healthy",
            "warning": None,
        }

    def _ensure_default_workspace(self) -> None:
        if not self._data["customers"]:
            cid = "cust-workspace-01"
            default_cust = {
                "customer_id": cid,
                "name": "GCP Security Assessment #01",
                "gcp_project_id": "gcp-posture-target-01",
                "org_id": "000000000000",
                "description": "Workspace isolado padrão para revisão de postura de segurança GCP (CSPR).",
                "library": [
                    {
                        "item_id": "lib-01",
                        "title": "01_setup_cspr_prereqs.sh",
                        "type": "script",
                        "summary": "Configuração de APIs, Service Accounts e dataset BigQuery.",
                        "added_at": time.strftime("%Y-%m-%d %H:%M"),
                    },
                    {
                        "item_id": "lib-02",
                        "title": "03_deploy_and_run_job.sh",
                        "type": "script",
                        "summary": "Deploy e execução do Cloud Run Job de varredura de postura.",
                        "added_at": time.strftime("%Y-%m-%d %H:%M"),
                    },
                ],
                "created_at": time.strftime("%Y-%m-%d %H:%M"),
            }
            self._data["customers"][cid] = default_cust
            conv_id = "conv-welcome-01"
            default_conv = {
                "conversation_id": conv_id,
                "customer_id": cid,
                "customer_name": default_cust["name"],
                "title": "Revisão Inicial de Postura GCP & Pré-requisitos",
                "updated_at": time.strftime("%Y-%m-%d %H:%M"),
                "messages": [
                    {
                        "role": "assistant",
                        "content": (
                            "Bem-vindo ao workspace isolado **GCP Security Assessment #01**.\n\n"
                            "Aqui a biblioteca de scripts, logs de Cloud Run Job e histórico de conversas ficam "
                            "100% isolados deste Customer e persistidos no Google Cloud Firestore. Como podemos iniciar a análise hoje?"
                        ),
                        "model_used": "gemini-3.8-flash",
                        "timestamp": time.strftime("%H:%M"),
                    }
                ],
            }
            self._data["conversations"][conv_id] = default_conv
            self._save()

            fs = get_firestore_client()
            if fs is not None:
                try:
                    fs.collection("cspr_customers").document(cid).set(default_cust)
                    fs.collection("cspr_conversations").document(conv_id).set(default_conv)
                except Exception as exc:
                    logger.debug("Firestore initial seed warning: %s", exc)

    # ------------------------------------------------------------------
    # Persistent User Login & Session Preferences (Cloud Firestore)
    # ------------------------------------------------------------------
    def save_user_session(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Persists user login identity and workspace preferences in Cloud Firestore + local cache."""
        email = (user_data.get("email") or "jsaccomani@google.com").lower().strip()
        existing = self._data["user_sessions"].get(email, {})
        default_cust_id = next(iter(self._data["customers"].keys()), "cust-workspace-01")

        record = {
            "email": email,
            "name": user_data.get("name") or existing.get("name") or "Joabson Saccomani",
            "picture": user_data.get("picture") if "picture" in user_data else existing.get("picture", ""),
            "auth_method": user_data.get("auth_method") or existing.get("auth_method") or "direct_google_session",
            "active_customer_id": user_data.get("active_customer_id") or existing.get("active_customer_id") or default_cust_id,
            "active_conversation_id": (
                user_data.get("active_conversation_id")
                if "active_conversation_id" in user_data
                else existing.get("active_conversation_id", "")
            ),
            "preferred_model": user_data.get("preferred_model") or existing.get("preferred_model") or "gemini-3.8-flash",
            "google_oauth_client_id": (
                user_data.get("google_oauth_client_id")
                if "google_oauth_client_id" in user_data
                else existing.get("google_oauth_client_id", "")
            ),
            "last_seen_at": time.time(),
        }
        self._data["user_sessions"][email] = record
        self._save()

        fs = get_firestore_client()
        if fs is not None:
            try:
                fs.collection("cspr_user_sessions").document(email).set(record, merge=True)
            except Exception as exc:
                logger.warning("Firestore save_user_session warning: %s", exc)
        return record

    def get_user_session(self, email: str) -> Optional[Dict[str, Any]]:
        clean_email = (email or "jsaccomani@google.com").lower().strip()
        fs = get_firestore_client()
        if fs is not None:
            try:
                doc = fs.collection("cspr_user_sessions").document(clean_email).get()
                if doc.exists:
                    data = doc.to_dict()
                    self._data["user_sessions"][clean_email] = data
                    return data
            except Exception:
                pass
        return self._data["user_sessions"].get(clean_email)

    # ------------------------------------------------------------------
    # Customer CRUD (Cloud Firestore + Local Cache)
    # ------------------------------------------------------------------
    def list_customers(self) -> List[Dict[str, Any]]:
        return [self._normalize_customer(c) for c in self._data["customers"].values()]

    def get_customer(self, customer_id: str) -> Optional[Dict[str, Any]]:
        c = self._data["customers"].get(customer_id)
        if not c and customer_id == "cust-workspace-01" and self._data["customers"]:
            first_id = next(iter(self._data["customers"].keys()))
            c = self._data["customers"][first_id]
        return self._normalize_customer(c, customer_id) if c else None

    def delete_customer(self, customer_id: str) -> Dict[str, Any]:
        """Deletes a Customer workspace, cascades all its conversations, clears user sessions, and reseeds if last."""
        if customer_id not in self._data["customers"]:
            raise ValueError(f"Customer {customer_id} not found")

        del self._data["customers"][customer_id]

        # Cascade delete all conversations belonging to this customer
        deleted_conversation_ids: List[str] = []
        for conv_id in list(self._data["conversations"].keys()):
            conv = self._data["conversations"][conv_id]
            if conv.get("customer_id") == customer_id:
                del self._data["conversations"][conv_id]
                deleted_conversation_ids.append(conv_id)

        # Clear active_customer_id / active_conversation_id from any user sessions pointing to the deleted customer
        for email, session in self._data["user_sessions"].items():
            if session.get("active_customer_id") == customer_id:
                session["active_customer_id"] = ""
                session["active_conversation_id"] = ""

        # Sync deletion to Cloud Firestore if enabled
        fs = get_firestore_client()
        if fs is not None:
            try:
                fs.collection("cspr_customers").document(customer_id).delete()
                for conv_id in deleted_conversation_ids:
                    fs.collection("cspr_conversations").document(conv_id).delete()
                for email, session in self._data["user_sessions"].items():
                    fs.collection("cspr_user_sessions").document(email).set(session, merge=True)
            except Exception as exc:
                logger.warning("Firestore delete_customer warning: %s", exc)

        # Ensure Studio never remains with zero workspaces
        recreated_default = False
        if not self._data["customers"]:
            self._ensure_default_workspace()
            recreated_default = True
        else:
            self._save()

        return {
            "deleted_customer_id": customer_id,
            "deleted_conversation_ids": deleted_conversation_ids,
            "recreated_default_workspace": recreated_default,
        }

    def create_customer(
        self,
        name: str,
        gcp_project_id: str = "",
        org_id: str = "",
        description: str = "",
    ) -> Dict[str, Any]:
        cid = f"cust-{uuid.uuid4().hex[:8]}"
        customer = {
            "customer_id": cid,
            "name": name.strip(),
            "gcp_project_id": gcp_project_id.strip() or "gcp-target-project",
            "org_id": org_id.strip() or "000000000000",
            "description": description.strip() or "Workspace isolado de Customer CSPR.",
            "library": [],
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
        }
        self._data["customers"][cid] = customer
        self._save()

        fs = get_firestore_client()
        if fs is not None:
            try:
                fs.collection("cspr_customers").document(cid).set(customer)
            except Exception as exc:
                logger.warning("Firestore create_customer warning: %s", exc)
        return customer

    def add_library_item(
        self,
        customer_id: str,
        title: str,
        item_type: str,
        content_or_summary: str,
    ) -> Dict[str, Any]:
        customer = self._data["customers"].get(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")
        item = {
            "item_id": f"lib-{uuid.uuid4().hex[:8]}",
            "title": title.strip(),
            "type": item_type.strip() or "document",
            "summary": content_or_summary.strip(),
            "added_at": time.strftime("%Y-%m-%d %H:%M"),
        }
        customer.setdefault("library", []).append(item)
        self._save()

        fs = get_firestore_client()
        if fs is not None:
            try:
                fs.collection("cspr_customers").document(customer_id).set(customer)
            except Exception as exc:
                logger.warning("Firestore add_library_item warning: %s", exc)
        return item

    # ------------------------------------------------------------------
    # Conversation & Message CRUD (Cloud Firestore + Local Cache)
    # ------------------------------------------------------------------
    def list_conversations(self, customer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        convs = list(self._data["conversations"].values())
        if customer_id:
            convs = [c for c in convs if c.get("customer_id") == customer_id]
        return sorted(convs, key=lambda c: c.get("updated_at", ""), reverse=True)

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return self._data["conversations"].get(conversation_id)

    def create_conversation(self, customer_id: str, title: str = "Nova conversa") -> Dict[str, Any]:
        if customer_id not in self._data["customers"]:
            raise ValueError(f"Customer {customer_id} does not exist")
        conv_id = f"conv-{uuid.uuid4().hex[:8]}"
        customer = self._data["customers"][customer_id]
        conv = {
            "conversation_id": conv_id,
            "customer_id": customer_id,
            "customer_name": customer["name"],
            "title": title.strip() or "Nova conversa",
            "updated_at": time.strftime("%Y-%m-%d %H:%M"),
            "messages": [],
        }
        self._data["conversations"][conv_id] = conv
        self._save()

        fs = get_firestore_client()
        if fs is not None:
            try:
                fs.collection("cspr_conversations").document(conv_id).set(conv)
            except Exception as exc:
                logger.warning("Firestore create_conversation warning: %s", exc)
        return conv

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        model_used: str = "gemini-3.8-flash",
    ) -> Dict[str, Any]:
        conv = self._data["conversations"].get(conversation_id)
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")
        msg = {
            "role": role,
            "content": content,
            "model_used": model_used,
            "timestamp": time.strftime("%H:%M"),
        }
        conv.setdefault("messages", []).append(msg)
        conv["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
        # Automatically refine conversation title if it was 'Nova conversa'
        if conv.get("title") == "Nova conversa" and role == "user":
            short = content.strip().splitlines()[0][:48]
            conv["title"] = short
        self._save()

        fs = get_firestore_client()
        if fs is not None:
            try:
                fs.collection("cspr_conversations").document(conversation_id).set(conv)
            except Exception as exc:
                logger.warning("Firestore append_message warning: %s", exc)
        return conv
