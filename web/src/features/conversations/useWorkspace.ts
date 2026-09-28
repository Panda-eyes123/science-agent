import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { Run, RunEvent, ServiceInfo, Thread, ThreadDetail } from '../../api/types'
import { terminal } from '../../api/types'

export function useWorkspace() {
  const [threads, setThreads] = useState<Thread[]>([])
  const [selected, setSelected] = useState<string | null>(
    new URLSearchParams(location.search).get('thread'),
  )
  const [detail, setDetail] = useState<ThreadDetail | null>(null)
  const [runs, setRuns] = useState<Run[]>([])
  const [run, setRun] = useState<Run | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const [info, setInfo] = useState<ServiceInfo | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [connected, setConnected] = useState(true)
  const selection = useRef(selected)
  selection.current = selected
  const seen = useRef(0)
  const selectionVersion = useRef(0)

  const fail = useCallback(
    (err: unknown) => setError(err instanceof Error ? err.message : '请求失败，请重试。'),
    [],
  )
  const refreshThreads = useCallback(async () => {
    setThreads(await api.threads())
  }, [])

  useEffect(() => {
    void refreshThreads().catch(fail)
    void api.info().then(setInfo).catch(fail)
    const pop = () => setSelected(new URLSearchParams(location.search).get('thread'))
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [refreshThreads, fail])

  const loadRun = useCallback(async (thread: string, id: string) => {
    const version = ++selectionVersion.current
    const next = await api.run(thread, id)
    // 切换会话/运行后忽略旧请求，避免较慢的响应覆盖当前工作区。
    if (selection.current !== thread || version !== selectionVersion.current) return
    seen.current = next.events.at(-1)?.seq ?? 0
    setEvents(next.events)
    setRun(next.run)
  }, [])

  useEffect(() => {
    let current = true
    ++selectionVersion.current
    setDetail(null)
    setRun(null)
    setRuns([])
    setEvents([])
    setError('')
    if (!selected) return
    setLoading(true)
    void Promise.all([api.thread(selected), api.runs(selected)])
      .then(async ([next, history]) => {
        if (!current) return
        setDetail(next)
        setRuns(history)
        const latest = next.active_run ?? history[0]
        if (latest) await loadRun(selected, latest.id)
      })
      .catch((err) => {
        if (current) fail(err)
      })
      .finally(() => {
        if (current) setLoading(false)
      })
    return () => {
      current = false
    }
  }, [selected, fail, loadRun])

  const activeId = run && !terminal(run.status) ? run.id : null
  useEffect(() => {
    if (!selected || !activeId) return
    let mounted = true
    const close = api.subscribe(
      selected,
      activeId,
      seen.current,
      (event) => {
        if (!mounted || event.seq <= seen.current) return
        seen.current = event.seq
        setEvents((previous) => [...previous, event])
        if (event.type === 'run.state') {
          setRun((previous) =>
            previous ? { ...previous, status: event.status, error: event.error } : previous,
          )
          setRuns((previous) =>
            previous.map((item) =>
              item.id === activeId ? { ...item, status: event.status, error: event.error } : item,
            ),
          )
          if (terminal(event.status)) {
            close()
            void Promise.all([api.thread(selected), api.runs(selected), api.threads()])
              .then(([next, history, list]) => {
                if (selection.current === selected) {
                  setDetail(next)
                  setRuns(history)
                  setThreads(list)
                }
              })
              .catch(fail)
          }
        }
        if (event.type === 'tool.started' || event.type === 'tool.completed') {
          void api
            .thread(selected)
            .then((next) => {
              if (selection.current === selected) setDetail(next)
            })
            .catch(fail)
        }
      },
      setConnected,
    )
    return () => {
      mounted = false
      close()
    }
  }, [selected, activeId, fail])

  function select(id: string | null) {
    const url = new URL(location.href)
    if (id) url.searchParams.set('thread', id)
    else url.searchParams.delete('thread')
    history.pushState(null, '', url)
    selection.current = id
    setSelected(id)
  }

  async function create() {
    setBusy(true)
    setError('')
    try {
      const thread = await api.createThread()
      await refreshThreads()
      select(thread.id)
      return thread.id
    } catch (err) {
      fail(err)
      throw err
    } finally {
      setBusy(false)
    }
  }

  async function send(text: string) {
    setBusy(true)
    setError('')
    try {
      if (!selected) {
        const thread = await api.createThread()
        await api.send(thread.id, text)
        await refreshThreads()
        select(thread.id)
        return
      }
      const id = selected
      const created = await api.send(id, text)
      const [next, history] = await Promise.all([api.thread(id), api.runs(id)])
      if (selection.current !== id) return
      setDetail(next)
      setRuns(history)
      await loadRun(id, created.id)
      await refreshThreads()
    } catch (err) {
      fail(err)
      throw err
    } finally {
      setBusy(false)
    }
  }

  async function approve(call: string, decision: 'allow' | 'deny') {
    if (!selected || !run) return
    try {
      await api.approve(selected, run.id, call, decision)
    } catch (err) {
      fail(err)
      throw err
    }
  }

  async function cancel() {
    if (!selected || !run) return
    // 命令响应可能晚于 SSE 终态到达，不能用较旧的 cancelling 覆盖 cancelled。
    try {
      await api.cancel(selected, run.id)
    } catch (err) {
      fail(err)
    }
  }

  return {
    threads,
    selected,
    detail,
    runs,
    run,
    events,
    info,
    error,
    busy,
    loading,
    connected,
    select,
    create,
    send,
    approve,
    cancel,
    selectRun: (id: string) => {
      if (selected) void loadRun(selected, id).catch(fail)
    },
    clearError: () => setError(''),
  }
}
