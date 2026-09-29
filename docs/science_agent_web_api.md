# science_agent_web 接口文档

本文描述当前 `0.1.0` Web API。路由实现见 [app.py](../src/science_agent_web/app.py)，请求/响应及公开事件定义见 [models.py](../src/science_agent_web/models.py)。示例 ID、时间和论文内容均为演示数据。

## 访问方式与约定

| 场景 | 地址 |
| --- | --- |
| 默认宿主机入口，经 Nginx | `http://127.0.0.1:8080/api/v1` |
| 同一 Compose 网络中的容器 | `http://api:8000/api/v1` |
| FastAPI OpenAPI JSON，仅 API 容器端点 | `http://api:8000/openapi.json` |
| FastAPI Swagger UI / ReDoc，仅 API 容器端点 | `http://api:8000/docs` / `http://api:8000/redoc` |

宿主机端口可用 `deploy/.env` 的 `WEB_PORT` 修改。API 的 8000 端口默认不发布到宿主机，Nginx 仅转发 `/api/`；浏览器访问 `http://127.0.0.1:8080/docs` 或 `/openapi.json` 会进入前端页面，不能作为 Swagger 或 schema 地址。

在 `deploy/` 中可查看运行中后端的 OpenAPI：

```powershell
docker compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/openapi.json').read().decode())"
```

生成前端类型使用 `docker compose run --rm node-tools npm run types`，结果回写 `web/src/api/schema.d.ts`。Pydantic 定义是类型来源；SSE 的传输格式以本文的事件流说明为准，当前 OpenAPI 没有完整表达流式响应。

- 当前为本地单用户应用，没有登录、访问令牌或用户隔离；调用时不需要 `Authorization`。模型密钥由服务端配置，不作为 Web API 请求参数。
- 除 PDF 上传外，有请求体的接口使用 `application/json`；成功响应直接返回对象或数组，没有统一的 `data` 包装层。
- `thread_id`、`run_id`、`paper_id` 使用服务端返回的 ID，当前由 32 位小写十六进制字符串生成。`call_id` 取自审批事件，拼接 URL 时需编码。
- `created_at`、`updated_at` 是 UTC ISO 8601 字符串；事件的 `timestamp` 是 Unix 秒数，可以带小数。
- 列表接口当前无分页参数。会话按 `updated_at` 倒序，Run 历史按 `created_at` 正序，论文按 `created_at` 倒序。

## 接口总览

下表列出完整路径；除健康检查外，业务端点均以 `/api/v1` 开头。

| 方法 | 路径 | 成功状态 | 响应 / 用途 |
| --- | --- | --- | --- |
| GET | `/api/v1/info` | 200 | `ServiceInfo`，配置状态 |
| GET | `/api/v1/threads` | 200 | `ThreadSummary[]`，会话列表 |
| POST | `/api/v1/threads` | 201 | `ThreadSummary`，新建会话 |
| GET | `/api/v1/threads/{thread_id}` | 200 | `ThreadDetail`，消息、工具、Todo 与证据 |
| POST | `/api/v1/threads/{thread_id}/runs` | 202 | `Run`，发送消息并启动运行 |
| GET | `/api/v1/threads/{thread_id}/runs` | 200 | `Run[]`，会话运行历史 |
| GET | `/api/v1/threads/{thread_id}/runs/{run_id}` | 200 | `RunDetail`，运行和事件快照 |
| GET | `/api/v1/threads/{thread_id}/runs/{run_id}/events` | 200 | `text/event-stream`，历史重放与实时事件 |
| POST | `/api/v1/threads/{thread_id}/runs/{run_id}/cancel` | 200 | `Run`，请求停止运行 |
| POST | `/api/v1/threads/{thread_id}/runs/{run_id}/approvals/{call_id}` | 200 | `Run`，允许或拒绝工具调用 |
| GET | `/api/v1/papers` | 200 | `PaperSummary[]`，全局论文状态 |
| POST | `/api/v1/threads/{thread_id}/papers` | 202 | `PaperSummary`，上传 PDF 并后台入库 |
| GET | `/healthz` | 200 | API 进程健康，不在 OpenAPI 中 |

