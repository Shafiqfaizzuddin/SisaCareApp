import { useEffect, useState } from 'react'
import { PrivateImage } from '../components/common/PrivateImage'
import { fetchPendingRecyclingActions, reviewRecyclingAction, type RecyclingAction } from '../features/reporting/recycling-actions'

export function AdminRecyclingReviewPage() {
  const [actions, setActions] = useState<RecyclingAction[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [reason, setReason] = useState<Record<string, string>>({})
  useEffect(() => {
    let active = true
    void fetchPendingRecyclingActions().then(result => { if (active) setActions(result) })
      .catch(value => { if (active) setError(value instanceof Error ? value.message : 'Could not load recycling reviews.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function decide(action: RecyclingAction, decision: 'verified' | 'rejected') {
    if (busyId) return
    if (decision === 'rejected' && !reason[action.id]?.trim()) {
      setError('Enter a rejection reason before rejecting the action.')
      return
    }
    setBusyId(action.id)
    setError('')
    try {
      await reviewRecyclingAction(action.id, decision, reason[action.id]?.trim())
      setActions(current => current.filter(item => item.id !== action.id))
    } catch (value) {
      setError(value instanceof Error ? value.message : 'The review could not be saved.')
    } finally {
      setBusyId(null)
    }
  }

  return <section className="admin-recycling-page">
    <header className="admin-page-heading"><div><p className="eyebrow">Campus recycling</p><h1>Pending recycling reviews</h1><p>Compare the photos, confirmed materials, point and proof location with the agreed manual procedure. Photos and location alone do not conclusively prove disposal.</p></div></header>
    {loading && <p role="status">Loading recycling reviews...</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && actions.length === 0 && <p>No recycling actions are pending verification.</p>}
    {actions.map(action => <article className="admin-panel recycling-review" key={action.id}>
      <h2>{action.recycling_point_name}</h2>
      <p>Participant: {action.user_id} · Submitted: {new Date(action.created_at).toLocaleString()}</p>
      <p>Confirmed items: {action.confirmed_waste.items.map(item => `${item.name} (${item.material})`).join(', ')}</p>
      <p>Proof location: {action.proof_location_source === 'manual'
        ? `Manually entered — ${action.proof_location ?? ''}`
        : action.proof_location_source === 'gps'
          ? `Device GPS — ${action.proof_latitude?.toFixed(6)}, ${action.proof_longitude?.toFixed(6)}`
          : 'Location source not recorded'}</p>
      <div className="recycling-history__photos"><figure><PrivateImage src={action.original_photo} alt="Original analyzed waste" /><figcaption>Original waste photo</figcaption></figure><figure><PrivateImage src={action.proof_photo} alt="Recycling proof" /><figcaption>Submitted proof photo</figcaption></figure></div>
      <div className="field"><label htmlFor={`recycling-reason-${action.id}`}>Rejection reason</label><textarea id={`recycling-reason-${action.id}`} value={reason[action.id] ?? ''} maxLength={2000} rows={2} disabled={busyId === action.id} onChange={event => setReason(current => ({ ...current, [action.id]: event.target.value }))} /></div>
      <div className="recycling-point-form__actions"><button type="button" className="button button--primary" disabled={busyId !== null} onClick={() => void decide(action, 'verified')}>{busyId === action.id ? 'Saving...' : 'Verify and award 5 Eco Points'}</button><button type="button" className="button button--secondary" disabled={busyId !== null} onClick={() => void decide(action, 'rejected')}>Reject</button></div>
    </article>)}
  </section>
}
