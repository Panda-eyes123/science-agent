# science-agent

事件驱动的研究 Agent SDK 与本地单用户研究工作台。支持模型流式回答、文件工具、人工审批、会话历史，以及 PDF 上传、Milvus 混合检索和来源证据。

## 项目目录结构

```text
science-agent/
├── src/
│   ├── science_agent/             # Python SDK，不依赖 Web 框架
│   │   ├── core/                  # Agent 循环、事件、模板、上下文与 Todo
│   │   ├── agent_runtime/         # 工具执行、权限判断与人工审批
│   │   ├── tools/                 # 文件、Todo、论文检索等工具定义和注册
│   │   ├── rag/                   # 分块、入库、检索、证据与多模态编排
│   │   ├── wiki/                  # 知识页面、变更集、引用校验与索引接口
│   │   ├── infra/                 # 模型 API、Docling、Milvus、文件存储等适配器
│   │   ├── utils/                 # 日志和 ID 等公共辅助函数
│   │   ├── config.py              # SDK 默认配置与数据目录
│   │   └── types.py               # 消息、模型响应、工具记录和事件数据结构
│   └── science_agent_web/         # FastAPI 应用，单向依赖 SDK
│       ├── app.py                 # HTTP 路由、SSE 与应用生命周期
│       ├── models.py              # 请求/响应 DTO 和公开事件契约
│       ├── service.py             # 会话、Run、审批、取消与事件重放
│       ├── papers.py              # PDF 上传、论文状态与后台入库
│       ├── adapter.py             # SDK 装配及内部事件到公开事件的转换
│       └── errors.py              # 应用层错误及 HTTP 状态
├── web/                          # React / TypeScript 前端源码和构建配置
│   └── src/
│       ├── api/                   # HTTP/SSE 客户端、生成的 OpenAPI 类型
│       ├── features/              # 会话、聊天、运行详情和论文库功能
│       └── App.tsx                # 工作台页面装配
├── deploy/                       # Docker 编排、镜像、配置模板及依赖清单/锁文件
├── docs/                         # 接口等开发文档
│   └── science_agent_web_api.md   # 当前 Web API 的完整使用说明
├── tests/
│   ├── unit/                     # SDK、Web、RAG 和迁移逻辑测试
│   └── integration/              # 按需启用的真实 Milvus 与容器 HTTP 验收
├── examples/                     # SDK 基础使用、工具、持久化和真实模型示例
└── README.md
```

浏览器通过 HTTP/SSE 访问 `science_agent_web`，Web 层调用 `science_agent`，SDK 不反向依赖 Web 层。业务逻辑在 SDK 和 Web 服务层维护，页面交互在 `web/src/features/` 维护，部署和包管理统一在 `deploy/` 维护。运行数据和模型缓存放在 Docker 数据卷中，不放入源码目录。

## 接口文档

完整说明见 [science_agent_web 接口文档](docs/science_agent_web_api.md)，包含全部业务端点、请求/响应字段、SSE 事件及续传、审批与取消、论文上传与错误处理。

默认浏览器 API 地址为 `http://127.0.0.1:8080/api/v1`。FastAPI 的 `/docs`、`/redoc` 和 `/openapi.json` 位于 API 容器内，默认 Nginx 不转发这些路径；访问方式和 OpenAPI 导出命令见接口文档。

## Docker 部署

宿主机只需要 Docker Engine / Docker Desktop（Linux 容器）及 Docker Compose。Python、Node、uv、npm 和测试工具都在容器中运行。

首次使用，在项目根目录执行：

```powershell
cd deploy
Copy-Item .env.example .env
```

编辑 `deploy/.env` 中的 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`。Embedding 可以单独配置，留空的密钥和地址沿用 OpenAI 配置；`EMBEDDING_DIM` 必须匹配模型输出。更换向量维度时使用新的 `MILVUS_COLLECTION`。

```powershell
docker compose --env-file .env up -d --build --wait
docker compose ps
```

打开 <http://127.0.0.1:8080>，端口由 `WEB_PORT` 配置。后续命令均在 `deploy/` 下执行。已有 `.env` 时直接编辑，不要再次复制覆盖。

| 服务 | 用途 | 数据 |
| --- | --- | --- |
| web | Nginx 静态页面与 `/api` 代理，仅绑定本机端口 | 镜像中的前端构建产物 |
| api | Python 3.13、FastAPI、单进程 Uvicorn | `/data`、`/cache` 命名卷 |
| milvus | Milvus 2.6.16，本地存储 | `/var/lib/milvus` 命名卷 |
| etcd | etcd 3.5.23，Milvus 元数据 | 同一卷中的 `/var/lib/milvus/etcd` |

API 和 Milvus 不发布宿主机端口；容器通过 `http://milvus:19530` 连接。若模型服务运行在宿主机，Docker Desktop 中使用 `host.docker.internal`，不能使用容器自己的 `127.0.0.1`。

