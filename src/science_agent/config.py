"""Central defaults used by the phase-one runtime."""

import os

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_STORE_DIR = ".science_agent"
DEFAULT_WORK_DIR = ".science_agent_workspace"
DEFAULT_MAX_ROUNDS = 8
DEFAULT_CONTEXT_MESSAGES = 24
