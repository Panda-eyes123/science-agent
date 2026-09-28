import type { components } from './schema'

export type Thread = components['schemas']['ThreadSummary']
export type ThreadDetail = components['schemas']['ThreadDetail']
export type Run = components['schemas']['Run']
export type RunDetail = components['schemas']['RunDetail']
export type RunEvent = RunDetail['events'][number]
export type ToolEvent = components['schemas']['ToolEvent']
export type Message = ThreadDetail['messages'][number]
export type ServiceInfo = components['schemas']['ServiceInfo']
export const terminal = (status: Run['status']) =>
  ['succeeded', 'failed', 'cancelled', 'interrupted'].includes(status)
export const statusLabel: Record<Run['status'], string> = {
  running: '正在执行',
  waiting_approval: '等待你的确认',
  cancelling: '正在停止',
  succeeded: '已完成',
  failed: '执行失败',
  cancelled: '已停止',
  interrupted: '运行已中断',
}
