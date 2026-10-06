import {
  ArrowLeft,
  BadgeCheck,
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  CircleX,
  Coins,
  FileImage,
  MapPin,
  UserRound,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ReportStatus } from '../components/reports/ReportStatus'
import { TomTomMap } from '../components/location/TomTomMap'
import { reportSummaries } from '../features/admin-reports/report-data'
import {
  fetchPersistedReport,
  validatePersistedReport,
} from '../features/admin-reports/admin-reports-api'
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
  const maximumConfidence = Math.max(
    0,
    ...report.detections.flatMap((detection) =>
      detection.confidence === null ? [] : [detection.confidence],
    ),
  )
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
    confidence: Math.round(maximumConfidence * 100),
    description: report.summary,
    reporter: report.reporter,
    reporterRole: report.reporterRole,
    validationStatus: report.validationStatus,
  }
}

export function AdminReportDetailPage() {
  const { reportId } = useParams()
  const sampleReport = reportSummaries.find((item) => item.id === reportId)
  const [persistedReport, setPersistedReport] = useState<AdminReportDetail | null>(null)
  const [isLoading, setIsLoading] = useState(!sampleReport)
  const report = sampleReport ?? (
    persistedReport ? reportSummaryFromDetail(persistedReport) : undefined
  )
  const [status, setStatus] = useState<ReportStatusValue>(
    report?.status ?? 'processing',
  )
  const [validationStatus, setValidationStatus] = useState(
    report?.validationStatus ?? 'pending',
  )
  const [rewardPoints, setRewardPoints] = useState(
    persistedReport?.rewardPoints ?? 0,
  )
  const [isValidating, setIsValidating] = useState(false)
  const [validationError, setValidationError] = useState('')

  useEffect(() => {
    if (sampleReport || !reportId) return
    const controller = new AbortController()
    setIsLoading(true)
    fetchPersistedReport(reportId, controller.signal)
      .then(setPersistedReport)
      .catch(() => setPersistedReport(null))
      .finally(() => setIsLoading(false))
    return () => controller.abort()
  }, [reportId, sampleReport])

  useEffect(() => {
    if (!persistedReport) return
    setStatus(persistedReport.status)
    setValidationStatus(persistedReport.validationStatus)
    setRewardPoints(persistedReport.rewardPoints)
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

    if (!persistedReport) {
      setValidationStatus(result)
      setStatus(result === 'valid' ? 'in_progress' : 'completed')
      return
    }

    setIsValidating(true)
    try {
      const saved = await validatePersistedReport(report.id, result)
      setValidationStatus(saved.validationStatus)
      setStatus(saved.status)
      setRewardPoints((current) => current + saved.rewardPoints)
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
              <span className="confidence">
                {report.confidence > 0
                  ? `${report.confidence}% classification confidence`
                  : 'No AI classification'}
              </span>
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
                      alt="YOLO annotated waste evidence"
                    />
                  ) : (
                    <div className="evidence-placeholder evidence-placeholder--compact">
                      <FileImage size={28} />
                      <strong>No annotated image</strong>
                    </div>
                  )}
                  <figcaption>YOLO annotation</figcaption>
                </figure>
              </div>
            ) : (
              <div className="evidence-placeholder">
                <FileImage size={34} />
                <strong>Image preview unavailable</strong>
                <span>Evidence remains attached to this sample report.</span>
              </div>
            )}
          </section>

          {(!persistedReport || !persistedReport.generatedReport) && (
            <section className="admin-panel report-description">
              <h2>{persistedReport?.title || 'Report description'}</h2>
              <p>{report.description}</p>
            </section>
          )}

          {persistedReport && persistedReport.detections.length > 0 && (
            <section className="admin-panel ai-detection-detail">
              <header className="admin-panel__heading">
                <div>
                  <h2>Final grouped waste summary</h2>
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
              <TomTomMap
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
                  {validationStatus === 'valid' && rewardPoints > 0
                    ? `${rewardPoints} bonus points awarded to ${report.reporter}.`
                    : validationStatus === 'valid'
                      ? 'The report is valid. No reward points were awarded.'
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
              <li>
                <span><CheckCircle2 size={15} /></span>
                <div>
                  <strong>Evidence classified</strong>
                  <small>{report.submittedAt}</small>
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
