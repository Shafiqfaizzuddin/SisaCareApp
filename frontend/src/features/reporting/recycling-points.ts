import { authenticatedFetch } from '../authentication/authenticated-fetch'

export interface RecyclingPoint {
  id: string
  name: string
  latitude: number
  longitude: number
  accepted_materials: string[]
  description: string
  active?: boolean
  created_at?: string
  updated_at?: string
}

export type RecyclingPointInput = Pick<RecyclingPoint, 'name' | 'latitude' | 'longitude' | 'accepted_materials' | 'description'> & { active: boolean }

async function readPointResponse(response: Response): Promise<RecyclingPoint> {
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    throw new Error(body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string'
      ? body.detail : 'The recycling point could not be saved.')
  }
  return response.json() as Promise<RecyclingPoint>
}

export async function fetchAdminRecyclingPoints(): Promise<RecyclingPoint[]> {
  const response = await authenticatedFetch('/api/recycling/admin/points')
  if (!response.ok) throw new Error('Registered recycling points could not be loaded.')
  return response.json() as Promise<RecyclingPoint[]>
}

export async function saveRecyclingPoint(input: RecyclingPointInput, id?: string): Promise<RecyclingPoint> {
  return readPointResponse(await authenticatedFetch(
    id ? `/api/recycling/admin/points/${encodeURIComponent(id)}` : '/api/recycling/admin/points',
    { method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) },
  ))
}

export async function fetchRecyclingPoints(signal?: AbortSignal): Promise<RecyclingPoint[]> {
  const response = await authenticatedFetch('/api/recycling/points', { signal })
  if (!response.ok) throw new Error('Registered recycling points could not be loaded. Try again later.')
  const result: unknown = await response.json()
  if (!Array.isArray(result)) throw new Error('Registered recycling points could not be loaded.')
  return result as RecyclingPoint[]
}
