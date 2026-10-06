import type {
  MemberDashboardData,
  MemberReportSummary,
  ReportStatus,
  ValidationStatus,
} from '../../types'
import { authenticatedFetch } from '../authentication/authenticated-fetch'


const configuredDashboardUrl = import.meta.env.VITE_MEMBER_DASHBOARD_URL as
  | string
  | undefined

export const MEMBER_DASHBOARD_URL =
  configuredDashboardUrl?.trim() || '/api/members/me/dashboard'

export class MemberDashboardRequestError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'MemberDashboardRequestError'
  }
}

const REPORT_STATUSES = new Set<ReportStatus>([
  'processing',
  'in_progress',
  'completed',
])
const VALIDATION_STATUSES = new Set<ValidationStatus>([
  'pending',
  'valid',
  'invalid',
])

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('en-MY', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function mapReport(value: unknown): MemberReportSummary | null {
  if (
    !isObject(value) ||
    typeof value.id !== 'string' ||
    typeof value.reference !== 'string' ||
    typeof value.location !== 'string' ||
    typeof value.status !== 'string' ||
    !REPORT_STATUSES.has(value.status as ReportStatus) ||
    typeof value.validation_status !== 'string' ||
    !VALIDATION_STATUSES.has(value.validation_status as ValidationStatus) ||
    typeof value.submitted_at !== 'string'
  ) {
    return null
  }
  const submittedAt = formatDate(value.submitted_at)
  if (!submittedAt) return null

  return {
    id: value.id,
    reference: value.reference,
    location: value.location,
    status: value.status as ReportStatus,
    validationStatus: value.validation_status as ValidationStatus,
    submittedAt,
  }
}

export async function fetchMemberDashboard(
  signal?: AbortSignal,
): Promise<MemberDashboardData> {
  let response: Response
  try {
    response = await authenticatedFetch(MEMBER_DASHBOARD_URL, { signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new MemberDashboardRequestError(
      'The member dashboard service is unavailable.',
    )
  }

  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new MemberDashboardRequestError(
      'The member dashboard returned an unreadable response.',
    )
  }

  if (!response.ok) {
    throw new MemberDashboardRequestError(
      isObject(value) && typeof value.detail === 'string'
        ? value.detail
        : 'The member dashboard could not be loaded.',
    )
  }
  if (
    !isObject(value) ||
    typeof value.points !== 'number' ||
    !Number.isInteger(value.points) ||
    value.points < 0 ||
    typeof value.valid_reports !== 'number' ||
    !Number.isInteger(value.valid_reports) ||
    value.valid_reports < 0 ||
    (value.rank !== null &&
      (typeof value.rank !== 'number' ||
        !Number.isInteger(value.rank) ||
        value.rank <= 0)) ||
    !Array.isArray(value.reports)
  ) {
    throw new MemberDashboardRequestError(
      'The member dashboard returned an unexpected response.',
    )
  }

  const reports = value.reports
    .map(mapReport)
    .filter((report): report is MemberReportSummary => report !== null)
  if (reports.length !== value.reports.length) {
    throw new MemberDashboardRequestError(
      'The member dashboard returned invalid report data.',
    )
  }

  return {
    points: value.points,
    validReports: value.valid_reports,
    rank: value.rank ?? undefined,
    reports,
  }
}
