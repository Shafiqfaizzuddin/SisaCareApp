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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ReportStatus } from '../components/reports/ReportStatus'
import { wasteCategoryOptions } from '../features/reporting/categories'
import {
  formatReportDate,
  getAdminReport,
  getReportImageUrl,
  getRewardRulePoints,
  updateReportStatus,
  validateReport,
} from '../features/reporting/report-api'
import type { ReportStatus as ReportStatusValue } from '../types'

const statusOptions: { value: ReportStatusValue; label: string }[] = [
  { value: 'processing', label: 'Processing' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'completed', label: 'Completed' },
]

export function AdminReportDetailPage() {
  const { reportId = '' } = useParams()
  const queryClient = useQueryClient()
  const [validationNote, setValidationNote] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)
  const reportQuery = useQuery({
    queryKey: ['admin-report', reportId],
    queryFn: () => getAdminReport(reportId),
    enabled: Boolean(reportId),
  })
  const rewardRules = useQuery({
    queryKey: ['reward-rules'],
    queryFn: getRewardRulePoints,
  })
  const imageQuery = useQuery({
    queryKey: ['report-image', reportQuery.data?.imagePath],
    queryFn: () => getReportImageUrl(reportQuery.data?.imagePath ?? ''),
    enabled: Boolean(reportQuery.data?.imagePath),
    staleTime: 20 * 60 * 1000,
  })

  async function refreshReports() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['admin-report', reportId] }),
      queryClient.invalidateQueries({ queryKey: ['admin-reports'] }),
      queryClient.invalidateQueries({ queryKey: ['leaderboard'] }),
    ])
  }

  const validationMutation = useMutation({
    mutationFn: (decision: 'valid' | 'invalid') =>
      validateReport(reportId, decision, validationNote),
    onSuccess: async () => {
      setActionError(null)
      await refreshReports()
    },
    onError: (error) => setActionError(error.message),
  })

  const statusMutation = useMutation({
    mutationFn: (status: ReportStatusValue) => updateReportStatus(reportId, status),
    onSuccess: async () => {
      setActionError(null)
      await refreshReports()
    },
    onError: (error) => setActionError(error.message),
  })

  if (reportQuery.isLoading) {
    return <p className="empty-state empty-state--page">Loading report...</p>
  }

  const report = reportQuery.data
  if (!report) {
    return (
      <div className="empty-state empty-state--page">
        <h1>Report not found</h1>
        <p>{reportQuery.error?.message ?? 'The requested report is not available.'}</p>
        <Link className="button button--secondary" to="/admin">
          <ArrowLeft size={17} /> Back to dashboard
        </Link>
      </div>
    )
  }

  const category = wasteCategoryOptions.find((option) => option.value === report.category)
  const validation = report.validations?.[0]

  return (
    <>
      <Link className="back-link" to="/admin"><ArrowLeft size={16} /> All reports</Link>
      <header className="admin-page-heading admin-page-heading--detail">
        <div>
          <div className="admin-page-heading__meta">
            <span>{report.reference}</span>
            <ReportStatus status={report.status} />
          </div>
          <h1>{category?.label ?? 'Waste report'}</h1>
          <p>{report.location}</p>
        </div>
        <label className="status-control">
          <span>Update status</span>
          <select
            value={report.status}
            disabled={statusMutation.isPending}
            onChange={(event) =>
              statusMutation.mutate(event.target.value as ReportStatusValue)
            }
          >
            {statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
      </header>

      {actionError && <p className="form-error" role="alert">{actionError}</p>}

      <div className="report-detail-grid">
        <div className="report-detail-main">
          <section className="admin-panel evidence-panel">
            <header className="admin-panel__heading">
              <div><h2>Submitted evidence</h2><p>Private image attached to this report</p></div>
              <span className="confidence">
                {report.confidence > 0
                  ? `${report.confidence}% classification confidence`
                  : 'AI analysis pending'}
              </span>
            </header>
            {imageQuery.data ? (
              <img className="evidence-image" src={imageQuery.data} alt={`Waste evidence for ${report.reference}`} />
            ) : (
              <div className="evidence-placeholder">
                <FileImage size={34} />
                <strong>{imageQuery.isLoading ? 'Loading image...' : 'Image preview unavailable'}</strong>
                <span>The evidence remains stored privately with this report.</span>
              </div>
            )}
          </section>

          <section className="admin-panel report-description">
            <h2>Reporter description</h2>
            <p>{report.description}</p>
          </section>

          <section className="admin-panel report-description">
            <h2>AI-generated report</h2>
            <p>{report.generatedReport ?? 'AI analysis has not been attached to this report yet.'}</p>
            {report.riskLevel && <span className="role-label">Risk: {report.riskLevel}</span>}
          </section>

          <section className="admin-panel map-panel">
            <div className="map-placeholder" aria-label="Reported location">
              <span className="map-placeholder__road map-placeholder__road--one" />
              <span className="map-placeholder__road map-placeholder__road--two" />
              <span className="map-placeholder__marker"><MapPin size={21} /></span>
            </div>
            <div>
              <h2>Reported location</h2>
              <p>{report.location}</p>
              {report.latitude !== undefined && report.longitude !== undefined && (
                <small>{report.latitude.toFixed(6)}, {report.longitude.toFixed(6)}</small>
              )}
            </div>
          </section>
        </div>

        <aside className="report-detail-side">
          <section className="admin-panel validation-panel">
            <div className="validation-panel__heading">
              <span><BadgeCheck size={20} /></span>
              <div><h2>Report validation</h2><p>Validation is final and separate from case progress.</p></div>
            </div>
            {report.validationStatus === 'pending' ? (
              <>
                {report.reporterRole === 'user' && (
                  <div className="reward-award-preview">
                    <Coins size={18} />
                    <span><strong>{rewardRules.data?.validation ?? 0} validation points</strong>Awarded once after a valid decision</span>
                  </div>
                )}
                <div className="field">
                  <label htmlFor="validation-note">Validation note</label>
                  <textarea
                    id="validation-note"
                    rows={3}
                    value={validationNote}
                    onChange={(event) => setValidationNote(event.target.value)}
                    placeholder="Optional reason or review note"
                  />
                </div>
                <div className="validation-actions">
                  <button className="button button--primary" type="button" disabled={validationMutation.isPending} onClick={() => validationMutation.mutate('valid')}>
                    <BadgeCheck size={17} /> Mark as valid
                  </button>
                  <button className="button button--secondary" type="button" disabled={validationMutation.isPending} onClick={() => validationMutation.mutate('invalid')}>
                    <CircleX size={17} /> Reject
                  </button>
                </div>
              </>
            ) : (
              <div className={`validation-result validation-result--${report.validationStatus}`}>
                {report.validationStatus === 'valid' ? <BadgeCheck size={20} /> : <CircleX size={20} />}
                <span>
                  <strong>{report.validationStatus === 'valid' ? 'Validated report' : 'Invalid report'}</strong>
                  {validation?.note ?? `Decision recorded by ${validation?.adminName ?? 'an administrator'}.`}
                </span>
              </div>
            )}
          </section>

          <section className="admin-panel detail-list">
            <h2>Report details</h2>
            <dl>
              <div><dt><CalendarClock size={17} /> Submitted</dt><dd>{formatReportDate(report.submittedAt)}</dd></div>
              <div>
                <dt><UserRound size={17} /> Reporter</dt>
                <dd>{report.reporter}<span className="role-label">{report.reporterRole === 'user' ? 'Registered user' : 'Guest'}</span></dd>
              </div>
              {report.reporterEmail && <div><dt>Email</dt><dd>{report.reporterEmail}</dd></div>}
              <div><dt><MapPin size={17} /> Location</dt><dd>{report.location}</dd></div>
            </dl>
          </section>

          <section className="admin-panel activity-panel">
            <h2>Activity</h2>
            <ol>
              {[...(report.statusHistory ?? [])].map((entry) => (
                <li key={entry.id}>
                  <span><CheckCircle2 size={15} /></span>
                  <div><strong>Status changed to {statusOptions.find((option) => option.value === entry.newStatus)?.label}</strong><small>{formatReportDate(entry.changedAt)} by {entry.changedBy}</small></div>
                </li>
              ))}
              {[...(report.validations ?? [])].map((entry) => (
                <li key={entry.id}>
                  <span><CheckCircle2 size={15} /></span>
                  <div><strong>Marked {entry.status}</strong><small>{formatReportDate(entry.validatedAt)} by {entry.adminName}</small></div>
                </li>
              ))}
              <li><span><CheckCircle2 size={15} /></span><div><strong>Report received</strong><small>{formatReportDate(report.submittedAt)}</small></div></li>
            </ol>
          </section>
        </aside>
      </div>
    </>
  )
}
