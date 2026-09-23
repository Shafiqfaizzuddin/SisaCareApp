import {
  ArrowRight,
  Award,
  Check,
  Clock3,
  FileCheck2,
  Home,
  Trophy,
} from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

export function ReportSuccessPage() {
  const location = useLocation()
  const state = location.state as {
    reference?: string
    submittedAt?: string
    isMember?: boolean
  } | null
  const reference = state?.reference ?? 'SCA-1051'
  const submittedAt = state?.submittedAt
    ? new Intl.DateTimeFormat('en-MY', {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(state.submittedAt))
    : 'Submission time unavailable'

  return (
    <section className="section success-page">
      <div className="container success-page__container">
        <div className="success-mark">
          <Check size={31} />
        </div>
        <p className="eyebrow">Report received</p>
        <h1>Thank you for looking out for your community.</h1>
        <p className="success-page__lead">
          Your report has been recorded for review. Keep the reference number
          below to identify it in future updates.
        </p>

        <div className="reference-panel">
          <span>Report reference</span>
          <strong>{reference}</strong>
          <small>Submitted {submittedAt}</small>
        </div>

        {state?.isMember ? (
          <div className="reward-confirmation">
            <span><Award size={21} /></span>
            <div>
              <strong>Reward pending verification</strong>
              <p>
                No points have been awarded yet. A reward is issued only if an
                administrator validates this report.
              </p>
            </div>
            <Trophy size={20} />
          </div>
        ) : (
          <div className="guest-reward-prompt">
            <Trophy size={20} />
            <div>
              <strong>Earn rewards on future reports</strong>
              <p>Registered members collect points, achievements, and community titles.</p>
            </div>
            <Link to="/signup">Create an account</Link>
          </div>
        )}

        <div className="next-steps">
          <div>
            <span><FileCheck2 size={19} /></span>
            <div>
              <strong>Initial review</strong>
              <p>The location and evidence are checked for completeness.</p>
            </div>
          </div>
          <div>
            <span><Clock3 size={19} /></span>
            <div>
              <strong>Response planning</strong>
              <p>The appropriate municipal team assesses priority and access.</p>
            </div>
          </div>
        </div>

        <div className="success-page__actions">
          <Link className="button button--primary" to="/">
            <Home size={17} />
            Return home
          </Link>
          <Link className="button button--secondary" to="/report">
            Make another report
            <ArrowRight size={17} />
          </Link>
        </div>
      </div>
    </section>
  )
}
