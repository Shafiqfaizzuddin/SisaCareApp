import type {
  ReportSubmissionPayload,
  ReportSubmissionResult,
} from '../../types'


const configuredSubmissionUrl = import.meta.env.VITE_REPORT_SUBMISSION_URL as
  | string
  | undefined

export const REPORT_SUBMISSION_URL =
  configuredSubmissionUrl?.trim() || '/api/reports'

export class ReportSubmissionRequestError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ReportSubmissionRequestError'
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isSubmissionResult(value: unknown): value is ReportSubmissionResult {
  return (
    isObject(value) &&
    typeof value.id === 'string' &&
    typeof value.reference === 'string' &&
    typeof value.status === 'string' &&
    typeof value.submitted_at === 'string'
  )
}

function errorMessage(value: unknown, status: number): string {
  if (isObject(value)) {
    if (typeof value.detail === 'string') {
      return value.detail
    }
    if (typeof value.message === 'string') {
      return value.message
    }
  }
  return `The report could not be submitted (status ${status}).`
}

export async function submitWasteReport(
  payload: ReportSubmissionPayload,
  signal?: AbortSignal,
  image?: File,
): Promise<ReportSubmissionResult> {
  const requestBody = image ? new FormData() : JSON.stringify(payload)
  if (image && requestBody instanceof FormData) {
    requestBody.append('payload', JSON.stringify(payload))
    requestBody.append('image', image)
  }

  let response: Response
  try {
    response = await fetch(
      image ? `${REPORT_SUBMISSION_URL}/with-image` : REPORT_SUBMISSION_URL,
      {
        method: 'POST',
        headers: image ? undefined : { 'Content-Type': 'application/json' },
        body: requestBody,
        signal,
      },
    )
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new ReportSubmissionRequestError(
      'The report service is unavailable. Your report has not been submitted.',
    )
  }

  let responseData: unknown
  try {
    responseData = await response.json()
  } catch {
    throw new ReportSubmissionRequestError(
      `The report service returned an unreadable response (status ${response.status}).`,
    )
  }

  if (!response.ok) {
    throw new ReportSubmissionRequestError(
      errorMessage(responseData, response.status),
    )
  }
  if (!isSubmissionResult(responseData)) {
    throw new ReportSubmissionRequestError(
      'The report service returned an unexpected result.',
    )
  }

  return responseData
}
