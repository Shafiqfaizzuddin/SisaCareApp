import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { supabaseClient } from '../lib/supabase'

export function PasswordResetPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [sent, setSent] = useState(false)
  const [message, setMessage] = useState('')
  const recovery = new URLSearchParams(window.location.search).get('mode') === 'recovery'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!supabaseClient) return setMessage('Authentication is not configured.')
    setMessage('')
    if (recovery) {
      const { error } = await supabaseClient.auth.updateUser({ password })
      setMessage(error?.message ?? 'Password updated. You can sign in now.')
    } else {
      const { error } = await supabaseClient.auth.resetPasswordForEmail(email.trim(), {
        redirectTo: `${window.location.origin}/password-reset?mode=recovery`,
      })
      if (error) setMessage(error.message)
      else setSent(true)
    }
  }

  return <main className="login-page member-login-page"><section className="login-panel"><div className="login-form-wrap">
    <Link className="back-link" to="/login">Back to sign in</Link>
    <div className="login-heading"><h1>{recovery ? 'Set a new password' : 'Reset your password'}</h1></div>
    {sent ? <p>Check your email for a password reset link.</p> : <form onSubmit={handleSubmit}>
      {recovery ? <div className="field"><label htmlFor="new-password">New password</label><input id="new-password" type="password" autoComplete="new-password" minLength={8} value={password} onChange={event => setPassword(event.target.value)} required /></div>
        : <div className="field"><label htmlFor="reset-email">Email address</label><input id="reset-email" type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required /></div>}
      <button className="button button--primary button--full" type="submit">{recovery ? 'Update password' : 'Send reset link'}</button>
    </form>}
    {message && <p role="status">{message}</p>}
  </div></section></main>
}
