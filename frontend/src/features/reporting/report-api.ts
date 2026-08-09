import { supabase } from '../../lib/supabase'
import type {
  ReportStatus,
  ReportSummary,
  ValidationStatus,
  WasteCategory,
} from '../../types'

const REPORT_SELECT = `
  report_id,
  reference,
  user_id,
  reporter_type,
  guest_name,
  guest_email,
  description,
  image_path,
  selected_waste_category_id,
  latitude,
  longitude,
  location_address,
  validation_status,
  case_status,
  submitted_at,
  profile:profiles!reports_user_id_fkey(id, name, email),
  ai_analysis:ai_analyses(
    confidence_score,
    risk_level,
    generated_report,
    model_name,
    waste_category_id
  ),
  status_history:report_status_history(
    history_id,
    previous_status,
    new_status,
    note,
    changed_at,
    actor:profiles!report_status_history_changed_by_fkey(name)
  ),
  validations:report_validations(
    validation_id,
    validation_status,
    validation_note,
    validated_at,
    admin:profiles!report_validations_admin_id_fkey(name)
  )
`

type UnknownRecord = Record<string, unknown>

function asRecord(value: unknown): UnknownRecord | null {
  if (!value || Array.isArray(value) || typeof value !== 'object') return null
  return value as UnknownRecord
}