etcd 使用与原内嵌版本相同的版本和数据目录，独立通过健康检查后才启动 Milvus。这样避免 Milvus 2.6.16 内嵌 etcd 重启时选主尚未完成、session 初始化直接 panic 的竞态；不改变索引内容或引入对象存储。

后端必须保持一个进程、一个实例：运行任务、实时订阅和审批回调由该进程持有。容器重启保留历史，但未完成任务会标记为中断，不自动重放工具。API `/healthz` 检查进程响应，不执行收费模型请求，也不表示所有外部模型可用。

```powershell
docker compose logs --tail 100 api
docker compose restart api
docker compose down
```

`down` 保留数据卷；`down -v` 会删除卷中的数据。更改环境变量后用 `docker compose up -d --force-recreate api`，单纯 `restart` 不会更新环境变量。

## 部署与依赖目录

```text
deploy/
  compose.yaml                 # 应用、工具与迁移服务
  .env.example                 # 配置模板；.env 不提交
  api.Dockerfile               # Python 构建、运行、工具、锁文件目标
  api.Dockerfile.dockerignore
  web.Dockerfile               # Node 构建、工具与 Nginx 运行目标
  web.Dockerfile.dockerignore
  nginx.conf                   # SSE、上传大小、容器 DNS
  toolbox.sh                   # 容器标准工作目录与依赖清单回写
  python/pyproject.toml
  python/uv.lock
  node/package.json
  node/package-lock.json
  scripts/migrate.py           # 旧数据复制、校验、路径迁移
  backups/                     # 本地迁移备份，不提交
```

源码仍位于 `src/`、`web/`，测试位于 `tests/`。构建时将集中存放的清单放到容器内 `/app` 和 `/app/web` 的标准位置。宿主机不维护虚拟环境、`node_modules`、构建输出或附带的 Python/uv 安装。

Python 通过 uv 锁定依赖并安装到专用镜像的系统 Python 环境。Docling 使用 CPU 版 PyTorch；运行镜像不安装测试依赖。前端按 `package-lock.json` 执行 `npm ci`，最终镜像只包含 Nginx 与静态资源。

## 容器内开发检查

工具服务属于 `tools` profile，不随应用默认启动。首次构建：

```powershell
docker compose build python-tools node-tools
```

```powershell
docker compose run --rm python-tools pytest -q
docker compose run --rm python-tools ruff check src tests examples deploy/scripts
docker compose run --rm node-tools npm run lint
docker compose run --rm node-tools npm run build
docker compose run --rm node-tools npm run format
```

工具容器按目录挂载源码，格式化修改会回写；构建输出和测试临时数据留在容器中。工具服务的 `/data` 为临时存储，不挂载正式会话卷。模型缓存复用 `/cache`。示例也可运行：

```powershell
docker compose run --rm python-tools python examples/getting_started.py
docker compose run --rm python-tools python examples/tool_usage.py
docker compose run --rm python-tools python examples/persistence_resume.py
```

后端运行时，重新生成 API 类型：

```powershell
docker compose run --rm node-tools npm run types
```

Pydantic 定义是公开类型来源，生成的 `web/src/api/schema.d.ts` 提交到版本库，不手工修改。

真实 PDF / Milvus 集成测试使用独立 collection 和确定性向量，不调用外部 Embedding/LLM：

```powershell
docker compose up -d --wait milvus
docker compose run --rm -e SCIENCE_AGENT_TEST_MILVUS=1 python-tools pytest tests/integration/test_milvus_rag.py -q
```

首次解析可能下载 Docling 布局/OCR 模型，需要联网；`/cache/huggingface` 与 `/cache/docling` 会保留下载结果。LLM、Embedding 和可选 VLM 仍通过外部 API 提供。

