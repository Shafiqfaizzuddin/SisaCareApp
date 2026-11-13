import { useEffect, useRef, useState } from 'react'
import { googleMapId, loadGoogleMaps } from '../../features/location/google-maps'

type Coordinates = { latitude: number; longitude: number }
type MapMarker = Coordinates & { id: string; name: string }
type HeatPoint = Coordinates & { weight: number; cellKey?: string;
  bounds?: { south: number; north: number; west: number; east: number } }

export const OBSERVED_DENSITY_BANDS = [
  { label: '1 report', min: 1, color: '#238b45' },
  { label: '2 reports', min: 2, color: '#a1d76a' },
  { label: '3–4 reports', min: 3, color: '#fee08b' },
  { label: '5–9 reports', min: 5, color: '#f46d43' },
  { label: '10+ reports', min: 10, color: '#a50026' },
] as const

function observedColor(count: number): string {
  return [...OBSERVED_DENSITY_BANDS].reverse().find(band => count >= band.min)?.color ?? OBSERVED_DENSITY_BANDS[0].color
}

function forecastCount(value: number): string {
  return value < 0.1 ? '<0.1' : value.toFixed(1)
}

function coordinate(value: google.maps.LatLng | google.maps.LatLngLiteral | google.maps.LatLngAltitude | null | undefined): Coordinates | null {
  if (!value) return null
  const latitude = typeof value.lat === 'function' ? value.lat() : value.lat
  const longitude = typeof value.lng === 'function' ? value.lng() : value.lng
  return typeof latitude === 'number' && typeof longitude === 'number' ? { latitude, longitude } : null
}

function fitHeatPoints(activeMap: google.maps.Map, points: HeatPoint[]): void {
  if (points.length === 1) {
    activeMap.panTo({ lat: points[0].latitude, lng: points[0].longitude })
    activeMap.setZoom(points[0].bounds ? 13 : 11)
  } else if (points.length > 1) {
    const bounds = points.map(point => point.bounds ?? { south: point.latitude - 0.025,
      north: point.latitude + 0.025, west: point.longitude - 0.025, east: point.longitude + 0.025 })
    activeMap.fitBounds({ south: Math.min(...bounds.map(bound => bound.south)),
      north: Math.max(...bounds.map(bound => bound.north)),
      west: Math.min(...bounds.map(bound => bound.west)),
      east: Math.max(...bounds.map(bound => bound.east)) }, 48)
  }
}

