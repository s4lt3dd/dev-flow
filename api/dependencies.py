"""
Shared FastAPI dependencies.

  get_current_user   — validates an Auth0 JWT and returns the matching DB User
  get_jira_exporter  — builds a JiraExporter from the current user's workspace config
"""

import os
import sys
from functools import lru_cache
from pathlib import Path

import requests as _requests
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

# Allow src/ flat imports (mirrors api/main.py)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.models import User, Workspace
from db.session import get_db

security = HTTPBearer()

AUTH0_DOMAIN   = os.getenv("AUTH0_DOMAIN", "")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE", "")


# ---------------------------------------------------------------------------
# Auth0 JWKS helper
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _fetch_jwks() -> dict:
    """Fetch and cache Auth0's public key set (JWKS).  Cached for the process lifetime."""
    url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
    resp = _requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_public_key(token: str) -> dict:
    """Return the RS256 public key that matches the token's 'kid' header."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token header: {exc}")

    jwks = _fetch_jwks()
    for key in jwks.get("keys", []):
        if key.get("kid") == header.get("kid"):
            return key

    # Kid not found — JWKS may have rotated; bust cache and retry once
    _fetch_jwks.cache_clear()
    jwks = _fetch_jwks()
    for key in jwks.get("keys", []):
        if key.get("kid") == header.get("kid"):
            return key

    raise HTTPException(status_code=401, detail="Public key not found in JWKS")


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    token=Security(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Validate the Bearer JWT issued by Auth0 and return the corresponding User.

    Raises 401 if the token is invalid or the user has not yet called /auth/register.
    """
    if not AUTH0_DOMAIN or not AUTH0_AUDIENCE:
        raise HTTPException(
            status_code=500,
            detail="AUTH0_DOMAIN and AUTH0_AUDIENCE must be set in the environment",
        )

    public_key = _get_public_key(token.credentials)

    try:
        payload = jwt.decode(
            token.credentials,
            public_key,
            algorithms=["RS256"],
            audience=AUTH0_AUDIENCE,
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {exc}")

    auth0_id: str = payload.get("sub", "")
    if not auth0_id:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")

    user = db.query(User).filter(User.auth0_id == auth0_id).first()
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not registered — call POST /auth/register after first login",
        )
    return user


def get_jira_exporter(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Build a JiraExporter from the current user's workspace Jira credentials.

    Raises 400 if the workspace has not been configured yet.
    """
    from jira_exporter import JiraExporter  # src/ flat import

    workspace: Workspace | None = (
        db.query(Workspace).filter(Workspace.id == current_user.workspace_id).first()
    )
    if not workspace or not workspace.jira_api_token:
        raise HTTPException(
            status_code=400,
            detail="Workspace Jira credentials are not configured — call POST /workspaces/configure-jira",
        )

    encryption_key = os.getenv("ENCRYPTION_KEY", "")
    if not encryption_key:
        raise HTTPException(status_code=500, detail="ENCRYPTION_KEY not set in environment")

    fernet = Fernet(encryption_key.encode())
    decrypted_token = fernet.decrypt(workspace.jira_api_token.encode()).decode()

    return JiraExporter(
        base_url=workspace.jira_base_url,
        email=workspace.jira_email,
        api_token=decrypted_token,
        project_key=workspace.jira_project_key,
    )
