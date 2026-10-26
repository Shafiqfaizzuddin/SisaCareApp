import { Eye, EyeOff, LoaderCircle, LockKeyhole, Mail } from 'lucide-react'
import { useCallback, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { GoogleIdentityButton } from '../components/common/GoogleIdentityButton'
import { signInWithGoogle } from '../features/authentication/google'
import { useRole } from '../features/authentication/useRole'
import { supabaseClient } from '../lib/supabase'

function destination(state: unknown): string {
  if (state && typeof state === 'object' && 'returnTo' in state) {
    const path = state.returnTo
    if (typeof path === 'string' && path.startsWith('/') && !path.startsWith('//')) return path
  }
  return '/account'
}

export function UserLoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { signIn, syncBrowserSession, refreshMemberData } = useRole()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [processing, setProcessing] = useState<'google' | 'password' | null>(null)
  const [loginError, setLoginError] = useState('')
  const [confirmationMessage, setConfirmationMessage] = useState('')
  const [linkMessage, setLinkMessage] = useState('')
  const [canRecoverLink, setCanRecoverLink] = useState(false)
  const busy = useRef(false)

  const handleGoogle = useCallback(async (credential: string) => {
    if (busy.current) return
    busy.current = true
    setProcessing('google')
    setLoginError('')
    setCanRecoverLink(false)
    try {
      await signInWithGoogle(credential)
      await syncBrowserSession()
      refreshMemberData()
      navigate(destination(location.state), { replace: true })
    } finally {
      busy.current = false
      setProcessing(null)
    }
  }, [location.state, navigate, refreshMemberData, syncBrowserSession])
  const handleGoogleError = useCallback((message: string) => {
    setLoginError(message)
    setCanRecoverLink(message.includes('An account already uses this email'))
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy.current) return
    busy.current = true
    setProcessing('password')
    setLoginError('')
    setConfirmationMessage('')
    try {
      await signIn(email, password, 'user')
      navigate(destination(location.state), { replace: true })
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Sign in failed. Please try again.')
    } finally {
      busy.current = false
      setProcessing(null)
    }
  }

  async function resendConfirmation() {
    if (!supabaseClient || !email.trim() || busy.current) return
    busy.current = true
    setProcessing('password')
    try {
      const { error } = await supabaseClient.auth.resend({ type: 'signup', email: email.trim(),
        options: { emailRedirectTo: `${window.location.origin}/login` } })
      setConfirmationMessage(error?.message ?? 'If this address needs confirmation, a new link has been sent.')
    } finally {
      busy.current = false
      setProcessing(null)
    }
  }

  async function sendAccountLink() {
    if (!supabaseClient || !email.trim() || busy.current) {
      setLinkMessage('Enter the account email above to request a sign-in link.')
      return
    }
    busy.current = true
    setProcessing('password')
    setLinkMessage('')
    try {
      const { error } = await supabaseClient.auth.signInWithOtp({
        email: email.trim(),
        options: { shouldCreateUser: false, emailRedirectTo: `${window.location.origin}/account` },
      })
      setLinkMessage(error?.message ?? 'If the account can receive an email sign-in link, check your inbox. Once signed in, connect Google from your account.')
    } catch (error) {
      setLinkMessage(error instanceof Error ? error.message : 'Could not send a sign-in link. Please try again.')
    } finally {
      busy.current = false
      setProcessing(null)
    }
  }

  return (
    <main className="login-page member-login-page">
      <div className="member-login-shell">
        <Brand compact />
        <section className="member-login-card" aria-labelledby="member-login-title">
          <div className="member-login-card__heading">
            <span className="member-login-card__mark" aria-hidden="true"><LockKeyhole size={23} /></span>
            <h1 id="member-login-title">Sign in to SisaCare.AI</h1>
            <p>Welcome back. Continue to your SisaCare account.</p>
          </div>

          <GoogleIdentityButton onCredential={handleGoogle} onError={handleGoogleError} disabled={processing !== null} />
          {processing === 'google' && (
            <p className="member-login-card__status" role="status"><LoaderCircle className="spin" size={17} /> Connecting to Google...</p>
          )}

          <div className="member-login-divider" role="separator" aria-label="Or sign in with email"><span>OR</span></div>

          <form onSubmit={handleSubmit} aria-busy={processing === 'password'}>
            <div className="field">
              <label htmlFor="member-email">Email</label>
              <div className="member-login-input">
                <Mail size={18} aria-hidden="true" />
                <input id="member-email" type="email" autoComplete="email" placeholder="you@example.com"
                  value={email} onChange={(event) => { setEmail(event.target.value); setLoginError('') }}
                  disabled={processing !== null} required />
              </div>
            </div>
            <div className="field">
              <label htmlFor="member-password">Password</label>
              <div className="member-login-input member-login-input--password">
                <LockKeyhole size={18} aria-hidden="true" />
                <input id="member-password" type={showPassword ? 'text' : 'password'} autoComplete="current-password"
                  placeholder="Enter your password" value={password}
                  onChange={(event) => { setPassword(event.target.value); setLoginError('') }}
                  disabled={processing !== null} required />
                <button type="button" className="member-login-password-toggle"
                  aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}
                  aria-controls="member-password" disabled={processing !== null}
                  onClick={() => setShowPassword((visible) => !visible)}>
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div className="member-login-card__forgot"><Link to="/password-reset">Forgot password?</Link></div>
            {loginError && <p className="login-error" role="alert">{loginError}</p>}
            {canRecoverLink && <div>
              <p>Use your account email to request a passwordless sign-in link. After signing in, connect Google from your account page.</p>
              <button className="member-login-card__resend" type="button" onClick={() => void sendAccountLink()}
                disabled={processing !== null}>Send email sign-in link</button>
            </div>}
            {linkMessage && <p className="member-login-card__status" role="status">{linkMessage}</p>}
            {loginError.toLowerCase().includes('confirm your email') && (
              <button className="member-login-card__resend" type="button" onClick={() => void resendConfirmation()}
                disabled={processing !== null}>Resend confirmation email</button>
            )}
            {confirmationMessage && <p className="member-login-card__status" role="status">{confirmationMessage}</p>}
            <button className="button button--primary button--full member-login-card__submit" type="submit"
              disabled={processing !== null}>
              {processing === 'password' && <LoaderCircle className="spin" size={17} aria-hidden="true" />}
              {processing === 'password' ? 'Signing in...' : 'Sign in'}
            </button>
          </form>

          <p className="member-login-card__signup">Don&apos;t have an account?{' '}
            <Link to="/signup">Create a SisaCare account</Link>
          </p>
        </section>
      </div>
    </main>
  )
}
