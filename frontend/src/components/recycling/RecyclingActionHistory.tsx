import { useEffect, useState } from 'react'
import { PrivateImage } from '../common/PrivateImage'
import { fetchOwnRecyclingActions, type RecyclingAction } from '../../features/reporting/recycling-actions'

export function RecyclingActionHistory() {
  const [actions, setActions] = useState<RecyclingAction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    void fetchOwnRecyclingActions().then(result => { if (active) setActions(result) })
      .catch(value => { if (active) setError(value instanceof Error ? value.message : 'Recycling history could not be loaded.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])
  return <section className="member-panel recycling-history">
    <header><div><h2>Your recycling actions</h2><p>Eco Points are awarded only after admin verification.</p></div></header>
    {loading && <p role="status">Loading recycling actions...</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && actions.length === 0 && <p>No recycling actions submitted yet.</p>}
    {actions.map(action => <article key={action.id} className="recycling-history__item">
      <div><strong>{action.recycling_point_name}</strong><p>Submitted {new Date(action.created_at).toLocaleString()}</p>
        <p>Status: {action.verification_status === 'pending' ? 'Pending Verification' : action.verification_status === 'verified' ? 'Verified' : 'Rejected'}</p>
        {action.verification_status === 'verified' && <p>5 Eco Points awarded after admin verification.</p>}
        <p>Proof location: {action.proof_location_source === 'manual'
          ? `Manually entered — ${action.proof_location ?? ''}`
          : action.proof_location_source === 'gps'
            ? `Device GPS — ${action.proof_latitude?.toFixed(6)}, ${action.proof_longitude?.toFixed(6)}`
            : 'Location source not recorded'}</p>
        {action.reviewed_at && <p>Reviewed {new Date(action.reviewed_at).toLocaleString()}</p>}
        {action.rejection_reason && <p>Reason: {action.rejection_reason}</p>}
      </div>
      <div className="recycling-history__photos"><PrivateImage src={action.original_photo} alt="Original analyzed waste" /><PrivateImage src={action.proof_photo} alt="Submitted recycling proof" /></div>
    </article>)}
  </section>
}
