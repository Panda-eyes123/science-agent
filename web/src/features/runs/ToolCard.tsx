import { ChevronDown, Terminal } from 'lucide-react'
import type { RunEvent, ThreadDetail } from '../../api/types'
import styles from '../../App.module.css'

// 聊天历史和侧栏复用同一展示；历史结果来自 SDK 记录，进行中的变化来自事件。
export function ToolCard({
  id,
  name,
  arguments: args,
  events,
  active,
  record,
}: {
  id: string
  name: string
  arguments: unknown
  events: RunEvent[]
  active: boolean
  record?: ThreadDetail['tool_calls'][number]
}) {
  const result = events.find(
    (e) => (e.type === 'tool.completed' || e.type === 'tool.failed') && e.call_id === id,
  )
  const waiting =
    events.some((e) => e.type === 'approval.required' && e.call_id === id) &&
    !events.some((e) => e.type === 'approval.resolved' && e.call_id === id)
  const completed = record?.state === 'COMPLETED' || result?.type === 'tool.completed'
  const failed =
    record?.state === 'FAILED' || record?.state === 'DENIED' || result?.type === 'tool.failed'
  const label = completed
    ? '已完成'
    : failed
      ? '未完成'
      : active
        ? waiting
          ? '待确认'
          : '执行中'
        : '已结束'
  const output =
    result && 'result' in result
      ? (result.error ?? result.result)
      : (record?.error ?? record?.result)
  return (
    <details className={styles.toolCard}>
      <summary>
        <Terminal size={15} />
        <strong>{name}</strong>
        <span>{label}</span>
        <ChevronDown size={14} />
      </summary>
      <pre>{JSON.stringify(args, null, 2)}</pre>
      {output !== undefined && output !== null && (
        <pre>{typeof output === 'string' ? output : JSON.stringify(output, null, 2)}</pre>
      )}
    </details>
  )
}
