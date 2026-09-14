"""Zero-Trust Google Identity & @google.com Domain Enforcement for CSPR Copilot Studio."""

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from fastapi import Header, HTTPException, Request

logger = logging.getLogger("cspr_copilot.auth")

ALLOWED_DOMAINS: List[str] = [
    d.strip().lower()
    for d in os.getenv("ALLOWED_DOMAINS", "google.com,jsaccomani.altostrat.com").split(",")
    if d.strip()
]

ALLOWED_EMAILS: List[str] = [
    e.strip().lower()
    for e in os.getenv(
        "ALLOWED_EMAILS",
        "jsaccomani@google.com,admin@jsaccomani.altostrat.com",
    ).split(",")
    if e.strip()
]

# Allows local development on 127.0.0.1/localhost while strictly enforcing @google.com on Cloud Run
ALLOW_LOCAL_DEV: bool = os.getenv("ALLOW_LOCAL_DEV", "true").lower() == "true"


def verify_google_id_token(id_token: str) -> Dict[str, Any]:
    """Verifies a Google OAuth2 ID token against Google's tokeninfo endpoint."""
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(id_token)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cspr-copilot-studio/3.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            email = (payload.get("email") or "").lower()
            hd = (payload.get("hd") or "").lower()
            if not email:
                raise HTTPException(status_code=401, detail="Invalid Google ID Token: missing email claim.")
            domain = email.split("@")[-1] if "@" in email else hd
            if domain not in ALLOWED_DOMAINS and email not in ALLOWED_EMAILS:
                raise HTTPException(
                    status_code=403,
                    detail=f"Acesso restrito exclusivamente a contas @google.com (Recebido: {email})",
                )
            return {
                "email": email,
                "domain": domain,
                "name": payload.get("name", email),
                "picture": payload.get("picture", ""),
                "auth_method": "google_id_token",
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Failed to verify Google ID token: %s", exc)
        raise HTTPException(status_code=401, detail="Falha ao validar token Google OAuth2.") from exc


def get_verified_google_user(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_goog_authenticated_user_email: Optional[str] = Header(default=None),
    x_goog_iap_jwt_assertion: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Enforces that the caller is authenticated with a @google.com identity via IAP or OAuth2."""
    # 1. Check Google Cloud IAP Header (injected automatically by Cloud Run + IAP)
    if x_goog_authenticated_user_email:
        # Format: "accounts.google.com:jsaccomani@google.com"
        raw_email = x_goog_authenticated_user_email.split(":")[-1].strip().lower()
        domain = raw_email.split("@")[-1] if "@" in raw_email else ""
        if domain in ALLOWED_DOMAINS or raw_email in ALLOWED_EMAILS:
            return {
                "email": raw_email,
                "domain": domain,
                "name": raw_email.split("@")[0],
                "auth_method": "google_cloud_iap",
                "iap_jwt_present": bool(x_goog_iap_jwt_assertion),
            }
        raise HTTPException(
            status_code=403,
            detail=f"Acesso bloqueado pelo IAP: apenas contas @google.com são permitidas ({raw_email}).",
        )

    # 2. Check Authorization Bearer Google ID Token from Google Sign-In UI
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            return verify_google_id_token(token)

    # 3. Check custom session header X-Google-User-Token
    custom_token = request.headers.get("X-Google-ID-Token")
    if custom_token:
        return verify_google_id_token(custom_token)

    # 4. Localhost dev fallback (when running locally on 127.0.0.1 and not in Cloud Run K_SERVICE)
    is_cloud_run = bool(os.getenv("K_SERVICE"))
    client_host = request.client.host if request.client else ""
    if not is_cloud_run and ALLOW_LOCAL_DEV and client_host in ("127.0.0.1", "::1", "localhost", "testclient"):
        default_email = os.getenv("DEFAULT_GOOGLE_USER", "jsaccomani@google.com")
        return {
            "email": default_email,
            "domain": "google.com",
            "name": "Juliano Saccomani (@google.com Local Dev)",
            "auth_method": "local_workstation",
        }

    raise HTTPException(
        status_code=401,
        detail="Autenticação obrigatória com conta corporativa @google.com.",
    )
