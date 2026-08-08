const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined

export const API_BASE_URL =
  configuredBaseUrl?.replace(/\/$/, '') ?? 'http://localhost:8000/api/v1'

export function apiUrl(path: string): string {
  return `${API_BASE_URL}/${path.replace(/^\//, '')}`
}
