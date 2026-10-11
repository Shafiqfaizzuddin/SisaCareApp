import { useEffect, useMemo, useState } from 'react'
import type { ReportLocation } from '../../types'
import type { RecyclingPoint } from '../../features/reporting/recycling-points'
import { straightLineDistanceKm } from '../../features/reporting/recycling-recommendations'
import { LocationPicker } from './LocationPicker'
import { TomTomMap } from './TomTomMap'
import { authenticatedFetch } from '../../features/authentication/authenticated-fetch'

const tomTomKey = (import.meta.env.VITE_TOMTOM_API_KEY as string | undefined)?.trim() ?? ''

type NearbyPoint = {
  id: string; name: string; latitude: number; longitude: number
  address: string | null; accepted_materials: string[] | null; source: 'tomtom' | 'registered'
}

function fromCoordinates(latitude: number, longitude: number): ReportLocation {
  return { latitude, longitude, address: `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`,
    street: null, city: null, state: null, postcode: null, country: null, source: 'gps' }
}

export function NearbyRecyclingMap({ registeredPoints }: { registeredPoints: RecyclingPoint[] }) {
  const [area, setArea] = useState<ReportLocation | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [found, setFound] = useState<NearbyPoint[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [route, setRoute] = useState<Array<{ latitude: number; longitude: number }>>([])
  const [routeError, setRouteError] = useState('')

  useEffect(() => {
    if (!navigator.geolocation) return
    let active = true
    navigator.geolocation.getCurrentPosition(position => {
      if (!active) return
      setArea(fromCoordinates(position.coords.latitude, position.coords.longitude))
      setConfirmed(true)
    }, () => { /* LocationPicker offers search and map selection. */ },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!area || !confirmed) return
    const controller = new AbortController()
    setLoading(true)
    setError('')
    void authenticatedFetch(`/api/location/recycling/nearby?latitude=${area.latitude}&longitude=${area.longitude}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Nearby place search is unavailable. Registered points remain visible.')
        const body: unknown = await response.json()
        if (!body || typeof body !== 'object' || !('results' in body) || !Array.isArray(body.results)) {
          throw new Error('Nearby place search returned invalid results.')
        }
        return body.results as NearbyPoint[]
      })
      .then(points => { if (!controller.signal.aborted) setFound(points) })
      .catch(value => { if (!controller.signal.aborted) { setFound([]); setError(value instanceof Error ? value.message : 'Nearby place search failed.') } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [area, confirmed])

  const points = useMemo(() => {
    if (!area || !confirmed) return []
    const registered: NearbyPoint[] = registeredPoints.filter(point => point.active !== false).map(point => ({
      id: `registered:${point.id}`, name: point.name, latitude: point.latitude, longitude: point.longitude,
      address: point.description || null, accepted_materials: point.accepted_materials, source: 'registered',
    }))
    return [...registered, ...found].map(point => ({ point,
      distance: straightLineDistanceKm(area, point) }))
      .filter(entry => entry.distance <= 20)
      .sort((a, b) => a.distance - b.distance)
  }, [area, confirmed, found, registeredPoints])
  const selected = points.find(entry => entry.point.id === selectedId)?.point ?? points[0]?.point

  useEffect(() => { setRoute([]); setRouteError('') }, [area, selected?.id])

  async function showRoute() {
    if (!area || !selected || !tomTomKey) {
      setRouteError('TomTom routing is unavailable. Use the destination coordinates and map marker.')
      return
    }
    try {
      const positions = `${area.latitude},${area.longitude}:${selected.latitude},${selected.longitude}`
      const response = await fetch(`https://api.tomtom.com/routing/1/calculateRoute/${positions}/json?key=${encodeURIComponent(tomTomKey)}&travelMode=pedestrian&routeRepresentation=polyline`)
      if (!response.ok) throw new Error('Routing unavailable')
      const body: unknown = await response.json()
      const points = (body as { routes?: { legs?: { points?: Array<{ latitude: number; longitude: number }> }[] }[] })?.routes?.[0]?.legs?.[0]?.points
      if (!Array.isArray(points) || points.length < 2 || points.some(point => !Number.isFinite(point.latitude) || !Number.isFinite(point.longitude))) {
        throw new Error('Routing unavailable')
      }
      setRoute(points)
      setRouteError('')
    } catch {
      setRouteError('TomTom could not calculate a pedestrian route. Use the destination coordinates and marker.')
    }
  }

  return <section aria-label="Nearby recycling points">
    <h3>Nearby recycling points</h3>
    <p>Choose a search area below if device location is unavailable or you want to search elsewhere. Distances are approximate straight-line distances.</p>
    <LocationPicker idPrefix="recycling-area" mapLabel="Choose a recycling search area on the map"
      value={area} confirmed={confirmed}
      onChange={value => { setArea(value); setConfirmed(false) }} onConfirm={() => setConfirmed(true)} />
    {loading && <p role="status">Searching nearby recycling places...</p>}
    {error && <p role="alert">{error}</p>}
    {confirmed && area && !loading && points.length === 0 && <p>No nearby recycling points were found in this area. Try another location or report the waste for collection.</p>}
    {points.length > 0 && <>
      <ul className="recycling-recommendations__list">{points.map(({ point, distance }) => <li key={point.id}>
        <button type="button" className={selected?.id === point.id ? 'recycling-point recycling-point--selected' : 'recycling-point'}
          aria-pressed={selected?.id === point.id} onClick={() => setSelectedId(point.id)}>
          <strong>{point.name}</strong>
          <span>About {distance < 1 ? `${Math.round(distance * 1000)} m` : `${distance.toFixed(1)} km`} straight-line</span>
          {point.address && <span>{point.address}</span>}
          <span>{point.accepted_materials === null ? 'Accepted materials unknown — check before visiting' : `Accepted materials: ${point.accepted_materials.join(', ')}`}</span>
          <span>{point.source === 'registered' ? 'Registered point' : 'TomTom place listing'}</span>
        </button>
      </li>)}</ul>
      {selected && <>
        <TomTomMap location={area} markers={points.map(({ point }) => ({ id: point.id, name: point.name, latitude: point.latitude, longitude: point.longitude }))} route={route}
          ariaLabel="Map of nearby recycling points" />
        <p>Selected destination: {selected.name} ({selected.latitude.toFixed(6)}, {selected.longitude.toFixed(6)}).</p>
        <button className="button button--secondary" type="button" onClick={() => void showRoute()}>Show pedestrian route on map</button>
        {route.length > 0 && <p>TomTom pedestrian route shown. Follow local access rules and signage.</p>}
        {routeError && <p role="alert">{routeError}</p>}
      </>}
    </>}
    <p>Place listings may omit accepted materials. Only registered points with confirmed materials can receive a recycling proof submission and Eco Points.</p>
  </section>
}