export function GoogleMap({ location, markers = [], interactive = false, onSelect, onMarkerSelect, selectedMarkerId,
  heatPoints = [], heatTone = 'observed', onHeatCellSelect, showHeatControls = false, ariaLabel = 'Google map' }: {
  location: Coordinates | null; markers?: MapMarker[]; interactive?: boolean
  onSelect?: (latitude: number, longitude: number) => void
  onMarkerSelect?: (id: string) => void; selectedMarkerId?: string | null; ariaLabel?: string
  heatPoints?: HeatPoint[]; heatTone?: 'observed' | 'forecast' | 'demo' | 'forecastDemo'
  onHeatCellSelect?: (key: string) => void
  showHeatControls?: boolean
}) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<google.maps.Map | null>(null)
  const selectedPin = useRef<google.maps.marker.AdvancedMarkerElement | null>(null)
  const stationPins = useRef<google.maps.marker.AdvancedMarkerElement[]>([])
  const heatTiles = useRef<google.maps.Rectangle[]>([])
  const heatLabels = useRef<google.maps.marker.AdvancedMarkerElement[]>([])
  const currentLocationPin = useRef<google.maps.marker.AdvancedMarkerElement | null>(null)
  const locationRequest = useRef(0)
  const userCentered = useRef(false)
  const lastHeatTone = useRef(heatTone)
  const callbacks = useRef({ onSelect, onMarkerSelect })
  callbacks.current = { onSelect, onMarkerSelect }
  const initial = useRef(location)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [retry, setRetry] = useState(0)
  const [locating, setLocating] = useState(false)
  const [locationMessage, setLocationMessage] = useState('')

  function focusHeatPoint(point: HeatPoint) {
    const activeMap = map.current
    if (!activeMap) return
    userCentered.current = true
    activeMap.panTo({ lat: point.latitude, lng: point.longitude })
    activeMap.setZoom(point.bounds ? 15 : 12)
    setLocationMessage(point.bounds ? 'Centered on the selected 1 km report area.'
      : 'Centered on the selected forecast area.')
    if (point.cellKey) onHeatCellSelect?.(point.cellKey)
  }

  function findCurrentLocation() {
    if (!navigator.geolocation) { setLocationMessage('Device location is unavailable.'); return }
    setLocating(true)
    setLocationMessage('')
    const request = ++locationRequest.current
    navigator.geolocation.getCurrentPosition(position => {
      if (request !== locationRequest.current) return
      setLocating(false)
      const activeMap = map.current
      if (!activeMap) { setLocationMessage('Map is unavailable. Try again.'); return }
      const latitude = position.coords.latitude
      const longitude = position.coords.longitude
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)
          || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
        setLocationMessage('Device returned invalid coordinates. Try again.')
        return
      }
      const point = { lat: latitude, lng: longitude }
      userCentered.current = true
      activeMap.panTo(point)
      activeMap.setZoom(14)
      setLocationMessage(position.coords.accuracy > 150
        ? `Centered on your approximate location (within ${Math.round(position.coords.accuracy)} m).`
        : 'Centered on your current location.')
      void loadGoogleMaps().then(async maps => {
        const { AdvancedMarkerElement, PinElement } = await maps.importLibrary('marker') as google.maps.MarkerLibrary
        if (request !== locationRequest.current || map.current !== activeMap) return
        if (currentLocationPin.current) currentLocationPin.current.map = null
        const pin = new PinElement({ background: '#3267bd', borderColor: '#ffffff', glyphColor: '#ffffff' })
        currentLocationPin.current = new AdvancedMarkerElement({ map: activeMap, position: point,
          title: 'Your current location' })
        currentLocationPin.current.append(pin)
      }).catch(() => { /* The map remains centered if the optional marker cannot load. */ })
    }, failure => {
      if (request !== locationRequest.current) return
      setLocating(false)
      setLocationMessage(failure.code === failure.PERMISSION_DENIED ? 'Location permission denied. Enable it in your browser and try again.'
        : failure.code === failure.TIMEOUT ? 'Location timed out. Try again.' : 'Device location is unavailable. Try again.')
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 })
  }

  useEffect(() => {
    if (!container.current || !googleMapId) { setStatus('error'); return }
    let active = true
    let listener: google.maps.MapsEventListener | null = null
    void loadGoogleMaps().then(async maps => {
      const { Map } = await maps.importLibrary('maps') as google.maps.MapsLibrary
      if (!active || !container.current) return
      const centre = initial.current ?? heatPoints[0] ?? null
      map.current = new Map(container.current, {
        center: centre ? { lat: centre.latitude, lng: centre.longitude } : { lat: 4.2105, lng: 101.9758 },
        zoom: initial.current ? 16 : centre ? 11 : 6, mapId: googleMapId, gestureHandling: 'cooperative',
        clickableIcons: false, streetViewControl: false,
      })
      if (interactive) listener = map.current.addListener('click', (event: google.maps.MapMouseEvent) => {
        const point = coordinate(event.latLng)
        if (point) callbacks.current.onSelect?.(point.latitude, point.longitude)
      })
      setStatus('ready')
    }).catch(() => { if (active) setStatus('error') })
    return () => {
      active = false
      ++locationRequest.current
      listener?.remove()
      if (selectedPin.current) selectedPin.current.map = null
      stationPins.current.forEach(pin => { pin.map = null })
      heatTiles.current.forEach(tile => tile.setMap(null))
      heatLabels.current.forEach(label => { label.map = null })
      if (currentLocationPin.current) currentLocationPin.current.map = null
      selectedPin.current = null
      stationPins.current = []
      heatTiles.current = []
      heatLabels.current = []
      currentLocationPin.current = null
      map.current = null
    }
  }, [interactive, retry])

  useEffect(() => {
    if (!map.current || status !== 'ready') return
    let active = true
    void loadGoogleMaps().then(async maps => {
      const { AdvancedMarkerElement } = await maps.importLibrary('marker') as google.maps.MarkerLibrary
      if (!active || !map.current) return
      if (!location) { if (selectedPin.current) selectedPin.current.map = null; selectedPin.current = null; return }
      const position = { lat: location.latitude, lng: location.longitude }
      if (!selectedPin.current) {
        selectedPin.current = new AdvancedMarkerElement({ map: map.current, position,
          gmpDraggable: interactive, title: interactive ? 'Selected location. Drag to adjust the pin.' : 'Selected location' })
        if (interactive) selectedPin.current.addEventListener('gmp-dragend', () => {
          const point = coordinate(selectedPin.current?.position)
          if (point) callbacks.current.onSelect?.(point.latitude, point.longitude)
        })
      } else selectedPin.current.position = position
      const activeMap = map.current
      activeMap.panTo(position)
      if ((activeMap.getZoom() ?? 0) < 14) activeMap.setZoom(16)
    })
    return () => { active = false }
  }, [location, interactive, status])

  useEffect(() => {
    if (!map.current || status !== 'ready') return
    let active = true
    void loadGoogleMaps().then(async maps => {
      const { AdvancedMarkerElement, PinElement } = await maps.importLibrary('marker') as google.maps.MarkerLibrary
      if (!active || !map.current) return
      stationPins.current.forEach(pin => { pin.map = null })
      stationPins.current = markers.map(point => {
        const pin = new PinElement({ background: point.id === selectedMarkerId ? '#176b50' : '#ea7c37',
          borderColor: '#173d35', glyphColor: '#ffffff' })
        const marker = new AdvancedMarkerElement({ map: map.current!, position: { lat: point.latitude, lng: point.longitude },
          title: point.name, gmpClickable: true })
        marker.append(pin)
        marker.addEventListener('gmp-click', () => callbacks.current.onMarkerSelect?.(point.id))
        return marker
      })
    })
    return () => { active = false }
  }, [markers, selectedMarkerId, status])

  useEffect(() => {
    if (!map.current || status !== 'ready') return
    heatTiles.current.forEach(tile => tile.setMap(null))
    heatLabels.current.forEach(label => { label.map = null })
    heatTiles.current = []
    heatLabels.current = []
    const valid = heatPoints.filter(point => Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
      && Number.isFinite(point.weight) && point.weight > 0 && (!point.bounds ||
        Object.values(point.bounds).every(Number.isFinite)))
    const peak = Math.max(1, ...valid.map(point => point.weight))
    const forecastLayer = heatTone === 'forecast' || heatTone === 'forecastDemo'
    if (lastHeatTone.current !== heatTone) { userCentered.current = false; lastHeatTone.current = heatTone }
    const colour = heatTone === 'forecast' ? '#3769b0' : '#8852a8'
    let active = true
    if (valid.length) void loadGoogleMaps().then(async maps => {
      const { Rectangle } = await maps.importLibrary('maps') as google.maps.MapsLibrary
      if (!active || !map.current) return
      heatTiles.current = valid.map(point => {
        const bounds = point.bounds ?? { south: point.latitude - 0.025, north: point.latitude + 0.025,
          west: point.longitude - 0.025, east: point.longitude + 0.025 }
        const tile = new Rectangle({ map: map.current, bounds,
          strokeColor: heatTone === 'demo' ? '#8852a8' : forecastLayer ? colour : '#52645b',
          strokeOpacity: 0.7, strokeWeight: 1,
          fillColor: forecastLayer ? colour : observedColor(point.weight),
          fillOpacity: forecastLayer ? 0.18 + 0.42 * Math.sqrt(point.weight / peak) : 0.72,
          clickable: Boolean(point.cellKey && onHeatCellSelect),
        })
        if (point.cellKey && onHeatCellSelect) tile.addListener('click', () => focusHeatPoint(point))
        return tile
      })
      if (showHeatControls) {
        try {
          const { AdvancedMarkerElement } = await maps.importLibrary('marker') as google.maps.MarkerLibrary
          if (!active || !map.current) return
          heatLabels.current = valid.map(point => {
            const badge = document.createElement('span')
            badge.className = `heat-count-badge${forecastLayer ? ' heat-count-badge--forecast' : ''}`
            badge.textContent = forecastLayer ? (point.weight < 0.1 ? '<0.1' : `≈${forecastCount(point.weight)}`) : String(point.weight)
            const title = forecastLayer ? `Predicted ${forecastCount(point.weight)} reports in this area`
              : `${point.weight} ${point.weight === 1 ? 'report' : 'reports'} in this area`
            const marker = new AdvancedMarkerElement({ map: map.current!,
              position: { lat: point.latitude, lng: point.longitude }, title,
              gmpClickable: true })
            marker.append(badge)
            marker.addEventListener('gmp-click', () => focusHeatPoint(point))
            return marker
          })
        } catch { /* Keep shaded cells visible if count markers cannot load. */ }
      }
    }).catch(() => { /* The map remains usable without the density overlay. */ })
    if (!location && !userCentered.current) fitHeatPoints(map.current, valid)
    return () => { active = false; heatTiles.current.forEach(tile => tile.setMap(null)); heatTiles.current = []
      heatLabels.current.forEach(label => { label.map = null }); heatLabels.current = [] }
  }, [heatPoints, heatTone, location, status, showHeatControls])

  return <div className="location-map-shell">
    {showHeatControls && <div className="heat-map-controls">
      <button type="button" className="button button--secondary" disabled={status !== 'ready' || locating}
        onClick={findCurrentLocation}>{locating ? 'Finding location...' : 'Find my location'}</button>
      <button type="button" className="button button--secondary" disabled={status !== 'ready' || !heatPoints.length}
        onClick={() => { userCentered.current = false; if (map.current) fitHeatPoints(map.current, heatPoints)
          setLocationMessage('Showing all mapped areas.') }}>Show all areas</button>
      {locationMessage && <span role="status">{locationMessage}</span>}
    </div>}
    <div ref={container} className="location-map" aria-label={ariaLabel} />
    {status === 'loading' && <p role="status">Loading Google map...</p>}
    {status === 'error' && <div role="alert"><p>Google Maps could not load. Search or enter known coordinates instead.</p>
      <button type="button" className="button button--secondary" onClick={() => { setStatus('loading'); setRetry(value => value + 1) }}>Retry map</button></div>}
  </div>
}
