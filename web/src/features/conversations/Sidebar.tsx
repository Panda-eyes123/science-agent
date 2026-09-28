import { FlaskConical, MessageSquare, Plus, X } from 'lucide-react'
import type { Thread } from '../../api/types'
import styles from '../../App.module.css'

export function Sidebar({
  threads,
  selected,
  open,
  onSelect,
  onNew,
  onClose,
}: {
  threads: Thread[]
  selected: string | null
  open: boolean
  onSelect: (id: string) => void
  onNew: () => void
  onClose: () => void
}) {
  return (
    <aside className={`${styles.sidebar} ${open ? styles.mobileOpen : ''}`}>
      <div className={styles.brand}>
        <span className={styles.brandIcon}>
          <FlaskConical size={22} />
        </span>
        <div>
          Science Agent<small>让研究，从想法开始</small>
        </div>
        <button className={styles.mobileClose} onClick={onClose} aria-label="关闭会话栏">
          <X size={18} />
        </button>
      </div>
      <button className={styles.newThread} onClick={onNew}>
        <Plus size={17} /> 新建会话 <span>＋</span>
      </button>
      <div className={styles.sectionLabel}>
        研究会话 <span>{threads.length.toString().padStart(2, '0')}</span>
      </div>
      <nav className={styles.threadList} aria-label="研究会话">
        {threads.map((thread) => (
          <button
            key={thread.id}
            className={`${styles.thread} ${thread.id === selected ? styles.selectedThread : ''}`}
            onClick={() => onSelect(thread.id)}
          >
            <MessageSquare size={16} />
            <span>{thread.title}</span>
          </button>
        ))}
        {!threads.length && <p className={styles.sidebarEmpty}>你的研究会话会保存在这里。</p>}
      </nav>
      <div className={styles.sidebarFoot}>
        <span className={styles.localDot} />
        <div>
          本地工作空间<small>思考有迹可循</small>
        </div>
        <span className={styles.version}>v0.1</span>
      </div>
    </aside>
  )
}
