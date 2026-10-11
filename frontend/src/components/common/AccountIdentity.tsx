import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { authenticatedFetch } from '../../features/authentication/authenticated-fetch'
import { linkGoogleIdentity } from '../../features/authentication/google'
import { supabaseClient } from '../../lib/supabase'
import { GoogleIdentityButton } from './GoogleIdentityButton'

interface Identity {
  google_sub: string | null
  claimed_affiliation: 'student' | 'staff' | null
  matric_number: string | null
  matric_source: string | null
  matric_status: 'not_submitted' | 'pending' | 'verified' | 'rejected'
  matric_submitted_at: string | null
  matric_rejection_reason: string | null
  e_merit_identity_eligible: boolean
  e_merit_available_points: number
}

async function detail(response: Response): Promise<string> {
  const body: unknown = await response.json().catch(() => null)
  return body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string'
    ? body.detail : 'The request could not be completed.'
}

export function AccountIdentity() {
  const [identity, setIdentity] = useState<Identity | null>(null)
  const [claim, setClaim] = useState<'student' | 'staff'>('student')
  const [matric, setMatric] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    void authenticatedFetch('/api/identity/me').then(async response => {
      if (!response.ok) throw new Error(await detail(response))
      return response.json() as Promise<Identity>
    }).then(async value => {
      if (!active) return
      const { data } = await supabaseClient!.auth.getUser()
      const signupClaim = data.user?.user_metadata.claimed_affiliation
      setIdentity(value)
      setClaim(value.claimed_affiliation ?? (signupClaim === 'staff' ? 'staff' : 'student'))
      setMatric(value.matric_number ?? '')
    }).catch(error => { if (active) setMessage(error instanceof Error ? error.message : 'Identity details could not be loaded.') })
    return () => { active = false }
  }, [])

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setMessage('')
    try {
      const response = claim === 'student'
        ? await authenticatedFetch('/api/identity/me/matric', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ matric_number: matric }),
          })
        : await authenticatedFetch('/api/identity/me', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ claimed_affiliation: 'staff', matric_number: null }),
          })
      if (!response.ok) throw new Error(await detail(response))
      const value = await response.json() as Identity
      setIdentity(value)
      setMatric(value.matric_number ?? '')
      setMessage(claim === 'student'
        ? value.matric_status === 'verified' ? 'Your verified matric number is unchanged.' : 'Matric submitted for admin review.'
        : 'Staff affiliation claim saved.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'The submission failed.')
    } finally {
      setBusy(false)
    }
  }

  async function requestEMerit() {
    if (busy) return
    setBusy(true)
    setMessage('')
    try {
      const response = await authenticatedFetch('/api/identity/me/e-merit/eligibility', { method: 'POST' })
      if (!response.ok) throw new Error(await detail(response))
      const refreshed = await authenticatedFetch('/api/identity/me')
      if (refreshed.ok) setIdentity(await refreshed.json() as Identity)
      setMessage('One E-Merit eligibility record is pending institutional approval. 50 Eco Points were reserved.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'E-Merit eligibility could not be created.')
    } finally {
      setBusy(false)
    }
  }

  const connect = useCallback(async (credential: string) => {
    await linkGoogleIdentity(credential)
    const response = await authenticatedFetch('/api/identity/me')
    if (response.ok) {
      const value = await response.json() as Identity
      setIdentity(value)
      setMatric(value.matric_number ?? '')
    }
    setMessage('Google account connected.')
  }, [])
  const error = useCallback((value: string) => setMessage(value), [])
  const status = identity?.matric_status ?? 'not_submitted'
  const changedVerifiedNumber = status === 'verified' && matric.trim() !== identity?.matric_number

  return <section className="identity-panel" aria-label="Account identity">
    <h2>Student verification</h2>
    <p>Status: <strong>{status === 'not_submitted' ? 'Not Submitted' : status === 'pending' ? 'Pending' : status === 'verified' ? 'Verified' : 'Rejected'}</strong></p>
    {identity?.matric_submitted_at && <p>Submitted: {new Date(identity.matric_submitted_at).toLocaleString()}</p>}
    {status === 'rejected' && identity?.matric_rejection_reason && <p role="alert">Reason: {identity.matric_rejection_reason}</p>}
    <p>Email ownership and a suggested matric number do not establish current UiTM Arau enrolment. Admin review uses an authorized record or a documented prototype manual procedure.</p>
    <form onSubmit={save}>
      <div className="field"><label htmlFor="affiliation">I am a</label><select id="affiliation" value={claim} onChange={event => setClaim(event.target.value as 'student' | 'staff')} disabled={busy}><option value="student">Student</option><option value="staff">Staff</option></select></div>
      {claim === 'student' && <div className="field"><label htmlFor="matric">Matric number</label><input id="matric" value={matric} onChange={event => setMatric(event.target.value)} autoComplete="off" disabled={busy} required />
        {identity?.matric_source === 'verified_email' && <span className="field__hint">Suggested from your verified student email. Confirm or correct it before submission; corrections are recorded as self-reported.</span>}
      </div>}
      {changedVerifiedNumber && <p>Changing a verified number starts a new admin review and blocks new E-Merit eligibility records until approval.</p>}
      <button className="button button--secondary" type="submit" disabled={busy}>{busy ? 'Processing...' : claim === 'student' ? status === 'rejected' ? 'Correct and resubmit' : 'Submit matric for verification' : 'Save staff claim'}</button>
    </form>
    <p>Reports and approved activities can earn internal Eco Points while verification is pending. Staff activity points cannot later count toward E-Merit.</p>
    {identity?.e_merit_identity_eligible && <div>
      <p>Eligible student activity points available: {identity.e_merit_available_points}. Every 50 points may create one E-Merit eligibility record, subject to institutional approval.</p>
      <button className="button button--primary" type="button" onClick={() => void requestEMerit()} disabled={busy || changedVerifiedNumber || identity.e_merit_available_points < 50}>Request E-Merit eligibility</button>
    </div>}
    {claim === 'staff' && <p>Staff participants are not eligible for E-Merit.</p>}
    {!identity?.google_sub && <div><p>Connect a verified UiTM Google account to this signed-in website account.</p><GoogleIdentityButton onCredential={connect} onError={error} text="continue_with" /></div>}
    {message && <p role="status">{message}</p>}
  </section>
}