## 更新依赖

轻量 `python-lock` 工具不依赖当前应用锁文件已可安装，可用于修复或更新依赖：

```powershell
docker compose build python-lock
docker compose run --rm python-lock uv lock
docker compose run --rm python-lock uv add --no-sync httpx
docker compose run --rm python-lock uv add --no-sync --optional dev pytest
docker compose run --rm python-lock uv remove --no-sync some-package
```

Node 依赖更新示例：

```powershell
docker compose run --rm node-tools npm install some-package
docker compose run --rm node-tools npm uninstall some-package
```

命令成功后，工具入口将更改过的清单及锁文件回写 `deploy/python/` 或 `deploy/node/`。随后重建应用及对应工具镜像，确保后续测试使用新依赖：

```powershell
docker compose build api web python-tools node-tools
docker compose up -d --wait
```

## 数据与旧环境迁移

`science-agent-data` 保存会话 JSON、事件、工具记录、论文状态、上传 PDF、解析产物、工作空间和 Wiki Markdown。`science-agent-model-cache` 保存可重新下载的模型资源。Milvus 卷名由 `MILVUS_VOLUME_NAME` 指定；新环境默认 `science-agent-milvus`。

从旧版本迁移时：先停止原生后端和旧 Milvus 容器；在 `.env` 将 `MILVUS_VOLUME_NAME` 设为旧卷名（原默认 `science-agent-rag_milvus`），并设置 `MILVUS_VOLUME_EXTERNAL=true`，从而接续原索引。该外部卷不由新 Compose 创建或删除。不要同时让两个 Milvus 实例写入同一数据卷。

在正式 API 启动前，从宿主机旧 `.local` 目录迁移。下面路径需替换为实际项目路径：

```powershell
docker compose build python-tools
docker compose up -d --wait milvus
docker compose run --rm --no-deps --volume 'D:/sci-wiki/science-agent/.local:/legacy:ro' maintenance python /app/deploy/scripts/migrate.py --old-data-root 'D:/sci-wiki/science-agent/.local/data'
docker compose up -d --wait
```

迁移工具先备份会话和工作空间，再复制并逐文件验证 SHA-256；目标已有不同内容时停止，不覆盖。它会备份并重写当前 corpus 中匹配旧根目录的 PDF/图片路径，保留原向量。备份和校验清单存放在 `deploy/backups/`。非默认旧数据目录使用 `--data-subdir` 和 `--old-data-root` 指定。

验证历史、论文检索和文件后，再删除旧虚拟环境、工具安装、构建输出及已迁移数据。备份需要和数据卷一起保留；仅删除镜像不会删除会话。

## 研究工作台

新建会话后，可要求助手用 `fs_write` 保存研究记录。文件写入和 Todo 更新需要审批，读工具自动执行。网页断开不会停止后台任务，刷新后可续传事件和继续审批；停止运行不会回滚已完成的文件写入。

右侧全局论文库支持上传不超过 50 MiB 的 PDF。所有会话共享已就绪论文，上传后后台自动入库，停止聊天不取消入库。失败或中断时可让助手按论文 ID 使用 `paper_ingest` 重试，该写工具仍需审批。

检索采用 BM25 与向量召回的 RRF 融合，不调用外部重排模型。证据展示实际命中的论文、章节、页码和摘录；缺失页码不会补造。来源证据不表示模型回答已逐句校验。Embedding API 会接收论文片段，模型 API 会接收检索证据；密钥仅在服务端使用。

## SDK 与模块边界

SDK 支持 `await agent.send(text)`；流式调用使用 `stream=True` 并订阅事件。工具层可单独装配 Docling、Embedding、Milvus、API reranker 和可选图表 VLM。容器环境中默认数据根为 `/data`，也可显式注入存储或通过 `SCIENCE_AGENT_DATA_DIR` 更改。

Wiki 编译层采用 `RawSourceSnapshot + WikiPage -> WikiChangeset -> 审批 -> Markdown` 流程。引用白名单、结构和版本检查通过后才能写回；Markdown 是权威存储，Milvus Wiki 索引可重建。源论文更新只将关联页面标记为 stale。该领域接口尚未接入 Web 页面。
