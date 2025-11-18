"""Helpers for GitHub App authentication (installation access tokens)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import time
from typing import Dict, Tuple

import httpx
from jose import jwt

from app.config import settings
from app.services.pipeline_exceptions import PipelineConfigurationError

_installation_tokens: Dict[str, Tuple[str, datetime]] = {}


def _load_private_key(raw: str) -> str:
    if "BEGIN PRIVATE KEY" in raw:
        return raw.replace("\\n", "\n")
    path = Path(raw.strip().strip('"'))
    if path.exists():
        return path.read_text()
    raise PipelineConfigurationError(
        "GITHUB_APP_PRIVATE_KEY must be a PEM string or path to a private key file",
    )


def _require_app_config() -> tuple[str, str]:
    app_id = settings.GITHUB_APP_ID
    private_key = settings.GITHUB_APP_PRIVATE_KEY
    if not app_id or not private_key:
        raise PipelineConfigurationError(
            "GitHub App credentials are not configured. "
            "Set GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY."
        )
    return app_id, private_key


def _generate_jwt(app_id: str, private_key: str) -> str:
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 600,
        "iss": app_id,
    }
    pem = _load_private_key(private_key)
    return jwt.encode(payload, pem, algorithm="RS256")


def _request_installation_token(
    jwt_token: str, installation_id: str
) -> tuple[str, datetime]:
    url = f"{settings.GITHUB_API_URL.rstrip('/')}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
    }
    response = httpx.post(url, headers=headers, timeout=15)
    response.raise_for_status()
    data = response.json()
    token = data.get("token")
    expires_at_raw = data.get("expires_at")
    expires_at = (
        datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
        if expires_at_raw
        else None
    )
    if not token or not expires_at:
        raise PipelineConfigurationError(
            "GitHub installation token response missing token or expires_at"
        )
    return token, expires_at


def get_installation_token(installation_id: str | None = None, db=None) -> str:
    if installation_id is None:
        raise PipelineConfigurationError(
            "Installation id is required to generate a GitHub App token"
        )

    # Check if installation is still active (not revoked/suspended)
    if db is not None:
        installation_doc = db.github_installations.find_one({"_id": installation_id})
        if installation_doc:
            if installation_doc.get("revoked_at") or installation_doc.get(
                "uninstalled_at"
            ):
                raise PipelineConfigurationError(
                    f"GitHub App installation {installation_id} has been uninstalled. "
                    "User needs to reinstall the app."
                )
            if installation_doc.get("suspended_at"):
                raise PipelineConfigurationError(
                    f"GitHub App installation {installation_id} is suspended."
                )

    app_id, private_key = _require_app_config()
    now = datetime.now(timezone.utc)
    cached = _installation_tokens.get(installation_id)
    if cached:
        token, expires_at = cached
        if now < (expires_at - timedelta(seconds=60)):
            return token

    jwt_token = _generate_jwt(app_id, private_key)
    token, expires_at = _request_installation_token(jwt_token, installation_id)
    _installation_tokens[installation_id] = (token, expires_at)
    return token


def clear_installation_token(installation_id: str) -> None:
    """Remove cached installation token when app is uninstalled or suspended."""
    if installation_id in _installation_tokens:
        del _installation_tokens[installation_id]


def github_app_configured() -> bool:
    return bool(settings.GITHUB_APP_ID and settings.GITHUB_APP_PRIVATE_KEY)
