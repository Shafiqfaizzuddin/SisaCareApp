import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { ThemeToggle } from '../components/common/ThemeToggle'
import { supabaseClient } from '../lib/supabase'

export function StaffAcceptInvitePage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [complete, setComplete] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const client = supabaseClient
    if (!client) { setError('Authentication is not configured.'); setLoading(false); return }
    void client.auth.getUser().then(async ({ data, error: authError }) => {
      if (authError || !data.user?.email) throw new Error('The invitation link is invalid or expired. Ask your administrator for a new invitation.')
      const { data: sessionData, error: sessionError } = await client.auth.getSession()
      if (sessionError || !sessionData.session?.access_token) throw new Error('The invitation session is missing. Open the link from your email again.')
      const response = await fetch('/api/collection/staff/invite/identity', {
        headers: { Authorization: `Bearer ${sessionData.session.access_token}` },
      })
      if (!response.ok) throw new Error(response.status === 403
        ? 'This invitation is not linked to an active staff or driver account. Contact your administrator.'
        : 'The invitation could not be verified. Ask your administrator for a new invitation.')
      const identity = await response.json() as { user_id: string; email: string }
      if (identity.user_id !== data.user.id || identity.email.toLowerCase() !== data.user.email.toLowerCase()) {
        throw new Error('The invitation account could not be verified.')
      }
      if (active) setEmail(data.user.email)
    }).catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : 'The invitation could not be verified.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!supabaseClient || !email || busy) return
    if (password.length < 8 || password !== confirmPassword) {
      setError('Use at least 8 characters and make sure both passwords match.'); return
    }
    setBusy(true); setError('')
    try {
      const { error: updateError } = await supabaseClient.auth.updateUser({ password })
      if (updateError) throw updateError
      await supabaseClient.auth.signOut()
      setComplete(true)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The password could not be saved.') }
    finally { setBusy(false) }
  }

  return <main className="login-page"><section className="login-context"><Brand /><div>
    <p className="eyebrow">Collection team</p><h1>Welcome to SisaCare.AI.</h1>
    <p>Set a password for your invited staff or driver account.</p>
  </div></section><section className="login-panel"><div className="login-form-wrap">
    <div className="login-heading"><h2>Accept your invitation</h2>{email && <p>Account: {email}</p>}</div>
    {loading ? <p role="status">Checking invitation…</p> : complete ? <p role="status">Password saved. <Link to="/staff/login">Sign in to the staff dashboard</Link>.</p>
      : email ? <form onSubmit={submit}>
        <div className="field"><label htmlFor="invite-password">New password</label><input id="invite-password" type={showPassword ? 'text' : 'password'} autoComplete="new-password" minLength={8} value={password} onChange={event => setPassword(event.target.value)} required /><small>Use at least 8 characters.</small></div>
        <div className="field"><label htmlFor="invite-confirm">Confirm password</label><input id="invite-confirm" type={showPassword ? 'text' : 'password'} autoComplete="new-password" minLength={8} value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} required /></div>
        <label className="invite-show-password"><input type="checkbox" checked={showPassword} onChange={event => setShowPassword(event.target.checked)} /> Show passwords</label>
        {confirmPassword && <p role="status">{password === confirmPassword ? 'Passwords match.' : 'Passwords do not match yet.'}</p>}
        <button className="button button--primary button--full" disabled={busy || password.length < 8 || password !== confirmPassword}>{busy ? 'Saving…' : 'Set password'}</button>
      </form> : <p>Open the invitation link from your email, or ask your administrator to invite you again.</p>}
    {error && <p role="alert">{error}</p>}
    <Link className="back-link" to="/staff/login">Staff sign in</Link>
  </div></section><ThemeToggle compact /></main>
}
