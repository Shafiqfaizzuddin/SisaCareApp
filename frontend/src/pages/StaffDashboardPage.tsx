import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ReportStatus } from '../components/reports/ReportStatus'
import { listMyTasks, type CollectionTask } from '../features/collection/collection-api'
import type { ReportStatus as Status } from '../types'

export function StaffDashboardPage() {
  const [tasks, setTasks] = useState<CollectionTask[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => { void listMyTasks().then(setTasks).catch(cause => setError(cause instanceof Error ? cause.message : 'Tasks unavailable.')).finally(() => setLoading(false)) }, [])
  return <><header className="admin-page-heading"><div><p className="eyebrow">Collection workflow</p><h1>My assigned tasks</h1>
    <p>Start work, upload cleanup proof, and send finished tasks for administrator verification.</p></div></header>
    {loading && <p>Loading tasks…</p>}{error && <p role="alert">{error}</p>}
    {!loading && !error && tasks.length === 0 && <div className="empty-state">No active assignments yet.</div>}
    <div className="staff-task-grid">{tasks.map(task => <article key={task.id} className="admin-panel staff-task-card">
      <header><span>{task.reference}</span><ReportStatus status={task.status as Status} /></header>
      <h2>{task.title}</h2><p>{task.location}</p><small>{task.team_name} · Assigned {new Date(task.assigned_at ?? task.created_at).toLocaleString()}</small>
      <Link className="button button--primary" to={`/staff/tasks/${task.id}`}>View task</Link>
    </article>)}</div></>
}
