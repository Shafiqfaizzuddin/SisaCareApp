import { ArrowLeft, Award, LogIn } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { useRole } from '../features/authentication/useRole'
import {
  emptyAdminCredentials,
  type AdminCredentials,
} from '../features/authentication/session'

export function UserLoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { signIn } = useRole()
  const [credentials, setCredentials] =
    useState<AdminCredentials>(emptyAdminCredentials)
  const [loginError, setLoginError] = useState('')
  const [isSigningIn, setIsSigningIn] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (isSigningIn) return
    setIsSigningIn(true)
    setLoginError('')
    try {
      await signIn(credentials.email, credentials.password, 'user')
      const state = location.state as { returnTo?: string } | null
      navigate(state?.returnTo ?? '/account')
    } catch (error) {
      setLoginError(
        error instanceof Error ? error.message : 'Sign in failed. Please try again.',
      )
    } finally {
      setIsSigningIn(false)
    }
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
          <div className="login-heading">
            <span><LogIn size={21} /></span>
            <h2>Member sign in</h2>
            <p>Sign in to track reports and collect rewards.</p>
          </div>
          <form onSubmit={handleSubmit}>
            <div className="field">
              <label htmlFor="member-email">Email address</label>
              <input
                id="member-email"
                type="email"
                autoComplete="email"
                placeholder="name@example.com"
                value={credentials.email}
                onChange={(event) => {
                  setLoginError('')
                  setCredentials((current) => ({
                    ...current,
                    email: event.target.value,
                  }))
                }}
                disabled={isSigningIn}
                required
              />
            </div>
            <div className="field">
              <div className="field__label-row">
                <label htmlFor="member-password">Password</label>
                <button type="button">Forgot password?</button>
              </div>
              <input
                id="member-password"
                type="password"
                autoComplete="current-password"
                placeholder="Enter your password"
                value={credentials.password}
                onChange={(event) => {
                  setLoginError('')
                  setCredentials((current) => ({
                    ...current,
                    password: event.target.value,
                  }))
                }}
                disabled={isSigningIn}
                required
              />
            </div>
            {loginError && (
              <p className="login-error" role="alert">{loginError}</p>
            )}
            <button
              className="button button--primary button--full"
              type="submit"
              disabled={isSigningIn}
            >
              <LogIn size={17} />
              {isSigningIn ? 'Signing in' : 'Sign in'}
            </button>
          </form>
          <p className="login-note">
            New to SisaCare.AI? <Link to="/signup">Create an account</Link>
          </p>
        </div>
      </section>
    </main>
  )
}
