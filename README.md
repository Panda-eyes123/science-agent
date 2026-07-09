# science-agent

A runnable phase-one Python skeleton for a science-focused agent SDK.

## Quick start

```powershell
uv venv --python 3.13
uv sync --extra dev
uv run pytest
uv run python examples\getting_started.py
```

## Current scope

- Async agent runtime
- Event subscription
- Tool registry and execution
- JSON persistence
- Local sandboxed file operations
- Minimal OpenAI provider adapter
