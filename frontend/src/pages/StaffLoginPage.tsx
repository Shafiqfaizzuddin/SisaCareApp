import { Eye, EyeOff, LoaderCircle, LockKeyhole, Mail } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { ThemeToggle } from '../components/common/ThemeToggle'
import { useRole } from '../features/authentication/useRole'

function staffDestination(state: unknown): string {
  if (state && typeof state === 'object' && 'returnTo' in state) {
    const path = state.returnTo
    if (typeof path === 'string' && (path === '/staff' || path.startsWith('/staff/'))
      && !path.startsWith('//')) return path
  }
  return '/staff'
}

export function StaffLoginPage() {
  const { signIn, role, isAuthLoading } = useRole()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [processing, setProcessing] = useState(false)
  const busy = useRef(false)

  useEffect(() => {
    if (!isAuthLoading && role === 'staff') navigate(staffDestination(location.state), { replace: true })
  }, [isAuthLoading, location.state, navigate, role])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy.current) return
    busy.current = true
    setProcessing(true)
    setError('')
    try {
      await signIn(email, password, 'staff')
      navigate(staffDestination(location.state), { replace: true })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Sign in failed. Please try again.')
    } finally {
      busy.current = false
      setProcessing(false)
    }
  }

  return <main className="login-page member-login-page">
    <div className="member-login-shell">
      <Brand compact />
      <section className="member-login-card" aria-labelledby="staff-login-title">
        <div className="member-login-card__heading">
          <span className="member-login-card__mark" aria-hidden="true"><LockKeyhole size={23} /></span>
          <h1 id="staff-login-title">Staff and driver sign in</h1>
          <p>Use the account invited by your administrator to manage assigned collection reports.</p>
        </div>
        <form onSubmit={submit} aria-busy={processing}>
          <div className="field"><label htmlFor="staff-email">Email</label>
            <div className="member-login-input"><Mail size={18} aria-hidden="true" />
              <input id="staff-email" type="email" autoComplete="email" placeholder="you@example.com"
                value={email} onChange={event => { setEmail(event.target.value); setError('') }}
                disabled={processing} required />
            </div>
          </div>
          <div className="field"><label htmlFor="staff-password">Password</label>
            <div className="member-login-input member-login-input--password"><LockKeyhole size={18} aria-hidden="true" />
              <input id="staff-password" type={showPassword ? 'text' : 'password'} autoComplete="current-password"
                placeholder="Enter your password" value={password}
                onChange={event => { setPassword(event.target.value); setError('') }}
                disabled={processing} required />
              <button type="button" className="member-login-password-toggle"
                aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}
                aria-controls="staff-password" disabled={processing}
                onClick={() => setShowPassword(visible => !visible)}>
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>
          <div className="member-login-card__forgot"><Link to="/password-reset">Forgot password?</Link></div>
          {error && <p className="login-error" role="alert">{error}</p>}
          {error.toLowerCase().includes('confirm your email') &&
            <p className="member-login-card__status">Ask your administrator to resend your invitation from Staff and Drivers.</p>}
          <button className="button button--primary button--full member-login-card__submit" type="submit" disabled={processing}>
            {processing && <LoaderCircle className="spin" size={17} aria-hidden="true" />}
            {processing ? 'Signing in...' : 'Sign in to staff dashboard'}
          </button>
        </form>
        <p className="member-login-card__signup">Community member? <Link to="/login">Citizen sign in</Link></p>
      </section>
    </div>
    <ThemeToggle compact />
  </main>
}
