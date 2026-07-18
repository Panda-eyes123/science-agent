"""Versioned SQL migration discovery and execution."""

from dataclasses import dataclass
from importlib import resources
from typing import Any

from science_agent.config import DEFAULT_POSTGRES_DSN
from science_agent.infra.store.postgres._dependencies import (
    load_postgres_dependencies,
)

_MIGRATIONS_PACKAGE = "science_agent.infra.store.postgres.migrations"
_MIGRATION_SEPARATOR = "-- science-agent:split"
_MIGRATION_LOCK_ID = 0x5343494147454E54


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


def load_migrations() -> list[Migration]:
    """Load packaged ``NNNN_name.sql`` files in version order."""
    migrations: list[Migration] = []
    root = resources.files(_MIGRATIONS_PACKAGE)
    for item in root.iterdir():
        if not item.name.endswith(".sql"):
            continue
        version_text, separator, remainder = item.name.partition("_")
        if not separator or not version_text.isdigit():
            raise ValueError(f"Invalid migration filename: {item.name}")
        statements = tuple(
            statement.strip()
            for statement in item.read_text(encoding="utf-8").split(
                _MIGRATION_SEPARATOR
            )
            if statement.strip()
        )
        if not statements:
            raise ValueError(f"Migration contains no SQL: {item.name}")
        migrations.append(
            Migration(
                version=int(version_text),
                name=remainder.removesuffix(".sql"),
                statements=statements,
            )
        )

    migrations.sort(key=lambda migration: migration.version)
    versions = [migration.version for migration in migrations]
    if len(versions) != len(set(versions)):
        raise ValueError("Migration versions must be unique.")
    return migrations


async def run_migrations(pool: Any) -> list[int]:
    """Apply pending migrations atomically and return applied versions."""
    migrations = load_migrations()
    applied_now: list[int] = []
    async with pool.connection() as connection:
        async with connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK_ID,)
            )
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS science_agent_schema_migrations (
                    version BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor = await connection.execute(
                "SELECT version FROM science_agent_schema_migrations"
            )
            applied = {int(row[0]) for row in await cursor.fetchall()}
            for migration in migrations:
                if migration.version in applied:
                    continue
                for statement in migration.statements:
                    await connection.execute(statement)
                await connection.execute(
                    """
                    INSERT INTO science_agent_schema_migrations (version, name)
                    VALUES (%s, %s)
                    """,
                    (migration.version, migration.name),
                )
                applied_now.append(migration.version)
    return applied_now


async def migrate_postgres(
    dsn: str = DEFAULT_POSTGRES_DSN,
    *,
    timeout: float = 30.0,
) -> list[int]:
    """Open a temporary pool and apply migrations independently of a Store."""
    pool_type, _ = load_postgres_dependencies()
    pool = pool_type(conninfo=dsn, min_size=1, max_size=1, open=False)
    await pool.open(wait=True, timeout=timeout)
    try:
        return await run_migrations(pool)
    finally:
        await pool.close()
