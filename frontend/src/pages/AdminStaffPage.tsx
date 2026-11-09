import { useEffect, useState, type FormEvent } from 'react'
import { grantStaff, inviteStaff, listStaff, resendStaffVerification, revokeStaff, type StaffGrant } from '../features/collection/collection-api'

export function AdminStaffPage() {
  const [grants, setGrants] = useState<StaffGrant[]>([])
  const [userId, setUserId] = useState('')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [role, setRole] = useState<'staff' | 'driver'>('staff')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function refresh() { setGrants(await listStaff()) }
  useEffect(() => { void refresh().catch(cause => setError(cause instanceof Error ? cause.message : 'Staff unavailable.')) }, [])
  async function invite(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      const result = await inviteStaff(email, displayName, role)
      await refresh(); setEmail(''); setDisplayName('')
      setMessage(`Invitation sent to ${result.email}. They can set a password from the email link, then sign in as ${role}.`)
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Invitation failed.') }
    finally { setBusy(false) }
  }
  async function grantExisting(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try { await grantStaff(userId, role); await refresh(); setUserId(''); setMessage('Existing account granted collection access.') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Grant failed.') }
    finally { setBusy(false) }
  }
  async function revoke(grant: StaffGrant) {
    setBusy(true); setError('')
    try { await revokeStaff(grant.user_id, grant.role); await refresh() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Revocation failed.') }
    finally { setBusy(false) }
  }
  async function resend(grant: StaffGrant) {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await resendStaffVerification(grant.user_id)
      setMessage(`Verification email requested for ${result.email}. Ask them to check their inbox.`)
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not resend the verification email.') }
    finally { setBusy(false) }
  }
  return <div className="admin-staff-page"><header className="admin-page-heading"><div><p className="eyebrow">Access control</p><h1>Staff and drivers</h1>
    <p>Invite a new staff member or driver, then assign verified reports to their account.</p></div></header>
    <section className="admin-panel"><h2>Invite a staff member or driver</h2><p>The invitation email lets them create their password. Access is granted by the server to that exact Auth account.</p>
      <form className="staff-grant-form" onSubmit={invite}>
      <div className="field"><label htmlFor="staff-name">Full name</label><input id="staff-name" autoComplete="name" maxLength={120} value={displayName} onChange={event => setDisplayName(event.target.value)} required /></div>
      <div className="field"><label htmlFor="staff-email">Email address</label><input id="staff-email" type="email" autoComplete="email" maxLength={254} value={email} onChange={event => setEmail(event.target.value)} required /></div>
      <div className="field"><label htmlFor="staff-role">Role</label><select id="staff-role" value={role} onChange={event => setRole(event.target.value as 'staff' | 'driver')}><option value="staff">Staff</option><option value="driver">Driver</option></select></div>
      <button className="button button--primary" disabled={busy}>{busy ? 'Sending…' : 'Create account and send invite'}</button></form>
      {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    </section>
    <section className="admin-panel"><h2>Grant an existing account</h2><p>Use this when the person already has a confirmed SisaCare account. Find their Auth UUID in Supabase Authentication.</p><form className="staff-grant-form" onSubmit={grantExisting}>
      <div className="field"><label htmlFor="staff-id">Auth user UUID</label><input id="staff-id" value={userId} onChange={event => setUserId(event.target.value)} required /></div>
      <button className="button button--secondary" disabled={busy}>Grant selected role</button></form></section>
    <section className="admin-panel"><h2>Role grants</h2><div className="staff-grant-list">{grants.map(grant => <div key={`${grant.user_id}:${grant.role}`}>
      <div><strong>{grant.display_name || grant.email || (grant.role === 'driver' ? 'Driver' : 'Staff')}</strong>
        {grant.display_name && grant.email && <small>{grant.email}</small>}
        <small>{grant.role === 'driver' ? 'Driver' : 'Staff'} · {grant.revoked_at ? 'Revoked' : 'Active'}{grant.invited_at ? ' · Invited by email' : ''}</small>
        <small>{grant.verification_status === 'verified' ? 'Email verified' : grant.verification_status === 'unverified' ? 'Email not verified' : 'Email verification unavailable'}</small>
        <small>{grant.user_id}</small></div>
      <div className="staff-grant-actions">
        <button className="button button--secondary" disabled={busy || !!grant.revoked_at || grant.verification_status !== 'unverified' || !grant.email} onClick={() => void resend(grant)}>Resend verification email</button>
        {!grant.revoked_at && <button className="button button--secondary" disabled={busy} onClick={() => void revoke(grant)}>Revoke</button>}
      </div>
    </div>)}</div></section></div>
}
