import { Activity, Check, Circle, ListTodo, ShieldCheck, Terminal, X } from 'lucide-react'
import type { Run, RunEvent, ThreadDetail, ToolEvent } from '../../api/types'
import { statusLabel, terminal } from '../../api/types'
import styles from '../../App.module.css'
import { ToolCard } from './ToolCard'

export function RunPanel({
  detail,
  run,
  runs,
  events,
  open,
  onClose,
  onSelect,
}: {
  detail: ThreadDetail | null
  run: Run | null
  runs: Run[]
  events: RunEvent[]
  open: boolean
  onClose: () => void
  onSelect: (id: string) => void
}) {
  const calls = events.filter((e): e is ToolEvent => e.type === 'tool.started')
  return (
    <aside className={`${styles.runPanel} ${open ? styles.panelOpen : ''}`}>
      <div className={styles.panelHeading}>
        <span>
          <Activity size={17} /> 运行详情
        </span>
        <button onClick={onClose} aria-label="收起运行详情">
          <X size={17} />
        </button>
      </div>
      <div className={styles.panelBody}>
        <div className={styles.sectionLabel}>当前状态</div>
        <div className={styles.statusCard}>
          <span className={styles.statusDot} />
          <strong>{run ? statusLabel[run.status] : '准备就绪'}</strong>
          <p>{run ? '每一步执行，都可以在这里查看。' : '开始一段对话，观察思路如何展开。'}</p>
        </div>
        <div className={styles.sectionLabel}>
          <span>
            <ListTodo size={14} /> 研究任务
          </span>
          <span>{detail?.todos.length ?? 0}</span>
        </div>
        {detail?.todos.length ? (
          <ul className={styles.todos}>
            {detail.todos.map((todo) => (
              <li key={todo.id}>
                {todo.status === 'completed' ? <Check size={15} /> : <Circle size={13} />}
                <span>{todo.content}</span>
              </li>
            ))}
          </ul>
        ) : (
          <div className={styles.panelEmpty}>
            <ListTodo size={25} strokeWidth={1.2} />
            <p>还没有研究任务</p>
            <span>让助手把想法拆解成行动清单</span>
          </div>
        )}
        <div className={styles.sectionLabel}>
          <span>
            <Terminal size={14} /> 工具活动
          </span>
          <span>{calls.length}</span>
        </div>
        {calls.length ? (
          calls.map((call) => (
            <ToolCard
              key={call.call_id}
              id={call.call_id}
              name={call.name}
              arguments={call.arguments}
              events={events}
              active={!!run && !terminal(run.status)}
            />
          ))
        ) : (
          <p className={styles.muted}>工具调用将在执行时显示。</p>
        )}
        {!!runs.length && (
          <>
            <div className={styles.sectionLabel}>运行记录</div>
            <div className={styles.runHistory}>
              {runs.map((item) => (
                <button
                  disabled={!!run && !terminal(run.status) && item.id !== run.id}
                  className={item.id === run?.id ? styles.historySelected : ''}
                  key={item.id}
                  onClick={() => onSelect(item.id)}
                >
                  <span>
                    {new Date(item.created_at).toLocaleTimeString('zh-CN', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                  <span>{statusLabel[item.status]}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
      <div className={styles.controlNote}>
        <ShieldCheck size={18} />
        <div>
          <strong>你始终掌握控制权</strong>
          <p>
            读取自动执行，写入需要确认。
            <br />
            所有文件保存在本地工作空间。
          </p>
        </div>
      </div>
    </aside>
  )
}
