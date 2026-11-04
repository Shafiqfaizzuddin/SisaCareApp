import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ReportStatus } from '../components/reports/ReportStatus'
import { getMyTask, startTask, submitTask, type CollectionTask } from '../features/collection/collection-api'
import type { ReportStatus as Status } from '../types'

export function StaffTaskDetailPage() {
  const { reportId } = useParams()
  const [task, setTask] = useState<CollectionTask | null>(null)
  const [note, setNote] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (reportId) void getMyTask(reportId).then(setTask).catch(cause => setError(cause instanceof Error ? cause.message : 'Task unavailable.')) }, [reportId])
  async function act(kind: 'start' | 'submit') {
    if (!reportId) return
    setBusy(true); setError('')
    try {
      if (kind === 'start') await startTask(reportId)
      else { if (!photo) throw new Error('Choose a cleanup photo.'); await submitTask(reportId, note, photo) }
      setTask(await getMyTask(reportId))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Task update failed.') }
    finally { setBusy(false) }
  }
  return <><Link className="back-link" to="/staff">Back to my tasks</Link>
    {error && <p role="alert">{error}</p>}
    {task && <><header className="admin-page-heading"><div><p>{task.reference}</p><h1>{task.title}</h1>
      <ReportStatus status={task.status as Status} /></div></header>
      <div className="report-detail-grid"><div className="report-detail-main"><section className="admin-panel">
        <h2>Collection details</h2><p>{task.summary}</p><p><strong>Location:</strong> {task.location}</p>
        <p><strong>Team:</strong> {task.assignment?.team_name}</p>
        {task.original_image && <img className="staff-proof" src={task.original_image} alt="Reported waste before collection" />}
      </section><section className="admin-panel"><h2>Progress</h2>
        {task.status === 'assigned' && <button className="button button--primary" disabled={busy} onClick={() => void act('start')}>Start collection</button>}
        {task.status === 'in_progress' && <div className="field"><label htmlFor="cleanup-note">Cleanup note</label>
          <textarea id="cleanup-note" maxLength={2000} value={note} onChange={event => setNote(event.target.value)} required />
          <label htmlFor="cleanup-photo">Cleanup photo</label><input id="cleanup-photo" type="file" accept="image/jpeg,image/png,image/webp" onChange={event => setPhoto(event.target.files?.[0] ?? null)} />
          <button className="button button--primary" disabled={busy || !note.trim() || !photo} onClick={() => void act('submit')}>Submit for verification</button></div>}
        {task.status === 'pending_verification' && <p>Cleanup proof submitted. An administrator will verify it.</p>}
        {task.after_photo && <img className="staff-proof" src={task.after_photo} alt="Cleanup proof" />}
      </section></div><aside className="report-detail-aside"><section className="admin-panel activity-panel"><h2>Status history</h2><ol>
        {task.status_events?.map((event, index) => <li key={index}><div><strong>{event.new_status.replaceAll('_', ' ')}</strong>
          <small>{new Date(event.created_at).toLocaleString()} · {event.reason || 'No note'}</small></div></li>)}
      </ol></section></aside></div></>}
  </>
}
