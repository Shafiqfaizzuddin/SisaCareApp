import { authenticatedFetch } from '../authentication/authenticated-fetch'

export type AnalyticsFilters = {
  start: string; end: string; category: string; status: string; area: string
  provenance: 'production' | 'legacy_unknown' | 'demo'
}
export type DensityCell = { cell_key: string; center_latitude: number; center_longitude: number;
  south: number; north: number; west: number; east: number; count: number }
export type ForecastCell = { cell_key: string; center_latitude: number; center_longitude: number; predicted_count: number }
export type Analytics = {
  filters: Record<string, string | null>; generated_at: string
  metrics: {
    total_submitted: number; by_status: Record<string, number>; by_category: Record<string, number>
    resolved_current: number; resolution_rate_percent: number | null
    verified_resolution_count: number; average_resolution_hours: number | null; median_resolution_hours: number | null
    missing_coordinates: number; resolved_without_verified_timestamp: number
    staff: { task_assignments: number; active_assignments: number; verified_completions_with_proof: number
      by_staff: { staff_id: string; assigned: number; active: number; verified_completions: number }[] }
  }
  trends: { date: string; reported: number; resolved: number }[]
  observed_heatmap: DensityCell[]
}
export type Forecast = {
  status: string; reason?: string; model_version?: string; provenance?: string; generated_at?: string
  periods: { start: string; end: string; cells: ForecastCell[] }[]
}

export function analyticsQuery(filters: AnalyticsFilters): string {
  const query = new URLSearchParams()
  for (const key of ['start', 'end', 'category', 'status', 'area'] as const) {
    if (filters[key]) query.set(key, filters[key])
  }
  query.set('provenance', filters.provenance)
  return query.toString()
}

export async function fetchAnalytics(filters: AnalyticsFilters, signal?: AbortSignal): Promise<Analytics> {
  const response = await authenticatedFetch(`/api/admin/analytics?${analyticsQuery(filters)}`, { signal })
  if (!response.ok) throw new Error('Administrative analytics could not be loaded.')
  return response.json() as Promise<Analytics>
}

export async function fetchForecast(provenance: 'production' | 'synthetic_demo', signal?: AbortSignal): Promise<Forecast> {
  const response = await authenticatedFetch(`/api/admin/hotspots/forecasts?provenance=${provenance}`, { signal })
  if (!response.ok) throw new Error('Forecasts could not be loaded.')
  return response.json() as Promise<Forecast>
}

export async function downloadAnalytics(format: 'csv' | 'pdf', filters: AnalyticsFilters): Promise<void> {
  const response = await authenticatedFetch(`/api/admin/analytics/export.${format}?${analyticsQuery(filters)}`)
  if (!response.ok) throw new Error(`The ${format.toUpperCase()} export could not be downloaded.`)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `sisacare-analytics.${format}`
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
