import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { Paper, RunEvent } from '../../api/types'

export function usePapers(
  threadId: string | null,
  createThread: () => Promise<string>,
  events: RunEvent[],
) {
  const [papers, setPapers] = useState<Paper[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const alive = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const result = await api.papers()
      if (alive.current) {
        setPapers(result)
        setError('')
      }
    } catch (err) {
      if (alive.current) setError(err instanceof Error ? err.message : '无法读取论文库。')
    }
  }, [])

  useEffect(() => {
    alive.current = true
    void refresh()
    const focus = () => {
      void refresh()
    }
    window.addEventListener('focus', focus)
    return () => {
      alive.current = false
      window.removeEventListener('focus', focus)
    }
  }, [refresh])

  const ingestEvent = events
    .filter(
      (event) =>
        (event.type === 'tool.completed' || event.type === 'tool.failed') &&
        event.name === 'paper_ingest',
    )
    .at(-1)
  const ingestUpdate = ingestEvent ? `${ingestEvent.run_id}:${ingestEvent.seq}` : null
  useEffect(() => {
    // Agent 发起的重试同样更新论文库，不能只依赖上传触发的轮询。
    if (ingestUpdate) void refresh()
  }, [ingestUpdate, refresh])

  const indexing = papers.some((paper) => paper.status === 'indexing')
  useEffect(() => {
    if (!indexing) return
    // 上传任务不属于聊天 Run，只在仍有入库任务时查询状态；终态后停止轮询。
    const timer = window.setInterval(() => void refresh(), 2000)
    return () => window.clearInterval(timer)
  }, [indexing, refresh])

  async function upload(file: File) {
    if (uploading) return
    if (!file.name.toLowerCase().endsWith('.pdf') || file.size > 50 * 1024 * 1024) {
      setError('请选择不超过 50 MB 的 PDF。')
      return
    }
    setUploading(true)
    setError('')
    try {
      const owner = threadId ?? (await createThread())
      const paper = await api.uploadPaper(owner, file)
      if (alive.current)
        setPapers((previous) => [
          paper,
          ...previous.filter((item) => item.paper_id !== paper.paper_id),
        ])
    } catch (err) {
      if (alive.current) setError(err instanceof Error ? err.message : '上传失败，请重试。')
    } finally {
      if (alive.current) setUploading(false)
    }
  }

  return { papers, uploading, error, upload }
}
