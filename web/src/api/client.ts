import type { Paper, Run, RunDetail, RunEvent, ServiceInfo, Thread, ThreadDetail } from './types'

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    `/api/v1${path}`,
    body === undefined
      ? undefined
      : {
          method: 'POST',
          headers: body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
          body: body instanceof FormData ? body : JSON.stringify(body),
        },
  )
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(
      typeof data?.detail === 'string' ? data.detail : `请求失败（${response.status}）`,
    )
  }
  return response.json() as Promise<T>
}

const runPath = (thread: string, run: string) => `/threads/${thread}/runs/${run}`
export const api = {
  info: () => request<ServiceInfo>('/info'),
  threads: () => request<Thread[]>('/threads'),
  createThread: () => request<Thread>('/threads', {}),
  papers: () => request<Paper[]>('/papers'),
  uploadPaper: (thread: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Paper>(`/threads/${thread}/papers`, form)
  },
  thread: (id: string) => request<ThreadDetail>(`/threads/${id}`),
  runs: (id: string) => request<Run[]>(`/threads/${id}/runs`),
  run: (thread: string, run: string) => request<RunDetail>(runPath(thread, run)),
  send: (id: string, text: string) => request<Run>(`/threads/${id}/runs`, { text }),
  cancel: (thread: string, run: string) => request<Run>(`${runPath(thread, run)}/cancel`, {}),
  approve: (thread: string, run: string, call: string, decision: 'allow' | 'deny') =>
    request<Run>(`${runPath(thread, run)}/approvals/${encodeURIComponent(call)}`, { decision }),
  subscribe: (
    thread: string,
    run: string,
    after: number,
    onEvent: (event: RunEvent) => void,
    onConnection: (connected: boolean) => void,
  ) => {
    const source = new EventSource(`/api/v1${runPath(thread, run)}/events?after=${after}`)
    source.onopen = () => onConnection(true)
    source.onmessage = (event) => onEvent(JSON.parse(event.data) as RunEvent)
    source.onerror = () => onConnection(false)
    return () => source.close()
  },
}
