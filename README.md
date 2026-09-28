# science-agent

`science-agent` is an alpha-stage Python SDK for building event-driven research agents.
It currently focuses on a small but working runtime: async agent execution, event
subscription, tool calls, local JSON persistence, sandboxed file tools, permission
approval, and an OpenAI-compatible provider adapter.

This project is intentionally still small. The alpha goal is to keep the runtime
easy to inspect while the core contracts settle.

## Current Status

The SDK can already:

- Run an async `Agent` with a template, model provider, message history, and event stream.
- Emit `progress`, `control`, and `monitor` events.
- Register and execute tools through `ToolRegistry`.
- Use built-in tools for todo management and sandboxed file read/write.
- Persist messages, tool calls, events, todos, snapshots, and agent info with `JSONStore`.
- Enforce local sandbox path boundaries for file tools.
- Request manual tool approval through `control.permission_required`.
- Call an OpenAI-compatible `/chat/completions` endpoint with categorized provider errors and retry handling.

## Requirements

- Python `3.13+`
- `uv`
- An `OPENAI_API_KEY` only when using the real `OpenAIProvider`

## Setup

```powershell
uv venv --python 3.13
uv sync --extra dev
```

To use the scientific-paper RAG stack, install the optional dependencies:

```powershell
uv sync --extra rag --extra dev
```

本地生成文件统一放在 `.local/` 中，该目录不提交到 Git：

```text
.local/
  cache/       pytest、Ruff、uv 缓存
  tmp/pytest/  pytest 临时文件
  logs/        本地后台服务日志
  data/        SDK 存储及 Web 会话数据、会话文件
  workspaces/  SDK 默认文件工作空间
  examples/    示例程序的持久化数据
  tools/       本机附带的 Python、uv 工具（如有）
```

根目录保留 `.venv/`，供 uv 自动发现虚拟环境；`.git/`、`.gitignore`、
`.python-version` 和 `.env.example` 也保持标准位置。后续运行测试和检查不会
再在根目录生成独立的 pytest、Ruff 或 uv 缓存目录。
本机附带的 uv 可通过 `.local/tools/bin/uv.exe` 调用。

旧工作区升级时，先停止后端，将 `.science_agent/` 移到 `.local/data/`，
将 `.science_agent_workspace/` 移到 `.local/workspaces/`，再启动服务。
若目标目录已经有数据，应先核对内容，避免直接合并覆盖。
`SCIENCE_AGENT_DATA_DIR` 的显式配置仍然优先。

## 本地研究工作台

工作台支持会话历史、真实模型流式回答、工具执行进度、人工审批和停止运行。
当前版本为本地单用户应用；论文 RAG 继续作为 SDK 能力提供，尚未接入网页。

准备 Python 3.13+、uv 和 Node.js 22.12+，在项目根目录执行：

```powershell
uv sync --extra web --extra dev
Copy-Item .env.example .env
```

编辑 `.env`，填写 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `OPENAI_MODEL`。
服务端使用 OpenAI-compatible Chat Completions 流式接口；密钥不会发送到浏览器。
缺少密钥时页面会提示配置，不会回退为模拟回答。

终端一，启动后端：

```powershell
uv run uvicorn science_agent_web.app:create_app --factory --host 127.0.0.1 --port 8000
```

终端二，启动前端：

```powershell
cd web
npm ci
npm run dev
```

打开 <http://127.0.0.1:5173>。Vite 将 `/api` 转发到本机 8000 端口。
前后端均只监听本机；不要使用多进程或 `--workers` 启动后端。

一次完整操作：新建会话，要求助手使用 `fs_write` 把实验模板保存到
`notes/experiment.md`，查看参数后允许写入，等待回答，再刷新页面检查历史。
写文件及 Todo 更新需要确认，读工具自动执行。拒绝会结束本次运行。

数据默认保存在 `.local/data/store`，文件位于
`.local/data/workspaces/<thread_id>`，可用 `SCIENCE_AGENT_DATA_DIR` 更改数据根目录。
运行由后端持有，网页断开不会停止任务；刷新后可续传事件、继续审批。
停止不会回滚已完成的文件写入。后端重启将未完成运行标记为“已中断”，不会自动重放工具。

### 模块与契约

