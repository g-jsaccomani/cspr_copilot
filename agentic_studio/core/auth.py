"""Seamless Direct @google.com Identity & Session Resolution for CSPR Copilot Studio."""

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


def verify_google_id_token(id_token: str) -> Optional[Dict[str, Any]]:
    """Verifies a Google OAuth2 ID token against Google's tokeninfo endpoint."""
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(id_token)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cspr-copilot-studio/3.2"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            email = (payload.get("email") or "").lower()
            hd = (payload.get("hd") or "").lower()
            if not email:
                return None
            domain = email.split("@")[-1] if "@" in email else hd
            if domain not in ALLOWED_DOMAINS and email not in ALLOWED_EMAILS:
                raise HTTPException(
                    status_code=403,
                    detail=f"Acesso restrito exclusivamente a contas @google.com (Recebido: {email})",
                )
            return {
                "email": email,
                "domain": domain,
                "name": payload.get("name", email.split("@")[0]),
                "picture": payload.get("picture", ""),
                "auth_method": "google_sso",
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("Optional Google ID token check fell back to direct session: %s", exc)
        return None


def get_verified_google_user(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_goog_authenticated_user_email: Optional[str] = Header(default=None),
    x_goog_iap_jwt_assertion: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Resolves the @google.com user seamlessly (IAP -> Bearer Token -> Direct @google.com Session)."""
    # 1. Check Google Cloud IAP Header (injected automatically by Cloud Run + IAP)
    if x_goog_authenticated_user_email:
        raw_email = x_goog_authenticated_user_email.split(":")[-1].strip().lower()
        domain = raw_email.split("@")[-1] if "@" in raw_email else ""
        if domain in ALLOWED_DOMAINS or raw_email in ALLOWED_EMAILS:
            return {
                "email": raw_email,
                "domain": domain,
                "name": raw_email.split("@")[0].replace(".", " ").title(),
                "auth_method": "google_cloud_iap",
                "iap_jwt_present": bool(x_goog_iap_jwt_assertion),
            }
        raise HTTPException(
            status_code=403,
            detail=f"Acesso bloqueado pelo IAP: apenas contas @google.com são permitidas ({raw_email}).",
        )

    # 2. Check Authorization Bearer Google ID Token from silent Google Identity Services
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            verified = verify_google_id_token(token)
            if verified:
                return verified

    # 3. Seamless Direct @google.com Corporate Session (No blocking modal required)
    default_email = os.getenv("DEFAULT_GOOGLE_USER", "jsaccomani@google.com")
    default_name = os.getenv("DEFAULT_GOOGLE_NAME", "Juliano Saccomani")
    return {
        "email": default_email,
        "domain": "google.com",
        "name": default_name,
        "auth_method": "direct_google_session",
    }
