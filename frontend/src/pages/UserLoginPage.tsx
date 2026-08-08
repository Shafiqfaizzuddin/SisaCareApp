import { ArrowLeft, Award, LogIn } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { useRole } from '../features/authentication/useRole'
import {
  emptyAdminCredentials,
  type AdminCredentials,
} from '../features/authentication/session'

export function UserLoginPage() {
  const navigate = useNavigate()
  const { signInAs } = useRole()
  const [credentials, setCredentials] =
    useState<AdminCredentials>(emptyAdminCredentials)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    signInAs('user')
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
                onChange={(event) =>
                  setCredentials((current) => ({
                    ...current,
                    email: event.target.value,
                  }))
                }
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
                onChange={(event) =>
                  setCredentials((current) => ({
                    ...current,
                    password: event.target.value,
                  }))
                }
                required
              />
            </div>
            <button className="button button--primary button--full" type="submit">
              <LogIn size={17} />
              Sign in
            </button>
          </form>
          <p className="login-note">
            New to SisaCare.AI? Account registration will be available with the
            secure authentication service.
          </p>
        </div>
      </section>
    </main>
  )
}
