import { useEffect, useRef, useState } from 'react'
import { googleMapId, loadGoogleMaps } from '../../features/location/google-maps'

type Coordinates = { latitude: number; longitude: number }
type MapMarker = Coordinates & { id: string; name: string }

function coordinate(value: google.maps.LatLng | google.maps.LatLngLiteral | google.maps.LatLngAltitude | null | undefined): Coordinates | null {
  if (!value) return null
  const latitude = typeof value.lat === 'function' ? value.lat() : value.lat
  const longitude = typeof value.lng === 'function' ? value.lng() : value.lng
  return typeof latitude === 'number' && typeof longitude === 'number' ? { latitude, longitude } : null
}

export function GoogleMap({ location, markers = [], interactive = false, onSelect, onMarkerSelect, selectedMarkerId,
  ariaLabel = 'Google map' }: {
  location: Coordinates | null; markers?: MapMarker[]; interactive?: boolean
  onSelect?: (latitude: number, longitude: number) => void
  onMarkerSelect?: (id: string) => void; selectedMarkerId?: string | null; ariaLabel?: string
}) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<google.maps.Map | null>(null)
  const selectedPin = useRef<google.maps.marker.AdvancedMarkerElement | null>(null)
  const stationPins = useRef<google.maps.marker.AdvancedMarkerElement[]>([])
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
      const centre = initial.current
      map.current = new Map(container.current, {
        center: centre ? { lat: centre.latitude, lng: centre.longitude } : { lat: 4.2105, lng: 101.9758 },
        zoom: centre ? 16 : 6, mapId: googleMapId, gestureHandling: 'cooperative',
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
      selectedPin.current = null
      stationPins.current = []
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

  return <div className="location-map-shell">
    <div ref={container} className="location-map" aria-label={ariaLabel} />
    {status === 'loading' && <p role="status">Loading Google map...</p>}
    {status === 'error' && <div role="alert"><p>Google Maps could not load. Search or enter known coordinates instead.</p>
      <button type="button" className="button button--secondary" onClick={() => { setStatus('loading'); setRetry(value => value + 1) }}>Retry map</button></div>}
  </div>
}
