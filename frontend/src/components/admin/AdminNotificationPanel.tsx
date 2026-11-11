import { useEffect, useState } from 'react'
import { AppDataTable, Column } from '../common/AppDataTable'
import { authenticatedFetch } from '../../features/authentication/authenticated-fetch'

type Delivery = {
  event_key: string; reference: string; new_status: string; channel: 'email' | 'telegram'
  delivery_status: 'queued' | 'retrying' | 'sent' | 'failed'
  recipient_hint: string; attempts: number; last_error: string | null
}
type DeliveryResponse = { delivery_configured: { email: boolean; telegram: boolean }; events: Delivery[] }

export function AdminNotificationPanel() {
  const [data, setData] = useState<DeliveryResponse | null>(null)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    authenticatedFetch('/api/admin/notifications/admin?limit=100', { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Administrator notification status is unavailable.')
        return response.json() as Promise<DeliveryResponse>
      })
      .then(result => { setData(result); setError('') })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Notifications are unavailable.') })
    return () => controller.abort()
  }, [refresh])

  async function retry(eventKey: string) {
    setBusy(eventKey)
    try {
      const response = await authenticatedFetch(`/api/admin/notifications/admin/${encodeURIComponent(eventKey)}/retry`, { method: 'POST' })
      if (!response.ok) throw new Error('This alert could not be requeued.')
      setError('')
      setRefresh(value => value + 1)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Retry failed.')
    } finally { setBusy(null) }
  }

  const waiting = data?.events.filter(item => item.delivery_status === 'queued' || item.delivery_status === 'retrying').length ?? 0
  const failed = data?.events.filter(item => item.delivery_status === 'failed').length ?? 0
  return <section className="admin-panel email-delivery-panel" aria-label="Administrator alerts">
    <header className="admin-panel__heading"><div><h2>Administrator alerts</h2>
      <p>Email and private Telegram channel · {waiting} waiting · {failed} failed in the latest 100 events</p></div>
      <button className="button button--secondary" type="button" onClick={() => setRefresh(value => value + 1)}>Refresh</button>
    </header>
    {data && !data.delivery_configured.email && <p role="status">Administrator SMTP is not configured. Email alerts remain queued.</p>}
    {data && !data.delivery_configured.telegram && <p role="status">Private Telegram delivery is not configured.</p>}
    {error && <p role="alert">{error}</p>}
    {data && <div className="report-table-wrap"><AppDataTable data={data.events} className="report-table">
      <Column title="Report" data="reference" />
      <Column title="Update" data="new_status">{(value: string) => <span>{value.replaceAll('_', ' ')}</span>}</Column>
      <Column title="Channel" data="channel" />
      <Column title="Destination" data="recipient_hint" />
      <Column title="Delivery" data="delivery_status" />
      <Column title="Attempts" data="attempts" />
      <Column title="Failure" data="last_error">{(value: string | null) => <span>{value ?? '—'}</span>}</Column>
      <Column title="Action" data="event_key" options={{ orderable: false, searchable: false, className: 'all' }}>
        {(eventKey: string, _type: string, row: Delivery) => <button className="button button--secondary" type="button"
          disabled={row.delivery_status !== 'failed' || busy === eventKey} onClick={() => void retry(eventKey)}>Retry</button>}
      </Column>
    </AppDataTable></div>}
  </section>
}
