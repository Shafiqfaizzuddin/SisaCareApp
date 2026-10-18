import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { authenticatedFetch } from '../features/authentication/authenticated-fetch'
import { ReportStatus } from '../components/reports/ReportStatus'
import type { ReportStatus as ReportStatusValue } from '../types'

interface TrackingEvent {
  new_status: string
  reason: string | null
  assigned_team: string | null
  resolution_details: string | null
  created_at: string
}
interface TrackingReport {
  reference: string
  title: string
  location: string
  category: string
  status: ReportStatusValue
  rejection_reason: string | null
  assigned_team: string | null
  resolution_details: string | null
  status_events: TrackingEvent[]
}

export function MemberReportDetailPage() {
  const { reportId } = useParams()
  const [report, setReport] = useState<TrackingReport | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    if (!reportId) return
    const controller = new AbortController()
    setLoading(true)
    void authenticatedFetch(`/api/members/me/reports/${encodeURIComponent(reportId)}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(response.status === 401 ? 'Your session has expired. Sign in again.' : 'Report tracking is unavailable.')
        const body: unknown = await response.json()
        if (!body || typeof body !== 'object' || !('status_events' in body) || !Array.isArray(body.status_events)) throw new Error('Report tracking returned invalid data.')
        setReport(body as TrackingReport)
        setError('')
      })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Report tracking is unavailable.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [reportId, retry])
  return <section className="section"><div className="container"><Link to="/account">Back to your reports</Link>
    {loading ? <p>Loading report...</p> : error ? <div role="alert"><p>{error}</p><button type="button" onClick={() => setRetry(value => value + 1)}>Try again</button></div>
      : report && <><h1>{report.title}</h1><p>{report.reference} · {report.category}</p>
        <p>{report.location}</p><ReportStatus status={report.status} />
        {report.rejection_reason && <p>Rejection reason: {report.rejection_reason}</p>}
        {report.assigned_team && <p>Assigned team: {report.assigned_team}</p>}
        {report.resolution_details && <p>Resolution: {report.resolution_details}</p>}
        <h2>Status history</h2><ol>{report.status_events.map((event, index) => <li key={`${event.created_at}-${index}`}>
          <strong>{event.new_status.replace('_', ' ')}</strong> · {new Date(event.created_at).toLocaleString()}
          {event.reason && <p>{event.reason}</p>}
        </li>)}</ol></>}
  </div></section>
}
