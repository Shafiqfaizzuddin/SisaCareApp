import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { ThemeToggle } from '../components/common/ThemeToggle'
import { useRole } from '../features/authentication/useRole'

export function StaffLoginPage() {
  const { signIn } = useRole()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { await signIn(email, password, 'staff'); navigate('/staff') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Sign in failed.') }
    finally { setBusy(false) }
  }
  return <main className="login-page"><section className="login-context"><Brand /><div>
    <p className="eyebrow">Collection team</p><h1>Keep every cleanup on track.</h1>
    <p>View your assignments, record collection progress, and submit photo evidence for review.</p>
  </div><p className="login-context__footer">Authorised staff and drivers only</p></section>
    <section className="login-panel"><div className="login-form-wrap"><Link className="back-link" to="/">Back to public site</Link>
      <div className="login-heading"><h2>Staff sign in</h2><p>Use your assigned Supabase account.</p></div>
      <form onSubmit={submit}><div className="field"><label htmlFor="staff-email">Email</label>
        <input id="staff-email" type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required /></div>
        <div className="field"><label htmlFor="staff-password">Password</label>
        <input id="staff-password" type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required /></div>
        <p><Link to="/password-reset">Forgot password?</Link></p>
        {error && <p role="alert" className="login-error">{error}</p>}
        <button className="button button--primary button--full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form></div></section><ThemeToggle compact /></main>
}
