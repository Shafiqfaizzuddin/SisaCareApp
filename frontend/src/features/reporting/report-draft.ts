import { authenticatedFetch } from '../authentication/authenticated-fetch'
import type { ReportSubmissionPayload, WasteAnalysisReport } from '../../types'

export interface ReportDraftResult extends WasteAnalysisReport {
  source: 'ollama' | 'template'
  model_id: string
}

export async function generateReportDraft(
  payload: Pick<ReportSubmissionPayload, 'analysis_id' | 'confirmed_items' | 'reviewed_detections'> & {
    user_description: string
    confirmed_address: string
  },
  signal?: AbortSignal,
): Promise<ReportDraftResult> {
  const response = await authenticatedFetch('/api/reports/draft', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload), signal,
  })
  const body: unknown = await response.json()
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null
    throw new Error(typeof detail === 'string' ? detail : 'Report drafting is unavailable.')
  }
  if (!body || typeof body !== 'object' || !('title' in body) || !('summary' in body) || !('source' in body) ||
      typeof body.title !== 'string' || typeof body.summary !== 'string' ||
      (body.source !== 'ollama' && body.source !== 'template')) {
    throw new Error('The report draft response was invalid.')
  }
  return body as ReportDraftResult
}
