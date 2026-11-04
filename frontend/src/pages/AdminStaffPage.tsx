import { useEffect, useState, type FormEvent } from 'react'
import { grantStaff, listStaff, revokeStaff, type StaffGrant } from '../features/collection/collection-api'

export function AdminStaffPage() {
  const [grants, setGrants] = useState<StaffGrant[]>([])
  const [userId, setUserId] = useState('')
  const [role, setRole] = useState<'staff' | 'driver'>('staff')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function refresh() { setGrants(await listStaff()) }
  useEffect(() => { void refresh().catch(cause => setError(cause instanceof Error ? cause.message : 'Staff unavailable.')) }, [])
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { await grantStaff(userId, role); await refresh(); setUserId('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Grant failed.') }
    finally { setBusy(false) }
  }
  async function revoke(grant: StaffGrant) {
    setBusy(true); setError('')
    try { await revokeStaff(grant.user_id, grant.role); await refresh() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Revocation failed.') }
    finally { setBusy(false) }
  }
  return <><header className="admin-page-heading"><div><p className="eyebrow">Access control</p><h1>Staff and drivers</h1>
    <p>Grant access to an existing Supabase Auth user by their UUID.</p></div></header>
    <section className="admin-panel"><h2>Grant collection role</h2><form className="staff-grant-form" onSubmit={submit}>
      <div className="field"><label htmlFor="staff-id">Auth user UUID</label><input id="staff-id" value={userId} onChange={event => setUserId(event.target.value)} required /></div>
      <div className="field"><label htmlFor="staff-role">Role</label><select id="staff-role" value={role} onChange={event => setRole(event.target.value as 'staff' | 'driver')}><option value="staff">Staff</option><option value="driver">Driver</option></select></div>
      <button className="button button--primary" disabled={busy}>Grant role</button></form>{error && <p role="alert">{error}</p>}</section>
    <section className="admin-panel"><h2>Role grants</h2><div className="staff-grant-list">{grants.map(grant => <div key={`${grant.user_id}:${grant.role}`}>
      <div><strong>{grant.role === 'driver' ? 'Driver' : 'Staff'}</strong><small>{grant.user_id}</small>
        <small>{grant.revoked_at ? 'Revoked' : 'Active'}</small></div>
      {!grant.revoked_at && <button className="button button--secondary" disabled={busy} onClick={() => void revoke(grant)}>Revoke</button>}
    </div>)}</div></section></>
}
