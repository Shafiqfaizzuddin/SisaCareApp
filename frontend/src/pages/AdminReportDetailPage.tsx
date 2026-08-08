import {
  ArrowLeft,
  BadgeCheck,
  CalendarClock,
  CheckCircle2,
  CircleX,
  Coins,
  FileImage,
  MapPin,
  UserRound,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ReportStatus } from '../components/reports/ReportStatus'
import { reportSummaries } from '../features/admin-reports/report-data'
import { useRole } from '../features/authentication/useRole'
import { wasteCategoryOptions } from '../features/reporting/categories'
import type { ReportStatus as ReportStatusValue } from '../types'

const statusOptions: { value: ReportStatusValue; label: string }[] = [
  { value: 'processing', label: 'Processing' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'completed', label: 'Completed' },
]

export function AdminReportDetailPage() {
  const { reportId } = useParams()
  const { rewardMember } = useRole()
  const report = reportSummaries.find((item) => item.id === reportId)
  const [status, setStatus] = useState<ReportStatusValue>(
    report?.status ?? 'processing',
  )
  const [validationStatus, setValidationStatus] = useState(
    report?.validationStatus ?? 'pending',
  )

  function handleValidation(result: 'valid' | 'invalid') {
    setValidationStatus(result)
    setStatus(result === 'valid' ? 'in_progress' : 'completed')
    if (result === 'valid' && report?.reporterRole === 'user') {
      rewardMember(40, true)
    }
  }

  if (!report) {
    return (
      <div className="empty-state empty-state--page">
        <h1>Report not found</h1>
        <p>The requested report is not available in this workspace.</p>
        <Link className="button button--secondary" to="/admin">
          <ArrowLeft size={17} />
          Back to dashboard
        </Link>
      </div>
    )
  }

  const category = wasteCategoryOptions.find(
    (option) => option.value === report.category,
  )

  return (
    <>
      <Link className="back-link" to="/admin">
        <ArrowLeft size={16} />
        All reports
      </Link>
      <header className="admin-page-heading admin-page-heading--detail">
        <div>
          <div className="admin-page-heading__meta">
            <span>{report.reference}</span>
            <ReportStatus status={status} />
          </div>
          <h1>{category?.label}</h1>
          <p>{report.location}</p>
        </div>
        <label className="status-control">
          <span>Update status</span>
          <select
            value={status}
            onChange={(event) =>
              setStatus(event.target.value as ReportStatusValue)
            }
          >
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </header>

      <div className="report-detail-grid">
        <div className="report-detail-main">
          <section className="admin-panel evidence-panel">
            <header className="admin-panel__heading">
              <div>
                <h2>Submitted evidence</h2>
                <p>Image received with the public report</p>
              </div>
              <span className="confidence">{report.confidence}% classification confidence</span>
            </header>
            <div className="evidence-placeholder">
              <FileImage size={34} />
              <strong>Image preview unavailable</strong>
              <span>Evidence remains attached to this sample report.</span>
            </div>
          </section>

          <section className="admin-panel report-description">
            <h2>Report description</h2>
            <p>{report.description}</p>
          </section>

          <section className="admin-panel map-panel">
            <div className="map-placeholder" aria-label="Reported location map placeholder">
              <span className="map-placeholder__road map-placeholder__road--one" />
              <span className="map-placeholder__road map-placeholder__road--two" />
              <span className="map-placeholder__marker"><MapPin size={21} /></span>
            </div>
            <div>
              <h2>Reported location</h2>
              <p>{report.location}</p>
            </div>
          </section>
        </div>

        <aside className="report-detail-side">
          <section className="admin-panel validation-panel">
            <div className="validation-panel__heading">
              <span><BadgeCheck size={20} /></span>
              <div>
                <h2>Report validation</h2>
                <p>Confirm whether this report is valid before assigning rewards.</p>
              </div>
            </div>
            {validationStatus === 'pending' ? (
              <>
                {report.reporterRole === 'user' && (
                  <div className="reward-award-preview">
                    <Coins size={18} />
                    <span>
                      <strong>40 bonus points</strong>
                      Awarded to {report.reporter} after validation
                    </span>
                  </div>
                )}
                <div className="validation-actions">
                  <button
                    className="button button--primary"
                    type="button"
                    onClick={() => handleValidation('valid')}
                  >
                    <BadgeCheck size={17} />
                    Mark as valid
                  </button>
                  <button
                    className="button button--secondary"
                    type="button"
                    onClick={() => handleValidation('invalid')}
                  >
                    <CircleX size={17} />
                    Reject
                  </button>
                </div>
              </>
            ) : (
              <div
                className={`validation-result validation-result--${validationStatus}`}
              >
                {validationStatus === 'valid' ? (
                  <BadgeCheck size={20} />
                ) : (
                  <CircleX size={20} />
                )}
                <span>
                  <strong>
                    {validationStatus === 'valid'
                      ? 'Validated report'
                      : 'Invalid report'}
                  </strong>
                  {validationStatus === 'valid' && report.reporterRole === 'user'
                    ? `40 bonus points awarded to ${report.reporter}.`
                    : validationStatus === 'valid'
                      ? 'Guest reports do not receive reward points.'
                      : 'No reward points were awarded.'}
                </span>
              </div>
            )}
          </section>

          <section className="admin-panel detail-list">
            <h2>Report details</h2>
            <dl>
              <div>
                <dt><CalendarClock size={17} /> Submitted</dt>
                <dd>{report.submittedAt}</dd>
              </div>
              <div>
                <dt><UserRound size={17} /> Reporter</dt>
                <dd>
                  {report.reporter}
                  <span className="role-label">
                    {report.reporterRole === 'user' ? 'Registered user' : 'Guest'}
                  </span>
                </dd>
              </div>
              <div>
                <dt><MapPin size={17} /> District</dt>
                <dd>Central district</dd>
              </div>
            </dl>
          </section>

          <section className="admin-panel activity-panel">
            <h2>Activity</h2>
            <ol>
              <li>
                <span><CheckCircle2 size={15} /></span>
                <div>
                  <strong>Report received</strong>
                  <small>8 Aug 2026, 09:42</small>
                </div>
              </li>
              <li>
                <span><CheckCircle2 size={15} /></span>
                <div>
                  <strong>Evidence classified</strong>
                  <small>8 Aug 2026, 09:43</small>
                </div>
              </li>
              <li className="activity-panel__pending">
                <span />
                <div>
                  <strong>Awaiting assignment</strong>
                  <small>Municipal review queue</small>
                </div>
              </li>
            </ol>
          </section>
        </aside>
      </div>
    </>
  )
}
