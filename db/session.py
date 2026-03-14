"""
SQLAlchemy engine and session factory.

DATABASE_URL defaults to a local SQLite file (devflow.db).
Switch to Postgres later with: DATABASE_URL=postgresql://user:pass@host/dbname
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./devflow.db")

# check_same_thread=False is required for SQLite when used with FastAPI's
# thread-pool executors; it's a no-op for other databases.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """FastAPI dependency that yields a database session and closes it afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
