import { ArrowLeft, Award, LogIn, UserPlus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { useRole } from '../features/authentication/useRole'

type AuthMode = 'sign-in' | 'sign-up'

interface AuthForm {
  name: string
  email: string
  password: string
  confirmPassword: string
}

const emptyForm: AuthForm = {
  name: '',
  email: '',
  password: '',
  confirmPassword: '',
}

export function UserLoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { signIn, signUp } = useRole()
  const [mode, setMode] = useState<AuthMode>('sign-in')
  const [form, setForm] = useState<AuthForm>(emptyForm)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(
    searchParams.get('confirmed') === '1'
      ? 'Email confirmed. You can now sign in.'
      : null,
  )

  function selectMode(nextMode: AuthMode) {
    setMode(nextMode)
    setError(null)
    setNotice(null)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setNotice(null)

    if (mode === 'sign-up') {
      if (form.password.length < 8) {
        setError('Use at least 8 characters for your password.')
        return
      }
      if (form.password !== form.confirmPassword) {
        setError('The passwords do not match.')
        return
      }
    }

    setSubmitting(true)

    if (mode === 'sign-in') {
      const result = await signIn(form.email, form.password)
      setSubmitting(false)

      if (result.error) {
        setError(result.error)
        return
      }

      navigate(result.role === 'admin' ? '/admin' : '/account')
      return
    }

    const result = await signUp(form.name, form.email, form.password)
    setSubmitting(false)

    if (result.error) {
      setError(result.error)
      return
    }

    if (result.requiresConfirmation) {
      setMode('sign-in')
      setForm((current) => ({ ...emptyForm, email: current.email }))
      setNotice('Check your email to confirm your account, then return to sign in.')
      return
    }

    navigate('/account')
  }

  return (
    <main className="login-page member-login-page">
      <section className="login-context">
        <Brand />
        <div>
          <span className="login-context__icon"><Award size={25} /></span>
          <p className="eyebrow">SisaCare rewards</p>
          <h1>Turn every valid report into community progress.</h1>
          <p>
            Track your reports, earn points after validation, unlock titles, and
            see your place on the community leaderboard.
          </p>
        </div>
        <p className="login-context__footer">Rewards recognise verified contributions.</p>
      </section>

      <section className="login-panel">
        <div className="login-form-wrap">
          <Link className="back-link" to="/">
            <ArrowLeft size={16} />
            Back to public site
          </Link>

          <div className="auth-mode" aria-label="Account access">
            <button
              className={mode === 'sign-in' ? 'active' : ''}
              type="button"
              onClick={() => selectMode('sign-in')}
            >
              <LogIn size={16} /> Sign in
            </button>
            <button
              className={mode === 'sign-up' ? 'active' : ''}
              type="button"
              onClick={() => selectMode('sign-up')}
            >
              <UserPlus size={16} /> Create account
            </button>
          </div>

          <div className="login-heading">
            <span>{mode === 'sign-in' ? <LogIn size={21} /> : <UserPlus size={21} />}</span>
            <h2>{mode === 'sign-in' ? 'Member sign in' : 'Create your account'}</h2>
            <p>
              {mode === 'sign-in'
                ? 'Sign in to track reports and collect rewards.'
                : 'Join SisaCare to track verified community contributions.'}
            </p>
          </div>

          {error && <p className="auth-alert auth-alert--error" role="alert">{error}</p>}
          {notice && <p className="auth-alert auth-alert--success" role="status">{notice}</p>}

          <form onSubmit={handleSubmit}>
            {mode === 'sign-up' && (
              <div className="field">
                <label htmlFor="member-name">Full name</label>
                <input
                  id="member-name"
                  type="text"
                  autoComplete="name"
                  placeholder="Your full name"
                  value={form.name}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, name: event.target.value }))
                  }
                  required
                />
              </div>
            )}
            <div className="field">
              <label htmlFor="member-email">Email address</label>
              <input
                id="member-email"
                type="email"
                autoComplete="email"
                placeholder="name@example.com"
                value={form.email}
                onChange={(event) =>
                  setForm((current) => ({ ...current, email: event.target.value }))
                }
                required
              />
            </div>
            <div className="field">
              <label htmlFor="member-password">Password</label>
              <input
                id="member-password"
                type="password"
                autoComplete={mode === 'sign-in' ? 'current-password' : 'new-password'}
                placeholder={mode === 'sign-in' ? 'Enter your password' : 'At least 8 characters'}
                minLength={mode === 'sign-up' ? 8 : undefined}
                value={form.password}
                onChange={(event) =>
                  setForm((current) => ({ ...current, password: event.target.value }))
                }
                required
              />
            </div>
            {mode === 'sign-up' && (
              <div className="field">
                <label htmlFor="member-confirm-password">Confirm password</label>
                <input
                  id="member-confirm-password"
                  type="password"
                  autoComplete="new-password"
                  placeholder="Enter the same password"
                  value={form.confirmPassword}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      confirmPassword: event.target.value,
                    }))
                  }
                  required
                />
              </div>
            )}
            <button
              className="button button--primary button--full"
              type="submit"
              disabled={submitting}
            >
              {mode === 'sign-in' ? <LogIn size={17} /> : <UserPlus size={17} />}
              {submitting
                ? 'Please wait...'
                : mode === 'sign-in'
                  ? 'Sign in'
                  : 'Create account'}
            </button>
          </form>
          <p className="login-note">
            Member accounts use secure email authentication. Titles unlock after verified impact points.
          </p>
        </div>
      </section>
    </main>
  )
}
