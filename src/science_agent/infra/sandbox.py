"""A small local sandbox with path boundary enforcement."""

import asyncio
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from science_agent.config import DEFAULT_WORK_DIR
from science_agent.errors import SandboxError


@dataclass(slots=True)
class SandboxResult:
    stdout: str
    stderr: str
    returncode: int


class LocalSandbox:
    def __init__(
        self, work_dir: str | Path = DEFAULT_WORK_DIR, enforce_boundary: bool = True
    ) -> None:
        self.work_dir = Path(work_dir).resolve()
        self.enforce_boundary = enforce_boundary
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, relative_path: str) -> Path:
        # Tool paths use the same rules on Windows and in Linux containers.
        # Reject drive/UNC paths and recognize either directory separator.
        if self.enforce_boundary and PureWindowsPath(relative_path).drive:
            raise SandboxError(f"Path escapes sandbox boundary: {relative_path}")
        normalized = relative_path.replace("\\", "/") if self.enforce_boundary else relative_path
        candidate = (self.work_dir / normalized).resolve()
        if (
            self.enforce_boundary
            and self.work_dir not in candidate.parents
            and candidate != self.work_dir
        ):
            raise SandboxError(f"Path escapes sandbox boundary: {relative_path}")
        return candidate

    def read_text(self, relative_path: str) -> str:
        return self._resolve_path(relative_path).read_text(encoding="utf-8")

    def write_text(self, relative_path: str, content: str) -> None:
        path = self._resolve_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    async def run(self, command: str) -> SandboxResult:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self.work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return SandboxResult(
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            returncode=process.returncode,
        )
