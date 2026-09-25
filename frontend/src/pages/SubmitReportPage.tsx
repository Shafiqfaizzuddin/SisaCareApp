import {
  AlertCircle,
  AlertTriangle,
  Award,
  BrainCircuit,
  Camera,
  Check,
  CheckCircle2,
  FileImage,
  Info,
  LoaderCircle,
  LockKeyhole,
  MapPin,
  ScanLine,
  ShieldCheck,
  Upload,
  UserRound,
} from 'lucide-react'
import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PageIntro } from '../components/common/PageIntro'
import { useRole } from '../features/authentication/useRole'
import { wasteCategoryOptions } from '../features/reporting/categories'
import {
  ReportSubmissionRequestError,
  submitWasteReport,
} from '../features/reporting/report-submission'
import {
  analyzeWasteImage,
  WasteAnalysisRequestError,
} from '../features/reporting/waste-analysis'
import type {
  WasteAnalysisSuccess,
  WasteAnalysisReport,
  WasteCategory,
  WasteDetection,
} from '../types'

const MAX_IMAGE_SIZE = 10 * 1024 * 1024
const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])
const EMPTY_REPORT: WasteAnalysisReport = {
  title: '',
  summary: '',
  waste_identified: '',
  recommended_action: '',
  environmental_concern: '',
}

interface DetectionGroup {
  className: string
  displayName: string
  category: string
  count: number
  detections: WasteDetection[]
}

function groupDetections(analysis: WasteAnalysisSuccess): DetectionGroup[] {
  return Object.entries(analysis.detection.counts).map(([className, count]) => {
    const detections = analysis.detection.detections.filter(
      (detection) => detection.class_name === className,
    )
    const firstDetection = detections[0]

    return {
      className,
      displayName: firstDetection?.display_name ?? className.replaceAll('_', ' '),
      category: firstDetection?.waste_category ?? 'Uncategorized Waste',
      count,
      detections,
    }
  })
}

