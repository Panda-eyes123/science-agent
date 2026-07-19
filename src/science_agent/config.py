"""Central defaults used by the phase-one runtime."""

import os

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
DEFAULT_MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION_NAME", "paper_chunks")
DEFAULT_WIKI_MILVUS_COLLECTION = os.getenv(
    "WIKI_MILVUS_COLLECTION_NAME", "wiki_pages"
)
DEFAULT_POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql://science_agent:science-agent-dev-password@localhost:5432/science_agent",
)
DEFAULT_STORE_DIR = ".science_agent"
DEFAULT_WORK_DIR = ".science_agent_workspace"
DEFAULT_MAX_ROUNDS = 8
DEFAULT_CONTEXT_MESSAGES = 24
