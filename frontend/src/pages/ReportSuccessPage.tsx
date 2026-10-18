import {
  ArrowRight,
  Check,
  Clock3,
  FileCheck2,
  Home,
} from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

export function ReportSuccessPage() {
  const location = useLocation()
  const state = location.state as {
    reference?: string
    submittedAt?: string
    isMember?: boolean
  } | null
  const reference = state?.reference ?? 'Unavailable'
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
        <h1>Your community waste report was submitted.</h1>
        <p className="success-page__lead">
          Your report has been recorded for review. Keep the reference number
          below to identify it in future updates.
        </p>

        <div className="reference-panel">
          <span>Report reference</span>
          <strong>{reference}</strong>
          <small>Submitted {submittedAt}</small>
        </div>

        <p>Sign in to follow the report through verification and resolution.</p>

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
              <p>Municipal administrators assess the report and assign a response team.</p>
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