export function SubmitReportPage() {
  const navigate = useNavigate()
  const { role, user } = useRole()
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [analysis, setAnalysis] = useState<WasteAnalysisSuccess | null>(null)
  const [analyzedFile, setAnalyzedFile] = useState<File | null>(null)
  const [analysisError, setAnalysisError] = useState('')
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [annotatedImageError, setAnnotatedImageError] = useState(false)
  const [category, setCategory] = useState<WasteCategory>('household')
  const [reportDraft, setReportDraft] = useState<WasteAnalysisReport>(EMPTY_REPORT)
  const [siteNotes, setSiteNotes] = useState('')
  const [submissionError, setSubmissionError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const analysisRequest = useRef<AbortController | null>(null)
  const submissionRequest = useRef<AbortController | null>(null)
  const canUseAi = role === 'user'
  const hasCurrentAnalysis =
    selectedFile !== null && analysis !== null && analyzedFile === selectedFile

  useEffect(() => {
    if (!selectedFile) {
      setPreviewUrl('')
      return
    }

    const objectUrl = URL.createObjectURL(selectedFile)
    setPreviewUrl(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [selectedFile])

  useEffect(
    () => () => {
      if (analysis?.annotated_image.startsWith('blob:')) {
        URL.revokeObjectURL(analysis.annotated_image)
      }
    },
    [analysis],
  )

  useEffect(
    () => () => {
      analysisRequest.current?.abort()
      submissionRequest.current?.abort()
    },
    [],
  )

  useEffect(() => {
    if (canUseAi) return
    analysisRequest.current?.abort()
    analysisRequest.current = null
    setIsAnalyzing(false)
    setAnalysis(null)
    setAnalyzedFile(null)
    setReportDraft(EMPTY_REPORT)
  }, [canUseAi])

  function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    analysisRequest.current?.abort()
    analysisRequest.current = null
    setIsAnalyzing(false)
    setAnalysis(null)
    setAnalyzedFile(null)
    setAnnotatedImageError(false)
    setReportDraft(EMPTY_REPORT)
    setSiteNotes('')
    setSubmissionError('')

    const file = event.target.files?.[0] ?? null
    if (!file) {
      setSelectedFile(null)
      setAnalysisError('')
      return
    }
    if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
      event.target.value = ''
      setSelectedFile(null)
      setAnalysisError('Choose a JPG, PNG, or WEBP image.')
      return
    }
    if (file.size > MAX_IMAGE_SIZE) {
      event.target.value = ''
      setSelectedFile(null)
      setAnalysisError('Choose an image smaller than 10 MB.')
      return
    }

    setSelectedFile(file)
    setAnalysisError('')
  }

  async function handleAnalyze() {
    if (!canUseAi) {
      navigate('/login', { state: { returnTo: '/report' } })
      return
    }
    if (analysisRequest.current || isAnalyzing) {
      return
    }
    if (!selectedFile) {
      setAnalysisError('Choose a waste photo before starting analysis.')
      return
    }

    const controller = new AbortController()
    analysisRequest.current = controller
    setIsAnalyzing(true)
    setAnalysisError('')
    setAnalysis(null)
    setAnalyzedFile(null)
    setAnnotatedImageError(false)
    setReportDraft(EMPTY_REPORT)
    setSubmissionError('')

    try {
      const result = await analyzeWasteImage(selectedFile, controller.signal)
      if (!controller.signal.aborted) {
        setAnalysis(result)
        setAnalyzedFile(selectedFile)
        setReportDraft(result.report)
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      const message =
        error instanceof WasteAnalysisRequestError
          ? error.message
          : 'Waste analysis failed unexpectedly. Please try again.'
      setAnalysisError(message)
    } finally {
      if (analysisRequest.current === controller) {
        analysisRequest.current = null
        setIsAnalyzing(false)
      }
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (isAnalyzing || submissionRequest.current || isSubmitting) {
      return
    }
    if (!selectedFile) {
      setSubmissionError('Choose a waste photo before submitting the report.')
      return
    }
    if (canUseAi && (!hasCurrentAnalysis || !analysis)) {
      setAnalysisError('Analyze the selected image before submitting the report.')
      return
    }

    const formData = new FormData(event.currentTarget)
    const controller = new AbortController()
    submissionRequest.current = controller
    setIsSubmitting(true)
    setSubmissionError('')

    try {
      const selectedCategory = wasteCategoryOptions.find(
        (option) => option.value === category,
      )
      const result = await submitWasteReport(
        {
          analysis_id: canUseAi ? analysis?.analysis_id : undefined,
          reporter_role: canUseAi ? 'user' : 'guest',
          user_id: canUseAi ? user?.id : undefined,
          guest_name:
            canUseAi ? undefined : String(formData.get('reporterName') ?? ''),
          guest_email:
            canUseAi ? undefined : String(formData.get('reporterEmail') ?? ''),
          title: canUseAi
            ? reportDraft.title
            : `${selectedCategory?.label ?? 'Community waste'} report`,
          summary: canUseAi ? reportDraft.summary : siteNotes,
          waste_identified: canUseAi ? reportDraft.waste_identified : '',
          recommended_action: canUseAi ? reportDraft.recommended_action : '',
          environmental_concern: canUseAi
            ? reportDraft.environmental_concern
            : '',
          category,
          location: String(formData.get('location') ?? ''),
          site_notes: canUseAi ? siteNotes : '',
        },
        controller.signal,
        canUseAi ? undefined : selectedFile,
      )
      if (controller.signal.aborted) {
        return
      }
      navigate('/report/success', {
        state: {
          reference: result.reference,
          submittedAt: result.submitted_at,
          isMember: role === 'user',
        },
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      setSubmissionError(
        error instanceof ReportSubmissionRequestError
          ? error.message
          : 'The report could not be submitted. Please try again.',
      )
    } finally {
      if (submissionRequest.current === controller) {
        submissionRequest.current = null
        setIsSubmitting(false)
      }
    }
  }

  return (
    <section className="section report-page">
      <div className="container">
        <PageIntro
          eyebrow={role === 'user' ? 'Member report' : 'Guest report'}
          title="Report illegal dumping"
          description="Share a clear image and location. Avoid touching unknown waste or entering unsafe areas."
        />

        <div className="report-layout">
          <form className="report-form" onSubmit={handleSubmit}>
            <section className="form-section reporter-section">
              <div className="form-section__heading">
                <span><UserRound size={16} /></span>
                <div>
                  <h2>Reporter information</h2>
                  <p>
                    {role === 'user'
                      ? 'Your registered account details are included automatically.'
                      : 'We need your name and email so the report can be followed up.'}
                  </p>
                </div>
              </div>
              {role === 'user' && user ? (
                <div className="member-identity">
                  <span className="member-identity__avatar">
                    {user.name.split(' ').map((part) => part[0]).join('')}
                  </span>
                  <div>
                    <strong>{user.name}</strong>
                    <span>{user.email}</span>
                  </div>
                  <span className="member-identity__verified">
                    <Check size={15} /> Registered member
                  </span>
                </div>
              ) : (
                <div className="guest-fields">
                  <div className="field">
                    <label htmlFor="reporter-name">Full name</label>
                    <input
                      id="reporter-name"
                      name="reporterName"
                      autoComplete="name"
                      placeholder="Enter your full name"
                      required
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="reporter-email">Email address</label>
                    <input
                      id="reporter-email"
                      name="reporterEmail"
                      type="email"
                      autoComplete="email"
                      placeholder="name@example.com"
                      required
                    />
                  </div>
                </div>
              )}
            </section>

            <section className="form-section">
              <div className="form-section__heading">
                <span>1</span>
                <div>
                  <h2>Add a photo</h2>
                  <p>Use a clear image that shows the waste and its surroundings.</p>
                </div>
              </div>
              <label className="upload-field">
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  required
                  disabled={isSubmitting}
                  onChange={handleImageChange}
                />
                <span className="upload-field__icon">
                  {selectedFile ? <FileImage size={25} /> : <Camera size={25} />}
                </span>
                <strong>{selectedFile?.name || 'Choose a waste photo'}</strong>
                <span>
                  {selectedFile
                    ? 'Photo selected. Choose another file to replace it.'
                    : 'JPG, PNG, or WEBP up to 10 MB'}
                </span>
              </label>
              {previewUrl && (
                <figure className="upload-preview">
                  <img src={previewUrl} alt="Selected waste" />
                  <figcaption>
                    <FileImage size={16} />
                    <span>
                      <strong>{selectedFile?.name}</strong>
                      <small>
                        {selectedFile
                          ? `${(selectedFile.size / 1024 / 1024).toFixed(2)} MB`
                          : ''}
                      </small>
                    </span>
                  </figcaption>
                </figure>
              )}
            </section>

            <section className="form-section">
              <div className="form-section__heading">
                <span>2</span>
                <div>
                  <h2>Analyze the waste</h2>
                  <p>Review detected items before completing the report.</p>
                </div>
              </div>

              <div className="analysis-controls">
                {canUseAi ? (
                  <button
                    className="button button--primary"
                    type="button"
                    disabled={!selectedFile || isAnalyzing || isSubmitting}
                    onClick={handleAnalyze}
                  >
                    {isAnalyzing ? (
                      <LoaderCircle className="spin" size={18} />
                    ) : (
                      <ScanLine size={18} />
                    )}
                    {isAnalyzing ? 'Analysis in progress' : 'Analyze Waste'}
                  </button>
                ) : (
                  <Link
                    className="button button--secondary"
                    to="/login"
                    state={{ returnTo: '/report' }}
                  >
                    <LockKeyhole size={18} />
                    Sign in to analyze waste
                  </Link>
                )}
                {hasCurrentAnalysis && (
                  <span className="analysis-complete">
                    <CheckCircle2 size={17} /> Analysis complete
                  </span>
                )}
              </div>

              {isAnalyzing && (
                <div
                  className="analysis-processing"
                  role="status"
                  aria-live="polite"
                >
                  <div className="analysis-processing__heading">
                    <LoaderCircle className="spin" size={20} />
                    <div>
                      <strong>Analyzing your image</strong>
                      <p>This may take a moment.</p>
                    </div>
                  </div>
                  <ol className="analysis-processing__steps">
                    <li>
                      <span><Upload size={17} /></span>
                      <strong>Uploading image</strong>
                    </li>
                    <li>
                      <span><ScanLine size={17} /></span>
                      <strong>Detecting waste</strong>
                    </li>
                    <li>
                      <span><BrainCircuit size={17} /></span>
                      <strong>Generating report</strong>
                    </li>
                  </ol>
                </div>
              )}

              {analysisError && (
                <div className="analysis-error" role="alert">
                  <AlertCircle size={19} />
                  <div>
                    <strong>Analysis could not be completed</strong>
                    <p>{analysisError}</p>
                  </div>
                </div>
              )}

              {hasCurrentAnalysis && analysis && (
                <div className="analysis-results" aria-live="polite">
                  <div className="analysis-results__grid">
                    <figure className="annotated-image">
                      {!annotatedImageError ? (
                        <img
                          src={analysis.annotated_image}
                          alt="Waste image with detected objects outlined"
                          onError={() => setAnnotatedImageError(true)}
                        />
                      ) : (
                        <div className="annotated-image__error">
                          <FileImage size={27} />
                          <span>Annotated image unavailable</span>
                        </div>
                      )}
                      <figcaption>Annotated detection</figcaption>
                    </figure>

                    <div className="detection-panel">
                      <div className="detection-panel__heading">
                        <div>
                          <span>Detected waste</span>
                          <strong>
                            {analysis.detection.total_objects}{' '}
                            {analysis.detection.total_objects === 1
                              ? 'object'
                              : 'objects'}
                          </strong>
                        </div>
                      </div>

                      <div className="detection-list">
                        {groupDetections(analysis).map((group) => (
                          <article className="detection-item" key={group.className}>
                            <div className="detection-item__title">
                              <strong>{group.displayName}</strong>
                              <span>Quantity {group.count}</span>
                            </div>
                            <p>{group.category}</p>
                            <div className="detection-confidence">
                              <span>Confidence</span>
                              <strong>
                                {group.detections
                                  .map(
                                    (detection) =>
                                      `${Math.round(detection.confidence * 100)}%`,
                                  )
                                  .join(', ')}
                              </strong>
                            </div>
                          </article>
                        ))}
                      </div>
                    </div>
                  </div>

                  <section className="ai-report">
                    <div className="ai-report__heading">
                      <BrainCircuit size={20} />
                      <div>
                        <span>AI-generated report</span>
                        <h3>Review report details</h3>
                      </div>
                    </div>
                    <div className="ai-report__editor">
                      <div className="field ai-report__field--wide">
                        <label htmlFor="report-title">Title</label>
                        <input
                          id="report-title"
                          value={reportDraft.title}
                          maxLength={180}
                          required
                          onChange={(event) =>
                            setReportDraft((current) => ({
                              ...current,
                              title: event.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="field ai-report__field--wide">
                        <label htmlFor="report-summary">Summary</label>
                        <textarea
                          id="report-summary"
                          value={reportDraft.summary}
                          rows={4}
                          maxLength={4000}
                          required
                          onChange={(event) =>
                            setReportDraft((current) => ({
                              ...current,
                              summary: event.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="waste-identified">Waste identified</label>
                        <textarea
                          id="waste-identified"
                          value={reportDraft.waste_identified}
                          rows={4}
                          maxLength={2000}
                          required
                          onChange={(event) =>
                            setReportDraft((current) => ({
                              ...current,
                              waste_identified: event.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="recommended-action">Recommended action</label>
                        <textarea
                          id="recommended-action"
                          value={reportDraft.recommended_action}
                          rows={4}
                          maxLength={2000}
                          required
                          onChange={(event) =>
                            setReportDraft((current) => ({
                              ...current,
                              recommended_action: event.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="environmental-concern">Environmental concern</label>
                        <textarea
                          id="environmental-concern"
                          value={reportDraft.environmental_concern}
                          rows={4}
                          maxLength={2000}
                          required
                          onChange={(event) =>
                            setReportDraft((current) => ({
                              ...current,
                              environmental_concern: event.target.value,
                            }))
                          }
                        />
                      </div>
                    </div>
                  </section>
                </div>
              )}
            </section>

            <section className="form-section">
              <div className="form-section__heading">
                <span>3</span>
                <div>
                  <h2>Describe the location</h2>
                  <p>Add enough detail for a response team to find the site.</p>
                </div>
              </div>
              <div className="field">
                <label htmlFor="location">Address or nearby landmark</label>
                <div className="input-with-icon">
                  <MapPin size={18} />
                  <input
                    id="location"
                    name="location"
                    placeholder="e.g. Jalan Tasik Selatan 8, near the service road"
                    required
                  />
                </div>
              </div>
              <div className="field">
                <label htmlFor="description">
                  {canUseAi ? 'Additional site notes' : 'What can you see?'}
                </label>
                <textarea
                  id="description"
                  name="description"
                  rows={4}
                  value={siteNotes}
                  placeholder="Describe the amount of waste, nearby hazards, or anything blocking access."
                  required={!canUseAi}
                  onChange={(event) => setSiteNotes(event.target.value)}
                />
                <span className="field__hint">Do not include sensitive personal information.</span>
              </div>
            </section>

            <section className="form-section">
              <div className="form-section__heading">
                <span>4</span>
                <div>
                  <h2>Choose a waste category</h2>
                  <p>Select the closest match. The report can be reviewed later.</p>
                </div>
              </div>
              <div className="category-options">
                {wasteCategoryOptions.map((option) => (
                  <label
                    className={`category-option ${
                      category === option.value ? 'category-option--selected' : ''
                    }`}
                    key={option.value}
                  >
                    <input
                      type="radio"
                      name="category"
                      value={option.value}
                      checked={category === option.value}
                      onChange={() => setCategory(option.value)}
                    />
                    <span className="category-option__check">
                      <Check size={14} />
                    </span>
                    <span>
                      <strong>{option.label}</strong>
                      <small>{option.description}</small>
                    </span>
                  </label>
                ))}
              </div>
              <label className="checkbox-field">
                <input type="checkbox" required />
                <span>
                  I confirm this report is accurate to the best of my knowledge.
                </span>
              </label>
            </section>

            <div className="form-actions">
              {submissionError && (
                <div className="analysis-error form-actions__error" role="alert">
                  <AlertCircle size={19} />
                  <div>
                    <strong>Report not submitted</strong>
                    <p>{submissionError}</p>
                  </div>
                </div>
              )}
              <p>
                <ShieldCheck size={17} />
                Your report is shared only with authorised response teams.
              </p>
              <button
                className="button button--primary"
                type="submit"
                disabled={
                  isAnalyzing ||
                  isSubmitting ||
                  !selectedFile ||
                  (canUseAi && !hasCurrentAnalysis)
                }
              >
                {isSubmitting ? 'Submitting report' : 'Submit report'}
                {isSubmitting ? (
                  <LoaderCircle className="spin" size={17} />
                ) : (
                  <Check size={17} />
                )}
              </button>
            </div>
          </form>

          <aside className="report-guidance">
            <div className="guidance-block guidance-block--warning">
              <AlertTriangle size={21} />
              <div>
                <h2>Stay at a safe distance</h2>
                <p>
                  Do not touch chemicals, sharp objects, smoke, or unknown
                  containers. Contact emergency services for immediate danger.
                </p>
              </div>
            </div>
            <div className="guidance-block">
              <Info size={21} />
              <div>
                <h2>A useful photo includes</h2>
                <ul>
                  <li>The full waste pile</li>
                  <li>A nearby landmark or road</li>
                  <li>Any access obstruction</li>
                </ul>
              </div>
            </div>
            {role === 'user' && (
              <div className="guidance-block guidance-block--reward">
                <Award size={21} />
                <div>
                  <h2>Rewards after verification</h2>
                  <p>
                    Points are awarded only after an administrator confirms the
                    submitted report is valid. AI analysis does not award points.
                  </p>
                </div>
              </div>
            )}
          </aside>
        </div>
      </div>
    </section>
  )
}
