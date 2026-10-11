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
  ScanLine,
  ShieldCheck,
  Upload,
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
import { LocationPicker } from '../components/location/LocationPicker'
import { RecyclingRecommendations } from '../components/location/RecyclingRecommendations'
import { useRole } from '../features/authentication/useRole'
import { categoryForItems, suggestedItems, type ConfirmedItem } from '../features/reporting/campus-workflow'
import { NearbyRecyclingMap } from '../components/location/NearbyRecyclingMap'
import { fetchRecyclingPoints, type RecyclingPoint } from '../features/reporting/recycling-points'
import {
  ReportSubmissionRequestError,
  submitWasteReport,
} from '../features/reporting/report-submission'
import {
  analyzeWasteImage,
  WasteAnalysisRequestError,
} from '../features/reporting/waste-analysis'
import type {
  ReportLocation,
  WasteAnalysisSuccess,
  WasteAnalysisReport,
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
  name: string
  label: string
  category: string
  count: number | null
}

function groupDetections(analysis: WasteAnalysisSuccess): DetectionGroup[] {
  return analysis.grouped_objects.map((group) => ({
    name: group.name,
    label: group.label,
    category: group.category === 'Non-Recyclable'
      ? 'Non-Recyclable Waste'
      : group.category === 'Unknown' ? 'Needs confirmation' : group.category,
    count: group.count,
  }))
}

