# Storage guide

The Agent runtime depends on the `Store` protocol. The repository provides
`JSONStore` for lightweight local work and `PostgresStore` for shared durable
state. Applications choose and inject the implementation through `AgentConfig`.

## Store selection

| Store | Intended use | Important limitation |
|---|---|---|
| `JSONStore` | Examples, offline work, single-process prototypes | State spans multiple files and is not transactionally committed |
| `PostgresStore` | Shared durable state, centralized backup, multi-process readers | One active writer is still expected for each `agent_id` |

The SDK does not silently fall back from PostgreSQL to JSONStore. Applications
must choose explicitly and decide how service failures affect their own startup
or requests.

## JSONStore

```python
from science_agent import JSONStore

store = JSONStore(".science_agent")
```

JSONStore implements the full Store contract, including event filtering,
snapshots, event-sequence recovery, idempotent duplicate events, and explicit
sequence-conflict errors. Do not point multiple processes at the same directory.

There is no existing JSONStore data that must be preserved for this migration.
No JSON-to-PostgreSQL importer is included.

## PostgresStore lifecycle

Create one pool-backed Store for the application lifecycle. Do not construct a
new Store for every request.

The recommended pattern is an async context manager:

```python
from science_agent import PostgresStore

async with PostgresStore() as store:
    agent = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=provider,
            store=store,
            agent_id="stable-agent-id",
        ),
        templates,
    )
```

Applications that manage startup and shutdown hooks explicitly can use:

```python
store = await PostgresStore.create(migrate=True)
try:
    agent = await Agent.create(config, templates)
finally:
    await store.close()
```

`PostgresStore` lazily opens a Psycopg 3 asynchronous connection pool. Pending
migrations are applied before the first Store operation. Passing `migrate=False`
to `create()` only defers the initial migration check; normal Store operations
still ensure the schema is current. Operators can run the migration CLI first,
after which the automatic check is an idempotent no-op.

See [`examples/postgres_persistence.py`](../examples/postgres_persistence.py) for
a complete state-save and restore flow using a mock provider.

## Migrations

Deployment systems can apply migrations before application startup:

```powershell
uv run science-agent-migrate
```

Override the configured DSN when necessary:

```powershell
uv run science-agent-migrate --dsn "postgresql://user:password@host:5432/database"
```

Migrations are versioned SQL resources included in the wheel. An advisory
transaction lock prevents concurrent application instances from applying the
same migration. Re-running the command is safe.

The initial schema contains:

| Table | Responsibility |
|---|---|
| `science_agent_schema_migrations` | Applied migration versions |
| `science_agent_state` | Agent info, messages, tool calls, and todos as JSONB |
| `science_agent_events` | Ordered events keyed by `(agent_id, seq)` |
| `science_agent_snapshots` | Named Agent snapshots |

Deleting an Agent state row cascades to its events and snapshots.

## State transaction semantics

`Agent._persist_state()` calls `save_agent_state()` once with messages, tool call
records, Agent info, and todos. PostgresStore commits those fields in one UPSERT
transaction. JSONStore preserves API compatibility but replaces its files one
at a time and cannot provide equivalent atomicity.

Individual Store methods such as `save_messages()` remain available for callers
that intentionally update one field.

## Event semantics

- Events are returned in ascending sequence order.
- `read_events(since=n)` returns events whose sequence is greater than `n`.
- Identical writes to the same `(agent_id, seq)` are idempotent.
- Different content at an existing sequence raises
  `EventSequenceConflictError`.
- Restored Agents resume numbering from the greatest persisted sequence.

The runtime expects one active writer for each `agent_id`. Conflict detection is
a data-integrity boundary, not a distributed lock or scheduling mechanism.
Applications that run the same Agent across multiple workers must implement their
own lease or ownership model.

## Failure behavior

- Connection, authentication, migration, constraint, and serialization errors
  are propagated to the caller.
- The SDK does not buffer failed writes for later replay.
- The SDK does not automatically switch Store implementations.
- A PostgreSQL outage can therefore prevent Agent creation, event persistence,
  or state persistence, depending on when it occurs.

The consuming service should decide whether to fail startup, reject requests,
retry operations, or expose a degraded state.

## Current non-goals

- JSON data import because there is no data to retain.
- Automatic PostgreSQL backup or restore.
- Distributed Agent locks and leases.
- Multi-writer conflict resolution.
- Automatic Store failover.
- Cross-database replication.
