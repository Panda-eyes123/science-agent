import { useEffect, useState } from 'react'
import { ArrowUpRight, Menu, PanelRight, X } from 'lucide-react'
import { Sidebar } from './features/conversations/Sidebar'
import { Chat } from './features/chat/Chat'
import { RunPanel } from './features/runs/RunPanel'
import { useWorkspace } from './features/conversations/useWorkspace'
import styles from './App.module.css'

export function App() {
  const work = useWorkspace()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [panelOpen, setPanelOpen] = useState(window.innerWidth >= 1200)
  useEffect(() => {
    const media = window.matchMedia('(min-width: 1200px)')
    const collapse = () => {
      if (!media.matches) setPanelOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPanelOpen(false)
        setSidebarOpen(false)
      }
    }
    media.addEventListener('change', collapse)
    window.addEventListener('keydown', escape)
    return () => {
      media.removeEventListener('change', collapse)
      window.removeEventListener('keydown', escape)
    }
  }, [])
  return (
    <div className={styles.app}>
      {sidebarOpen && (
        <button
          className={styles.overlay}
          onClick={() => setSidebarOpen(false)}
          aria-label="关闭会话面板"
        />
      )}
      <Sidebar
        threads={work.threads}
        selected={work.selected}
        open={sidebarOpen}
        onSelect={(id) => {
          work.select(id)
          setSidebarOpen(false)
        }}
        onNew={() => {
          void work.create().catch(() => {})
          setSidebarOpen(false)
        }}
        onClose={() => setSidebarOpen(false)}
      />
      <main className={styles.main}>
        <header className={styles.header}>
          <button
            className={styles.mobileMenu}
            onClick={() => setSidebarOpen(true)}
            aria-label="打开会话栏"
          >
            <Menu size={20} />
          </button>
          <div>
            <span className={styles.breadcrumb}>
              工作空间 <span>/</span>
            </span>
            <strong>{work.detail?.thread.title ?? '新的探索'}</strong>
          </div>
          <div className={styles.headerActions}>
            <span className={styles.modelBadge}>
              <span />
              {work.info?.model ?? '连接服务中'}
            </span>
            <button
              onClick={() => setPanelOpen(!panelOpen)}
              aria-label={panelOpen ? '收起运行详情' : '展开运行详情'}
            >
              <PanelRight size={18} />
            </button>
          </div>
        </header>
        {work.error && (
          <div className={styles.errorBanner} role="alert">
            <span>{work.error}</span>
            <button aria-label="关闭错误提示" onClick={work.clearError}>
              <X size={15} />
            </button>
          </div>
        )}
        {work.info && !work.info.configured && (
          <div className={styles.configBanner}>
            <span>尚未配置模型密钥，请在服务端 .env 中设置 OPENAI_API_KEY 后重启服务。</span>
            <ArrowUpRight size={14} />
          </div>
        )}
        {work.loading ? (
          <div className={styles.loading}>正在加载研究会话…</div>
        ) : (
          <Chat
            detail={work.detail}
            run={work.run}
            events={work.events}
            busy={work.busy}
            connected={work.connected}
            onSend={work.send}
            onStop={() => void work.cancel()}
            onApprove={work.approve}
          />
        )}
      </main>
      <RunPanel
        detail={work.detail}
        run={work.run}
        runs={work.runs}
        events={work.events}
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        onSelect={work.selectRun}
      />
    </div>
  )
}