export function SubmitReportPage() {
  const navigate = useNavigate()
  const { role, user, refreshMemberData } = useRole()
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [analysis, setAnalysis] = useState<WasteAnalysisSuccess | null>(null)
  const [analyzedFile, setAnalyzedFile] = useState<File | null>(null)
  const [analysisError, setAnalysisError] = useState('')
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [annotatedImageError, setAnnotatedImageError] = useState(false)
  const [confirmedItems, setConfirmedItems] = useState<ConfirmedItem[]>([])
  const [chosenAction, setChosenAction] = useState<'report' | 'recycle' | 'nearby' | null>(null)
  const [recyclingPoints, setRecyclingPoints] = useState<RecyclingPoint[]>([])
  const [recyclingPointError, setRecyclingPointError] = useState('')
  const [recyclingPointsLoading, setRecyclingPointsLoading] = useState(false)
  const [reportDraft, setReportDraft] = useState<WasteAnalysisReport>(EMPTY_REPORT)
  const [siteNotes, setSiteNotes] = useState('')
  const [selectedLocation, setSelectedLocation] = useState<ReportLocation | null>(null)
  const [draftLocation, setDraftLocation] = useState<ReportLocation | null>(null)
  const [draftNote, setDraftNote] = useState('')
  const [locationPickerOpen, setLocationPickerOpen] = useState(false)
  const [locationError, setLocationError] = useState('')
  const locationTrigger = useRef<HTMLButtonElement>(null)
  const locationSearch = useRef<HTMLDivElement>(null)
  const [submissionError, setSubmissionError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const analysisRequest = useRef<AbortController | null>(null)
  const submissionRequest = useRef<AbortController | null>(null)
  const canUseAi = role === 'user'
  const hasCurrentAnalysis =
    selectedFile !== null && analysis !== null && analyzedFile === selectedFile
  const category = categoryForItems(confirmedItems)
  const reportAction = category !== 'Recyclable Waste' || chosenAction === 'report'
  function openLocationPicker(clearError = true) {
    setDraftLocation(selectedLocation)
    setDraftNote(siteNotes)
    if (clearError) setLocationError('')
    setLocationPickerOpen(true)
    window.setTimeout(() => locationSearch.current?.querySelector<HTMLInputElement>('input[role="combobox"]')?.focus(), 0)
  }

  function closeLocationPicker() {
    setLocationPickerOpen(false)
    window.setTimeout(() => locationTrigger.current?.focus(), 0)
  }
  useEffect(() => {
    if (chosenAction !== 'recycle' && chosenAction !== 'nearby') return
    const controller = new AbortController()
    setRecyclingPointsLoading(true)
    void fetchRecyclingPoints(controller.signal)
      .then((points) => { setRecyclingPoints(points); setRecyclingPointError('') })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setRecyclingPointError(error instanceof Error ? error.message : 'Registered recycling points could not be loaded.')
      })
      .finally(() => { if (!controller.signal.aborted) setRecyclingPointsLoading(false) })
    return () => controller.abort()
  }, [chosenAction])

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
      if (analysis?.annotated_image?.startsWith('blob:')) {
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
    setConfirmedItems([])
    setChosenAction(null)
  }, [canUseAi])

  function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    analysisRequest.current?.abort()
    analysisRequest.current = null
    setIsAnalyzing(false)
    setAnalysis(null)
    setAnalyzedFile(null)
    setAnnotatedImageError(false)
    setReportDraft(EMPTY_REPORT)
    setConfirmedItems([])
    setChosenAction(null)
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
    setConfirmedItems([])
    setChosenAction(null)
    setSubmissionError('')

    try {
      const result = await analyzeWasteImage(selectedFile, controller.signal)
      if (!controller.signal.aborted) {
        setAnalysis(result)
        setAnalyzedFile(selectedFile)
        setReportDraft(result.report)
        setConfirmedItems(suggestedItems(result.detections))
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      const message =
        error instanceof WasteAnalysisRequestError
          ? error.message
          : error instanceof Error ? error.message : 'Waste analysis failed unexpectedly. Please try again.'
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
    if (!selectedLocation) {
      openLocationPicker(false)
      setLocationError('Choose and confirm the waste location before submitting.')
      return
    }
    if (!category || !reportAction) {
      setSubmissionError('Confirm every detected item and choose Report It Instead to submit a report.')
      return
    }

    const controller = new AbortController()
    submissionRequest.current = controller
    setIsSubmitting(true)
    setSubmissionError('')

    try {
      const result = await submitWasteReport(
        {
          analysis_id: analysis?.analysis_id,
          reporter_role: 'user',
          user_id: user?.id,
          title: reportDraft.title,
          summary: reportDraft.summary,
          waste_identified: reportDraft.waste_identified,
          recommended_action: reportDraft.recommended_action,
          environmental_concern: reportDraft.environmental_concern,
          category,
          confirmed_items: confirmedItems.map((item) => ({
            name: item.name.trim(),
            category: item.category as Exclude<ConfirmedItem['category'], ''>,
            material: item.material,
          })),
          location: selectedLocation.address,
          latitude: selectedLocation.latitude,
          longitude: selectedLocation.longitude,
          location_address: selectedLocation.address,
          location_address_source: selectedLocation.addressSource,
          location_street: selectedLocation.street ?? undefined,
          location_city: selectedLocation.city ?? undefined,
          location_state: selectedLocation.state ?? undefined,
          location_postcode: selectedLocation.postcode ?? undefined,
          location_country: selectedLocation.country ?? undefined,
          location_source: selectedLocation.source,
          site_notes: siteNotes,
        },
        controller.signal,
      )
      if (controller.signal.aborted) {
        return
      }
      if (role === 'user') {
        refreshMemberData()
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
          eyebrow="Waste reporting"
          title="Report waste"
          description="Analyze a photo first, review the findings, then add an incident location if you submit a report."
        />

        <div className="report-layout">
          <form className="report-form" onSubmit={handleSubmit}>
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
              <label className="button button--secondary camera-capture">
                <Camera size={17} /> Take a photo
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  capture="environment"
                  aria-label="Take a photo"
                  disabled={isSubmitting}
                  onChange={handleImageChange}
                />
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
                  <h2>Confirm analysis and report details</h2>
                  <p>Confirm each waste category and edit the report description.</p>
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
                    <p>Check the photo and retry. You can keep the selected image while correcting the error.</p>
                  </div>
                </div>
              )}

              {hasCurrentAnalysis && analysis && (
                <div className="analysis-results" aria-live="polite">
                  <div className="analysis-results__grid">
                    <figure className="annotated-image">
                      {analysis.annotated_image && !annotatedImageError ? (
                        <img
                          src={analysis.annotated_image}
                          alt="Waste image with AI-detected objects outlined"
                          onError={() => setAnnotatedImageError(true)}
                        />
                      ) : (
                        <div className="annotated-image__error">
                          <FileImage size={27} />
                          <span>Annotated image unavailable</span>
                        </div>
                      )}
                      <figcaption>AI-annotated waste image</figcaption>
                    </figure>

                    <div className="detection-panel">
                      <div className="detection-panel__heading">
                        <div>
                          <span>Waste summary</span>
                          <strong>
                            {analysis.grouped_objects.length}{' '}
                            {analysis.grouped_objects.length === 1
                              ? 'waste type'
                              : 'waste types'}
                          </strong>
                        </div>
                      </div>

                      <div className="detection-list">
                        {groupDetections(analysis).map((group) => (
                          <article className="detection-item" key={group.name}>
                            <div className="detection-item__title">
                              <strong>{group.label}</strong>
                              <span>Detected by AI</span>
                            </div>
                            <dl className="detection-item__details">
                              <div>
                                <dt>Quantity</dt>
                                <dd>{group.count ?? 'Not estimated'}</dd>
                              </div>
                              <div>
                                <dt>Category</dt>
                                <dd>{group.category}</dd>
                              </div>
                            </dl>
                          </article>
                        ))}
                      </div>
                      <div className="confirmed-items">
                        <h3>Confirm each detected item</h3>
                        <p>AI suggestions may be uncertain. Check the material and disposal guidance, then correct each item before choosing an action.</p>
                        {analysis.detections.map((detection, index) => (
                          <div className="confirmed-item" key={`${detection.name}-${index}`}>
                            <div className="field">
                              <label htmlFor={`item-name-${index}`}>Item {index + 1}</label>
                              <input
                                id={`item-name-${index}`}
                                value={confirmedItems[index]?.name ?? ''}
                                maxLength={150}
                                onChange={(event) => {
                                  setConfirmedItems((items) => items.map((item, itemIndex) =>
                                    itemIndex === index ? { ...item, name: event.target.value } : item))
                                  setChosenAction(null)
                                }}
                              />
                            </div>
                            <p>Material: {detection.material || 'Unknown'} · {detection.recommended_handling || 'Confirm a safe disposal route.'}</p>
                            {!detection.rule_known && <p className="field__hint">Classification uncertain. Choose a category manually.</p>}
                            <div className="field">
                              <label htmlFor={`item-category-${index}`}>Confirmed category for item {index + 1}</label>
                              <select
                                id={`item-category-${index}`}
                                value={confirmedItems[index]?.category ?? ''}
                                onChange={(event) => {
                                  setConfirmedItems((items) => items.map((item, itemIndex) =>
                                    itemIndex === index ? { ...item, category: event.target.value as ConfirmedItem['category'] } : item))
                                  setChosenAction(null)
                                }}
                              >
                                <option value="">Select category</option>
                                <option value="Recyclable Waste">Recyclable Waste</option>
                                <option value="Non-Recyclable Waste">Non-Recyclable Waste</option>
                                <option value="Bulky Waste">Bulky Waste</option>
                              </select>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <section className="ai-report">
                    <div className="ai-report__heading">
                      <BrainCircuit size={20} />
                      <div>
                        <span>AI-generated draft</span>
                        <h3>Review and edit report details</h3>
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
                  <h2>Choose an action</h2>
                  <p>Each item must be confirmed before the overall action is available.</p>
                </div>
              </div>
              {category ? (
                <div className="action-choice">
                  <p><strong>Confirmed overall category: {category}</strong></p>
                  {category === 'Recyclable Waste' ? (
                    <div className="action-choice__buttons">
                      <button type="button" className="button button--secondary" onClick={() => setChosenAction('recycle')}>Recycle It</button>
                      <button type="button" className="button button--secondary" onClick={() => setChosenAction('nearby')}>View nearby recycling points</button>
                      <button type="button" className="button button--primary" onClick={() => setChosenAction('report')}>Report It Instead</button>
                    </div>
                  ) : (
                    <p>{category === 'Bulky Waste' ? 'Bulky waste should be reported for collection.' : 'This waste should be reported for collection.'}</p>
                  )}
                  {chosenAction === 'nearby' && <>
                    {recyclingPointError && <p role="alert">{recyclingPointError}</p>}
                    <NearbyRecyclingMap registeredPoints={recyclingPoints} items={confirmedItems} compact />
                  </>}
                  {chosenAction === 'recycle' && category === 'Recyclable Waste' && (
                    <RecyclingRecommendations points={recyclingPoints} items={confirmedItems}
                      compact
                      wasteLocation={selectedLocation} loading={recyclingPointsLoading}
                      error={recyclingPointError} analysisId={analysis?.analysis_id ?? ''}
                      onReport={() => setChosenAction('report')}
                      onSubmitted={() => { refreshMemberData(); navigate('/account?recycling=submitted') }} />
                  )}
                </div>
              ) : hasCurrentAnalysis ? <p role="status">Confirm every detected item to continue.</p> : null}
              <label className="checkbox-field">
                <input type="checkbox" required />
                <span>
                  I confirm this report is accurate to the best of my knowledge.
                </span>
              </label>
            </section>

            <section className="form-section" aria-label="Waste location">
              <div className="form-section__heading">
                <span>4</span>
                <div>
                  <h2>Waste location</h2>
                  <p>Choose where the waste was found.</p>
                </div>
              </div>
              {!locationPickerOpen && <div className="report-location-summary" role="status">
                {selectedLocation && <p><strong>{selectedLocation.address}</strong>{siteNotes && <><br />Landmark: {siteNotes}</>}</p>}
                <button ref={locationTrigger} type="button" className="button button--secondary" onClick={() => openLocationPicker()}>
                  {selectedLocation ? 'Edit location' : 'Choose location'}
                </button>
              </div>}
              {locationError && <p role="alert" className="field__error">{locationError}</p>}
              {locationPickerOpen && <div ref={locationSearch} className="report-location-editor">
                <LocationPicker value={draftLocation} confirmed={false} incidentHint showCoordinates={false}
                  note={draftNote} onNoteChange={setDraftNote} confirmLabel="Confirm location" onCancel={closeLocationPicker}
                  onChange={setDraftLocation} onConfirm={() => {
                    if (!draftLocation) return
                    setSelectedLocation(draftLocation)
                    setSiteNotes(draftNote)
                    setLocationError('')
                    setSubmissionError('')
                    closeLocationPicker()
                  }} />
              </div>}
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
                  !hasCurrentAnalysis ||
                  !category ||
                  !reportAction
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
