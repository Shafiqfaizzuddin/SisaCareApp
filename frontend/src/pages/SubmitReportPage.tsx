import { AlertCircle, AlertTriangle, Award, Camera, Check, FileImage, Info, LoaderCircle, ScanLine, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageIntro } from '../components/common/PageIntro'
import { LocationPicker } from '../components/location/LocationPicker'
import { RecyclingRecommendations } from '../components/location/RecyclingRecommendations'
import { NearbyRecyclingMap } from '../components/location/NearbyRecyclingMap'
import { useRole } from '../features/authentication/useRole'
import { categoryForItems, type ConfirmedItem } from '../features/reporting/campus-workflow'
import { categoriesForItems, groupReviewedItems, initialItem, isCap, type ReviewedItem, type ReviewDisposition } from '../features/reporting/confirmation'
import { fetchRecyclingPoints, type RecyclingPoint } from '../features/reporting/recycling-points'
import { ReportSubmissionRequestError, submitWasteReport } from '../features/reporting/report-submission'
import { generateReportDraft, type ReportDraftResult } from '../features/reporting/report-draft'
import { classifyConfirmedItem } from '../features/reporting/waste-rules'
import { analyzeWasteImage, WasteAnalysisRequestError } from '../features/reporting/waste-analysis'
import type { CampusWasteCategory, FlorenceAnalysisSuccess, ReportLocation, WasteAnalysisReport } from '../types'

const MAX_IMAGE_SIZE = 10 * 1024 * 1024
const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])
const EMPTY_REPORT: WasteAnalysisReport = { title: '', summary: '', waste_identified: '', recommended_action: '', environmental_concern: '' }
const CATEGORIES: CampusWasteCategory[] = ['Recyclable Waste', 'Non-Recyclable Waste', 'Bulky Waste', 'Hazardous Waste']