## 服务与会话

### GET /api/v1/info

无请求体。响应示例：

```json
{"model":"gpt-4.1-mini","configured":true,"rag_configured":true}
```

`configured` 表示聊天模型密钥非空；`rag_configured` 表示已设置非占位的 Embedding 密钥。它们只检查配置是否存在，不验证远端认证、网络、模型可用性或 Milvus 健康。配置缺失不影响创建会话和读取已有历史。

### GET /api/v1/threads

返回会话摘要数组，无会话时为 `[]`。每项字段见 [ThreadSummary](#threadsummary)。

### POST /api/v1/threads

无必填请求体；前端发送空 JSON 对象 `{}`。返回 `201`：

```json
{
  "id":"11111111111111111111111111111111",
  "title":"新的探索",
  "updated_at":"2026-09-29T04:00:00+00:00"
}
```

新建会话不会调用模型。标题取第一条用户消息的前 36 个字符，没有用户消息时为“新的探索”。当前没有单独的会话重命名或删除接口。

### GET /api/v1/threads/{thread_id}

返回完整会话快照，未知或非法会话 ID 返回 `404`。新建会话的示例：

```json
{
  "thread":{
    "id":"11111111111111111111111111111111",
    "title":"新的探索",
    "updated_at":"2026-09-29T04:00:00+00:00"
  },
  "messages":[],
  "tool_calls":[],
  "todos":[],
  "active_run":null,
  "evidence":[]
}
```

`active_run` 是尚未结束的 Run，包含等待审批和正在取消的状态；没有活动运行时为 `null`。`evidence` 保存历史工具调用中的证据快照，刷新页面不重新执行检索。

## 运行、审批与取消

### POST /api/v1/threads/{thread_id}/runs

请求体：

```json
{"text":"请用 fs_write 将实验计划保存到 notes/experiment.md。"}
```

`text` 必填，长度为 1–32000 个字符，服务端执行前去除首尾空白；只有空白的输入返回 `422`。同一会话同时只能有一个非终态 Run，包括等待审批和取消中的 Run，否则返回 `409`。缺少聊天模型密钥返回 `503`，未知会话返回 `404`。

成功返回 `202` 和当前 Run 快照：

```json
{
  "id":"22222222222222222222222222222222",
  "thread_id":"11111111111111111111111111111111",
  "status":"running",
  "created_at":"2026-09-29T04:00:01+00:00",
  "updated_at":"2026-09-29T04:00:01+00:00",
  "error":null
}
```

`202` 不表示回答或工具执行已经成功。任务在后台运行，返回时可能已经进入等待审批、失败或其他状态；通过 SSE 或运行详情获取最终结果。运行启动后的模型、工具错误记录为 `Run.status="failed"` 和 `Run.error`，不会再改写已返回的 HTTP 状态。

### GET /api/v1/threads/{thread_id}/runs

返回此会话的 `Run[]`，按创建时间正序排列，包括正在执行的 Run；未知会话返回 `404`。该接口不附带每次运行的事件列表。

### GET /api/v1/threads/{thread_id}/runs/{run_id}

返回 `{"run": Run, "events": RunEvent[]}`。`events` 是当前已持久化的公开事件，类型与 SSE 中的 JSON 一致；内部事件不直接暴露。未知 Run 或 Run 不属于给定会话时返回 `404`。

### POST /api/v1/threads/{thread_id}/runs/{run_id}/approvals/{call_id}

收到 `approval.required` 后，根据用户决定提交：

```json
{"decision":"allow"}
```

`decision` 只能是 `allow` 或 `deny`，其他值返回 `422`。成功返回 `200` 和当前 Run 快照，后续状态仍通过事件流或详情查询。

允许后继续工具执行；拒绝会使该工具记录变为 `DENIED`，本次 Run 最终进入 `failed`。当前 Web 中文件写入、Todo 更新及 `paper_ingest` 重试需要审批，读取和检索工具自动执行。PDF 上传接口本身直接启动入库，不等待聊天工具审批。

运行不处于 `waiting_approval`、审批已处理、已失效或 `call_id` 不匹配时返回 `409`；未知或不属于该会话的 Run 返回 `404`。服务重启后，旧审批回调不会恢复。

### POST /api/v1/threads/{thread_id}/runs/{run_id}/cancel

无必填请求体，可发送 `{}`。返回 `200` 和当前 Run 快照。取消通常先进入 `cancelling`，随后变为 `cancelled`；应继续接收事件或查询详情确认结束。

对已取消、已完成或其他终态的 Run 重复调用会返回现状。未知 Run 返回 `404`。取消不会回滚已完成的文件写入，也不会取消论文服务持有的后台入库任务。

### Run 状态

| 状态 | 含义 | 是否终态 |
| --- | --- | --- |
| `running` | 模型或工具正在执行 | 否 |
| `waiting_approval` | 等待人工审批 | 否 |
| `cancelling` | 已请求取消，正在结束任务 | 否 |
| `succeeded` | 运行成功结束 | 是 |
| `failed` | 模型、工具或审批拒绝等导致失败 | 是 |
| `cancelled` | 用户取消已完成 | 是 |
| `interrupted` | 服务停止或重启导致中断 | 是 |

常见路径为 `running → waiting_approval → running → succeeded`，或 `running / waiting_approval → cancelling → cancelled`。服务重启将保存的非终态 Run 标记为 `interrupted`，不自动重新执行工具。后台状态有竞争时，应以服务端后续事件和快照为准。

## SSE 事件流

### GET /api/v1/threads/{thread_id}/runs/{run_id}/events

| 输入 | 位置 | 约束与默认值 |
| --- | --- | --- |
| `after` | Query | 整数，`>=0`，默认 `0` |
| `Last-Event-ID` | Header | 可选整数，`>=0` |

服务端取两者的最大值，只返回 `seq` 大于该值且属于此 Run 的事件。非法游标返回 `422`；未知或不属于该会话的 Run 返回 `404`。

API 设置 `Content-Type: text/event-stream`、`Cache-Control: no-cache` 和用于控制代理缓冲的 `X-Accel-Buffering: no`。客户端按 Content-Type 和 SSE 数据解析，不依赖代理是否转发该控制头。每条消息采用标准 SSE 格式：

```text
id: 12
data: {"run_id":"22222222222222222222222222222222","seq":12,"timestamp":1790654402.5,"type":"message.delta","message_id":"44444444444444444444444444444444","delta":"实验计划"}

```

没有 `event:` 字段，事件种类由 JSON 中的 `type` 标识；浏览器应使用 `EventSource.onmessage`。空闲约 15 秒时发送注释心跳 `: heartbeat`，心跳不是 JSON 事件，没有 `seq`。

### 事件类型与字段

所有事件共享 `run_id: string`、`seq: integer`、`timestamp: number`。`seq` 在会话内递增，包含内部事件及不同 Run 的序号，因此公开事件不一定连续，不能把它当作数组下标。

| `type` | 其他字段 | 客户端用途 |
| --- | --- | --- |
| `message.delta` | `message_id`, `delta` | 按消息 ID 拼接文本片段 |
| `tool.started` | `call_id`, `name`, `arguments`, `result`, `error`, `evidence_pack` | 登记工具调用，随后可能等待审批 |
| `tool.completed` | 同上 | 展示工具结果；检索结果可附带证据 |
| `tool.failed` | 同上 | 展示工具错误，`error` 为错误说明 |
| `approval.required` | `call_id`, `name`, `arguments`, `decision` | 展示审批，`decision` 初始为 `null` |
| `approval.resolved` | 同上 | `decision` 为 `allow` 或 `deny`，`name`/`arguments` 可为默认空值 |
| `run.state` | `status`, `error` | 更新状态；终态时关闭连接 |

工具事件中的 `result` 是任意 JSON 值，`error` 为字符串或 `null`，`evidence_pack` 为 `EvidenceView` 或 `null`。开始事件通常尚无结果。`tool.started` 可能先于 `approval.required`，不表示工具已经获得执行授权；后续事件的 `arguments` 可能为空，应从开始/审批事件或历史工具记录获取完整参数。

审批和结束事件示例：

```text
id: 15
data: {"run_id":"22222222222222222222222222222222","seq":15,"timestamp":1790654403.0,"type":"approval.required","call_id":"call_example","name":"fs_write","arguments":{"path":"notes/experiment.md","content":"实验计划"},"decision":null}

id: 23
data: {"run_id":"22222222222222222222222222222222","seq":23,"timestamp":1790654405.0,"type":"run.state","status":"succeeded","error":null}

```

服务端先订阅实时事件，再补发磁盘历史，并按序号去重。连接中断不会取消任务。客户端保存最后处理的 `seq`，重新建立连接时传入 `after`；浏览器 `EventSource` 在自动重连时也会携带最近的 `Last-Event-ID`。

已有终态 Run 会在重放历史后关闭流；实时流在发送终态后关闭。客户端应在收到 `succeeded`、`failed`、`cancelled` 或 `interrupted` 时主动 `close()`，避免浏览器对已结束的运行持续自动重连。对传输断开和无法判断的连接错误，可查询 Run 详情恢复状态。

浏览器接入示例：

```javascript
const terminal = new Set(['succeeded', 'failed', 'cancelled', 'interrupted'])
let lastSeq = 0 // 页面恢复时使用已保存的游标
const source = new EventSource(
  `/api/v1/threads/${threadId}/runs/${runId}/events?after=${lastSeq}`,
)
source.onmessage = ({ data }) => {
  const event = JSON.parse(data)
  if (event.seq <= lastSeq) return
  lastSeq = event.seq
  // 保存游标，并按 type 更新文本、工具或审批 UI。
  if (event.type === 'run.state' && terminal.has(event.status)) source.close()
}
source.onerror = () => {
  // EventSource 会自动重连；必要时 GET Run 详情核对状态或显示连接错误。
}
```

## 论文上传与状态

### POST /api/v1/threads/{thread_id}/papers

使用 `multipart/form-data`，文件字段名为 `file`。上传必须关联一个已存在的会话；文件名仅用于展示，服务器按生成的 `paper_id` 保存文件。

```powershell
curl.exe -X POST 'http://127.0.0.1:8080/api/v1/threads/11111111111111111111111111111111/papers' -F 'file=@C:/papers/study.pdf;type=application/pdf'
```

将示例中的会话 ID 和文件路径替换为实际值。浏览器使用 `FormData`，不要手工设置 multipart 的 `Content-Type`，以便浏览器生成 boundary。

文件扩展名必须为 `.pdf`（不区分大小写），文件头必须以 `%PDF-` 开始，文件最大为 `50 * 1024 * 1024` 字节（50 MiB）。Nginx 的请求体上限为 64 MiB，包含 multipart 开销。通过上传检查不等于 PDF 已完整解析。

成功返回 `202`：

```json
{
  "paper_id":"33333333333333333333333333333333",
  "thread_id":"11111111111111111111111111111111",
  "filename":"study.pdf",
  "title":null,
  "status":"indexing",
  "created_at":"2026-09-29T04:00:06+00:00",
  "updated_at":"2026-09-29T04:00:06+00:00",
  "error":null
}
```

后台继续进行解析、分块和向量入库。`202` 不是入库完成信号，应轮询论文列表直到状态为 `ready`、`failed` 或 `interrupted`。论文状态不通过聊天 Run 的 SSE 单独推送。

缺少文件字段返回 `422`；会话不存在返回 `404`；缺少 Embedding 配置返回 `503`；扩展名或文件头不符返回 `415`；超过文件大小上限返回 `413`。上传后解析、Embedding 或 Milvus 失败体现在论文状态及 `error` 中。

### GET /api/v1/papers

返回全局 `PaperSummary[]`，包括入库中、可检索、失败及中断的论文，无论文时为 `[]`。`thread_id` 表示上传所属会话，不限制其他会话检索；所有会话共享 `ready` 的论文。

| 论文状态 | 含义 |
| --- | --- |
| `indexing` | 已接收，排队或正在入库 |
| `ready` | 入库完成，可参与检索 |
| `failed` | 入库失败，查看 `error` |
| `interrupted` | 服务停止/重启，入库未完成 |

服务不自动重放失败或中断任务。可发送聊天消息让助手使用 `paper_ingest`，参数为已登记的 `paper_id`；这是需要审批的写工具。已就绪论文重复执行该工具会直接返回状态。重复上传同一个文件会生成新的论文 ID，不按文件内容去重。

当前没有单独的 HTTP 检索、入库重试、论文删除或 PDF 下载端点。检索通过聊天中的 `paper_search` 工具执行，结果中的公开证据随工具事件和会话历史返回。

## 数据结构

### ThreadSummary

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | string | 会话 ID |
| `title` | string | 首条用户消息前 36 个字符，或默认标题 |
| `updated_at` | string | 会话更新时间 |

### Run 与 RunDetail

`Run` 包含 `id`、`thread_id`、`status`、`created_at`、`updated_at` 和可空的 `error`。状态枚举见前文。`RunDetail` 包含 `run: Run` 和 `events: RunEvent[]`。

### ThreadDetail

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `thread` | ThreadSummary | 会话摘要 |
| `messages` | Message[] | 已保存的消息，按会话消息顺序 |
| `tool_calls` | ToolCallRecord[] | 工具记录，检索证据单独投影到 `evidence` |
| `todos` | TodoItem[] | 当前研究任务 |
| `active_run` | Run / null | 非终态运行 |
| `evidence` | RunEvidence[] | 历史检索证据快照 |

### Message、ToolCallRequest 与 ToolCallRecord

| 结构 | 字段 |
| --- | --- |
| `Message` | `id: string`、`role: system / user / assistant / tool`、`content: string`、`name: string / null`、`tool_call_id: string / null`、`tool_calls: ToolCallRequest[]`、`run_id: string / null` |
| `ToolCallRequest` | `name: string`、`arguments: object`、`call_id: string / null` |
| `ToolCallRecord` | `call_id: string`、`name: string`、`arguments: object`、`state: ToolCallState`、`result: any / null`、`error: string / null`、`created_at: string`、`updated_at: string`、`run_id: string / null` |

`ToolCallState` 为 `PENDING`、`APPROVAL_REQUIRED`、`APPROVED`、`EXECUTING`、`COMPLETED`、`FAILED`、`DENIED`。它与 Run 的小写状态是两套不同的枚举。

### TodoItem 与 PaperSummary

`TodoItem` 包含 `id`、`content`、`status`、`created_at`、`updated_at`；`status` 为 `pending`、`in_progress` 或 `completed`。

`PaperSummary` 包含 `paper_id`、`thread_id`、`filename`、`title`、`status`、`created_at`、`updated_at`、`error`；`title` 和 `error` 可为 `null`，其余字段为字符串。`title` 缺失时客户端可以用 `filename` 展示。

### EvidenceView 与 RunEvidence

`RunEvidence` 将 `run_id`、`call_id` 和 `evidence_pack: EvidenceView` 关联起来。`EvidenceView` 也可出现在 `tool.completed` 等工具事件的 `evidence_pack` 字段中：

```json
{
  "query":"论文中的培养条件是什么？",
  "route":"method",
  "items":[{
    "chunk_id":"example-chunk-1",
    "paper_id":"33333333333333333333333333333333",
    "title":"示例论文",
    "section_kind":"method",
    "score":0.032,
    "excerpt":"酵母样本在 30°C 培养。",
    "sources":[{
      "element_id":"example-element-1",
      "page_no":2,
      "element_type":"paragraph",
      "text":"酵母样本在 30°C 培养。"
    }]
  }]
}
```

| 结构 | 字段说明 |
| --- | --- |
| `EvidenceView` | `query: string`、`route: SectionKind / null`、`items: EvidenceItem[]` |
| `EvidenceItem` | `chunk_id: string`、`paper_id: string / null`、`title: string / null`、`section_kind: SectionKind / null`、`score: number`、`excerpt: string`、`sources: EvidenceSource[]` |
| `EvidenceSource` | `element_id: string`、`page_no: integer / null`、`element_type: ElementType`、`text: string` |

`SectionKind` 为 `background`、`method`、`experiment`、`result`、`discussion`、`other`。`ElementType` 为 `title`、`section_heading`、`paragraph`、`list`、`table`、`figure`、`caption`、`formula`、`code`、`reference`、`other`。

页码从 1 开始，缺失时为 `null`。`score` 是检索排名分数，不是答案正确率。公开证据不包含源文件路径、图片路径或解析器内部载荷；它表示检索来源，不代表回答已经逐句校验。

## 健康检查与错误处理

### GET /healthz

直接请求 API 容器时返回 `200` 和 `{"status":"ok"}`，表示应用完成启动并能够响应 HTTP，不检测外部模型或 Milvus 连通性，也不在 OpenAPI schema 中。

宿主机 `http://127.0.0.1:8080/healthz` 由 Nginx 自身响应，返回纯文本 `ok`，不能据此判断 API 或检索链路健康。各容器状态可用 `docker compose ps` 查看。

### HTTP 错误

应用层 `ServiceError` 返回：

```json
{"detail":"当前会话仍在运行，请等待结束或停止后再发送。"}
```

| HTTP 状态 | 典型原因 |
| --- | --- |
| `404` | 会话不存在、Run 不存在或不属于该会话 |
| `409` | 同一会话已有活动 Run；当前不在审批状态；审批已处理或失效 |
| `413` | API 的 PDF 文件上限或 Nginx 的请求体上限被触发 |
| `415` | 文件扩展名不是 PDF，或内容没有 PDF 文件头 |
| `422` | JSON/参数校验失败、缺少 `file`、`text` 长度非法/仅空白、审批值或 SSE 游标非法 |
| `503` | 启动 Run 前缺少聊天模型配置，或上传前缺少 Embedding 配置 |

FastAPI 参数校验错误的 `detail` 是数组，而不是字符串，例如：

```json
{"detail":[{"type":"missing","loc":["body","text"],"msg":"Field required","input":{}}]}
```

未处理异常可能返回 `500`，代理层可能返回 `502`/`504` 或 HTML 错误页；客户端不能假设所有失败响应都是 JSON。中文 `detail` 用于展示，不应当作稳定的业务错误码。

已经接受的后台任务失败，使用 Run / Paper 的 `status` 和 `error` 表达。例如密钥非空但远端认证失败时，Run 可能先返回 `202` 再进入 `failed`，不会由 Web API 改为同步 `401`。

## 最小调用流程

以下为 PowerShell 示例，默认应用已启动。创建会话并发送消息：

```powershell
$api = 'http://127.0.0.1:8080/api/v1'
$thread = Invoke-RestMethod -Method Post -Uri "$api/threads" -ContentType 'application/json; charset=utf-8' -Body '{}'
$body = @{ text = '请总结实验设计中的对照组作用。' } | ConvertTo-Json
$run = Invoke-RestMethod -Method Post -Uri "$api/threads/$($thread.id)/runs" -ContentType 'application/json; charset=utf-8' -Body $body
curl.exe -N "$api/threads/$($thread.id)/runs/$($run.id)/events?after=0"
```

如果收到 `approval.required`，在另一个终端填入会话、Run 和调用 ID，再提交人工决定：

```powershell
$url = 'http://127.0.0.1:8080/api/v1/threads/THREAD_ID/runs/RUN_ID/approvals/CALL_ID'
Invoke-RestMethod -Method Post -Uri $url -ContentType 'application/json' -Body '{"decision":"allow"}'
```

需要停止时调用对应 Run 的 `/cancel`，结束后读取会话详情或 Run 详情恢复完整记录。创建会话、启动运行和重复上传不提供幂等键；请求超时后应先查询当前会话/Run 状态，避免盲目重试产生重复任务。
