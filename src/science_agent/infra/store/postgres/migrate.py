"""Command-line entry point for PostgreSQL schema migrations."""

import argparse
import asyncio

from science_agent.config import DEFAULT_POSTGRES_DSN
from science_agent.infra.store.postgres.migration_runner import migrate_postgres


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply science-agent PostgreSQL schema migrations."
    )
    parser.add_argument(
        "--dsn",
        default=DEFAULT_POSTGRES_DSN,
        help="PostgreSQL connection string; defaults to POSTGRES_DSN.",
    )
    args = parser.parse_args()
    versions = asyncio.run(migrate_postgres(args.dsn))
    if versions:
        print(f"Applied PostgreSQL migrations: {versions}")
    else:
        print("PostgreSQL schema is already up to date.")


if __name__ == "__main__":
    main()