export function SubmitReportPage() {
  const navigate = useNavigate()
  const { role, user, refreshMemberData } = useRole()
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [analysis, setAnalysis] = useState<FlorenceAnalysisSuccess | null>(null)
  const [analyzedFile, setAnalyzedFile] = useState<File | null>(null)
  const [analysisError, setAnalysisError] = useState('')
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [displayImageError, setDisplayImageError] = useState(false)
  const [showBoxes, setShowBoxes] = useState(true)
  const [manualMode, setManualMode] = useState(false)
  const [reviewedItems, setReviewedItems] = useState<ReviewedItem[]>([])
  const [ruleBusyId, setRuleBusyId] = useState<string | null>(null)
  const [ruleError, setRuleError] = useState('')
  const [chosenAction, setChosenAction] = useState<'report' | 'recycle' | 'nearby' | null>(null)
  const [recyclingPoints, setRecyclingPoints] = useState<RecyclingPoint[]>([])
  const [recyclingPointError, setRecyclingPointError] = useState('')
  const [recyclingPointsLoading, setRecyclingPointsLoading] = useState(false)
  const [reportDraft, setReportDraft] = useState<WasteAnalysisReport>(EMPTY_REPORT)
  const [userDescription, setUserDescription] = useState('')
  const [generatedDraft, setGeneratedDraft] = useState<ReportDraftResult | null>(null)
  const [draftNeedsRefresh, setDraftNeedsRefresh] = useState(false)
  const [draftError, setDraftError] = useState('')
  const [isDrafting, setIsDrafting] = useState(false)
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
  const draftRequest = useRef<AbortController | null>(null)
  const manuallyEditedReportFields = useRef<Set<keyof WasteAnalysisReport>>(new Set())
  const canUseAi = role === 'user'
  const hasCurrentAnalysis = selectedFile !== null && analysis !== null && analyzedFile === selectedFile
  const confirmedItems = reviewedItems.filter((item) => item.status === 'waste')
  const recyclableItems = confirmedItems.filter((item) => item.category === 'Recyclable Waste' && item.stationMaterialKey)
  const hasRecyclableItems = confirmedItems.some((item) => item.category === 'Recyclable Waste')
  const hasOtherWaste = confirmedItems.some((item) => item.category !== 'Recyclable Waste')
  const unresolvedItems = reviewedItems.some((item) => item.status === 'needs_confirmation' ||
    (item.quantity !== undefined && (!Number.isInteger(item.quantity) || item.quantity < 1 || item.quantity > 1000)) ||
    (isCap(item.name) && ((item.status === 'waste' && item.componentRelation !== 'detached') || (item.status === 'attached_component' && item.componentRelation !== 'attached'))))
  const category = unresolvedItems || reviewedItems.some((item) => !item.reviewed) ? null : categoryForItems(confirmedItems)
  const applicableCategories = categoriesForItems(confirmedItems)
  const groupedItems = groupReviewedItems(reviewedItems)
  const reportAction = !hasRecyclableItems || chosenAction === 'report'

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
      .catch((error: unknown) => { if (!controller.signal.aborted) setRecyclingPointError(error instanceof Error ? error.message : 'Registered recycling points could not be loaded.') })
      .finally(() => { if (!controller.signal.aborted) setRecyclingPointsLoading(false) })
    return () => controller.abort()
  }, [chosenAction])

  useEffect(() => {
    if (!selectedFile) { setPreviewUrl(''); return }
    const url = URL.createObjectURL(selectedFile)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [selectedFile])

  useEffect(() => () => {
    if (analysis?.display_image?.startsWith('blob:')) URL.revokeObjectURL(analysis.display_image)
  }, [analysis])

  useEffect(() => () => { analysisRequest.current?.abort(); submissionRequest.current?.abort(); draftRequest.current?.abort() }, [])

  function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    if (!ALLOWED_IMAGE_TYPES.has(file.type)) { event.target.value = ''; setAnalysisError('Choose a JPG, PNG, or WEBP image.'); return }
    if (file.size > MAX_IMAGE_SIZE) { event.target.value = ''; setAnalysisError('Choose an image smaller than 10 MB.'); return }
    analysisRequest.current?.abort()
    analysisRequest.current = null
    setIsAnalyzing(false)
    setSelectedFile(file)
    setAnalysis(null)
    setAnalyzedFile(null)
    setDisplayImageError(false)
    setManualMode(false)
    setReviewedItems([])
    setReportDraft(EMPTY_REPORT)
    manuallyEditedReportFields.current.clear()
    setUserDescription('')
    setGeneratedDraft(null)
    setDraftNeedsRefresh(false)
    draftRequest.current?.abort()
    draftRequest.current = null
    setIsDrafting(false)
    setChosenAction(null)
    setAnalysisError('')
    setSubmissionError('')
  }

  async function handleAnalyze() {
    if (!canUseAi) { navigate('/login', { state: { returnTo: '/report' } }); return }
    if (!selectedFile || analysisRequest.current || isAnalyzing) return
    const controller = new AbortController()
    analysisRequest.current = controller
    setIsAnalyzing(true)
    setAnalysisError('')
    // Preserve the previous result and edits until a replacement succeeds.
    try {
      const result = await analyzeWasteImage(selectedFile, controller.signal)
      if (!controller.signal.aborted) {
        setAnalysis(result)
        setAnalyzedFile(selectedFile)
        setReviewedItems(result.detections.map(initialItem))
        setGeneratedDraft(null)
        setDraftNeedsRefresh(false)
        setReportDraft(EMPTY_REPORT)
        manuallyEditedReportFields.current.clear()
        setManualMode(false)
        setDisplayImageError(false)
        setChosenAction(null)
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setAnalysisError(error instanceof WasteAnalysisRequestError ? error.message : 'Photo analysis failed. You can identify items manually.')
      if (!hasCurrentAnalysis) setManualMode(true)
    } finally {
      if (analysisRequest.current === controller) { analysisRequest.current = null; setIsAnalyzing(false) }
    }
  }

  function updateItem(id: string, patch: Partial<ReviewedItem>) {
    draftRequest.current?.abort()
    if (generatedDraft) setDraftNeedsRefresh(true)
    setReviewedItems((items) => items.map((item) => item.id === id ? { ...item, ...patch } : item))
    setChosenAction(null)
  }

  function addItem() {
    draftRequest.current?.abort()
    if (generatedDraft) setDraftNeedsRefresh(true)
    setReviewedItems((items) => [...items, { id: `manual-${crypto.randomUUID()}`, sourceDetectionId: null, originalLabel: null,
      name: '', material: 'Unknown', category: '', status: 'waste', componentRelation: null, reviewed: false, condition_answers: {} }])
    setChosenAction(null)
  }

  async function applyRules(item: ReviewedItem) {
    if (!item.name.trim() || ruleBusyId) return
    setRuleBusyId(item.id)
    setRuleError('')
    try {
      const result = await classifyConfirmedItem(item.name.trim(), item.material, item.condition_answers ?? {})
      setReviewedItems((items) => items.map((current) => current.id === item.id &&
        current.name === item.name && current.material === item.material
        ? { ...current, category: result.category ?? current.category,
          material: result.material ?? current.material, questions: result.questions,
          handlingGuidance: result.handling_guidance, confirmationReason: result.confirmation_reason,
          ruleId: result.rule_id, stationMaterialKey: result.station_material_key, reviewed: false }
        : current))
    } catch (error) {
      setRuleError(error instanceof Error ? error.message : 'Waste rules are unavailable.')
    } finally {
      setRuleBusyId(null)
    }
  }

  function reviewPayload() {
    return {
      analysis_id: hasCurrentAnalysis ? analysis?.analysis_id : undefined,
      confirmed_items: confirmedItems.map((item) => ({ review_id: item.id, name: item.name.trim(),
        category: item.category as CampusWasteCategory, material: item.material, quantity: item.quantity,
        condition_answers: item.condition_answers })),
      reviewed_detections: reviewedItems.map((item) => ({ id: item.id, source_detection_id: item.sourceDetectionId,
        disposition: item.status, corrected_label: item.name.trim(), material: item.material,
        category: item.status === 'waste' ? item.category as CampusWasteCategory : null,
        quantity: item.quantity, condition_answers: item.condition_answers ?? {}, component_relation: item.componentRelation })),
    }
  }

  async function handleGenerateDraft() {
    if (!category || draftRequest.current || isDrafting) return
    const controller = new AbortController()
    draftRequest.current = controller
    setIsDrafting(true)
    setDraftError('')
    try {
      const result = await generateReportDraft({ ...reviewPayload(), user_description: userDescription,
        confirmed_address: selectedLocation?.address ?? '' }, controller.signal)
      if (controller.signal.aborted) return
      setGeneratedDraft(result)
      setDraftNeedsRefresh(false)
      setReportDraft((current) => ({
        title: manuallyEditedReportFields.current.has('title') ? current.title : result.title,
        summary: manuallyEditedReportFields.current.has('summary') ? current.summary : result.summary,
        waste_identified: manuallyEditedReportFields.current.has('waste_identified') ? current.waste_identified : result.waste_identified,
        recommended_action: manuallyEditedReportFields.current.has('recommended_action') ? current.recommended_action : result.recommended_action,
        environmental_concern: manuallyEditedReportFields.current.has('environmental_concern') ? current.environmental_concern : result.environmental_concern,
      }))
    } catch (error) {
      if (!controller.signal.aborted) setDraftError(error instanceof Error ? error.message : 'Report drafting failed. You can still write and submit the report.')
    } finally {
      if (draftRequest.current === controller) { draftRequest.current = null; setIsDrafting(false) }
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (isAnalyzing || submissionRequest.current || isSubmitting) return
    if (!selectedFile) { setSubmissionError('Choose a waste photo before submitting.'); return }
    if (!hasCurrentAnalysis && !manualMode) { setAnalysisError('Analyze the photo or identify items manually.'); return }
    if (!category || !reportAction) { setSubmissionError('Resolve uncertain objects and confirm at least one waste item and a report action.'); return }
    if (!selectedLocation) { openLocationPicker(false); setLocationError('Choose and confirm the waste location before submitting.'); return }
    const controller = new AbortController()
    submissionRequest.current = controller
    setIsSubmitting(true)
    setSubmissionError('')
    try {
      const result = await submitWasteReport({
        rule_version: '1.0.0',
        reporter_role: 'user', user_id: user?.id,
        ...reportDraft, category,
        ...reviewPayload(),
        location: selectedLocation.address, latitude: selectedLocation.latitude, longitude: selectedLocation.longitude,
        location_address: selectedLocation.address, location_address_source: selectedLocation.addressSource,
        location_street: selectedLocation.street ?? undefined, location_city: selectedLocation.city ?? undefined,
        location_state: selectedLocation.state ?? undefined, location_postcode: selectedLocation.postcode ?? undefined,
        location_country: selectedLocation.country ?? undefined, location_source: selectedLocation.source, site_notes: siteNotes,
      }, controller.signal, hasCurrentAnalysis ? undefined : selectedFile)
      if (controller.signal.aborted) return
      if (role === 'user') refreshMemberData()
      navigate('/report/success', { state: { reference: result.reference, submittedAt: result.submitted_at, isMember: role === 'user' } })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setSubmissionError(error instanceof ReportSubmissionRequestError ? error.message : 'The report could not be submitted. Please try again.')
    } finally {
      if (submissionRequest.current === controller) { submissionRequest.current = null; setIsSubmitting(false) }
    }
  }

  return <section className="section report-page"><div className="container">
    <PageIntro eyebrow="Waste reporting" title="Report waste" description="Analyze a photo, review possible waste, then add the incident location when you submit." />
    <div className="report-layout"><form className="report-form" onSubmit={handleSubmit}>
      <section className="form-section"><div className="form-section__heading"><span>1</span><div><h2>Add a photo</h2><p>Use a clear image that shows the waste and its surroundings.</p></div></div>
        <label className="upload-field"><input type="file" accept="image/jpeg,image/png,image/webp" disabled={isSubmitting} onChange={handleImageChange} />
          <span className="upload-field__icon">{selectedFile ? <FileImage size={25} /> : <Camera size={25} />}</span>
          <strong>{selectedFile?.name || 'Choose a waste photo'}</strong><span>JPG, PNG, or WEBP up to 10 MB</span></label>
        <label className="button button--secondary camera-capture"><Camera size={17} /> Take a photo
          <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" aria-label="Take a photo" disabled={isSubmitting} onChange={handleImageChange} /></label>
        {previewUrl && <figure className="upload-preview"><img src={previewUrl} alt="Selected waste" /><figcaption><FileImage size={16} /> {selectedFile?.name}</figcaption></figure>}
      </section>
      <section className="form-section"><div className="form-section__heading"><span>2</span><div><h2>Review photo and report details</h2><p>Check each object before deciding whether it is waste.</p></div></div>
        <div className="analysis-controls"><button className="button button--primary" type="button" disabled={!selectedFile || isAnalyzing || isSubmitting} onClick={handleAnalyze}>
          {isAnalyzing ? <LoaderCircle className="spin" size={18} /> : <ScanLine size={18} />}{isAnalyzing ? 'Analysis in progress' : 'Analyze photo'}</button>
          {hasCurrentAnalysis && <span className="analysis-complete"><Check size={17} /> Analysis complete</span>}
        </div>
        {isAnalyzing && <div className="analysis-processing" role="status"><LoaderCircle className="spin" size={20} /> Detecting objects locally. This may take a moment.</div>}
        {analysisError && <div className="analysis-error" role="alert"><AlertCircle size={19} /><div><strong>Analysis could not be completed</strong><p>{analysisError}</p><p>Your photo and entered details are still here. Retry or identify items manually.</p></div></div>}
        {selectedFile && !hasCurrentAnalysis && <button type="button" className="button button--secondary" onClick={() => canUseAi ? setManualMode(true) : navigate('/login', { state: { returnTo: '/report' } })}>{canUseAi ? 'Identify items manually' : 'Sign in to report waste'}</button>}
        {hasCurrentAnalysis && analysis && <div className="analysis-results" aria-live="polite"><div className="analysis-results__grid">
          <figure className="florence-photo"><div className="florence-photo__frame">
            <img src={analysis.display_image && !displayImageError ? analysis.display_image : previewUrl} alt="Uploaded waste photo" onError={() => setDisplayImageError(true)} />
            {analysis.display_image && !displayImageError && showBoxes && <svg viewBox={`0 0 ${analysis.image_width} ${analysis.image_height}`} preserveAspectRatio="none" aria-label="Detected object outlines">
              {analysis.detections.map(({ id, bounding_box: box }) => <rect key={id} x={box.x1} y={box.y1} width={box.x2 - box.x1} height={box.y2 - box.y1} className={`florence-photo__box florence-photo__box--${reviewedItems.find((item) => item.sourceDetectionId === id)?.status ?? 'needs_confirmation'}`} />)}
            </svg>}
          </div><figcaption>Photo analyzed with {analysis.model_id} in {analysis.processing_time_ms} ms</figcaption>
            {analysis.display_image && !displayImageError && <label><input type="checkbox" checked={showBoxes} onChange={(event) => setShowBoxes(event.target.checked)} /> Show object outlines</label>}
            {(!analysis.display_image || displayImageError) && <p>Aligned preview unavailable; outlines are hidden.</p>}
          </figure>
          <div className="detection-panel"><h3>{analysis.detections.length} objects to review</h3><p>Detections may be waste, background, or uncertain. No confidence score is available.</p>
            {analysis.detections.length === 0 && <p>No objects were detected. Add an item if the photo contains waste.</p>}
            {analysis.warnings.map((warning, index) => <p key={index}>{warning}</p>)}
          </div></div></div>}
        {(hasCurrentAnalysis || manualMode) && <div className="analysis-results"><div className="confirmed-items"><h3>Identify waste items</h3>
          {groupedItems.map((group, groupIndex) => <section className="review-group" key={`${group[0].id}-${groupIndex}`}>
            <h4>{group[0].name.trim() || 'Unnamed item'} <small>({group.length} {group.every((item) => item.reviewed && item.status === 'waste') ? 'confirmed items' : 'possible detections'})</small></h4>
            {group.length > 1 && <p>Review each occurrence. Counts are provisional until confirmed.</p>}
            {group.map((item) => {
              const index = reviewedItems.findIndex((candidate) => candidate.id === item.id)
              return <div className="confirmed-item" key={item.id}>
                <p><strong>{item.sourceDetectionId ? `Detection ${index + 1}` : 'Added item'}</strong>{item.originalLabel && ` · Model label: ${item.originalLabel}`}</p>
                <div className="field"><label htmlFor={`item-name-${index}`}>Correct item label</label><input id={`item-name-${index}`} value={item.name} maxLength={150} onChange={(event) => updateItem(item.id, { name: event.target.value, material: 'Unknown', category: '', questions: [], condition_answers: {}, handlingGuidance: '', confirmationReason: null, ruleId: undefined, stationMaterialKey: null, reviewed: false, componentRelation: isCap(event.target.value) ? 'unclear' : null })} /></div>
                {item.status === 'waste' && item.handlingGuidance && <p><strong>Reviewed handling:</strong> {item.handlingGuidance}</p>}
                {item.confirmationReason && <p className="field__hint">{item.confirmationReason}</p>}
                {item.status === 'waste' && <button type="button" className="button button--secondary" disabled={ruleBusyId !== null || !item.name.trim()} onClick={() => void applyRules(item)}>{ruleBusyId === item.id ? 'Checking rules…' : 'Apply waste rules'}</button>}
                <div className="field"><label htmlFor={`item-status-${index}`}>Review decision</label><select id={`item-status-${index}`} value={item.status} onChange={(event) => updateItem(item.id, { status: event.target.value as ReviewDisposition, reviewed: false })}>
                  <option value="needs_confirmation">Needs confirmation</option><option value="waste">Waste item</option>
                  {item.sourceDetectionId && <><option value="background">Background / not waste</option><option value="removed">Remove incorrect item</option></>}
                  {isCap(item.name) && <option value="attached_component">Attached cap (part of bottle)</option>}</select></div>
                {isCap(item.name) && item.status !== 'background' && item.status !== 'removed' && <div className="field"><label htmlFor={`item-relation-${index}`}>Bottle cap relationship</label><select id={`item-relation-${index}`} value={item.componentRelation ?? 'unclear'} onChange={(event) => {
                  const relation = event.target.value as 'attached' | 'detached' | 'unclear'
                  updateItem(item.id, { componentRelation: relation, status: relation === 'attached' ? 'attached_component' : relation === 'detached' ? 'waste' : 'needs_confirmation', reviewed: false })
                }}><option value="unclear">Unclear — review</option><option value="attached">Attached to bottle (do not count separately)</option><option value="detached">Detached (separate item)</option></select></div>}
                {item.status === 'waste' && <><div className="field"><label htmlFor={`item-${index}-material`}>Confirmed material</label><input id={`item-${index}-material`} value={item.material === 'Unknown' ? '' : item.material} placeholder="Unknown" maxLength={150} onChange={(event) => updateItem(item.id, { material: event.target.value || 'Unknown', category: '', handlingGuidance: '', confirmationReason: null, ruleId: undefined, stationMaterialKey: null, reviewed: false })} /></div>
                  <div className="field"><label htmlFor={`item-${index}-quantity`}>Quantity (optional, only if counted)</label><input id={`item-${index}-quantity`} type="number" min="1" max="1000" value={item.quantity ?? ''} onChange={(event) => updateItem(item.id, { quantity: event.target.value ? Number(event.target.value) : undefined, reviewed: false })} /></div>
                  <div className="field"><label htmlFor={`item-category-${index}`}>Confirmed category</label><select id={`item-category-${index}`} value={item.category} onChange={(event) => updateItem(item.id, { category: event.target.value as ConfirmedItem['category'], handlingGuidance: '', ruleId: undefined, stationMaterialKey: null, reviewed: false })}>
                    <option value="">Select category</option>{CATEGORIES.map((value) => <option key={value} value={value}>{value}</option>)}</select></div>
                  {item.questions?.filter((question) => question.key !== 'material').map((question) => <div className="field" key={question.key}><label htmlFor={`item-${index}-${question.key}`}>{question.prompt}</label><select id={`item-${index}-${question.key}`} value={item.condition_answers?.[question.key] === undefined ? '' : String(item.condition_answers[question.key])} onChange={(event) => updateItem(item.id, { condition_answers: { ...item.condition_answers, [question.key]: event.target.value === 'true' }, category: '', handlingGuidance: '', confirmationReason: null, ruleId: undefined, stationMaterialKey: null, reviewed: false })}>
                    <option value="">Select answer</option><option value="true">Yes</option><option value="false">No</option></select></div>)}
                  {item.category === 'Hazardous Waste' && <p className="review-hazard" role="status">Hazardous waste — handle according to the reviewed guidance. Do not use an ordinary recycling station.</p>}</>}
                <label className="checkbox-field"><input type="checkbox" checked={item.reviewed} disabled={item.status === 'needs_confirmation' || (item.quantity !== undefined && (!Number.isInteger(item.quantity) || item.quantity < 1 || item.quantity > 1000)) || (item.status === 'attached_component' && item.componentRelation !== 'attached') || (item.status === 'waste' && (!item.name.trim() || !item.category || (isCap(item.name) && item.componentRelation !== 'detached')))} onChange={(event) => updateItem(item.id, { reviewed: event.target.checked })} /> I confirm this decision</label>
                {!item.sourceDetectionId && <button type="button" className="button button--secondary" onClick={() => { setReviewedItems((items) => items.filter((candidate) => candidate.id !== item.id)); if (generatedDraft) setDraftNeedsRefresh(true) }}>Remove added item</button>}
              </div>
            })}
          </section>)}
          {ruleError && <p role="alert">{ruleError}</p>}
          <button type="button" className="button button--secondary" onClick={addItem}>Add missed waste item</button>
        </div>
      </div>}
      </section>
      <section className="form-section"><div className="form-section__heading"><span>3</span><div><h2>Choose an action</h2><p>Resolve uncertain objects and confirm the waste items first.</p></div></div>
        {category ? <div className="action-choice"><p><strong>Primary report category: {category}</strong></p>
          <p>Confirmed item categories: {applicableCategories.join(', ')}.</p>
          {applicableCategories.includes('Hazardous Waste') && <p className="review-hazard" role="status">Hazardous item present. Keep it separate and follow its reviewed handling guidance.</p>}
          {hasOtherWaste && <p>Non-recyclable, bulky, and hazardous items use the staff reporting path.</p>}
          {hasRecyclableItems ? <div className="action-choice__buttons">
            {hasCurrentAnalysis && <button type="button" className="button button--secondary" onClick={() => setChosenAction('recycle')}>{hasOtherWaste ? 'Stations for recyclable items' : 'Recycle It'}</button>}
            <button type="button" className="button button--secondary" onClick={() => setChosenAction('nearby')}>View registered recycling points</button>
            <button type="button" className="button button--primary" onClick={() => setChosenAction('report')}>{hasOtherWaste ? 'Report all items to staff' : 'Report It Instead'}</button>
          </div> : <p>Report this waste for staff collection.</p>}
          {hasRecyclableItems && recyclableItems.length === 0 && <p role="status">Apply waste rules to the recyclable items before viewing material-matched stations.</p>}
          {chosenAction === 'nearby' && <><p role="alert">{recyclingPointError}</p><NearbyRecyclingMap registeredPoints={recyclingPoints} items={recyclableItems} compact /></>}
          {chosenAction === 'recycle' && hasCurrentAnalysis && <RecyclingRecommendations points={recyclingPoints} items={recyclableItems} compact allowProof={!hasOtherWaste && recyclableItems.length === confirmedItems.length} proofUnavailableReason={hasOtherWaste ? 'This photo also contains items for staff reporting. Use a separate photo of the recyclable items for a recycling-proof activity.' : undefined} wasteLocation={selectedLocation} loading={recyclingPointsLoading} error={recyclingPointError} analysisId={analysis?.analysis_id ?? ''} onReport={() => setChosenAction('report')} onSubmitted={() => { refreshMemberData(); navigate('/account?recycling=submitted') }} />}
        </div> : (hasCurrentAnalysis || manualMode) && <p role="status">Confirm at least one waste item and resolve uncertain objects to continue.</p>}
        <label className="checkbox-field"><input type="checkbox" required /><span>I confirm this report is accurate to the best of my knowledge.</span></label>
      </section>
      <section className="form-section" aria-label="Waste location"><div className="form-section__heading"><span>4</span><div><h2>Waste location</h2><p>Choose where the waste was found.</p></div></div>
        {!locationPickerOpen && <div className="report-location-summary" role="status">{selectedLocation && <p><strong>{selectedLocation.address}</strong>{siteNotes && <><br />Landmark: {siteNotes}</>}</p>}
          <button ref={locationTrigger} type="button" className="button button--secondary" onClick={() => openLocationPicker()}>{selectedLocation ? 'Edit location' : 'Choose location'}</button></div>}
        {locationError && <p role="alert" className="field__error">{locationError}</p>}
        {locationPickerOpen && <div ref={locationSearch} className="report-location-editor"><LocationPicker value={draftLocation} confirmed={false} incidentHint showCoordinates={false} note={draftNote} onNoteChange={setDraftNote} confirmLabel="Confirm location" onCancel={closeLocationPicker} onChange={setDraftLocation} onConfirm={() => {
          if (!draftLocation) return
          setSelectedLocation(draftLocation); setSiteNotes(draftNote); if (generatedDraft) setDraftNeedsRefresh(true); setLocationError(''); setSubmissionError(''); closeLocationPicker()
        }} /></div>}
      </section>
      {(hasCurrentAnalysis || manualMode) && reportAction && <section className="form-section"><div className="form-section__heading"><span>5</span><div><h2>Review and draft report</h2><p>Generate a local draft after confirming items and choosing the incident location, or write your own.</p></div></div>
        <section className="ai-report"><div className="ai-report__heading"><div><span>Report details</span><h3>Draft and review your report</h3></div></div><div className="ai-report__editor">
          <div className="field"><label htmlFor="report-user-description">Your description for the draft (optional)</label><textarea id="report-user-description" value={userDescription} maxLength={1000} rows={3} onChange={(event) => { setUserDescription(event.target.value); if (generatedDraft) setDraftNeedsRefresh(true) }} /><p className="field__hint">Review the editable report fields below; this note is drafting input.</p></div>
          <button type="button" className="button button--secondary" disabled={!category || isDrafting} onClick={handleGenerateDraft}>{isDrafting ? 'Drafting report…' : generatedDraft ? 'Regenerate report draft' : 'Generate report draft'}</button>
          {draftError && <p role="alert">{draftError} Your edits remain available.</p>}
          {generatedDraft && draftNeedsRefresh && <p role="status">Confirmed facts changed. Regenerate the draft or review and update the report fields before submitting.</p>}
          {generatedDraft && <div className="report-draft-preview"><p><strong>Editable preview · {generatedDraft.source === 'ollama' ? `Local Ollama (${generatedDraft.model_id})` : 'Factual template'}</strong></p>
            <p><strong>Title:</strong> {generatedDraft.title}</p><p><strong>Description:</strong> {generatedDraft.summary}</p>
            <button type="button" className="button button--secondary" onClick={() => setReportDraft((current) => ({ ...current, title: generatedDraft.title, summary: generatedDraft.summary }))}>Use preview title and description</button>
            <p>Review every field below before submitting. Generating a draft never submits the report.</p></div>}
          {([['title', 'Title', 180], ['summary', 'Summary', 4000], ['waste_identified', 'Waste identified', 2000], ['recommended_action', 'Recommended action', 2000], ['environmental_concern', 'Environmental concern', 2000]] as const).map(([key, label, maxLength]) => <div className="field" key={key}>
            <label htmlFor={`report-${key}`}>{label}</label>{key === 'title'
              ? <input id={`report-${key}`} value={reportDraft[key]} maxLength={maxLength} required onChange={(event) => { manuallyEditedReportFields.current.add(key); setReportDraft((current) => ({ ...current, [key]: event.target.value })) }} />
              : <textarea id={`report-${key}`} value={reportDraft[key]} maxLength={maxLength} rows={4} required onChange={(event) => { manuallyEditedReportFields.current.add(key); setReportDraft((current) => ({ ...current, [key]: event.target.value })) }} />}</div>)}
        </div></section></section>}
      <div className="form-actions">{submissionError && <div className="analysis-error form-actions__error" role="alert"><AlertCircle size={19} /><div><strong>Report not submitted</strong><p>{submissionError}</p></div></div>}
        <p><ShieldCheck size={17} /> Your report is shared only with authorised response teams.</p>
        <button className="button button--primary" type="submit" disabled={isAnalyzing || isSubmitting || !selectedFile || (!hasCurrentAnalysis && !manualMode) || !category || !reportAction}>
          {isSubmitting ? 'Submitting report' : 'Submit report'} {isSubmitting ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />}</button></div>
    </form><aside className="report-guidance"><div className="guidance-block guidance-block--warning"><AlertTriangle size={21} /><div><h2>Stay at a safe distance</h2><p>Do not touch chemicals, sharp objects, smoke, or unknown containers. Contact emergency services for immediate danger.</p></div></div>
      <div className="guidance-block"><Info size={21} /><div><h2>A useful photo includes</h2><ul><li>The full waste pile</li><li>A nearby landmark or road</li><li>Any access obstruction</li></ul></div></div>
      {role === 'user' && <div className="guidance-block guidance-block--reward"><Award size={21} /><div><h2>Rewards after verification</h2><p>Points are awarded only after an administrator confirms the submitted report is valid. Photo analysis does not award points.</p></div></div>}
    </aside></div></div></section>
}
