import { useEffect, useState } from 'react'
import { AppDataTable, Column } from '../common/AppDataTable'
import { authenticatedFetch } from '../../features/authentication/authenticated-fetch'

type Delivery = {
  outbox_event_key: string; reference: string; event_type: string
  delivery_status: 'queued' | 'retrying' | 'sent' | 'failed'
  attempts: number; last_error: string | null; next_attempt_at: string | null
  recipient_hint: string
}
type DeliveryResponse = { delivery_configured: { admin: boolean; citizen: boolean }; events: Delivery[] }

export function EmailDeliveryPanel() {
  const [data, setData] = useState<DeliveryResponse | null>(null)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    authenticatedFetch('/api/admin/notifications/email?limit=100', { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Email delivery status is unavailable.')
        return response.json() as Promise<DeliveryResponse>
      })
      .then(result => { setData(result); setError('') })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Email delivery status is unavailable.') })
    return () => controller.abort()
  }, [refresh])

  async function retry(eventKey: string) {
    setBusy(eventKey)
    try {
      const response = await authenticatedFetch(`/api/admin/notifications/email/${encodeURIComponent(eventKey)}/retry`, { method: 'POST' })
      if (!response.ok) throw new Error('This notification could not be queued again.')
      setError('')
      setRefresh(value => value + 1)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Retry failed.')
    } finally { setBusy(null) }
  }

  const failed = data?.events.filter(item => item.delivery_status === 'failed') ?? []
  const waiting = data?.events.filter(item => item.delivery_status === 'queued' || item.delivery_status === 'retrying').length ?? 0
  return <section className="admin-panel email-delivery-panel" aria-label="Email delivery">
    <header className="admin-panel__heading"><div><h2>Email delivery</h2>
      <p>{waiting} waiting · {failed.length} failed in the latest 100 events</p></div>
      <button className="button button--secondary" type="button" onClick={() => setRefresh(value => value + 1)}>Refresh</button>
    </header>
    {data && !data.delivery_configured.citizen && <p role="status">Citizen SMTP is not configured. Resolution notifications remain queued until a sender is configured.</p>}
    {error && <p role="alert">{error}</p>}
    {failed.length > 0 && <div className="report-table-wrap"><AppDataTable data={failed} className="report-table">
      <Column title="Report" data="reference">{(value: string) => <span>{value}</span>}</Column>
      <Column title="Update" data="event_type">{(value: string) => <span>{value.replaceAll('_', ' ')}</span>}</Column>
      <Column title="Recipient" data="recipient_hint">{(value: string) => <span>{value}</span>}</Column>
      <Column title="Attempts" data="attempts" />
      <Column title="Failure" data="last_error">{(value: string | null) => <span>{value ?? 'Unknown'}</span>}</Column>
      <Column title="Action" data="outbox_event_key" options={{ orderable: false, searchable: false, className: 'all' }}>
        {(eventKey: string) => <button className="button button--secondary" type="button" disabled={busy === eventKey}
          onClick={() => void retry(eventKey)}>Retry</button>}
      </Column>
    </AppDataTable></div>}
  </section>
}
