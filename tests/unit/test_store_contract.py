import pytest

from science_agent import JSONStore
from science_agent.infra.store.postgres import load_migrations
from tests.store_contract import assert_store_contract


@pytest.mark.asyncio
async def test_json_store_satisfies_store_contract(tmp_path):
    await assert_store_contract(JSONStore(tmp_path), "json-contract-agent")


def test_postgres_migrations_are_versioned_and_non_empty():
    migrations = load_migrations()

    assert [migration.version for migration in migrations] == [1]
    assert migrations[0].name == "initial"
    assert len(migrations[0].statements) == 5