- `web/`：React + TypeScript + Vite + CSS Modules，按会话、对话与运行详情组织。
- `src/science_agent_web/`：路由/DTO、运行服务、SDK 事件适配。单向依赖 SDK。
- `src/science_agent/`：模型循环、工具、权限、事件和存储；不依赖 Web 框架。

HTTP 文档在 <http://127.0.0.1:8000/docs>。Pydantic 定义是公开类型的唯一来源；
运行详情中的事件和 SSE 使用同一模型。更改契约后，在后端运行时执行：

```powershell
cd web
npm run types
npm run lint
npm run build
```

生成的 `schema.d.ts` 随代码提交，不手工修改。前端新增组件按 ESLint/Prettier 规范维护，
`npm run format` 可统一格式。Python 检查继续使用 `uv run pytest` 与 `uv run ruff check .`。
新增回归覆盖流式工具参数、多轮消息配对、审批、取消、事件续传和重启后的中断状态。
这些使用隔离的测试 Provider；真实模型验收仍需要有效的服务端配置。

SDK 仍可使用 `await agent.send(text)`；需要流式事件时使用
`await agent.send(text, stream=True)`，并订阅原有 progress/control/monitor 通道。
流式 Provider 实现独立的 `StreamingModelProvider` 协议，输出 `ModelTextDelta` 和
`ModelStreamEnd`；不支持流式的 Provider 会明确报错。消息和事件新增字段均有默认值，
现有 JSON 历史可继续读取。

## Paper RAG (Stages 1-3)

## Wiki 知识编译层

Wiki 采用审阅优先的编译流程。LLM 只根据 Raw RAG `RawSourceSnapshot` 和现有
Wiki Markdown 页面生成 `WikiChangeset`，不能直接改写页面，也不能用生成文本替代
原始证据。Changeset 必须通过引用白名单、Markdown 结构校验和页面版本校验，审批后
才会写回 Markdown。

```text
RawSourceSnapshot + WikiPage
        -> LLM compiler
        -> WikiChangeset (pending)
        -> citation whitelist + structure validation + expected version
        -> MarkdownWikiStore (authoritative Markdown)
        -> rebuildable Wiki index (Milvus adapter)
```

- `src/science_agent/wiki/types.py` 定义 SourceSnapshot、WikiPage、Changeset、查询结果和 Claim 验证记录。
- `src/science_agent/wiki/changesets.py` 负责引用白名单、结构校验、乐观版本控制和 stale 标记。
- `src/science_agent/infra/wiki/markdown_store.py` 将正文与页面元数据保存在同一个 Markdown 文件中；索引删除后可从这些文件重建。
- `src/science_agent/wiki/indexing.py` 定义从 Markdown 重建派生索引的流程。
- `src/science_agent/wiki/query.py` 提供 `wiki_guided`、`raw_first`、`raw_only` 三种查询编排，并保留 Raw EvidencePack 供 Claim 验证。

源论文产生新快照时，关联页面只标记为 `stale`，不会自动改正文。查询时只有新鲜 Wiki 页面进入概念关联上下文，Raw RAG 仍作为最终 Claim 引用验证来源。

当前这些是独立领域和存储接口，尚未接入 Web 工作台的页面路由；接入时应在 Web 装配层注入 Markdown store、LLM compiler、Raw RAG searcher 和 Wiki index adapter。

The SDK now includes an optional, tool-layer scientific-paper RAG pipeline. The
agent runtime remains independent; applications explicitly create the parser,
embedding model, Milvus corpus, ingestion service, and retrieval service, then
register the tools they need.

```text
PDF -> Docling (PyMuPDF fallback) -> source elements -> parent/child chunks
    -> Milvus native BM25 + dense vector -> RRF -> CrossEncoder -> EvidencePack
```

- Sections are rule-routed as `background`, `method`, `experiment`, `result`,
  `discussion`, or `other`.
- Tables retain Markdown, and figures retain captions, page number, bounding box,
  exported local image paths, and source-element identity for future VLM retrieval.
- Every child hit links back to a parent chunk and then original source elements.
- Milvus stores both the indexed child chunks and the provenance records; the
  default URI may point at a local Milvus Lite database.

Minimal wiring:

