import { ArrowLeft, LockKeyhole, ShieldCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { useRole } from '../features/authentication/useRole'
import {
  emptyAdminCredentials,
  type AdminCredentials,
} from '../features/authentication/session'

export function AdminLoginPage() {
  const navigate = useNavigate()
  const { signInAs } = useRole()
  const [credentials, setCredentials] =
    useState<AdminCredentials>(emptyAdminCredentials)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    signInAs('admin')
    navigate('/admin')
  }

  return (
    <main className="login-page">
      <section className="login-context">
        <Brand />
        <div>
          <span className="login-context__icon">
            <ShieldCheck size={25} />
          </span>
          <p className="eyebrow">Municipal workspace</p>
          <h1>Coordinate cleaner communities from one clear view.</h1>
          <p>
            Review incoming evidence, prioritise sites, and track response
            progress across the district.
          </p>
        </div>
        <p className="login-context__footer">
          Authorised municipal personnel only
        </p>
      </section>

      <section className="login-panel">
        <div className="login-form-wrap">
          <Link className="back-link" to="/">
            <ArrowLeft size={16} />
            Back to public site
          </Link>
          <div className="login-heading">
            <span><LockKeyhole size={21} /></span>
            <h2>Administrator sign in</h2>
            <p>Use your municipal account to continue.</p>
          </div>
          <form onSubmit={handleSubmit}>
            <div className="field">
              <label htmlFor="admin-email">Work email</label>
              <input
                id="admin-email"
                type="email"
                autoComplete="email"
                placeholder="name@council.gov.my"
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
                <label htmlFor="admin-password">Password</label>
                <button type="button">Forgot password?</button>
              </div>
              <input
                id="admin-password"
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
              Sign in
            </button>
          </form>
          <p className="login-note">
            Access is restricted to authorised municipal personnel. Account
            activity may be monitored.
          </p>
        </div>
      </section>
    </main>
  )
}
