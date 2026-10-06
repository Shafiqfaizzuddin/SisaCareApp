import type { LocationSearchResult, ReportLocation } from '../../types'


export const LOCATION_API_URL = '/api/location'

export class LocationRequestError extends Error {
  readonly status: number

  constructor(message: string, status = 0) {
    super(message)
    this.name = 'LocationRequestError'
    this.status = status
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function nullableString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function parseLocation(value: unknown): Omit<ReportLocation, 'source'> | null {
  if (
    !isObject(value) ||
    typeof value.latitude !== 'number' ||
    !Number.isFinite(value.latitude) ||
    value.latitude < -90 ||
    value.latitude > 90 ||
    typeof value.longitude !== 'number' ||
    !Number.isFinite(value.longitude) ||
    value.longitude < -180 ||
    value.longitude > 180
  ) {
    return null
  }
  const address = nullableString(value.address)
  if (!address) return null
  return {
    latitude: value.latitude,
    longitude: value.longitude,
    address,
    street: nullableString(value.street),
    city: nullableString(value.city),
    state: nullableString(value.state),
    postcode: nullableString(value.postcode),
    country: nullableString(value.country),
  }
}

async function responseJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    throw new LocationRequestError(
      'The location service returned an unreadable response.',
      response.status,
    )
  }
}

function errorMessage(value: unknown, fallback: string): string {
  return isObject(value) && typeof value.detail === 'string'
    ? value.detail
    : fallback
}

export async function searchLocations(
  query: string,
  signal?: AbortSignal,
  bias?: Pick<ReportLocation, 'latitude' | 'longitude'> | null,
): Promise<LocationSearchResult[]> {
  const parameters = new URLSearchParams({ query: query.trim() })
  if (bias) {
    parameters.set('latitude', String(bias.latitude))
    parameters.set('longitude', String(bias.longitude))
  }
  let response: Response
  try {
    response = await fetch(`${LOCATION_API_URL}/search?${parameters}`, { signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new LocationRequestError('Location search is temporarily unavailable.')
  }
  const payload = await responseJson(response)
  if (!response.ok) {
    throw new LocationRequestError(
      errorMessage(payload, 'Location search could not be completed.'),
      response.status,
    )
  }
  if (!isObject(payload) || !Array.isArray(payload.results)) {
    throw new LocationRequestError('Location search returned an invalid response.')
  }
  const results = payload.results.map((value) => {
    const location = parseLocation(value)
    if (!location || !isObject(value) || typeof value.id !== 'string') return null
    const label = nullableString(value.label)
    if (!label) return null
    return { ...location, id: value.id, label }
  })
  if (results.some((result) => result === null)) {
    throw new LocationRequestError('Location search returned invalid result data.')
  }
  return results as LocationSearchResult[]
}

export async function reverseGeocode(
  latitude: number,
  longitude: number,
  signal?: AbortSignal,
): Promise<Omit<ReportLocation, 'source'>> {
  const parameters = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
  })
  let response: Response
  try {
    response = await fetch(`${LOCATION_API_URL}/reverse?${parameters}`, { signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new LocationRequestError('Address lookup is temporarily unavailable.')
  }
  const payload = await responseJson(response)
  if (!response.ok) {
    throw new LocationRequestError(
      errorMessage(payload, 'No readable address was found.'),
      response.status,
    )
  }
  const location = parseLocation(payload)
  if (!location) {
    throw new LocationRequestError('Address lookup returned invalid location data.')
  }
  return location
}