```python
from science_agent.infra.corpus import MilvusCorpusStore
from science_agent.infra.document_parsing import DoclingPDFParser
from science_agent.infra.embeddings import OpenAIEmbeddingProvider
from science_agent.infra.rerankers import APIReranker
from science_agent.rag import PaperChunker, PaperIngestionService, RetrievalService
from science_agent.tools import ToolRegistry, register_rag_tools

embeddings = OpenAIEmbeddingProvider(model="text-embedding-3-small")
corpus = MilvusCorpusStore(
    uri="./data/science_rag.db",
    embedding_dim=1536,
)
ingestion = PaperIngestionService(
    parser=DoclingPDFParser(),
    chunker=PaperChunker(),
    embeddings=embeddings,
    corpus=corpus,
)
retrieval = RetrievalService(
    corpus=corpus,
    embeddings=embeddings,
    reranker=APIReranker(model="BAAI/bge-reranker-v2-m3"),
)
tools = register_rag_tools(ToolRegistry(), ingestion=ingestion, retrieval=retrieval)
```

Configure reranking with `RERANK_API_KEY`, `RERANK_MODEL`, `RERANK_BASE_URL`,
and optionally `RERANK_ENDPOINT` (default: `/rerank`). The adapter accepts the
common Jina/Cohere-style response shape with `index` and `relevance_score`.

`paper_ingest` indexes a local PDF and `paper_search` returns a serializable
evidence pack. Embeddings, reranking, and VLM inference use API adapters; no
model weights are loaded into the agent process.

## Multimodal RAG (Stage 4)

Stage four adds visual evidence without coupling the core retrieval service to a
specific PDF renderer or vision model:

```text
visual query -> figure/table/mixed retrieval -> source-element backtrace
             -> Docling image or PyMuPDF bbox crop -> fallback policy
             -> optional OpenAI-compatible VLM -> structured observations
```

`PDFRegionRenderer` explicitly converts Docling bottom-left coordinates to
PyMuPDF top-left coordinates. `PDFVisualAssetResolver` reuses exported figures
when possible and only crops the source PDF when an image is missing. Generated
assets keep page, bbox, dimensions, caption, and parent context.

```python
from science_agent.infra.visual_assets import PDFVisualAssetResolver
from science_agent.infra.vlm import OpenAIVisionProvider
from science_agent.rag.multimodal import FigureSearchService

figure_search = FigureSearchService(
    retrieval=retrieval,
    paper_store=corpus,
    asset_resolver=PDFVisualAssetResolver(),
    vlm=OpenAIVisionProvider(model="gpt-4.1-mini"),
)
tools = register_rag_tools(
    ToolRegistry(),
    ingestion=ingestion,
    retrieval=retrieval,
    figure_search=figure_search,
)
```

The resulting `paper_figure_search` tool accepts `vlm_mode="auto"`, `"always"`,
or `"never"`. Auto mode invokes the VLM for explicit visual questions or when
captions do not contain enough information. VLM output is query-scoped evidence
and is not written back into the Milvus corpus.

Configure an OpenAI-compatible vision endpoint with `VLM_API_KEY`, `VLM_MODEL`,
and `VLM_BASE_URL`. The provider falls back to the corresponding `OPENAI_*`
variables when dedicated VLM settings are absent.

## Development Commands

Run the test suite:

```powershell
uv run pytest
```

Run lint checks:

```powershell
uv run ruff check .
```

Run all local quality checks:

```powershell
uv run pytest
uv run ruff check .
```

Run the built-in examples:

```powershell
uv run python examples\getting_started.py
uv run python examples\tool_usage.py
uv run python examples\persistence_resume.py
```

## Local Example

`examples/getting_started.py` runs without external API calls. It uses a tiny mock
provider and prints progress events from the agent.

```python
import asyncio

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    ModelResponse,
    ToolRegistry,
)


class EchoProvider:
    async def complete(self, messages, *, tools=None, system_prompt=None):
        last_user = next(
            message.content for message in reversed(messages) if message.role == "user"
        )
        return ModelResponse(text=f"Science agent received: {last_user}")


async def main() -> None:
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            system_prompt="You are a concise scientific research assistant.",
        )
    )

    agent = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=EchoProvider(),
            tool_registry=ToolRegistry(),
        ),
        templates,
    )

    async def consume() -> None:
        async for envelope in agent.subscribe(["progress"]):
            print(envelope.event)
            if envelope.event["type"] == "done":
                break

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await agent.send("Summarize the role of controls in a simple experiment.")
    await consumer


asyncio.run(main())
```

