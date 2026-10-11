import { useMemo, useState } from 'react'
import type { ReportLocation } from '../../types'
import type { ConfirmedItem } from '../../features/reporting/campus-workflow'
import type { RecyclingPoint } from '../../features/reporting/recycling-points'
import { straightLineDistanceKm } from '../../features/reporting/recycling-recommendations'
import { googleMapsNavigationUrl } from '../../features/location/google-maps'
import { LocationPicker } from './LocationPicker'
import { GoogleMap } from './GoogleMap'

export function NearbyRecyclingMap({ registeredPoints, items = [], compact = false }: { registeredPoints: RecyclingPoint[]; items?: ConfirmedItem[]; compact?: boolean }) {
  const [origin, setOrigin] = useState<ReportLocation | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const materials = useMemo(() => new Set(items.filter(item => item.category === 'Recyclable Waste')
    .map(item => item.material.trim().toLocaleLowerCase()).filter(value => value && value !== 'unknown')), [items])
  const points = useMemo(() => registeredPoints.filter(point => point.active !== false).map(point => ({
    point, distance: origin && confirmed ? straightLineDistanceKm(origin, point) : null,
    matches: point.accepted_materials.some(value => materials.has(value.trim().toLocaleLowerCase())),
  })).sort((a, b) => a.distance === null || b.distance === null
    ? a.point.name.localeCompare(b.point.name) : a.distance - b.distance), [registeredPoints, origin, confirmed, materials])
  const selected = points.find(entry => entry.point.id === selectedId)?.point ?? null
  const nearby = points.filter(entry => entry.distance !== null && entry.distance <= 20)

  return <section aria-label="Nearby registered recycling stations">
    <h3>Registered recycling stations</h3>
    <p>{compact ? 'These stations come from the SisaCare registry. Open one in Google Maps for directions.'
      : 'Choose an origin to rank stations by approximate straight-line distance. GPS is requested only if you select “Use my current location”.'}</p>
    {!compact && <LocationPicker idPrefix="recycling-origin" mapLabel="Select an origin for recycling stations"
      value={origin} confirmed={confirmed} onChange={value => { setOrigin(value); setConfirmed(false) }}
      onConfirm={() => setConfirmed(true)} />}
    {points.length === 0 && <p>No active registered recycling stations are available. Try reporting the waste or ask staff for disposal guidance.</p>}
    {origin && confirmed && points.length > 0 && nearby.length === 0 && <p>No registered stations were found within 20 km of this origin. Other registered stations remain listed below.</p>}
    {points.length > 0 && <>
      <ul className="recycling-recommendations__list">{points.map(({ point, distance, matches }) => <li key={point.id}>
        <button type="button" className={selected?.id === point.id ? 'recycling-point recycling-point--selected' : 'recycling-point'}
          aria-pressed={selected?.id === point.id} onClick={() => setSelectedId(point.id)}>
          <strong>{point.name}</strong>
          {distance !== null && <span>About {distance < 1 ? `${Math.round(distance * 1000)} m` : `${distance.toFixed(1)} km`} straight-line</span>}
          {point.address && <span>{point.address}</span>}
          <span>{point.accepted_materials.length ? `Accepts: ${point.accepted_materials.join(', ')}` : 'Accepted materials unknown'}</span>
          {matches && <span>Matches your confirmed material</span>}
          {point.access_notes && <span>Access: {point.access_notes}</span>}
          {point.opening_hours && <span>Hours: {point.opening_hours}</span>}
        </button>
      </li>)}</ul>
      {!compact && <GoogleMap location={origin && confirmed ? origin : selected}
        markers={points.map(({ point }) => ({ id: point.id, name: point.name, latitude: point.latitude, longitude: point.longitude }))}
        selectedMarkerId={selected?.id} onMarkerSelect={setSelectedId} ariaLabel="Map of registered recycling stations" />}
      {selected && <p>Selected station: {selected.name}. Coordinates: {selected.latitude.toFixed(6)}, {selected.longitude.toFixed(6)}.{' '}
        <a href={googleMapsNavigationUrl(selected.latitude, selected.longitude)} target="_blank" rel="noopener noreferrer">Open in Google Maps</a></p>}
    </>}
  </section>
}
