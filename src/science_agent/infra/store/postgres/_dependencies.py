"""Lazy loading for the optional PostgreSQL dependencies."""

from typing import Any


def load_postgres_dependencies() -> tuple[type[Any], type[Any]]:
    """Return Psycopg pool and JSONB adapters with a useful install error."""
    try:
        from psycopg.types.json import Jsonb
        from psycopg_pool import AsyncConnectionPool
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise ModuleNotFoundError(
            "PostgresStore requires the 'postgres' extra. "
            "Install it with `uv sync --extra postgres`."
        ) from exc
    return AsyncConnectionPool, Jsonb
