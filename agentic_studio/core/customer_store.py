"""Multi-Customer Workspace & Isolated Library Store for CSPR Copilot Studio."""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class CustomerStore:
    """Manages strictly isolated Customer workspaces, Libraries, and Conversations."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        base_dir = Path(os.getenv("CSPR_DATA_DIR", "/tmp/cspr_copilot_data"))
        base_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path: Path = storage_path or (base_dir / "customer_workspaces.json")
        self._data: Dict[str, Any] = {
            "customers": {},
            "conversations": {},
        }
        self._load()
        self._ensure_default_workspace()

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                self._data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {"customers": {}, "conversations": {}}

    def _save(self) -> None:
        try:
            self.storage_path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _ensure_default_workspace(self) -> None:
        if not self._data["customers"]:
            cid = "cust-workspace-01"
            self._data["customers"][cid] = {
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
            conv_id = "conv-welcome-01"
            self._data["conversations"][conv_id] = {
                "conversation_id": conv_id,
                "customer_id": cid,
                "title": "Revisão Inicial de Postura GCP & Pré-requisitos",
                "updated_at": time.strftime("%Y-%m-%d %H:%M"),
                "messages": [
                    {
                        "role": "assistant",
                        "content": (
                            "Bem-vindo ao workspace isolado **GCP Security Assessment #01**.\n\n"
                            "Aqui a biblioteca de scripts, logs de Cloud Run Job e histórico de conversas ficam "
                            "100% isolados deste Customer. Como podemos iniciar a análise hoje?"
                        ),
                        "model_used": "gemini-3.8-flash",
                        "timestamp": time.strftime("%H:%M"),
                    }
                ],
            }
            self._save()

    def list_customers(self) -> List[Dict[str, Any]]:
        return list(self._data["customers"].values())

    def get_customer(self, customer_id: str) -> Optional[Dict[str, Any]]:
        return self._data["customers"].get(customer_id)

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
        return item

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
        return conv
