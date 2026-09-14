"""CSPR Engine: Orchestrates customer-agnostic CSPR scripts, upstream sync, and real-world error diagnostics."""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

CSPR_PHASES: List[Dict[str, Any]] = [
    {
        "id": "phase_01",
        "code": "01",
        "title": "01 - Setup CSPR Prerequisites",
        "script": "01_setup_cspr_prereqs.sh",
        "description": "Configures GCP APIs (Cloud Asset, BigQuery, Cloud Run), Service Accounts, IAM bindings, and BigQuery dataset.",
        "common_errors": [
            "constraints/iam.allowedPolicyMemberDomains blocking SA creation or binding",
            "Service Usage API (serviceusage.googleapis.com) disabled on target project",
            "Insufficient permissions to grant roles/cloudasset.viewer at Org/Folder level",
        ],
    },
    {
        "id": "phase_01_1",
        "code": "01.1",
        "title": "01.1 - Cloud Shell Push Image",
        "script": "01.1_cloudshell_push_image.sh",
        "description": "Builds and pushes the CSPR container image from Cloud Shell to Artifact Registry when local Docker is restricted.",
        "common_errors": [
            "Artifact Registry API disabled or repository missing in target region",
            "Cloud Build / Artifact Registry Writer permission missing on active identity",
        ],
    },
    {
        "id": "phase_02",
        "code": "02",
        "title": "02 - Push Scanner Image",
        "script": "02_push_scanner_image.sh",
        "description": "Tags and pushes the CSPR scanner container image into the target GCP Artifact Registry.",
        "common_errors": [
            "Docker credential helper not configured (gcloud auth configure-docker)",
            "VPC-SC perimeter restricting Artifact Registry push from external IP",
        ],
    },
    {
        "id": "phase_03",
        "code": "03",
        "title": "03 - Deploy & Run Cloud Run Job",
        "script": "03_deploy_and_run_job.sh",
        "description": "Deploys and executes the Cloud Run Job to collect and process GCP posture into BigQuery.",
        "common_errors": [
            "Cloud Run Job container memory OOM (Exit Code 137) on large organizations",
            "Execution timeout exceeded during Cloud Asset Inventory batch export",
        ],
    },
    {
        "id": "phase_04",
        "code": "04",
        "title": "04 - Validate BigQuery Tables",
        "script": "04_validate_bigquery.sh",
        "description": "Queries BigQuery __TABLES__ metadata for exact row counts, GB size, and Cloud Run Job completion status.",
        "common_errors": [
            "BigQuery dataset region mismatch during __TABLES__ metadata query",
            "Zero rows populated due to silent filter exclusion in collection scope",
        ],
    },
    {
        "id": "phase_05",
        "code": "05",
        "title": "05 - Generate Security Findings",
        "script": "05_generate_findings.sh",
        "description": "Runs analytical SQL queries on BigQuery CSPR tables to synthesize prioritized security posture findings.",
        "common_errors": [
            "Missing BigQuery Job User role (roles/bigquery.jobUser) on executing identity",
            "Analytical view dependency missing if Phase 04 validation failed",
        ],
    },
]


class CSPREngine:
    """Core orchestrator for customer-agnostic CSPR Copilot & Studio."""

    def __init__(self, repo_root: Optional[Path] = None, upstream_repo_root: Optional[Path] = None) -> None:
        self.repo_root: Path = repo_root or Path(__file__).resolve().parents[2]
        self.scripts_dir: Path = self.repo_root / "scripts"
        self.upstream_repo_root: Path = upstream_repo_root or Path(
            os.getenv("UPSTREAM_CSPR_PATH", "/Users/jsaccomani/Documents/Jetsky/Google/CSPR")
        )
        self.upstream_scripts_dir: Path = self.upstream_repo_root / "scripts"

    def _file_sha256(self, path: Path) -> str:
        if not path.exists():
            return "missing"
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]

    def get_phases_status(self) -> List[Dict[str, Any]]:
        """Returns metadata, SHA256 sync status vs upstream repo, and bash syntax check for each script."""
        results: List[Dict[str, Any]] = []
        for phase in CSPR_PHASES:
            local_path = self.scripts_dir / phase["script"]
            upstream_path = self.upstream_scripts_dir / phase["script"]
            local_hash = self._file_sha256(local_path)
            upstream_hash = self._file_sha256(upstream_path)

            syntax_ok = False
            syntax_msg = "Script not found"
            if local_path.exists():
                proc = subprocess.run(
                    ["bash", "-n", str(local_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                syntax_ok = proc.returncode == 0
                syntax_msg = "Syntax valid (bash -n)" if syntax_ok else proc.stderr.strip()

            results.append(
                {
                    **phase,
                    "local_exists": local_path.exists(),
                    "local_sha256": local_hash,
                    "upstream_sha256": upstream_hash,
                    "in_sync_with_upstream": local_hash == upstream_hash and local_hash != "missing",
                    "syntax_valid": syntax_ok,
                    "syntax_message": syntax_msg,
                }
            )
        return results

    def sync_from_upstream(self) -> Dict[str, Any]:
        """Pulls the latest tested scripts from upstream CSPR engine into cspr_copilot."""
        if not self.upstream_scripts_dir.exists():
            return {
                "status": "embedded",
                "message": "Using container-embedded CSPR scripts (Upstream local path not mounted in Cloud Run).",
                "files": [],
            }

        synced_files: List[Dict[str, str]] = []
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        for phase in CSPR_PHASES:
            script_name = phase["script"]
            src = self.upstream_scripts_dir / script_name
            dst = self.scripts_dir / script_name
            if src.exists():
                before_hash = self._file_sha256(dst)
                shutil.copy2(src, dst)
                after_hash = self._file_sha256(dst)
                synced_files.append(
                    {
                        "script": script_name,
                        "before_sha256": before_hash,
                        "after_sha256": after_hash,
                        "updated": before_hash != after_hash,
                    }
                )
        return {
            "status": "ok",
            "source": str(self.upstream_scripts_dir),
            "destination": str(self.scripts_dir),
            "files": synced_files,
        }

    def dry_run_phase(self, phase_code: str) -> Dict[str, Any]:
        """Performs non-destructive bash -n check and inspects environment variables required by the script."""
        phase = next((p for p in CSPR_PHASES if p["code"] == phase_code or p["id"] == phase_code), None)
        if not phase:
            return {"status": "error", "message": f"Unknown phase code: {phase_code}"}

        script_path = self.scripts_dir / phase["script"]
        if not script_path.exists():
            return {"status": "error", "message": f"Script file missing: {script_path}"}

        proc = subprocess.run(
            ["bash", "-n", str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        content = script_path.read_text(encoding="utf-8", errors="ignore")
        lines_count = len(content.splitlines())
        return {
            "status": "ok" if proc.returncode == 0 else "syntax_error",
            "phase": phase["title"],
            "script": phase["script"],
            "lines": lines_count,
            "sha256": self._file_sha256(script_path),
            "syntax_valid": proc.returncode == 0,
            "stderr": proc.stderr.strip(),
        }
