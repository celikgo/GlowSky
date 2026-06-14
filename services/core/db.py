"""Database engine/session setup.

Phase 0 uses a synchronous SQLAlchemy engine (SQLite by default) for simplicity.
Phase 1 swaps DATABASE_URL to Postgres; the repository seam stays the same.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from services.core.config import get_settings
from services.core.models import Base

_settings = get_settings()
_connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}

engine = create_engine(_settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create tables + seed the built-in local tenant.

    `create_all` is the zero-setup path for dev/test (SQLite). **Alembic is the
    source of truth for schema evolution** — for Postgres/production, run
    `make migrate` (alembic upgrade head) instead of relying on create_all. The
    baseline migration is kept in sync with these models by tests/test_migrations.py.
    Seeding the local org/user keeps single-tenant dev mode's foreign keys satisfiable.
    """
    Base.metadata.create_all(engine)
    # Imported here to avoid a circular import (auth -> models, db -> models).
    from services.core.auth import seed_local_tenant

    with session_scope() as session:
        seed_local_tenant(session)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
