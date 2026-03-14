"""
GET /dashboard/stats    — workspace-level aggregate statistics
GET /dashboard/sessions — paginated session history
GET /dashboard/stories  — paginated story history with optional filters
"""

import json
import traceback
from typing import Dict, Optional

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from api.dependencies import get_current_user
from db.models import Session as SessionModel, Story as StoryModel, User
from db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _session_to_dict(s: SessionModel) -> dict:
    priority_breakdown: Dict[str, int] = {}
    for story in s.stories:
        p = story.priority or "Unknown"
        priority_breakdown[p] = priority_breakdown.get(p, 0) + 1
    return {
        "id": s.id,
        "source_type": s.source_type,
        "project_context": s.project_context,
        "story_count": s.story_count,
        "priority_breakdown": priority_breakdown,
        "audio_filename": s.audio_filename,
        "transcript_preview": (s.transcript or "")[:200] if s.transcript else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _story_to_dict(s: StoryModel) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "issue_type": s.issue_type or "Story",
        "story_text": s.story_text,
        "acceptance_criteria": json.loads(s.acceptance_criteria) if s.acceptance_criteria else [],
        "story_points": s.story_points,
        "priority": s.priority,
        "priority_confidence": s.priority_confidence,
        "priority_explanation": s.priority_explanation,
        "jira_key": s.jira_key,
        "jira_url": s.jira_url,
        "model_used": s.model_used,
        "notes": s.notes,
        "session_id": s.session_id,
        "source_type": s.session.source_type if s.session else None,
        "project_context": s.session.project_context if s.session else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "qus_scores": json.loads(s.qus_scores) if s.qus_scores else None,
    }


@router.get("/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Return aggregate analytics for the current workspace."""
    try:
        ws_id = current_user.workspace_id

        total_stories = (
            db.query(func.count(StoryModel.id))
            .filter(StoryModel.workspace_id == ws_id)
            .scalar() or 0
        )
        total_sessions = (
            db.query(func.count(SessionModel.id))
            .filter(SessionModel.workspace_id == ws_id)
            .scalar() or 0
        )

        by_priority: Dict[str, int] = {}
        for priority in ("High", "Medium", "Low"):
            by_priority[priority] = (
                db.query(func.count(StoryModel.id))
                .filter(StoryModel.workspace_id == ws_id, StoryModel.priority == priority)
                .scalar() or 0
            )

        by_source: Dict[str, int] = {}
        for source in ("text", "audio"):
            by_source[source] = (
                db.query(func.count(SessionModel.id))
                .filter(SessionModel.workspace_id == ws_id, SessionModel.source_type == source)
                .scalar() or 0
            )

        jira_linked = (
            db.query(func.count(StoryModel.id))
            .filter(StoryModel.workspace_id == ws_id, StoryModel.jira_key.isnot(None))
            .scalar() or 0
        )

        avg_pts = (
            db.query(func.avg(StoryModel.story_points))
            .filter(StoryModel.workspace_id == ws_id, StoryModel.story_points.isnot(None))
            .scalar()
        )
        avg_story_points = round(float(avg_pts), 1) if avg_pts else 0.0

        qus_rows = (
            db.query(StoryModel.qus_scores)
            .filter(StoryModel.workspace_id == ws_id, StoryModel.qus_scores.isnot(None))
            .all()
        )
        qus_values = []
        for (qus_json,) in qus_rows:
            try:
                scores = json.loads(qus_json)
                if "overall_qus" in scores:
                    qus_values.append(scores["overall_qus"])
            except Exception:
                pass
        avg_qus = round(sum(qus_values) / len(qus_values) * 100) if qus_values else None

        recent_raw = (
            db.query(SessionModel)
            .filter(SessionModel.workspace_id == ws_id)
            .order_by(SessionModel.created_at.desc())
            .limit(5)
            .all()
        )
        recent_sessions = [_session_to_dict(s) for s in recent_raw]

        issues = (
            db.query(StoryModel)
            .filter(StoryModel.workspace_id == ws_id, StoryModel.priority == "High")
            .order_by(StoryModel.created_at.desc())
            .limit(10)
            .all()
        )
        issues_to_watch = [_story_to_dict(s) for s in issues]

        return {
            "total_stories": total_stories,
            "total_sessions": total_sessions,
            "by_priority": by_priority,
            "by_source": by_source,
            "jira_linked": jira_linked,
            "avg_story_points": avg_story_points,
            "avg_qus": avg_qus,
            "recent_sessions": recent_sessions,
            "issues_to_watch": issues_to_watch,
        }
    except Exception as exc:
        logger.error("Dashboard stats error:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Dashboard error: {exc}")


@router.get("/sessions")
async def get_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Return paginated session history for the current workspace."""
    try:
        ws_id = current_user.workspace_id
        query = db.query(SessionModel).filter(SessionModel.workspace_id == ws_id)
        total = query.count()
        rows = query.order_by(SessionModel.created_at.desc()).offset(offset).limit(limit).all()
        return {"sessions": [_session_to_dict(s) for s in rows], "total": total, "limit": limit, "offset": offset}
    except Exception as exc:
        logger.error("Dashboard sessions error:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Dashboard error: {exc}")


@router.get("/stories")
async def get_stories(
    priority: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Return paginated story history with optional priority/source filters."""
    try:
        ws_id = current_user.workspace_id
        query = db.query(StoryModel).filter(StoryModel.workspace_id == ws_id)

        if priority:
            query = query.filter(StoryModel.priority == priority)
        if source_type:
            query = query.join(SessionModel, StoryModel.session_id == SessionModel.id).filter(
                SessionModel.source_type == source_type
            )

        total = query.count()
        rows = query.order_by(StoryModel.created_at.desc()).offset(offset).limit(limit).all()
        return {"stories": [_story_to_dict(s) for s in rows], "total": total, "limit": limit, "offset": offset}
    except Exception as exc:
        logger.error("Dashboard stories error:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Dashboard error: {exc}")