## Tool And Persistence Examples

The repository includes two practical local demos:

- `examples/tool_usage.py`: simulates a model requesting `todo_write`, then persists the agent state in `.local/examples/demo_store`.
- `examples/persistence_resume.py`: creates an agent with a fixed `agent_id`, writes state through `JSONStore`, then restores a second agent instance from the same store.

These examples use mock providers so they are stable in tests and offline development.

## Real OpenAI Example

Set your API key:

```powershell
$env:OPENAI_API_KEY="sk-..."
```

Then use the real provider:

```python
import asyncio

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    OpenAIProvider,
    RetryConfig,
    ToolRegistry,
)


async def main() -> None:
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            system_prompt="You are a careful scientific research assistant.",
        )
    )

    provider = OpenAIProvider(
        model="gpt-4.1-mini",
        retry=RetryConfig(max_attempts=3, backoff_seconds=0.5),
    )
    agent = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=provider,
            tool_registry=ToolRegistry(),
        ),
        templates,
    )

    async def consume() -> None:
        async for envelope in agent.subscribe(["progress", "monitor"]):
            print(envelope.event)
            if envelope.event["type"] == "done":
                break

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await agent.send("Give me a concise hypothesis for testing yeast growth rates.")
    await consumer


asyncio.run(main())
```

`OpenAIProvider` currently uses the Chat Completions API. It categorizes common
provider failures into authentication, invalid request, not found, rate limit,
server, timeout, network, and response parsing errors. Retry is applied only to
retryable failures such as `408`, `429`, `409`, `5xx`, timeout, and network errors.

## Permission Approval Example

Use `permission_mode="manual"` when tool calls should require an explicit decision.
Subscribers listen to the `control` channel and call the event's `respond` function.

```python
async for envelope in agent.subscribe(["control", "progress"]):
    if envelope.event["type"] == "permission_required":
        call = envelope.event["call"]
        if call["name"] == "fs_write":
            await envelope.event["respond"]("allow", note="approved file write")
        else:
            await envelope.event["respond"]("deny", note="tool not allowed")
```

Persisted control events are sanitized before being written to `JSONStore`, so the
runtime callback is available to subscribers but is not serialized to disk.

## Public API Surface

The alpha public exports are:

- `Agent`, `AgentConfig`
- `AgentTemplateDefinition`, `AgentTemplateRegistry`
- `JSONStore`
- `LocalSandbox`, `SandboxResult`
- `OpenAIProvider`, `RetryConfig`
- `Tool`, `ToolExecutionContext`, `ToolRegistry`
- `TodoItem`, `TodoService`
- `ModelProvider`, `ModelResponse`, `ToolCallRequest`

## Capability Boundaries

This alpha is useful for local development, SDK contract exploration, and small
research-agent prototypes. It is not production-ready yet.

Currently supported:

- Single-process async runtime.
- Local JSON persistence.
- Local sandbox file read/write with path boundary checks.
- Sequential tool execution.
- Manual approval flow for tool calls.
- Minimal OpenAI-compatible provider with categorized errors and retry.
- Unit-tested core behavior.

Not yet supported:

- SQLite/PostgreSQL stores.
- Distributed locks or multi-worker coordination.
- MCP tools.
- E2B/OpenSandbox remote sandboxes.
- Full breakpoint/resume state machine.
- Token-aware context compression.
- Provider usage accounting.
- CI configuration.
- A stable semantic-versioned API.

## Project Layout

```text
src/science_agent/
  core/              Agent runtime, events, templates, todos
  agent_runtime/     Tool execution, permissions, approval coordination
  infra/             Providers, stores, sandbox implementations
  tools/             Tool primitives, registry, built-in tools
  utils/             Small utility helpers
tests/unit/          Unit tests for runtime, store, tools, provider behavior
examples/            Local runnable examples
```

## Alpha Roadmap

Near-term work:

- Add an approval-control example under `examples/`.
- Add provider usage/token parsing.
- Add request logging hooks for provider calls.
- Add CI for tests and linting.
- Decide whether Python `3.13+` remains required or whether to support `3.11+`.