function firstRecord(value: unknown): UnknownRecord | null {
  if (Array.isArray(value)) return asRecord(value[0])
  return asRecord(value)
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function numberValue(value: unknown): number | undefined {
  if (value === null || value === undefined) return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function mapReport(row: UnknownRecord): ReportSummary {
  const profile = firstRecord(row.profile)
  const analysis = firstRecord(row.ai_analysis)
  const category = stringValue(
    analysis?.waste_category_id ?? row.selected_waste_category_id,
    'other',
  ) as WasteCategory

  return {
    id: stringValue(row.report_id),
    reference: stringValue(row.reference),
    category,
    location: stringValue(row.location_address),
    submittedAt: stringValue(row.submitted_at),
    status: stringValue(row.case_status, 'processing') as ReportStatus,
    confidence: numberValue(analysis?.confidence_score) ?? 0,
    description: stringValue(row.description, 'No additional description provided.'),
    reporter: stringValue(profile?.name ?? row.guest_name, 'Public submission'),
    reporterEmail: stringValue(profile?.email ?? row.guest_email) || undefined,
    reporterRole: stringValue(row.reporter_type, 'guest') as 'guest' | 'user',
    validationStatus: stringValue(
      row.validation_status,
      'pending',
    ) as ValidationStatus,
    userId: stringValue(row.user_id) || undefined,
    imagePath: stringValue(row.image_path) || undefined,
    latitude: numberValue(row.latitude),
    longitude: numberValue(row.longitude),
    generatedReport: stringValue(analysis?.generated_report) || undefined,
    riskLevel: stringValue(analysis?.risk_level) || undefined,
    modelName: stringValue(analysis?.model_name) || undefined,
    statusHistory: (Array.isArray(row.status_history) ? row.status_history : [])
      .map(asRecord)
      .filter((entry): entry is UnknownRecord => entry !== null)
      .map((entry) => ({
        id: stringValue(entry.history_id),
        previousStatus: stringValue(entry.previous_status) as ReportStatus,
        newStatus: stringValue(entry.new_status) as ReportStatus,
        note: stringValue(entry.note) || undefined,
        changedAt: stringValue(entry.changed_at),
        changedBy: stringValue(firstRecord(entry.actor)?.name, 'Administrator'),
      }))
      .sort((a, b) => Date.parse(b.changedAt) - Date.parse(a.changedAt)),
    validations: (Array.isArray(row.validations) ? row.validations : [])
      .map(asRecord)
      .filter((entry): entry is UnknownRecord => entry !== null)
      .map((entry) => ({
        id: stringValue(entry.validation_id),
        status: stringValue(entry.validation_status) as 'valid' | 'invalid',
        note: stringValue(entry.validation_note) || undefined,
        validatedAt: stringValue(entry.validated_at),
        adminName: stringValue(firstRecord(entry.admin)?.name, 'Administrator'),
      }))
      .sort((a, b) => Date.parse(b.validatedAt) - Date.parse(a.validatedAt)),
  }
}

export function formatReportDate(value: string): string {
  if (!value) return 'Unknown date'
  return new Intl.DateTimeFormat('en-MY', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export async function getAdminReports(): Promise<ReportSummary[]> {
  const { data, error } = await supabase
    .from('reports')
    .select(REPORT_SELECT)
    .order('submitted_at', { ascending: false })

  if (error) throw error
  return (data as unknown as UnknownRecord[]).map(mapReport)
}

export async function getAdminReport(reportId: string): Promise<ReportSummary> {
  const { data, error } = await supabase
    .from('reports')
    .select(REPORT_SELECT)
    .eq('report_id', reportId)
    .single()

  if (error) throw error
  return mapReport(data as unknown as UnknownRecord)
}

export async function getMyReports(): Promise<ReportSummary[]> {
  const { data, error } = await supabase
    .from('reports')
    .select(REPORT_SELECT)
    .order('submitted_at', { ascending: false })

  if (error) throw error
  return (data as unknown as UnknownRecord[]).map(mapReport)
}

export interface SubmitReportInput {
  file: File
  userId?: string
  guestName?: string
  guestEmail?: string
  description: string
  locationAddress: string
  category: WasteCategory
  latitude?: number
  longitude?: number
}

export interface SubmittedReport {
  id: string
  reference: string
  submittedAt: string
  awardedPoints: number
}

export async function submitReport(input: SubmitReportInput): Promise<SubmittedReport> {
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(input.file.type)) {
    throw new Error('Upload a JPG, PNG, or WEBP image.')
  }
  if (input.file.size > 10 * 1024 * 1024) {
    throw new Error('The image must be 10 MB or smaller.')
  }

  const extension = input.file.name.split('.').pop()?.toLowerCase() || 'jpg'
  const folder = input.userId ?? 'guest'
  const imagePath = `${folder}/${crypto.randomUUID()}.${extension}`
  const { error: uploadError } = await supabase.storage
    .from('report-images')
    .upload(imagePath, input.file, {
      cacheControl: '3600',
      contentType: input.file.type,
      upsert: false,
    })

  if (uploadError) throw uploadError

  const { data, error } = await supabase.rpc('submit_report', {
    guest_name: input.guestName ?? '',
    guest_email: input.guestEmail ?? '',
    description: input.description,
    image_path: imagePath,
    location_address: input.locationAddress,
    latitude: input.latitude ?? null,
    longitude: input.longitude ?? null,
    selected_waste_category_id: input.category,
  })

  if (error) {
    if (input.userId) {
      await supabase.storage.from('report-images').remove([imagePath])
    }
    throw error
  }

  const result = firstRecord(data)
  if (!result) throw new Error('The report was submitted without a response.')

  return {
    id: stringValue(result.report_id),
    reference: stringValue(result.reference),
    submittedAt: stringValue(result.submitted_at),
    awardedPoints: numberValue(result.awarded_points) ?? 0,
  }
}

export async function validateReport(
  reportId: string,
  decision: 'valid' | 'invalid',
  note?: string,
): Promise<void> {
  const { error } = await supabase.rpc('admin_validate_report', {
    target_report_id: reportId,
    decision,
    note: note ?? null,
  })
  if (error) throw error
}

export async function updateReportStatus(
  reportId: string,
  status: ReportStatus,
  note?: string,
): Promise<void> {
  const { error } = await supabase.rpc('admin_update_report_status', {
    target_report_id: reportId,
    new_status: status,
    note: note ?? null,
  })
  if (error) throw error
}

export async function getReportImageUrl(imagePath: string): Promise<string> {
  const { data, error } = await supabase.storage
    .from('report-images')
    .createSignedUrl(imagePath, 60 * 30)
  if (error) throw error
  return data.signedUrl
}

export async function getRewardRulePoints(): Promise<{
  submission: number
  validation: number
}> {
  const { data, error } = await supabase
    .from('reward_rules')
    .select('reward_type, points')
    .in('reward_type', ['report_submitted', 'valid_report'])

  if (error) throw error
  const rules = new Map(
    (data ?? []).map((rule) => [rule.reward_type as string, Number(rule.points)]),
  )
  return {
    submission: rules.get('report_submitted') ?? 0,
    validation: rules.get('valid_report') ?? 0,
  }
}
