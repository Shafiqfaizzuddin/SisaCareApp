import { authenticatedFetch } from '../authentication/authenticated-fetch'
import type { ConfirmedItem } from './campus-workflow'

export interface RecyclingAction {
  id: string
  analysis_id: string
  original_photo: string
  proof_photo: string
  confirmed_waste: { category: string; items: ConfirmedItem[] }
  recycling_point_id: string
  recycling_point_name: string
  proof_latitude: number | null
  proof_longitude: number | null
  proof_location: string | null
  proof_location_source: 'gps' | 'manual' | null
  verification_status: 'pending' | 'verified' | 'rejected'
  reviewer_id: string | null
  reviewed_at: string | null
  rejection_reason: string | null
  created_at: string
  updated_at: string
  user_id?: string
  reward_points?: number
}

async function message(response: Response): Promise<string> {
  const data: unknown = await response.json().catch(() => null)
  return data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string'
    ? data.detail : `The request failed (status ${response.status}).`
}

export async function submitRecyclingAction(
  input: { analysis_id: string; recycling_point_id: string; confirmed_items: ConfirmedItem[];
    proof_location_source: 'gps' | 'manual'; proof_latitude?: number; proof_longitude?: number;
    proof_location?: string }, proof: File,
): Promise<RecyclingAction> {
  const body = new FormData()
  body.append('payload', JSON.stringify(input))
  body.append('proof', proof)
  const response = await authenticatedFetch('/api/recycling/actions', { method: 'POST', body })
  if (!response.ok) throw new Error(await message(response))
  return response.json() as Promise<RecyclingAction>
}

export async function fetchOwnRecyclingActions(): Promise<RecyclingAction[]> {
  const response = await authenticatedFetch('/api/recycling/actions/me')
  if (!response.ok) throw new Error(await message(response))
  return response.json() as Promise<RecyclingAction[]>
}

export async function fetchPendingRecyclingActions(): Promise<RecyclingAction[]> {
  const response = await authenticatedFetch('/api/recycling/admin/actions/pending')
  if (!response.ok) throw new Error(await message(response))
  return response.json() as Promise<RecyclingAction[]>
}

export async function reviewRecyclingAction(id: string, decision: 'verified' | 'rejected', rejectionReason?: string): Promise<RecyclingAction> {
  const response = await authenticatedFetch(`/api/recycling/admin/actions/${encodeURIComponent(id)}/review`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, rejection_reason: rejectionReason ?? null }),
  })
  if (!response.ok) throw new Error(await message(response))
  return response.json() as Promise<RecyclingAction>
}
