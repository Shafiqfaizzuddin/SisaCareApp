import { authenticatedFetch } from '../authentication/authenticated-fetch'
import type { CampusWasteCategory } from '../../types'

export interface ConfirmedRuleResult {
  category: CampusWasteCategory | null
  material: string | null
  handling_guidance: string
  confirmation_reason: string | null
  rule_id: string
  questions: Array<{ key: string; prompt: string }>
  station_material_key: string | null
}

export async function classifyConfirmedItem(
  label: string, material: string, conditionAnswers: Record<string, boolean>, signal?: AbortSignal,
): Promise<ConfirmedRuleResult> {
  const response = await authenticatedFetch('/api/waste/classify', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label, material, condition_answers: conditionAnswers }), signal,
  })
  if (!response.ok) throw new Error('Waste rules are unavailable. Confirm the item manually.')
  const data: unknown = await response.json()
  if (!data || typeof data !== 'object' || !('handling_guidance' in data) || !('rule_id' in data) ||
      typeof data.handling_guidance !== 'string' || typeof data.rule_id !== 'string') {
    throw new Error('Waste rules returned an invalid result.')
  }
  return data as ConfirmedRuleResult
}
