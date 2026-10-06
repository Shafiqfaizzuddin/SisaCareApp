import L, { type Map as LeafletMap, type Marker } from 'leaflet'
import { useEffect, useRef, useState } from 'react'
import type { ReportLocation } from '../../types'


const DEFAULT_CENTER: [number, number] = [4.2105, 101.9758]
const configuredApiKey = import.meta.env.VITE_TOMTOM_API_KEY as string | undefined

interface TomTomMapProps {
  location: Pick<ReportLocation, 'latitude' | 'longitude'> | null
  interactive?: boolean
  onSelect?: (latitude: number, longitude: number) => void
  apiKey?: string
  ariaLabel?: string
}

export function TomTomMap({
  location,
  interactive = false,
  onSelect,
  apiKey = configuredApiKey?.trim() ?? '',
  ariaLabel = 'TomTom map',
}: TomTomMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<LeafletMap | null>(null)
  const markerRef = useRef<Marker | null>(null)
  const onSelectRef = useRef(onSelect)
  const initialLocationRef = useRef(location)
  const [mapState, setMapState] = useState<'loading' | 'ready' | 'error'>(
    apiKey ? 'loading' : 'error',
  )

  onSelectRef.current = onSelect

  useEffect(() => {
    if (!apiKey || !containerRef.current) return

    const initialLocation = initialLocationRef.current
    const initialCenter: [number, number] = initialLocation
      ? [initialLocation.latitude, initialLocation.longitude]
      : DEFAULT_CENTER
    const map = L.map(containerRef.current, {
      center: initialCenter,
      zoom: initialLocation ? 16 : 6,
      zoomControl: true,
      attributionControl: true,
    })
    const tiles = L.tileLayer(
      `https://api.tomtom.com/maps/orbis/display/raster/tile/{z}/{x}/{y}?apiVersion=2&key=${encodeURIComponent(apiKey)}&style=street-light&tileSize=256&geopoliticalView=MY`,
      {
        minZoom: 0,
        maxZoom: 22,
        attribution: '&copy; TomTom',
      },
    )
    tiles.once('load', () => setMapState('ready'))
    tiles.on('tileerror', () => setMapState('error'))
    tiles.addTo(map)

    if (interactive) {
      map.on('click', (event) => {
        onSelectRef.current?.(event.latlng.lat, event.latlng.lng)
      })
    }
    mapRef.current = map
    return () => {
      markerRef.current = null
      mapRef.current = null
      map.remove()
    }
  }, [apiKey, interactive])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !location) return
    const coordinates: [number, number] = [location.latitude, location.longitude]
    if (!markerRef.current) {
      markerRef.current = L.marker(coordinates, {
        draggable: interactive,
        icon: L.divIcon({
          className: 'tomtom-marker',
          html: '<span aria-hidden="true"></span>',
          iconSize: [30, 38],
          iconAnchor: [15, 38],
        }),
      }).addTo(map)
      if (interactive) {
        markerRef.current.on('dragend', (event) => {
          const marker = event.target as Marker
          const position = marker.getLatLng()
          onSelectRef.current?.(position.lat, position.lng)
        })
      }
    } else {
      markerRef.current.setLatLng(coordinates)
    }
    map.setView(coordinates, Math.max(map.getZoom(), 16))
  }, [interactive, location])

  if (!apiKey) {
    return (
      <div className="location-map location-map--error" role="alert">
        TomTom Map Display is not configured. Add VITE_TOMTOM_API_KEY to
        frontend/.env.local.
      </div>
    )
  }

  return (
    <div className="location-map-shell">
      <div className="location-map" ref={containerRef} aria-label={ariaLabel} />
      {mapState === 'loading' && (
        <span className="location-map__status">Loading map...</span>
      )}
      {mapState === 'error' && (
        <span className="location-map__status location-map__status--error">
          The map could not be loaded. Search and GPS coordinates remain available.
        </span>
      )}
    </div>
  )
}
