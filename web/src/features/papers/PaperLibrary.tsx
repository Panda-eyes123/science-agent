import { useRef } from 'react'
import { BookOpen, FileText, LoaderCircle, Upload } from 'lucide-react'
import type { Paper } from '../../api/types'
import styles from './Papers.module.css'

const labels: Record<Paper['status'], string> = {
  indexing: '正在入库',
  ready: '可以检索',
  failed: '入库失败',
  interrupted: '入库已中断',
}

export function PaperLibrary({
  papers,
  uploading,
  error,
  configured,
  onUpload,
}: {
  papers: Paper[]
  uploading: boolean
  error: string
  configured: boolean
  onUpload: (file: File) => Promise<void>
}) {
  const input = useRef<HTMLInputElement>(null)
  return (
    <section className={styles.library} aria-label="全局论文库">
      <div className={styles.heading}>
        <span>
          <BookOpen size={15} /> 全局论文库
        </span>
        <span>{papers.filter((paper) => paper.status === 'ready').length} 篇可检索</span>
      </div>
      <button
        className={styles.upload}
        disabled={uploading || !configured}
        onClick={() => input.current?.click()}
      >
        {uploading ? <LoaderCircle size={15} className={styles.spin} /> : <Upload size={15} />}
        {uploading ? '正在上传…' : '上传 PDF · 自动入库'}
      </button>
      <input
        ref={input}
        hidden
        type="file"
        accept=".pdf,application/pdf"
        aria-label="选择 PDF"
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          if (file) void onUpload(file)
        }}
      />
      <p className={styles.hint}>
        {configured ? '所有会话共享 · 单文件上限 50 MB' : '配置 Embedding 模型后即可上传论文。'}
      </p>
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {!papers.length && (
        <div className={styles.empty}>上传论文后，可在对话中提问并查看来源证据。</div>
      )}
      <div className={styles.paperList}>
        {papers.map((paper) => (
          <details key={paper.paper_id} className={styles.paper}>
            <summary>
              <FileText size={16} />
              <div>
                <strong title={paper.title ?? paper.filename}>
                  {paper.title ?? paper.filename}
                </strong>
                <span data-status={paper.status}>{labels[paper.status]}</span>
              </div>
            </summary>
            <p>{paper.filename}</p>
            <p>论文 ID</p>
            <code>{paper.paper_id}</code>
            {paper.error && <p className={styles.error}>{paper.error}</p>}
            {(paper.status === 'failed' || paper.status === 'interrupted') && (
              <p className={styles.hint}>可让助手按此论文 ID 重新入库。</p>
            )}
          </details>
        ))}
      </div>
    </section>
  )
}
