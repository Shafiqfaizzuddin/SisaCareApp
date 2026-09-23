import type {
  AdminReportDetail,
  AdminWasteDetection,
  ReportStatus,
  ReportSummary,
  ReportValidationResult,
  ValidationStatus,
  WasteAnalysisReport,
  WasteCategory,
} from '../../types'
import { REPORT_SUBMISSION_URL } from '../reporting/report-submission'


function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('en-MY', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function mapSummary(value: unknown): ReportSummary | null {
  if (!isObject(value)) return null
  if (
    typeof value.id !== 'string' ||
    typeof value.reference !== 'string' ||
    typeof value.category !== 'string' ||
    typeof value.location !== 'string' ||
    typeof value.submitted_at !== 'string' ||
    typeof value.status !== 'string' ||
    typeof value.confidence !== 'number' ||
    typeof value.description !== 'string' ||
    typeof value.reporter !== 'string' ||
    typeof value.reporter_role !== 'string'
  ) {
    return null
  }
  return {
    id: value.id,
    reference: value.reference,
    category: value.category as WasteCategory,
    location: value.location,
    submittedAt: formatDate(value.submitted_at),
    status: value.status as ReportStatus,
    confidence: value.confidence,
    description: value.description,
    reporter: value.reporter,
    reporterRole: value.reporter_role as 'guest' | 'user',
    validationStatus: (value.validation_status ?? 'pending') as ValidationStatus,
  }
}

function mapDetection(value: unknown): AdminWasteDetection | null {
  if (!isObject(value)) return null
  const requiredStrings = [
    value.id,
    value.class_name,
    value.display_name,
    value.waste_category,
    value.material,
    value.created_at,
  ]
  const requiredNumbers = [
    value.confidence,
    value.x1,
    value.y1,
    value.x2,
    value.y2,
  ]
  if (
    !requiredStrings.every((item) => typeof item === 'string') ||
    !requiredNumbers.every((item) => typeof item === 'number')
  ) {
    return null
  }
  return {
    id: value.id as string,
    className: value.class_name as string,
    displayName: value.display_name as string,
    wasteCategory: value.waste_category as string,
    material: value.material as string,
    confidence: value.confidence as number,
    boundingBox: {
      x1: value.x1 as number,
      y1: value.y1 as number,
      x2: value.x2 as number,
      y2: value.y2 as number,
    },
    createdAt: value.created_at as string,
  }
}

function mapGeneratedReport(value: unknown): WasteAnalysisReport | null {
  if (!isObject(value)) return null
  const fields = [
    value.title,
    value.summary,
    value.waste_identified,
    value.recommended_action,
    value.environmental_concern,
  ]
  if (!fields.every((field) => typeof field === 'string')) return null
  return {
    title: value.title as string,
    summary: value.summary as string,
    waste_identified: value.waste_identified as string,
    recommended_action: value.recommended_action as string,
    environmental_concern: value.environmental_concern as string,
  }
}

export async function fetchPersistedReports(
  signal?: AbortSignal,
): Promise<ReportSummary[]> {
  const response = await fetch(REPORT_SUBMISSION_URL, { signal })
  if (!response.ok) return []
  const value: unknown = await response.json()
  return Array.isArray(value)
    ? value.map(mapSummary).filter((item): item is ReportSummary => item !== null)
    : []
}

export async function fetchPersistedReport(
  reportId: string,
  signal?: AbortSignal,
): Promise<AdminReportDetail | null> {
  const response = await fetch(`${REPORT_SUBMISSION_URL}/${encodeURIComponent(reportId)}`, {
    signal,
  })
  if (response.status === 404) return null
  if (!response.ok) throw new Error('Report details are unavailable.')
  const value: unknown = await response.json()
  if (!isObject(value) || !Array.isArray(value.detections)) return null
  const summary = mapSummary({
    ...value,
    submitted_at: value.created_at,
    confidence: 0,
    description: value.summary,
    validation_status: value.validation_status,
  })
  if (!summary) return null

  return {
    ...summary,
    siteNotes: typeof value.site_notes === 'string' ? value.site_notes : '',
    title: typeof value.title === 'string' ? value.title : '',
    summary: typeof value.summary === 'string' ? value.summary : '',
    wasteIdentified:
      typeof value.waste_identified === 'string' ? value.waste_identified : '',
    recommendedAction:
      typeof value.recommended_action === 'string' ? value.recommended_action : '',
    environmentalConcern:
      typeof value.environmental_concern === 'string'
        ? value.environmental_concern
        : '',
    generatedReport: mapGeneratedReport(value.generated_report),
    originalImage:
      typeof value.original_image === 'string' ? value.original_image : '',
    annotatedImage:
      typeof value.annotated_image === 'string' ? value.annotated_image : '',
    createdAt: value.created_at as string,
    updatedAt: typeof value.updated_at === 'string' ? value.updated_at : '',
    detections: value.detections
      .map(mapDetection)
      .filter((item): item is AdminWasteDetection => item !== null),
  }
}

export async function validatePersistedReport(
  reportId: string,
  validationStatus: 'valid' | 'invalid',
): Promise<ReportValidationResult> {
  const response = await fetch(
    `${REPORT_SUBMISSION_URL}/${encodeURIComponent(reportId)}/validation`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ validation_status: validationStatus }),
    },
  )
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new Error('The validation service returned an unreadable response.')
  }
  if (!response.ok) {
    throw new Error(
      isObject(value) && typeof value.detail === 'string'
        ? value.detail
        : 'The validation decision could not be saved.',
    )
  }
  if (
    !isObject(value) ||
    typeof value.report_id !== 'string' ||
    (value.validation_status !== 'valid' && value.validation_status !== 'invalid') ||
    typeof value.status !== 'string' ||
    typeof value.reward_awarded !== 'boolean' ||
    typeof value.reward_points !== 'number'
  ) {
    throw new Error('The validation service returned an unexpected result.')
  }
  return {
    reportId: value.report_id,
    validationStatus: value.validation_status,
    status: value.status as ReportStatus,
    rewardAwarded: value.reward_awarded,
    rewardPoints: value.reward_points,
  }
}
