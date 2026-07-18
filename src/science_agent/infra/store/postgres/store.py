"""PostgreSQL persistence backed by Psycopg 3's asynchronous pool."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from science_agent.config import DEFAULT_POSTGRES_DSN
from science_agent.infra.store.errors import EventSequenceConflictError
from science_agent.infra.store.postgres._dependencies import (
    load_postgres_dependencies,
)
from science_agent.infra.store.postgres.migration_runner import run_migrations
from science_agent.infra.store.serialization import (
    dump_agent_info,
    dump_messages,
    dump_tool_call_records,
    load_agent_info,
    load_event,
    load_messages,
    load_tool_call_records,
)
from science_agent.types import (
    AgentChannel,
    AgentEventEnvelope,
    AgentInfo,
    Message,
    ToolCallRecord,
)


class PostgresStore:
    """Store implementation with atomic state saves and durable event ordering."""

    def __init__(
        self,
        dsn: str = DEFAULT_POSTGRES_DSN,
        *,
        min_size: int = 1,
        max_size: int = 10,
        open_timeout: float = 30.0,
    ) -> None:
        pool_type, jsonb_type = load_postgres_dependencies()
        self._pool = pool_type(
            conninfo=dsn,
            min_size=min_size,
            max_size=max_size,
            open=False,
        )
        self._jsonb = jsonb_type
        self._open_timeout = open_timeout
        self._open_lock = asyncio.Lock()
        self._opened = False
        self._migrated = False

    @classmethod
    async def create(
        cls,
        dsn: str = DEFAULT_POSTGRES_DSN,
        *,
        min_size: int = 1,
        max_size: int = 10,
        open_timeout: float = 30.0,
        migrate: bool = True,
    ) -> "PostgresStore":
        store = cls(
            dsn,
            min_size=min_size,
            max_size=max_size,
            open_timeout=open_timeout,
        )
        await store.open(migrate=migrate)
        return store

    async def __aenter__(self) -> "PostgresStore":
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    async def open(self, *, migrate: bool = True) -> None:
        """Open the pool and apply migrations once before the first operation."""
        async with self._open_lock:
            if not self._opened:
                await self._pool.open(wait=True, timeout=self._open_timeout)
                self._opened = True
            if migrate and not self._migrated:
                await run_migrations(self._pool)
                self._migrated = True

    async def close(self) -> None:
        if self._opened:
            await self._pool.close()
            self._opened = False

    async def migrate(self) -> list[int]:
        await self.open(migrate=False)
        versions = await run_migrations(self._pool)
        self._migrated = True
        return versions

    async def save_agent_state(
        self,
        agent_id: str,
        *,
        messages: list[Message],
        records: list[ToolCallRecord],
        info: AgentInfo,
        todos: list[dict],
    ) -> None:
        await self.open()
        async with self._pool.connection() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO science_agent_state (
                        agent_id, info, messages, tool_calls, todos
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (agent_id) DO UPDATE SET
                        info = EXCLUDED.info,
                        messages = EXCLUDED.messages,
                        tool_calls = EXCLUDED.tool_calls,
                        todos = EXCLUDED.todos,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        agent_id,
                        self._jsonb(dump_agent_info(info)),
                        self._jsonb(dump_messages(messages)),
                        self._jsonb(dump_tool_call_records(records)),
                        self._jsonb(todos),
                    ),
                )

    async def _save_state_column(
        self, agent_id: str, column: str, payload: Any
    ) -> None:
        await self.open()
        allowed = {"info", "messages", "tool_calls", "todos"}
        if column not in allowed:
            raise ValueError(f"Unsupported state column: {column}")
        query = f"""
            INSERT INTO science_agent_state (agent_id, {column})
            VALUES (%s, %s)
            ON CONFLICT (agent_id) DO UPDATE SET
                {column} = EXCLUDED.{column},
                updated_at = CURRENT_TIMESTAMP
        """
        async with self._pool.connection() as connection:
            await connection.execute(query, (agent_id, self._jsonb(payload)))

    async def _load_state_column(self, agent_id: str, column: str) -> Any | None:
        await self.open()
        allowed = {"info", "messages", "tool_calls", "todos"}
        if column not in allowed:
            raise ValueError(f"Unsupported state column: {column}")
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                f"SELECT {column} FROM science_agent_state WHERE agent_id = %s",
                (agent_id,),
            )
            row = await cursor.fetchone()
        return row[0] if row is not None else None

    async def save_messages(self, agent_id: str, messages: list[Message]) -> None:
        await self._save_state_column(agent_id, "messages", dump_messages(messages))

    async def load_messages(self, agent_id: str) -> list[Message]:
        payload = await self._load_state_column(agent_id, "messages")
        return load_messages(payload if payload is not None else [])

    async def save_tool_call_records(
        self, agent_id: str, records: list[ToolCallRecord]
    ) -> None:
        await self._save_state_column(
            agent_id, "tool_calls", dump_tool_call_records(records)
        )

    async def load_tool_call_records(self, agent_id: str) -> list[ToolCallRecord]:
        payload = await self._load_state_column(agent_id, "tool_calls")
        return load_tool_call_records(payload if payload is not None else [])

    async def append_event(self, agent_id: str, envelope: AgentEventEnvelope) -> None:
        await self.open()
        async with self._pool.connection() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO science_agent_state (agent_id)
                    VALUES (%s)
                    ON CONFLICT (agent_id) DO NOTHING
                    """,
                    (agent_id,),
                )
                cursor = await connection.execute(
                    """
                    INSERT INTO science_agent_events (
                        agent_id, seq, event_timestamp, channel, event
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (agent_id, seq) DO NOTHING
                    RETURNING seq
                    """,
                    (
                        agent_id,
                        envelope.seq,
                        envelope.timestamp,
                        envelope.channel,
                        self._jsonb(envelope.event),
                    ),
                )
                if await cursor.fetchone() is not None:
                    return
                cursor = await connection.execute(
                    """
                    SELECT seq, event_timestamp, channel, event
                    FROM science_agent_events
                    WHERE agent_id = %s AND seq = %s
                    FOR UPDATE
                    """,
                    (agent_id, envelope.seq),
                )
                row = await cursor.fetchone()
                stored = (
                    load_event(
                        {
                            "seq": row[0],
                            "timestamp": row[1],
                            "channel": row[2],
                            "event": row[3],
                        }
                    )
                    if row is not None
                    else None
                )
                if stored != envelope:
                    raise EventSequenceConflictError(
                        f"Event sequence {envelope.seq} for agent {agent_id!r} "
                        "already contains different content."
                    )

    async def read_events(
        self,
        agent_id: str,
        *,
        since: int | None = None,
        channel: AgentChannel | None = None,
    ) -> AsyncIterator[AgentEventEnvelope]:
        await self.open()
        conditions = ["agent_id = %s"]
        parameters: list[Any] = [agent_id]
        if since is not None:
            conditions.append("seq > %s")
            parameters.append(since)
        if channel is not None:
            conditions.append("channel = %s")
            parameters.append(channel)
        query = f"""
            SELECT seq, event_timestamp, channel, event
            FROM science_agent_events
            WHERE {" AND ".join(conditions)}
            ORDER BY seq ASC
        """
        async with self._pool.connection() as connection:
            cursor = await connection.execute(query, parameters)
            rows = await cursor.fetchall()
        for row in rows:
            yield load_event(
                {
                    "seq": row[0],
                    "timestamp": row[1],
                    "channel": row[2],
                    "event": row[3],
                }
            )

    async def last_event_seq(self, agent_id: str) -> int:
        await self.open()
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT COALESCE(MAX(seq), 0)
                FROM science_agent_events
                WHERE agent_id = %s
                """,
                (agent_id,),
            )
            row = await cursor.fetchone()
        return int(row[0]) if row is not None else 0

    async def save_info(self, agent_id: str, info: AgentInfo) -> None:
        await self._save_state_column(agent_id, "info", dump_agent_info(info))

    async def load_info(self, agent_id: str) -> AgentInfo | None:
        payload = await self._load_state_column(agent_id, "info")
        return load_agent_info(payload) if payload is not None else None

    async def save_todos(self, agent_id: str, todos: list[dict]) -> None:
        await self._save_state_column(agent_id, "todos", todos)

    async def load_todos(self, agent_id: str) -> list[dict]:
        payload = await self._load_state_column(agent_id, "todos")
        return list(payload) if payload is not None else []

    async def save_snapshot(
        self, agent_id: str, snapshot_id: str, snapshot: dict[str, Any]
    ) -> None:
        await self.open()
        async with self._pool.connection() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO science_agent_state (agent_id)
                    VALUES (%s)
                    ON CONFLICT (agent_id) DO NOTHING
                    """,
                    (agent_id,),
                )
                await connection.execute(
                    """
                    INSERT INTO science_agent_snapshots (
                        agent_id, snapshot_id, payload
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (agent_id, snapshot_id) DO UPDATE SET
                        payload = EXCLUDED.payload,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (agent_id, snapshot_id, self._jsonb(snapshot)),
                )

    async def load_snapshot(
        self, agent_id: str, snapshot_id: str
    ) -> dict[str, Any] | None:
        await self.open()
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT payload
                FROM science_agent_snapshots
                WHERE agent_id = %s AND snapshot_id = %s
                """,
                (agent_id, snapshot_id),
            )
            row = await cursor.fetchone()
        return dict(row[0]) if row is not None else None

    async def list_snapshots(self, agent_id: str) -> list[str]:
        await self.open()
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT snapshot_id
                FROM science_agent_snapshots
                WHERE agent_id = %s
                ORDER BY snapshot_id ASC
                """,
                (agent_id,),
            )
            rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def list(self, prefix: str | None = None) -> list[str]:
        await self.open()
        parameters: tuple[Any, ...] = ()
        query = "SELECT agent_id FROM science_agent_state"
        if prefix is not None:
            query += " WHERE starts_with(agent_id, %s)"
            parameters = (prefix,)
        query += " ORDER BY agent_id ASC"
        async with self._pool.connection() as connection:
            cursor = await connection.execute(query, parameters)
            rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def delete(self, agent_id: str) -> None:
        await self.open()
        async with self._pool.connection() as connection:
            await connection.execute(
                "DELETE FROM science_agent_state WHERE agent_id = %s", (agent_id,)
            )
