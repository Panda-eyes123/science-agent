import os
import uuid

import pytest

from science_agent import PostgresStore
from tests.store_contract import assert_store_contract


@pytest.mark.asyncio
async def test_postgres_store_satisfies_store_contract():
    dsn = os.getenv("POSTGRES_TEST_DSN")
    if not dsn:
        pytest.skip("Set POSTGRES_TEST_DSN to run PostgreSQL integration tests.")

    store = await PostgresStore.create(dsn, min_size=1, max_size=2)
    agent_id = f"postgres-contract-{uuid.uuid4().hex}"
    try:
        assert await store.migrate() == []
        await assert_store_contract(store, agent_id)
    finally:
        await store.delete(agent_id)
        await store.close()
