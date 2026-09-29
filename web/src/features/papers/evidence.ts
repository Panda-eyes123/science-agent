import type { RunEvent, RunEvidence, ThreadDetail } from '../../api/types'

export function collectEvidence(detail: ThreadDetail | null, events: RunEvent[]): RunEvidence[] {
  const records = new Map<string, RunEvidence>()
  for (const evidence of detail?.evidence ?? [])
    records.set(`${evidence.run_id}:${evidence.call_id}`, evidence)
  // 重放与快照可能覆盖同一工具调用，按 run_id + call_id 合并后只显示一份引用。
  for (const event of events) {
    if (event.type === 'tool.completed' && event.evidence_pack) {
      records.set(`${event.run_id}:${event.call_id}`, {
        run_id: event.run_id,
        call_id: event.call_id,
        evidence_pack: event.evidence_pack,
      })
    }
  }
  return [...records.values()]
}
