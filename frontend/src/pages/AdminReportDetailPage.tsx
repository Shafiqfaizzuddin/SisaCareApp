import {
  ArrowLeft,
  BadgeCheck,
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  CircleX,
  FileImage,
  MapPin,
  UserRound,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ReportStatus } from '../components/reports/ReportStatus'
import { ClassificationSummaryPanel } from '../components/reports/ClassificationSummaryPanel'
import { validSummary } from '../features/reporting/waste-analysis'
import { GoogleMap } from '../components/location/GoogleMap'
import {
  assignPersistedReport,
  fetchPersistedReport,
  validatePersistedReport,
} from '../features/admin-reports/admin-reports-api'
import { listStaff, reviewTask, type StaffGrant } from '../features/collection/collection-api'
import { wasteCategoryOptions } from '../features/reporting/categories'
import type {
  AdminReportDetail,
  AdminWasteDetection,
  ReportStatus as ReportStatusValue,
  ReportSummary,
  WasteAnalysisReport,
} from '../types'

interface DetectionGroup {
  className: string
  displayName: string
  wasteCategory: string
  material: string
  detections: AdminWasteDetection[]
}

function groupDetections(detections: AdminWasteDetection[]): DetectionGroup[] {
  const groups = new Map<string, DetectionGroup>()
  detections.forEach((detection) => {
    const existing = groups.get(detection.className)
    if (existing) {
      existing.detections.push(detection)
      return
    }
    groups.set(detection.className, {
      className: detection.className,
      displayName: detection.displayName,
      wasteCategory: detection.wasteCategory,
      material: detection.material,
      detections: [detection],
    })
  })
  return [...groups.values()]
}

const sourceLabels: Record<AdminWasteDetection['source'], string> = {
  yolo: 'YOLO',
  vlm: 'VLM',
  'yolo+vlm': 'YOLO + VLM',
  florence2: 'Florence-2',
}

function finalReportContent(report: AdminReportDetail): WasteAnalysisReport {
  return {
    title: report.title,
    summary: report.summary,
    waste_identified: report.wasteIdentified,
    recommended_action: report.recommendedAction,
    environmental_concern: report.environmentalConcern,
  }
}

function reportsDiffer(
  generated: WasteAnalysisReport,
  final: WasteAnalysisReport,
): boolean {
  return (Object.keys(generated) as (keyof WasteAnalysisReport)[]).some(
    (key) => generated[key].trim() !== final[key].trim(),
  )
}

function ReportContent({ report }: { report: WasteAnalysisReport }) {
  return (
    <dl className="ai-report-content">
      <div>
        <dt>Title</dt>
        <dd>{report.title}</dd>
      </div>
      <div>
        <dt>Summary</dt>
        <dd>{report.summary}</dd>
      </div>
      <div>
        <dt>Waste identified</dt>
        <dd>{report.waste_identified}</dd>
      </div>
      <div>
        <dt>Recommended action</dt>
        <dd>{report.recommended_action}</dd>
      </div>
      <div>
        <dt>Environmental concern</dt>
        <dd>{report.environmental_concern}</dd>
      </div>
    </dl>
  )
}

function reportSummaryFromDetail(report: AdminReportDetail): ReportSummary {
  return {
    id: report.id,
    reference: report.reference,
    category: report.category,
    location: report.location,
    submittedAt: new Intl.DateTimeFormat('en-MY', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(report.createdAt)),
    status: report.status,
    confidence: null,
    description: report.summary,
    reporter: report.reporter,
    reporterRole: report.reporterRole,
    validationStatus: report.validationStatus,
  }
}

