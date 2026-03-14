"""
Workspace management routes.

POST /workspaces/configure-jira  — admin saves Jira credentials for their workspace
GET  /workspaces/me              — return the calling user's workspace info
"""

import os

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.dependencies import get_current_user
from db.models import User, Workspace
from db.session import get_db

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet:
    key = os.getenv("ENCRYPTION_KEY", "")
    if not key:
        raise HTTPException(status_code=500, detail="ENCRYPTION_KEY not set in environment")
    return Fernet(key.encode())


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class JiraConfigRequest(BaseModel):
    jira_base_url:    str
    jira_email:       str
    jira_api_token:   str
    jira_project_key: str


class WorkspaceInfoResponse(BaseModel):
    workspace_id:    str
    workspace_name:  str
    jira_configured: bool
    jira_base_url:   str | None
    jira_project_key: str | None
    your_role:       str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/configure-jira", status_code=200)
def configure_jira(
    payload: JiraConfigRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Save (or update) the Jira credentials for the current user's workspace.
    Only workspace admins may call this endpoint.

    The API token is encrypted with Fernet before storage so it is never
    persisted in plain text.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only workspace admins can configure Jira credentials",
        )

    workspace: Workspace | None = (
        db.query(Workspace).filter(Workspace.id == current_user.workspace_id).first()
    )
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    fernet = _get_fernet()
    encrypted_token = fernet.encrypt(payload.jira_api_token.encode()).decode()

    workspace.jira_base_url    = payload.jira_base_url.rstrip("/")
    workspace.jira_email       = payload.jira_email
    workspace.jira_api_token   = encrypted_token
    workspace.jira_project_key = payload.jira_project_key.upper()
    db.commit()

    return {"status": "Jira configured successfully", "project_key": workspace.jira_project_key}


@router.get("/me", response_model=WorkspaceInfoResponse)
def get_my_workspace(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the current user's workspace details (no secrets exposed)."""
    workspace: Workspace | None = (
        db.query(Workspace).filter(Workspace.id == current_user.workspace_id).first()
    )
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return WorkspaceInfoResponse(
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        jira_configured=workspace.jira_api_token is not None,
        jira_base_url=workspace.jira_base_url,
        jira_project_key=workspace.jira_project_key,
        your_role=current_user.role,
    )
