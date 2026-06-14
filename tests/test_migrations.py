"""Guard: the Alembic migrations must stay in sync with the SQLAlchemy models.

Applies every migration to a throwaway database, then autogenerate-compares the
resulting schema against `Base.metadata`. Any diff means a model changed without a
matching migration — fix with `make migration m="..."`.
"""
from __future__ import annotations

import pathlib
import tempfile

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from services.core.config import get_settings
from services.core.models import Base

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_migrations_match_models():
    settings = get_settings()
    original_url = settings.database_url
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{pathlib.Path(tmp) / 'migrate_check.db'}"
        # env.py reads the URL from settings; point it at the throwaway DB.
        object.__setattr__(settings, "database_url", url)
        try:
            cfg = Config(str(ROOT / "alembic.ini"))
            command.upgrade(cfg, "head")

            engine = create_engine(url)
            with engine.connect() as conn:
                ctx = MigrationContext.configure(
                    conn, opts={"compare_type": True, "render_as_batch": True}
                )
                diff = compare_metadata(ctx, Base.metadata)
            engine.dispose()
        finally:
            object.__setattr__(settings, "database_url", original_url)

    assert diff == [], (
        "Models and migrations have diverged — run `make migration m=\"...\"`.\n"
        f"Pending changes: {diff}"
    )


def test_migrations_downgrade_to_base():
    """upgrade head -> downgrade base must run cleanly (reversible baseline)."""
    settings = get_settings()
    original_url = settings.database_url
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{pathlib.Path(tmp) / 'downgrade_check.db'}"
        object.__setattr__(settings, "database_url", url)
        try:
            cfg = Config(str(ROOT / "alembic.ini"))
            command.upgrade(cfg, "head")
            command.downgrade(cfg, "base")  # raises if any downgrade step fails
        finally:
            object.__setattr__(settings, "database_url", original_url)
