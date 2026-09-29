import { BookOpen, ChevronDown, Quote } from 'lucide-react'
import type { EvidencePack } from '../../api/types'
import styles from './Papers.module.css'

const sections: Record<string, string> = {
  background: '背景',
  method: '方法',
  experiment: '实验',
  result: '结果',
  discussion: '讨论',
  other: '正文',
}

export function EvidenceList({ pack }: { pack: EvidencePack }) {
  return (
    <section className={styles.evidence} aria-label="检索证据">
      <div className={styles.evidenceHeading}>
        <BookOpen size={16} />
        <strong>检索证据</strong>
        <span>{pack.items.length} 条</span>
      </div>
      <p className={styles.query}>{pack.query}</p>
      {!pack.items.length ? (
        <p className={styles.empty}>没有找到匹配证据。请确认论文已入库，或换一种提问方式。</p>
      ) : (
        <>
          <p className={styles.hint}>以下是本次检索来源，供你核对回答。</p>
          {pack.items.map((item, index) => {
            const pages = [
              ...new Set(
                item.sources.flatMap((source) => (source.page_no == null ? [] : [source.page_no])),
              ),
            ].sort((a, b) => a - b)
            return (
              <details key={item.chunk_id} className={styles.citation}>
                <summary>
                  <span className={styles.number}>{index + 1}</span>
                  <div>
                    <strong>{item.title || item.paper_id || '未命名文献'}</strong>
                    <span>
                      {sections[item.section_kind ?? 'other']} ·{' '}
                      {pages.length ? `第 ${pages.join('、')} 页` : '页码未提供'}
                    </span>
                  </div>
                  <ChevronDown size={14} />
                </summary>
                <blockquote>
                  <Quote size={13} />
                  {item.excerpt}
                </blockquote>
                {item.sources.map((source) => (
                  <div className={styles.source} key={source.element_id}>
                    <span>
                      {source.page_no == null ? '页码未提供' : `第 ${source.page_no} 页`} ·{' '}
                      {source.element_type}
                    </span>
                    <p>{source.text}</p>
                    <code>{source.element_id}</code>
                  </div>
                ))}
                <p className={styles.sourceId}>论文 ID：{item.paper_id ?? '未提供'}</p>
              </details>
            )
          })}
        </>
      )}
    </section>
  )
}
