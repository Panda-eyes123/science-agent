"""Central defaults used by the phase-one runtime."""

import os

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_DATA_DIR = os.getenv("SCIENCE_AGENT_DATA_DIR", "/data")
DEFAULT_STORE_DIR = f"{DEFAULT_DATA_DIR}/store"
DEFAULT_WORK_DIR = f"{DEFAULT_DATA_DIR}/workspaces"
DEFAULT_WIKI_DIR = f"{DEFAULT_DATA_DIR}/wiki"
DEFAULT_MAX_ROUNDS = 8
DEFAULT_CONTEXT_MESSAGES = 24