export function AdminReportDetailPage() {
  const { reportId } = useParams()
  const [persistedReport, setPersistedReport] = useState<AdminReportDetail | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const report = persistedReport ? reportSummaryFromDetail(persistedReport) : undefined
  const [currentStatus, setStatus] = useState<ReportStatusValue>(
    report?.status ?? 'submitted',
  )
  const status = persistedReport?.status ?? currentStatus
  const [validationStatus, setValidationStatus] = useState(
    report?.validationStatus ?? 'pending',
  )
  const [isValidating, setIsValidating] = useState(false)
  const [validationError, setValidationError] = useState('')
  const [rejectionReason, setRejectionReason] = useState('')
  const [assignedTeam, setAssignedTeam] = useState('')
  const [assigneeId, setAssigneeId] = useState('')
  const [staffGrants, setStaffGrants] = useState<StaffGrant[]>([])
  const [workflowReason, setWorkflowReason] = useState('')

  useEffect(() => { void listStaff().then(setStaffGrants).catch(() => undefined) }, [])

  useEffect(() => {
    if (!reportId) return
    const controller = new AbortController()
    setIsLoading(true)
    fetchPersistedReport(reportId, controller.signal)
      .then(setPersistedReport)
      .catch(() => setPersistedReport(null))
      .finally(() => setIsLoading(false))
    return () => controller.abort()
  }, [reportId])

  useEffect(() => {
    if (!persistedReport) return
    setStatus(persistedReport.status)
    setValidationStatus(persistedReport.validationStatus)
  }, [persistedReport])

  useEffect(
    () => () => {
      if (persistedReport?.originalImage.startsWith('blob:')) {
        URL.revokeObjectURL(persistedReport.originalImage)
      }
      if (persistedReport?.annotatedImage.startsWith('blob:')) {
        URL.revokeObjectURL(persistedReport.annotatedImage)
      }
    },
    [persistedReport],
  )

  async function handleValidation(result: 'valid' | 'invalid') {
    if (!report || isValidating || validationStatus !== 'pending') return
    setValidationError('')

    setIsValidating(true)
    try {
      const saved = await validatePersistedReport(report.id, result, rejectionReason)
      setValidationStatus(saved.validationStatus)
      setStatus(saved.status)
      setPersistedReport(await fetchPersistedReport(report.id))
    } catch (error) {
      setValidationError(
        error instanceof Error
          ? error.message
          : 'The validation decision could not be saved.',
      )
    } finally {
      setIsValidating(false)
    }
  }

  async function handleWorkflow(action: 'assign' | 'verify' | 'rework' | 'reject') {
    if (!report || isValidating) return
    setIsValidating(true)
    setValidationError('')
    try {
      if (action === 'assign') await assignPersistedReport(report.id, assignedTeam, assigneeId, workflowReason)
      else await reviewTask(report.id, action, workflowReason)
      setPersistedReport(await fetchPersistedReport(report.id))
    } catch (error) {
      setValidationError(error instanceof Error ? error.message : 'The status update failed.')
    } finally {
      setIsValidating(false)
    }
  }

  if (isLoading) {
    return <p className="empty-state empty-state--page">Loading report details...</p>
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
  const detectionGroups = groupDetections(persistedReport?.detections ?? [])
  const submittedReport = persistedReport
    ? finalReportContent(persistedReport)
    : null
  const wasEdited = Boolean(
    persistedReport?.generatedReport &&
      submittedReport &&
      reportsDiffer(persistedReport.generatedReport, submittedReport),
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
      </header>

      <div className="report-detail-grid">
        <div className="report-detail-main">
          <section className="admin-panel evidence-panel">
            <header className="admin-panel__heading">
              <div>
                <h2>Submitted evidence</h2>
                <p>Image received with the public report</p>
              </div>
              <span className="confidence">Model detections require human review</span>
            </header>
            {persistedReport ? (
              <div className="evidence-comparison">
                <figure>
                  {persistedReport.originalImage ? (
                    <img
                      src={persistedReport.originalImage}
                      alt="Original uploaded waste evidence"
                    />
                  ) : (
                    <div className="evidence-placeholder evidence-placeholder--compact">
                      <FileImage size={28} />
                      <strong>Original image unavailable</strong>
                    </div>
                  )}
                  <figcaption>Original upload</figcaption>
                </figure>
                <figure>
                  {persistedReport.annotatedImage ? (
                    <img
                      src={persistedReport.annotatedImage}
                      alt="Analysis evidence preview"
                    />
                  ) : (
                    <div className="evidence-placeholder evidence-placeholder--compact">
                      <FileImage size={28} />
                      <strong>No annotated image</strong>
                    </div>
                  )}
                  <figcaption>Analysis preview</figcaption>
                </figure>
              </div>
            ) : null}
          </section>

          {(!persistedReport || !persistedReport.generatedReport) && (
            <section className="admin-panel report-description">
              <h2>{persistedReport?.title || 'Report description'}</h2>
              <p>{report.description}</p>
            </section>
          )}

          {persistedReport && persistedReport.confirmedItems.length > 0 && (
            <section className="admin-panel ai-detection-detail">
              <h2>Reported analysis items</h2>
              <p>AI suggestions and user edits are shown separately from municipal verification.</p>
              <p>Overall category: {persistedReport.category}</p>
              {persistedReport.confirmedItems.some((item) => item.category === 'Hazardous Waste') &&
                <p className="review-hazard" role="status">Hazardous item confirmed. Review handling and arrange an appropriate response team.</p>}
              {persistedReport.groupedReportItems.length > 0 && <ul>{persistedReport.groupedReportItems.map((group, index) => <li key={`${group.canonical_name}-${index}`}>
                {group.display_name} — {group.category ?? 'Needs assessment'} ({group.material}) · {group.detection_count} detections
                {group.uncertainty_reason && <small> · {group.uncertainty_reason}</small>}
              </li>)}</ul>}
              <details><summary>Individual detection and correction audit</summary><ul>
                {persistedReport.confirmedItems.map((item, index) => <li key={`${item.name}-${index}`}>
                  {item.name} — {item.category ?? 'Needs Confirmation'} ({item.material}) · {item.classification_source === 'user_confirmed' ? 'User edited' : 'AI/rule suggestion'}
                </li>)}
              </ul></details>
            </section>
          )}

          {persistedReport && validSummary(persistedReport.aiAnalysis?.classification_summary) &&
            <section className="admin-panel"><ClassificationSummaryPanel summary={persistedReport.aiAnalysis.classification_summary} /></section>}

          {persistedReport && persistedReport.detections.length > 0 && (
            <section className="admin-panel ai-detection-detail">
              <header className="admin-panel__heading">
                <div>
                  <h2>AI and rule suggestions</h2>
                  {typeof persistedReport.aiAnalysis?.model_id === 'string' && (
                    <p>Inference: {String(persistedReport.aiAnalysis.provider)} · {persistedReport.aiAnalysis.model_id}</p>
                  )}
                  <p>
                    {persistedReport.detections.length} detected objects
                    {persistedReport.finalCategories.length > 0 &&
                      ` · ${persistedReport.finalCategories.join(', ')}`}
                  </p>
                </div>
                <BrainCircuit size={20} />
              </header>
              <div className="admin-detection-list">
                {detectionGroups.map((group) => (
                  <article key={group.className}>
                    <header>
                      <strong>{group.displayName}</strong>
                      <span>
                        {group.detections.every(
                          (detection) => detection.boundingBox === null,
                        )
                          ? 'Quantity not established'
                          : `Quantity ${group.detections.length}`}
                      </span>
                    </header>
                    <dl>
                      <div>
                        <dt>Class</dt>
                        <dd>{group.className}</dd>
                      </div>
                      <div>
                        <dt>Category</dt>
                        <dd>{group.wasteCategory}</dd>
                      </div>
                      <div>
                        <dt>Material</dt>
                        <dd>{group.material}</dd>
                      </div>
                      <div>
                        <dt>Source</dt>
                        <dd>
                          {[...new Set(group.detections.map((item) => item.source))]
                            .map((source) => sourceLabels[source])
                            .join(', ')}
                        </dd>
                      </div>
                      <div>
                        <dt>Confidence</dt>
                        <dd>
                          {group.detections
                            .map(
                              (detection) =>
                                detection.confidence === null
                                  ? 'Not available'
                                  : `${Math.round(detection.confidence * 100)}%`,
                            )
                            .join(', ')}
                        </dd>
                      </div>
                      <div className="detection-boxes">
                        <dt>Bounding boxes</dt>
                        <dd>
                          {group.detections.map((detection, index) => (
                            <span key={detection.id}>
                              #{index + 1}:{' '}
                              {detection.boundingBox
                                ? `${detection.boundingBox.x1}, ${detection.boundingBox.y1} to ${detection.boundingBox.x2}, ${detection.boundingBox.y2}`
                                : 'Not available for this VLM observation'}
                            </span>
                          ))}
                        </dd>
                      </div>
                    </dl>
                  </article>
                ))}
              </div>
              {Array.isArray(persistedReport.aiAnalysis?.model_detections) && <details>
                <summary>Unchanged Florence-2 labels and boxes</summary><ol>
                  {persistedReport.aiAnalysis.model_detections.map((raw, index) =>
                    raw && typeof raw === 'object' && 'label' in raw && typeof raw.label === 'string'
                      ? <li key={index}>{raw.label} · Detector confidence unavailable</li> : null)}
                </ol></details>}
            </section>
          )}

          {submittedReport && (
            <section className="admin-panel report-description ai-report-detail ai-report-detail--final">
              <div className="report-content-heading">
                <div>
                  <h2>Final submitted report</h2>
                  <p>
                    {wasEdited
                      ? 'Content edited by the reporter before submission.'
                      : 'Final content confirmed by the reporter before submission.'}
                  </p>
                </div>
                <BadgeCheck size={20} />
              </div>
              <ReportContent report={submittedReport} />
            </section>
          )}

          {persistedReport?.generatedReport && (
            <section className="admin-panel report-description ai-report-detail">
              <div className="report-content-heading">
                <div>
                  <h2>Original AI-generated draft</h2>
                  <p>Original report content generated from the saved detections.</p>
                </div>
                <BrainCircuit size={20} />
              </div>
              <ReportContent report={persistedReport.generatedReport} />
            </section>
          )}

          <section className="admin-panel map-panel">
            {persistedReport?.reportLocation ? (
              <GoogleMap
                location={persistedReport.reportLocation}
                ariaLabel="Submitted waste report location"
              />
            ) : (
              <div className="map-unavailable">
                Location information is not available for this report.
              </div>
            )}
            <div>
              <h2>Reported location</h2>
              <p>{report.location}</p>
              {persistedReport?.reportLocation && (
                <dl className="report-location-details">
                  <div>
                    <dt>Address</dt>
                    <dd>{persistedReport.reportLocation.address}</dd>
                  </div>
                  <div>
                    <dt>Coordinates</dt>
                    <dd>
                      {persistedReport.reportLocation.latitude.toFixed(6)},{' '}
                      {persistedReport.reportLocation.longitude.toFixed(6)}
                    </dd>
                  </div>
                  <div>
                    <dt>Selected using</dt>
                    <dd>{persistedReport.reportLocation.source}</dd>
                  </div>
                </dl>
              )}
            </div>
          </section>
        </div>

        <aside className="report-detail-side">
          <section className="admin-panel validation-panel">
            <div className="validation-panel__heading">
              <span><BadgeCheck size={20} /></span>
              <div>
                <h2>Report validation</h2>
                <p>Verify the evidence, or reject the report with a reason.</p>
              </div>
            </div>
            {validationStatus === 'pending' ? (
              <>
                <label className="field">Reason for rejection
                  <textarea value={rejectionReason} maxLength={2000} onChange={event => setRejectionReason(event.target.value)} placeholder="Required when rejecting a report" />
                </label>
                <div className="validation-actions">
                  <button
                    className="button button--primary"
                    type="button"
                    disabled={isValidating}
                    onClick={() => handleValidation('valid')}
                  >
                    <BadgeCheck size={17} />
                    {isValidating ? 'Saving decision' : 'Mark as valid'}
                  </button>
                  <button
                    className="button button--secondary"
                    type="button"
                    disabled={isValidating}
                    onClick={() => handleValidation('invalid')}
                  >
                    <CircleX size={17} />
                    Reject
                  </button>
                </div>
                {validationError && (
                  <p className="validation-error" role="alert">
                    {validationError}
                  </p>
                )}
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
                  {validationStatus === 'valid' ? 'Ready for municipal assignment.' : 'Rejected with a recorded reason.'}
                </span>
              </div>
            )}
          </section>

          {validationStatus === 'valid' && status !== 'resolved' && status !== 'rejected' && <section className="admin-panel validation-panel">
            <h2>Municipal response</h2>
            {(status === 'verified' || status === 'assigned' || status === 'in_progress') && <div className="field"><label htmlFor="assigned-team">Assign to team</label>
              <input id="assigned-team" value={assignedTeam} maxLength={120} onChange={event => setAssignedTeam(event.target.value)} />
              <label htmlFor="assignee">Staff or driver</label><select id="assignee" value={assigneeId} onChange={event => setAssigneeId(event.target.value)}>
                <option value="">Select staff account</option>{staffGrants.filter(grant => !grant.revoked_at).map(grant =>
                  <option key={`${grant.user_id}:${grant.role}`} value={grant.user_id}>{grant.display_name || grant.email || grant.user_id} · {grant.role}</option>)}</select>
              <label htmlFor="assignment-reason">Reason {status !== 'verified' ? '(required for reassignment)' : '(optional)'}</label>
              <textarea id="assignment-reason" value={workflowReason} maxLength={2000} onChange={event => setWorkflowReason(event.target.value)} />
              <button className="button button--primary" type="button" disabled={isValidating || !assignedTeam.trim() || !assigneeId || (status !== 'verified' && !workflowReason.trim())} onClick={() => void handleWorkflow('assign')}>{status === 'verified' ? 'Assign report' : 'Reassign report'}</button></div>}
            {status === 'in_progress' && <p>Collection in progress with {persistedReport?.assignedTeam}.</p>}
            {status === 'pending_verification' && <div className="field"><p>Review the cleanup proof and collection note in the history below.</p>
              {persistedReport?.afterPhoto && <img className="staff-proof" src={persistedReport.afterPhoto} alt="Cleanup proof awaiting verification" />}
              <label htmlFor="review-reason">Verification note or rework reason</label>
              <textarea id="review-reason" value={workflowReason} maxLength={2000} onChange={event => setWorkflowReason(event.target.value)} />
              <div className="staff-review-actions"><button className="button button--primary" type="button" disabled={isValidating} onClick={() => void handleWorkflow('verify')}>Verify resolution</button>
                <button className="button button--secondary" type="button" disabled={isValidating || !workflowReason.trim()} onClick={() => void handleWorkflow('rework')}>Request rework</button>
                <button className="button button--secondary" type="button" disabled={isValidating || !workflowReason.trim()} onClick={() => void handleWorkflow('reject')}>Reject task</button></div></div>}
            {validationError && <p role="alert">{validationError}</p>}
          </section>}
          {status === 'resolved' && <section className="admin-panel"><h2>Resolution</h2><p>{persistedReport?.resolutionDetails}</p>
            {persistedReport?.resolutionSeconds != null && <p>Time from report to verified resolution: {Math.floor(persistedReport.resolutionSeconds / 3600)}h {Math.floor((persistedReport.resolutionSeconds % 3600) / 60)}m</p>}
            {persistedReport?.afterPhoto && <img src={persistedReport.afterPhoto} alt="Verified cleanup photo" />}
          </section>}

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
                    {report.reporterRole === 'user' ? 'Community User' : 'Legacy guest'}
                  </span>
                </dd>
              </div>
              <div>
                <dt><MapPin size={17} /> Address</dt>
                <dd>
                  {persistedReport?.reportLocation?.address ?? report.location}
                </dd>
              </div>
              <div>
                <dt><CheckCircle2 size={17} /> Report status</dt>
                <dd>{status.replace('_', ' ')}</dd>
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
                  <small>{report.submittedAt}</small>
                </div>
              </li>
              {persistedReport?.statusEvents?.map((event, index) => <li key={`${event.createdAt}-${index}`}>
                <span><CheckCircle2 size={15} /></span><div><strong>{event.newStatus.replace('_', ' ')}</strong>
                <small>{event.createdAt}{event.actorId ? ` · Actor ${event.actorId}` : ''}{event.reason ? ` · ${event.reason}` : ''}{event.assignedTeam ? ` · ${event.assignedTeam}` : ''}</small></div>
              </li>)}
            </ol>
          </section>
        </aside>
      </div>
    </>
  )
}
