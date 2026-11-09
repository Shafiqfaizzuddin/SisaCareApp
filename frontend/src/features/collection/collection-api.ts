import { authenticatedFetch } from '../authentication/authenticated-fetch'

const base = '/api/collection'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(`${base}${path}`, init)
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const message = body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string'
      ? body.detail : 'The collection request failed.'
    throw new Error(message)
  }
  return body as T
}

export interface StaffGrant { user_id: string; role: 'staff' | 'driver'; granted_at: string; revoked_at: string | null;
  email?: string | null; display_name?: string | null; invited_at?: string | null;
  verification_status: 'verified' | 'unverified' | 'unknown' }
export interface CollectionTask {
  id: string; reference: string; title: string; summary?: string; location: string; status: string;
  category: string; created_at: string; assigned_at?: string; team_name?: string;
  assignment?: { assignee_id: string; team_name: string; assigned_at: string };
  after_photo?: string | null;
  original_image?: string | null; annotated_image?: string | null;
  status_events?: Array<{ actor_id: string; previous_status: string; new_status: string; reason: string | null; created_at: string }>
}

export const listStaff = () => request<StaffGrant[]>('/admin/staff')
export const inviteStaff = (email: string, displayName: string, role: 'staff' | 'driver') => request<{
  user_id: string; email: string; role: 'staff' | 'driver'; invitation_sent: boolean
}>('/admin/staff/invite', { method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, display_name: displayName, role }) })
export const grantStaff = (userId: string, role: 'staff' | 'driver') => request('/admin/staff/grants', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: userId, role }),
})
export const revokeStaff = (userId: string, role: 'staff' | 'driver') => request(`/admin/staff/grants/${encodeURIComponent(userId)}/${role}`, { method: 'DELETE' })
export const resendStaffVerification = (userId: string) => request<{ user_id: string; email: string; verification_email_requested: boolean }>(
  `/admin/staff/${encodeURIComponent(userId)}/resend-verification`, { method: 'POST' })
export const listMyTasks = () => request<CollectionTask[]>('/tasks')
export const getMyTask = (id: string) => request<CollectionTask>(`/tasks/${encodeURIComponent(id)}`)
export const startTask = (id: string) => request(`/tasks/${encodeURIComponent(id)}/start`, { method: 'POST' })
export const submitTask = (id: string, note: string, image: File) => {
  const body = new FormData(); body.set('note', note); body.set('image', image)
  return request(`/tasks/${encodeURIComponent(id)}/submit`, { method: 'POST', body })
}
export const reviewTask = (id: string, action: 'verify' | 'rework' | 'reject', reason: string) => request(`/admin/tasks/${encodeURIComponent(id)}/${action}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason }),
})
