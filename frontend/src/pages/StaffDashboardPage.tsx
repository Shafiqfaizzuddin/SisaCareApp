import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ReportStatus } from '../components/reports/ReportStatus'
import { listMyTasks, type CollectionTask } from '../features/collection/collection-api'
import type { ReportStatus as Status } from '../types'

export function StaffDashboardPage() {
  const [tasks, setTasks] = useState<CollectionTask[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const refresh = useCallback(async () => {
    setLoading(true); setError('')
    try { setTasks(await listMyTasks()) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Tasks unavailable.') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void refresh() }, [refresh])
  const assigned = tasks.filter(task => task.status === 'assigned').length
  const inProgress = tasks.filter(task => task.status === 'in_progress').length
  const awaitingVerification = tasks.filter(task => task.status === 'pending_verification').length
  return <><header className="admin-page-heading"><div><p className="eyebrow">Collection workflow</p><h1>Staff dashboard</h1>
    <p>These are the reports currently assigned to you. Start work, upload cleanup proof, and send finished tasks for administrator verification.</p></div>
    <button className="button button--secondary" type="button" disabled={loading} onClick={() => void refresh()}>Refresh tasks</button></header>
    {loading && <p>Loading tasks…</p>}{error && <p role="alert">{error}</p>}
    {!loading && !error && <div className="staff-dashboard-summary" aria-label="My task summary">
      <div><strong>{tasks.length}</strong><span>Active tasks</span></div>
      <div><strong>{assigned}</strong><span>Assigned</span></div>
      <div><strong>{inProgress}</strong><span>In progress</span></div>
      <div><strong>{awaitingVerification}</strong><span>Awaiting verification</span></div>
    </div>}
    {!loading && !error && tasks.length === 0 && <div className="empty-state">No active assignments yet. New reports will appear here when an administrator assigns them to you.</div>}
    {!loading && !error && <div className="staff-task-grid">{tasks.map(task => <article key={task.id} className="admin-panel staff-task-card">
      <header><span>{task.reference}</span><ReportStatus status={task.status as Status} /></header>
      <h2>{task.title}</h2><p>{task.location}</p><small>{task.category} · {task.team_name}</small>
      <small>Assigned {new Date(task.assigned_at ?? task.created_at).toLocaleString()}</small>
      <Link className="button button--primary" to={`/staff/tasks/${task.id}`}>View task</Link>
    </article>)}</div>}</>
}
