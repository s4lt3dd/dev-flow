"""
SQLAlchemy ORM models for DevFlow multi-tenancy.

Schema:
    Workspace  — one per team, holds Jira credentials
    User       — one per person, belongs to exactly one Workspace
    Session    — one per transcript/audio submission
    Story      — one per generated user story, linked to a Session
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class Workspace(Base):
    __tablename__ = "workspaces"

    id               = Column(String, primary_key=True, default=_uuid)
    name             = Column(String, nullable=False)
    jira_base_url    = Column(String, nullable=True)
    jira_email       = Column(String, nullable=True)
    jira_api_token   = Column(String, nullable=True)   # Fernet-encrypted at rest
    jira_project_key = Column(String, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    members  = relationship("User",    back_populates="workspace")
    sessions = relationship("Session", back_populates="workspace")
    stories  = relationship("Story",   back_populates="workspace")


class User(Base):
    __tablename__ = "users"

    id           = Column(String, primary_key=True, default=_uuid)
    auth0_id     = Column(String, unique=True, nullable=False)   # e.g. "auth0|abc123"
    email        = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=True)
    # product_owner | developer | scrum_master | admin
    role         = Column(String, default="developer")
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    workspace = relationship("Workspace", back_populates="members")
    sessions  = relationship("Session",   back_populates="user")


class Session(Base):
    """One transcript/audio submission that produced one or more stories."""
    __tablename__ = "sessions"

    id              = Column(String, primary_key=True, default=_uuid)
    workspace_id    = Column(String, ForeignKey("workspaces.id"), nullable=True)
    user_id         = Column(String, ForeignKey("users.id"),      nullable=True)
    source_type     = Column(String, nullable=False)   # "text" | "audio"
    transcript      = Column(Text,   nullable=True)    # raw text (or transcribed from audio)
    audio_filename  = Column(String, nullable=True)    # original filename for audio uploads
    project_context = Column(String, nullable=True)
    story_count     = Column(Integer, default=0)
    created_at      = Column(DateTime, default=datetime.utcnow)

    workspace = relationship("Workspace", back_populates="sessions")
    user      = relationship("User",      back_populates="sessions")
    stories   = relationship("Story",     back_populates="session")


class Story(Base):
    """One generated user story, persisted for analytics and history."""
    __tablename__ = "stories"

    id                   = Column(String,  primary_key=True, default=_uuid)
    session_id           = Column(String,  ForeignKey("sessions.id"),   nullable=True)
    workspace_id         = Column(String,  ForeignKey("workspaces.id"), nullable=True)
    title                = Column(String,  nullable=False)
    issue_type           = Column(String,  nullable=True)   # Story | Bug | Task | Epic
    story_text           = Column(Text,    nullable=True)
    acceptance_criteria  = Column(Text,    nullable=True)   # JSON-encoded list of strings
    story_points         = Column(Integer, nullable=True)
    priority             = Column(String,  nullable=True)   # High | Medium | Low
    priority_confidence  = Column(Float,   nullable=True)
    priority_explanation = Column(Text,    nullable=True)
    source_requirement   = Column(Text,    nullable=True)
    model_used           = Column(String,  nullable=True)
    notes                = Column(Text,    nullable=True)
    jira_key             = Column(String,  nullable=True)
    jira_url             = Column(String,  nullable=True)
    qus_scores           = Column(Text,    nullable=True)   # JSON-encoded QUS criterion scores
    created_at           = Column(DateTime, default=datetime.utcnow)

    session   = relationship("Session",   back_populates="stories")
    workspace = relationship("Workspace", back_populates="stories")
