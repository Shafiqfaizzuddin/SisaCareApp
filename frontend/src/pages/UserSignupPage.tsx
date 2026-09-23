import { ArrowLeft, MailCheck, UserPlus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Brand } from '../components/common/Brand'
import { useRole } from '../features/authentication/useRole'

interface SignupFields {
  fullName: string
  email: string
  password: string
  confirmPassword: string
}

const EMPTY_FIELDS: SignupFields = {
  fullName: '',
  email: '',
  password: '',
  confirmPassword: '',
}

export function UserSignupPage() {
  const navigate = useNavigate()
  const { signUp } = useRole()
  const [fields, setFields] = useState(EMPTY_FIELDS)
  const [signupError, setSignupError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [confirmationEmail, setConfirmationEmail] = useState('')

  function updateField(field: keyof SignupFields, value: string) {
    setSignupError('')
    setFields((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (isSubmitting) return
    if (fields.fullName.trim().length < 2) {
      setSignupError('Enter your full name.')
      return
    }
    if (fields.password.length < 8) {
      setSignupError('Use a password with at least 8 characters.')
      return
    }
    if (fields.password !== fields.confirmPassword) {
      setSignupError('The passwords do not match.')
      return
    }

    setIsSubmitting(true)
    setSignupError('')
    try {
      const result = await signUp(fields.fullName, fields.email, fields.password)
      if (result.requiresEmailConfirmation) {
        setConfirmationEmail(fields.email.trim())
      } else {
        navigate('/account')
      }
    } catch (error) {
      setSignupError(
        error instanceof Error
          ? error.message
          : 'The account could not be created. Please try again.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="login-page member-login-page">
      <section className="login-context">
        <Brand />
        <div>
          <span className="login-context__icon"><UserPlus size={25} /></span>
          <p className="eyebrow">Join SisaCare</p>
          <h1>Make your community reports count.</h1>
          <p>
            Create a member account to track submitted reports and earn rewards
            after municipal verification.
          </p>
        </div>
        <p className="login-context__footer">
          Rewards recognise verified contributions.
        </p>
      </section>

      <section className="login-panel">
        <div className="login-form-wrap">
          <Link className="back-link" to="/">
            <ArrowLeft size={16} />
            Back to public site
          </Link>

          {confirmationEmail ? (
            <div className="signup-confirmation" role="status">
              <span><MailCheck size={24} /></span>
              <h2>Check your email</h2>
              <p>
                A confirmation link was sent to <strong>{confirmationEmail}</strong>.
                Confirm the address before signing in.
              </p>
              <Link className="button button--primary button--full" to="/login">
                Continue to sign in
              </Link>
            </div>
          ) : (
            <>
              <div className="login-heading">
                <span><UserPlus size={21} /></span>
                <h2>Create member account</h2>
                <p>Register to track reports and receive verified rewards.</p>
              </div>
              <form onSubmit={handleSubmit}>
                <div className="field">
                  <label htmlFor="signup-name">Full name</label>
                  <input
                    id="signup-name"
                    type="text"
                    autoComplete="name"
                    placeholder="Enter your full name"
                    value={fields.fullName}
                    onChange={(event) => updateField('fullName', event.target.value)}
                    disabled={isSubmitting}
                    required
                  />
                </div>
                <div className="field">
                  <label htmlFor="signup-email">Email address</label>
                  <input
                    id="signup-email"
                    type="email"
                    autoComplete="email"
                    placeholder="name@example.com"
                    value={fields.email}
                    onChange={(event) => updateField('email', event.target.value)}
                    disabled={isSubmitting}
                    required
                  />
                </div>
                <div className="field">
                  <label htmlFor="signup-password">Password</label>
                  <input
                    id="signup-password"
                    type="password"
                    autoComplete="new-password"
                    placeholder="At least 8 characters"
                    minLength={8}
                    value={fields.password}
                    onChange={(event) => updateField('password', event.target.value)}
                    disabled={isSubmitting}
                    required
                  />
                </div>
                <div className="field">
                  <label htmlFor="signup-confirm-password">Confirm password</label>
                  <input
                    id="signup-confirm-password"
                    type="password"
                    autoComplete="new-password"
                    placeholder="Repeat your password"
                    minLength={8}
                    value={fields.confirmPassword}
                    onChange={(event) =>
                      updateField('confirmPassword', event.target.value)
                    }
                    disabled={isSubmitting}
                    required
                  />
                </div>
                {signupError && (
                  <p className="login-error" role="alert">{signupError}</p>
                )}
                <button
                  className="button button--primary button--full"
                  type="submit"
                  disabled={isSubmitting}
                >
                  <UserPlus size={17} />
                  {isSubmitting ? 'Creating account' : 'Create account'}
                </button>
              </form>
              <p className="login-note">
                Already have an account? <Link to="/login">Sign in</Link>
              </p>
            </>
          )}
        </div>
      </section>
    </main>
  )
}
