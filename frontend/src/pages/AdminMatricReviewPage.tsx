import { useEffect, useState, type FormEvent } from 'react'
import { authenticatedFetch } from '../features/authentication/authenticated-fetch'

interface PendingMatric {
  user_id: string
  matric_number: string
  matric_source: string | null
  matric_submitted_at: string | null
  matric_submitted_email: string | null
}

async function responseDetail(response: Response): Promise<string> {
  const body: unknown = await response.json().catch(() => null)
  return body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string'
    ? body.detail : 'The review could not be saved.'
}

function ReviewItem({ item, onReviewed }: { item: PendingMatric; onReviewed: (id: string) => void }) {
  const [decision, setDecision] = useState<'verified' | 'rejected'>('verified')
  const [method, setMethod] = useState<'prototype_manual' | 'authorized_student_record'>('prototype_manual')
  const [reference, setReference] = useState('')
  const [reason, setReason] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const response = await authenticatedFetch(`/api/identity/admin/matric/${encodeURIComponent(item.user_id)}/review`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision, verification_method: method, review_reference: reference,
          rejection_reason: decision === 'rejected' ? reason : null,
          procedure_confirmed: confirmed,
        }),
      })
      if (!response.ok) throw new Error(await responseDetail(response))
      onReviewed(item.user_id)
    } catch (value) {
      setError(value instanceof Error ? value.message : 'The review could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  return <article className="admin-panel matric-review-item">
    <h2>Matric: {item.matric_number}</h2>
    <p>Account ID: {item.user_id}</p>
    <p>Verified account email at submission: {item.matric_submitted_email ?? 'Not available for legacy submissions'}</p>
    <p>Source: {item.matric_source === 'verified_email' ? 'Suggested from verified email' : 'Self-reported'} · Submitted: {item.matric_submitted_at ? new Date(item.matric_submitted_at).toLocaleString() : 'Unknown'}</p>
    <form onSubmit={submit}>
      <div className="field"><label htmlFor={`decision-${item.user_id}`}>Decision</label><select id={`decision-${item.user_id}`} value={decision} onChange={event => setDecision(event.target.value as 'verified' | 'rejected')} disabled={busy}><option value="verified">Verify</option><option value="rejected">Reject</option></select></div>
      <div className="field"><label htmlFor={`method-${item.user_id}`}>Verification method</label><select id={`method-${item.user_id}`} value={method} onChange={event => setMethod(event.target.value as 'prototype_manual' | 'authorized_student_record')} disabled={busy}><option value="prototype_manual">Prototype manual verification</option><option value="authorized_student_record">Authorized student record</option></select></div>
      <div className="field"><label htmlFor={`reference-${item.user_id}`}>Record or procedure checked</label><input id={`reference-${item.user_id}`} value={reference} onChange={event => setReference(event.target.value)} disabled={busy} required maxLength={500} /></div>
      {decision === 'rejected' && <div className="field"><label htmlFor={`reason-${item.user_id}`}>Rejection reason shown to student</label><textarea id={`reason-${item.user_id}`} value={reason} onChange={event => setReason(event.target.value)} disabled={busy} required maxLength={500} /></div>}
      <label className="matric-review-confirm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={busy} required /> I checked an authorized student record or the agreed manual procedure.</label>
      {error && <p role="alert">{error}</p>}
      <button className="button button--primary" type="submit" disabled={busy}>{busy ? 'Saving review...' : 'Save review'}</button>
    </form>
  </article>
}

export function AdminMatricReviewPage() {
  const [queue, setQueue] = useState<PendingMatric[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let active = true
    void authenticatedFetch('/api/identity/admin/matric/pending').then(async response => {
      if (!response.ok) throw new Error(await responseDetail(response))
      return response.json() as Promise<PendingMatric[]>
    }).then(items => { if (active) setQueue(items) })
      .catch(value => { if (active) setError(value instanceof Error ? value.message : 'Could not load pending reviews.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  return <section className="matric-review-page">
    <header className="admin-page-heading"><div><p className="eyebrow">Student identity</p><h1>Pending matric reviews</h1><p>Prototype manual verification unless an authorized UiTM student record is available. Email ownership and a matric prefix do not prove current UiTM Arau enrolment.</p></div></header>
    {loading && <p role="status">Loading reviews...</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && queue.length === 0 && <p>No matric submissions are pending.</p>}
    {queue.map(item => <ReviewItem key={item.user_id} item={item} onReviewed={id => setQueue(current => current.filter(entry => entry.user_id !== id))} />)}
  </section>
}
