import { authenticatedFetch } from '../authentication/authenticated-fetch'

export interface LearnArticle {
  id: string
  title: string
  summary: string
  body: string
  image_url: string | null
  image_alt: string
  published: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export type LearnArticleInput = Pick<LearnArticle, 'title' | 'summary' | 'body' | 'image_alt' | 'published' | 'sort_order'>

async function responseError(response: Response, fallback: string): Promise<Error> {
  const value: unknown = await response.json().catch(() => null)
  return new Error(value && typeof value === 'object' && 'detail' in value && typeof value.detail === 'string' ? value.detail : fallback)
}

export async function fetchLearnArticles(signal?: AbortSignal): Promise<LearnArticle[]> {
  const response = await fetch('/api/education/articles', { signal })
  if (!response.ok) throw await responseError(response, 'Learning content is unavailable.')
  return response.json() as Promise<LearnArticle[]>
}

export async function fetchAdminLearnArticles(signal?: AbortSignal): Promise<LearnArticle[]> {
  const response = await authenticatedFetch('/api/education/admin/articles', { signal })
  if (!response.ok) throw await responseError(response, 'Learning content could not be loaded.')
  return response.json() as Promise<LearnArticle[]>
}

export async function saveLearnArticle(input: LearnArticleInput, id?: string): Promise<LearnArticle> {
  const response = await authenticatedFetch(id ? `/api/education/admin/articles/${encodeURIComponent(id)}` : '/api/education/admin/articles', {
    method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  })
  if (!response.ok) throw await responseError(response, 'The article could not be saved.')
  return response.json() as Promise<LearnArticle>
}

export async function uploadLearnImage(id: string, image: File): Promise<void> {
  const payload = new FormData()
  payload.set('image', image)
  const response = await authenticatedFetch(`/api/education/admin/articles/${encodeURIComponent(id)}/image`, {
    method: 'POST', body: payload,
  })
  if (!response.ok) throw await responseError(response, 'The image could not be uploaded.')
}

export async function removeLearnImage(id: string): Promise<void> {
  const response = await authenticatedFetch(`/api/education/admin/articles/${encodeURIComponent(id)}/image/remove`, { method: 'POST' })
  if (!response.ok) throw await responseError(response, 'The image could not be removed.')
}
