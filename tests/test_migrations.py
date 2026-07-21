"""Guard: the Alembic migrations must stay in sync with the SQLAlchemy models.

Applies every migration to a throwaway database, then autogenerate-compares the
resulting schema against `Base.metadata`. Any diff means a model changed without a
matching migration — fix with `make migration m="..."`.
"""
from __future__ import annotations

import contextlib
import io
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


def test_migrations_render_on_postgres():
    """The migration scripts must render as valid Postgres DDL, not just SQLite.

    Driver-free proof for the local gate (a live Postgres apply needs Docker, which the
    unit gate excludes). We point the URL at a postgresql+psycopg:// DSN and run Alembic
    in OFFLINE mode (`upgrade --sql`), which compiles the ops against the Postgres dialect
    without ever opening a DBAPI connection. We then assert the emitted SQL is real Postgres
    DDL and carries none of the SQLite batch-recreate artifacts — so the batch_alter_table
    index ops in the scripts emit plain CREATE/DROP INDEX on Postgres rather than a
    table rebuild. A full live apply is exercised by `docker compose -f
    docker-compose.prod.yml up` (the `migrate` one-shot), outside this unit gate.
    """
    settings = get_settings()
    original_url = settings.database_url
    object.__setattr__(
        settings, "database_url", "postgresql+psycopg://u:p@localhost:5432/db"
    )
    try:
        cfg = Config(str(ROOT / "alembic.ini"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            command.upgrade(cfg, "head", sql=True)  # offline: emit SQL, never connects
        ddl = buf.getvalue()
    finally:
        object.__setattr__(settings, "database_url", original_url)

    assert ddl.strip(), "offline upgrade emitted no SQL"
    # Real Postgres DDL for tables from across all three migrations.
    assert "CREATE TABLE organizations" in ddl  # baseline migration
    assert "CREATE TABLE libraries" in ddl  # second migration
    assert "CREATE TABLE llm_provider_credentials" in ddl  # third (routes/creds) migration
    # timezone-aware DateTime maps to the Postgres type, not SQLite's untyped column.
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    # No SQLite batch table-recreate leaked into the Postgres render.
    assert "_alembic_tmp" not in ddl
    assert "PRAGMA" not in ddl
