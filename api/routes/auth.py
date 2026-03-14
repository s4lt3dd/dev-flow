"""
POST /auth/register  — called once after a user's first Auth0 login.

The frontend exchanges the Auth0 token for a local User + Workspace record.
Subsequent logins skip this step; the user already exists.
"""

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.dependencies import _get_public_key, AUTH0_AUDIENCE
from db.models import User, Workspace
from db.session import get_db
from jose import JWTError, jwt

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()


@router.get("/config")
def get_auth_config():
    """
    Return public Auth0 configuration for the frontend SPA.
    Domain, client ID, and audience are not secret — they are embedded
    in every browser request anyway.
    """
    import os
    return {
        "domain":    os.getenv("AUTH0_DOMAIN", ""),
        "client_id": os.getenv("AUTH0_CLIENT_ID", ""),
        "audience":  os.getenv("AUTH0_AUDIENCE", ""),
    }


class RegisterRequest(BaseModel):
    email:          str
    display_name:   str
    workspace_name: str


class RegisterResponse(BaseModel):
    user_id:      str
    workspace_id: str
    message:      str


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(payload: RegisterRequest, token=Security(security), db: Session = Depends(get_db)):
    """
    Create a new User and a new Workspace for them.

    This is a one-time call made immediately after Auth0 returns a token for
    a brand-new user.  If the user already exists, a 400 is returned so the
    frontend can redirect to the normal login flow instead.

    The auth0_id is extracted from the Bearer JWT so it always matches what
    get_current_user will look for on subsequent requests.
    """
    public_key = _get_public_key(token.credentials)
    try:
        jwt_payload = jwt.decode(
            token.credentials,
            public_key,
            algorithms=["RS256"],
            audience=AUTH0_AUDIENCE,
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {exc}")

    auth0_id: str = jwt_payload.get("sub", "")
    if not auth0_id:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")

    if db.query(User).filter(User.auth0_id == auth0_id).first():
        raise HTTPException(status_code=400, detail="User already registered")

    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already in use")

    workspace = Workspace(name=payload.workspace_name)
    db.add(workspace)
    db.flush()  # populate workspace.id before creating the user

    user = User(
        auth0_id=auth0_id,
        email=str(payload.email),
        display_name=payload.display_name,
        role="admin",           # first user in a workspace is the admin
        workspace_id=workspace.id,
    )
    db.add(user)
    db.commit()

    return RegisterResponse(
        user_id=user.id,
        workspace_id=workspace.id,
        message="Registration successful. Configure Jira credentials via POST /workspaces/configure-jira.",
    )
