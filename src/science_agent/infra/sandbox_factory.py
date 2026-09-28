"""Factory helpers for local development sandboxes."""

from science_agent.config import DEFAULT_WORK_DIR
from science_agent.infra.sandbox import LocalSandbox


def create_local_sandbox(
    work_dir: str = DEFAULT_WORK_DIR, enforce_boundary: bool = True
) -> LocalSandbox:
    return LocalSandbox(work_dir=work_dir, enforce_boundary=enforce_boundary)
