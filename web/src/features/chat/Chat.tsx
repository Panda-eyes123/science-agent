import { useEffect, useRef, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  Check,
  FlaskConical,
  Lightbulb,
  LoaderCircle,
  Paperclip,
  ShieldCheck,
  Square,
  Terminal,
  X,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message, Run, RunEvent, ThreadDetail, ToolEvent } from '../../api/types'
import { statusLabel, terminal } from '../../api/types'
import styles from '../../App.module.css'
import { ToolCard } from '../runs/ToolCard'
import { EvidenceList } from '../papers/EvidenceList'
import { collectEvidence } from '../papers/evidence'

type Approval = Extract<RunEvent, { type: 'approval.required' | 'approval.resolved' }>
export function Chat({
  detail,
  events,
  run,
  busy,
  connected,
  onSend,
  onStop,
  onApprove,
  onOpenPapers,
}: {
  detail: ThreadDetail | null
  events: RunEvent[]
  run: Run | null
  busy: boolean
  connected: boolean
  onSend: (text: string) => Promise<void>
  onStop: () => void
  onApprove: (call: string, decision: 'allow' | 'deny') => Promise<void>
  onOpenPapers: () => void
}) {
  const [draft, setDraft] = useState('')
  const [following, setFollowing] = useState(true)
  const viewport = useRef<HTMLDivElement>(null)
  const composing = useRef(false)
  const active = !!run && !terminal(run.status)
  const evidence = collectEvidence(detail, events)
  const messages = [...(detail?.messages ?? [])].filter(
    (m) => m.role === 'user' || (m.role === 'assistant' && (m.content || m.tool_calls?.length)),
  )
  // 已落盘的消息以快照为准；仍在生成或已中断的部分文本从事件恢复，按消息 ID 合并。
  const streamed = new Map<string, string>()
  for (const event of events)
    if (event.type === 'message.delta')
      streamed.set(event.message_id, (streamed.get(event.message_id) ?? '') + event.delta)
  for (const [id, content] of streamed)
    if (!messages.some((m) => m.id === id))
      messages.push({ id, role: 'assistant', content, run_id: run?.id, tool_calls: [] } as Message)
  const approvals = events.filter(
    (e): e is Approval =>
      e.type === 'approval.required' &&
      !events.some((later) => later.type === 'approval.resolved' && later.call_id === e.call_id),
  )
  const tools = events.filter(
    (e): e is ToolEvent =>
      e.type === 'tool.started' &&
      !messages.some(
        (message) =>
          message.run_id === e.run_id &&
          message.tool_calls?.some((call) => call.call_id === e.call_id),
      ),
  )

  useEffect(() => {
    setDraft('')
    setFollowing(true)
  }, [detail?.thread.id])
  useEffect(() => {
    if (following && viewport.current)
      viewport.current.scrollTop = messages.length || active ? viewport.current.scrollHeight : 0
  }, [events.length, messages.length, following, active])

  async function submit() {
    const text = draft.trim()
    if (!text || busy || active) return
    try {
      await onSend(text)
      setDraft('')
      setFollowing(true)
    } catch {
      /* 错误由工作台统一展示，保留草稿供用户修改。 */
    }
  }

  return (
    <>
      <div
        className={styles.transcript}
        ref={viewport}
        onScroll={() => {
          const el = viewport.current!
          setFollowing(el.scrollHeight - el.scrollTop - el.clientHeight < 80)
        }}
      >
        {!messages.length && !active ? (
          <div className={styles.welcome}>
            <div className={styles.welcomeMark}>
              <FlaskConical size={30} strokeWidth={1.5} />
            </div>
            <div className={styles.eyebrow}>A SPACE FOR YOUR NEXT DISCOVERY</div>
            <h1>
              把一个想法，
              <br />
              <span>变成下一步探索。</span>
            </h1>
            <p>
              梳理问题、拆解计划，或记录一次新的发现。
              <br />
              你的研究助手，已经准备就绪。
            </p>
            <div className={styles.suggestions}>
              <button
                onClick={() =>
                  setDraft('帮我梳理一个关于温度如何影响酵母生长的研究问题，并说明关键变量。')
                }
              >
                <Lightbulb size={19} />
                <strong>梳理研究思路</strong>
                <span>从问题出发，找到探索方向</span>
                <ArrowUp size={15} />
              </button>
              <button onClick={() => setDraft('使用 todo_write 为一项对照实验创建三个研究任务。')}>
                <Check size={19} />
                <strong>制定实验计划</strong>
                <span>把目标拆解为可执行的步骤</span>
                <ArrowUp size={15} />
              </button>
              <button
                onClick={() =>
                  setDraft('用 fs_write 将一份简短的实验观察模板写入 notes/experiment.md。')
                }
              >
                <Terminal size={19} />
                <strong>整理研究记录</strong>
                <span>将思考保存到本地工作空间</span>
                <ArrowUp size={15} />
              </button>
            </div>
          </div>
        ) : (
          <div className={styles.messageList}>
            {messages.map((message, index) => (
              <article
                key={message.id}
                className={message.role === 'user' ? styles.userMessage : styles.assistantMessage}
              >
                <div className={styles.messageBy}>
                  {message.role === 'user' ? (
                    <span className={styles.userAvatar}>你</span>
                  ) : (
                    <span className={styles.agentAvatar}>
                      <FlaskConical size={15} />
                    </span>
                  )}
                  <strong>{message.role === 'user' ? '你' : 'Science Agent'}</strong>
                  {message.role === 'assistant' && <span>研究助手</span>}
                </div>
                <div className={styles.markdown}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
                    {message.content}
                  </ReactMarkdown>
                </div>
                {message.tool_calls?.map((call) => (
                  <ToolCard
                    key={call.call_id}
                    id={call.call_id!}
                    name={call.name}
                    arguments={call.arguments}
                    events={message.run_id === run?.id ? events : []}
                    active={active && message.run_id === run?.id}
                    record={detail?.tool_calls.find(
                      (record) =>
                        record.call_id === call.call_id && record.run_id === message.run_id,
                    )}
                  />
                ))}
                {!messages.slice(index + 1).some((later) => later.run_id === message.run_id) &&
                  evidence
                    .filter((item) => item.run_id === message.run_id)
                    .map((item) => (
                      <EvidenceList
                        key={`${item.run_id}:${item.call_id}`}
                        pack={item.evidence_pack}
                      />
                    ))}
              </article>
            ))}
            {tools.map((tool) => (
              <ToolCard
                key={tool.call_id}
                id={tool.call_id}
                name={tool.name}
                arguments={tool.arguments}
                events={events}
                active={active}
              />
            ))}
            {active &&
              approvals.map((approval) => (
                <ApprovalCard key={approval.call_id} event={approval} onApprove={onApprove} />
              ))}
            {active && (
              <div className={styles.running}>
                <LoaderCircle size={15} className={styles.spin} />
                {run && statusLabel[run.status]}
                <span>{connected ? '任务进行中' : '连接中断，正在重连…'}</span>
              </div>
            )}
            {run && terminal(run.status) && (
              <div className={run.status === 'failed' ? styles.runError : styles.runEnd}>
                {run.status === 'succeeded' ? <Check size={14} /> : <Square size={12} />}
                {statusLabel[run.status]}
                {run.error && <span>{run.error}</span>}
              </div>
            )}
          </div>
        )}
      </div>
      <div className={styles.composerArea}>
        {!following && (
          <button className={styles.followButton} onClick={() => setFollowing(true)}>
            <ArrowDown size={14} /> 回到最新
          </button>
        )}
        <div className={styles.composer}>
          <textarea
            aria-label="发送消息"
            placeholder="描述你的研究问题，或告诉我下一步想做什么…"
            value={draft}
            rows={3}
            onChange={(e) => setDraft(e.target.value)}
            onCompositionStart={() => {
              composing.current = true
            }}
            onCompositionEnd={() => {
              composing.current = false
            }}
            onKeyDown={(e) => {
              if (
                e.key === 'Enter' &&
                !e.shiftKey &&
                !e.nativeEvent.isComposing &&
                !composing.current
              ) {
                e.preventDefault()
                void submit()
              }
            }}
          />
          <div className={styles.composerFooter}>
            <button className={styles.paperButton} onClick={onOpenPapers}>
              <Paperclip size={14} /> 论文库
            </button>
            <span>
              <ShieldCheck size={14} /> 写入前由你确认
            </span>
            {active ? (
              <button
                className={styles.sendButton}
                onClick={onStop}
                disabled={run?.status === 'cancelling'}
                aria-label="停止运行"
              >
                <Square size={16} fill="currentColor" />
              </button>
            ) : (
              <button
                className={styles.sendButton}
                onClick={() => void submit()}
                disabled={!draft.trim() || busy}
                aria-label="发送"
              >
                <ArrowUp size={19} />
              </button>
            )}
          </div>
        </div>
        <div className={styles.composerHint}>
          <span>结果仅供研究参考，请核实重要信息。</span>
          <span>Enter 发送 · Shift + Enter 换行</span>
        </div>
      </div>
    </>
  )
}

function ApprovalCard({
  event,
  onApprove,
}: {
  event: Approval
  onApprove: (call: string, decision: 'allow' | 'deny') => Promise<void>
}) {
  const [pending, setPending] = useState(false)
  async function decide(decision: 'allow' | 'deny') {
    setPending(true)
    try {
      await onApprove(event.call_id, decision)
    } catch {
      setPending(false)
    }
  }
  return (
    <div className={styles.approval}>
      <div className={styles.approvalHeading}>
        <ShieldCheck size={20} />
        <div>
          <strong>这一步，需要你的确认</strong>
          <p>研究助手希望执行 {event.name}</p>
        </div>
      </div>
      <pre>{JSON.stringify(event.arguments, null, 2)}</pre>
      <div className={styles.approvalActions}>
        <button disabled={pending} onClick={() => void decide('deny')}>
          <X size={14} /> 拒绝
        </button>
        <button disabled={pending} onClick={() => void decide('allow')}>
          <Check size={14} /> 允许执行
        </button>
      </div>
    </div>
  )
}
