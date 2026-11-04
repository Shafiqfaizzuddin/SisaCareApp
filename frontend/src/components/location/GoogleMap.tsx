import { useEffect, useRef, useState } from 'react'
import { googleMapId, loadGoogleMaps } from '../../features/location/google-maps'

type Coordinates = { latitude: number; longitude: number }
type MapMarker = Coordinates & { id: string; name: string }
type HeatPoint = Coordinates & { weight: number }

function coordinate(value: google.maps.LatLng | google.maps.LatLngLiteral | google.maps.LatLngAltitude | null | undefined): Coordinates | null {
  if (!value) return null
  const latitude = typeof value.lat === 'function' ? value.lat() : value.lat
  const longitude = typeof value.lng === 'function' ? value.lng() : value.lng
  return typeof latitude === 'number' && typeof longitude === 'number' ? { latitude, longitude } : null
}

export function GoogleMap({ location, markers = [], interactive = false, onSelect, onMarkerSelect, selectedMarkerId,
  heatPoints = [], heatTone = 'observed', ariaLabel = 'Google map' }: {
  location: Coordinates | null; markers?: MapMarker[]; interactive?: boolean
  onSelect?: (latitude: number, longitude: number) => void
  onMarkerSelect?: (id: string) => void; selectedMarkerId?: string | null; ariaLabel?: string
  heatPoints?: HeatPoint[]; heatTone?: 'observed' | 'forecast' | 'demo'
}) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<google.maps.Map | null>(null)
  const selectedPin = useRef<google.maps.marker.AdvancedMarkerElement | null>(null)
  const stationPins = useRef<google.maps.marker.AdvancedMarkerElement[]>([])
  const heatTiles = useRef<google.maps.Rectangle[]>([])
  const callbacks = useRef({ onSelect, onMarkerSelect })
  callbacks.current = { onSelect, onMarkerSelect }
  const initial = useRef(location)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [retry, setRetry] = useState(0)

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
      listener?.remove()
      if (selectedPin.current) selectedPin.current.map = null
      stationPins.current.forEach(pin => { pin.map = null })
      heatTiles.current.forEach(tile => tile.setMap(null))
      selectedPin.current = null
      stationPins.current = []
      heatTiles.current = []
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
    heatTiles.current = []
    const valid = heatPoints.filter(point => Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
      && Number.isFinite(point.weight) && point.weight > 0)
    const peak = Math.max(1, ...valid.map(point => point.weight))
    const colour = heatTone === 'forecast' ? '#3769b0' : heatTone === 'demo' ? '#8852a8' : '#d75036'
    let active = true
    if (valid.length) void loadGoogleMaps().then(async maps => {
      const { Rectangle } = await maps.importLibrary('maps') as google.maps.MapsLibrary
      if (!active || !map.current) return
      heatTiles.current = valid.map(point => new Rectangle({
        map: map.current, bounds: { south: point.latitude - 0.025, north: point.latitude + 0.025,
          west: point.longitude - 0.025, east: point.longitude + 0.025 }, strokeColor: colour,
        strokeOpacity: 0.45, strokeWeight: 1, fillColor: colour,
        fillOpacity: 0.18 + 0.42 * Math.sqrt(point.weight / peak), clickable: false,
      }))
    }).catch(() => { /* The map remains usable without the density overlay. */ })
    if (!location && valid[0]) {
      map.current.panTo({ lat: valid[0].latitude, lng: valid[0].longitude })
      if ((map.current.getZoom() ?? 0) < 10) map.current.setZoom(11)
    }
    return () => { active = false; heatTiles.current.forEach(tile => tile.setMap(null)); heatTiles.current = [] }
  }, [heatPoints, heatTone, location, status])

  return <div className="location-map-shell">
    <div ref={container} className="location-map" aria-label={ariaLabel} />
    {status === 'loading' && <p role="status">Loading Google map...</p>}
    {status === 'error' && <div role="alert"><p>Google Maps could not load. Search or enter known coordinates instead.</p>
      <button type="button" className="button button--secondary" onClick={() => { setStatus('loading'); setRetry(value => value + 1) }}>Retry map</button></div>}
  </div>
}
