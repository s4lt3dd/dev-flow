"""
POST /stories/from-text   — transcript string → stories + Jira keys
POST /stories/from-audio  — audio file upload → transcribe → same pipeline

Jira export uses each workspace's credentials from the database so that
changes made via POST /workspaces/configure-jira take effect immediately
without requiring a server restart.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import requests as _requests
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from api.dependencies import get_current_user
from db.models import Session as SessionModel, Story as StoryModel, User, Workspace
from db.session import get_db
from evaluation import StoryEvaluator  # src/ flat import

_evaluator = StoryEvaluator()

router = APIRouter()


class TranscriptRequest(BaseModel):
    transcript: str
    project_context: str = "Software development project"


def _run_sync(fn):
    """Run a blocking callable in the default thread pool."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, fn)


def _export_to_jira(stories: list[dict], workspace: Workspace) -> list[dict]:
    """
    Export each story to Jira using the workspace's stored credentials.
    Raises requests.HTTPError on Jira API failure.
    Returns the same stories list with jira_key/jira_url added.
    """
    from jira_exporter import JiraExporter  # src/ flat import

    encryption_key = os.getenv("ENCRYPTION_KEY", "")
    if not encryption_key:
        return stories  # can't decrypt — skip silently

    fernet = Fernet(encryption_key.encode())
    decrypted_token = fernet.decrypt(workspace.jira_api_token.encode()).decode()

    exporter = JiraExporter(
        base_url=workspace.jira_base_url,
        email=workspace.jira_email,
        api_token=decrypted_token,
        project_key=workspace.jira_project_key,
    )

    for story in stories:
        result = exporter.export_story(story)  # raises HTTPError on failure
        story["jira_key"] = result["jira_key"]
        story["jira_url"] = result["jira_url"]

    return stories


def _persist_session(
    db: DBSession,
    user: User,
    source_type: str,
    transcript: str | None,
    audio_filename: str | None,
    project_context: str,
    stories: list[dict],
) -> None:
    """Persist a Session and its generated Stories to the database."""
    session = SessionModel(
        workspace_id=user.workspace_id,
        user_id=user.id,
        source_type=source_type,
        transcript=transcript,
        audio_filename=audio_filename,
        project_context=project_context,
        story_count=len(stories),
    )
    db.add(session)
    db.flush()  # get session.id before inserting stories

    for s in stories:
        story = StoryModel(
            session_id=session.id,
            workspace_id=user.workspace_id,
            title=s.get("title", ""),
            issue_type=s.get("issue_type", "Story"),
            story_text=s.get("story", ""),
            acceptance_criteria=json.dumps(s.get("acceptance_criteria") or []),
            story_points=s.get("story_points"),
            priority=s.get("priority"),
            priority_confidence=s.get("priority_confidence"),
            priority_explanation=s.get("priority_explanation"),
            source_requirement=s.get("source_requirement"),
            model_used=s.get("model_used"),
            notes=s.get("notes"),
            jira_key=s.get("jira_key"),
            jira_url=s.get("jira_url"),
            qus_scores=json.dumps(s.get("qus_scores")) if s.get("qus_scores") else None,
        )
        db.add(story)

    db.commit()


def _evaluate_stories(stories: list[dict]) -> dict:
    """Run QUS evaluation on the generated stories, attaching per-story scores."""
    aggregate, individual = _evaluator.evaluate_batch(stories)
    for story, scores in zip(stories, individual):
        story["qus_scores"] = {k: v for k, v in scores.items() if k != "story_title"}
    return aggregate


def _get_workspace_if_jira_configured(user: User, db: DBSession) -> Workspace | None:
    """Return the user's workspace if Jira credentials are stored, else None."""
    ws = db.query(Workspace).filter(Workspace.id == user.workspace_id).first()
    if ws and ws.jira_api_token:
        return ws
    return None


@router.post("/from-text")
async def stories_from_text(
    body: TranscriptRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Accept a transcript string, return stories + Jira keys."""
    pipeline = request.app.state.pipeline
    try:
        stories = await _run_sync(
            lambda: pipeline.process_transcript(body.transcript, body.project_context)
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    qus_aggregate = _evaluate_stories(stories)

    workspace = _get_workspace_if_jira_configured(current_user, db)
    if workspace:
        try:
            stories = await _run_sync(lambda: _export_to_jira(stories, workspace))
        except _requests.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Jira export failed: {exc}")

    _persist_session(
        db, current_user, "text",
        body.transcript, None, body.project_context, stories,
    )
    return {"stories": stories, "count": len(stories), "qus_aggregate": qus_aggregate}


@router.post("/from-audio")
async def stories_from_audio(
    request: Request,
    file: UploadFile = File(...),
    project_context: str = "Software development project",
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Accept an audio file, transcribe via Whisper, return stories + Jira keys."""
    pipeline = request.app.state.pipeline

    if pipeline.transcriber is None:
        raise HTTPException(status_code=503, detail="Transcriber not available.")

    suffix = Path(file.filename or "audio").suffix or ".webm"
    original_filename = file.filename
    audio_bytes = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        stories = await _run_sync(
            lambda: pipeline.process_audio_file(tmp_path, project_context)
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        os.unlink(tmp_path)

    qus_aggregate = _evaluate_stories(stories)

    workspace = _get_workspace_if_jira_configured(current_user, db)
    if workspace:
        try:
            stories = await _run_sync(lambda: _export_to_jira(stories, workspace))
        except _requests.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Jira export failed: {exc}")

    _persist_session(
        db, current_user, "audio",
        None, original_filename, project_context, stories,
    )
    return {"stories": stories, "count": len(stories), "qus_aggregate": qus_aggregate}
