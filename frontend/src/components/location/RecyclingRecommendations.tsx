import { useEffect, useState } from 'react'
import type { ReportLocation } from '../../types'
import type { ConfirmedItem } from '../../features/reporting/campus-workflow'
import type { RecyclingPoint } from '../../features/reporting/recycling-points'
import { conditionConfirmedForRecycling, recommendPoints, type Coordinates } from '../../features/reporting/recycling-recommendations'
import { submitRecyclingAction } from '../../features/reporting/recycling-actions'
import { GoogleMap } from './GoogleMap'
import { LocationPicker } from './LocationPicker'
import { googleMapsNavigationUrl } from '../../features/location/google-maps'

export function RecyclingRecommendations({ points, items, wasteLocation, loading, error, analysisId, onReport, onSubmitted, compact = false, allowProof = true, proofUnavailableReason }:
  { points: RecyclingPoint[]; items: (ConfirmedItem & { id?: string })[]; wasteLocation: ReportLocation | null;
    loading: boolean; error: string; analysisId: string; onReport: () => void; onSubmitted: () => void; compact?: boolean; allowProof?: boolean; proofUnavailableReason?: string }) {
  const [searchArea, setSearchArea] = useState<ReportLocation | null>(null)
  const [searchAreaConfirmed, setSearchAreaConfirmed] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [proof, setProof] = useState<File | null>(null)
  const [proofCoordinates, setProofCoordinates] = useState<Coordinates | null>(null)
  const [manualLocation, setManualLocation] = useState('')
  const [proofSource, setProofSource] = useState<'gps' | 'manual'>('manual')
  const [proofError, setProofError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [capturing, setCapturing] = useState(false)
  useEffect(() => { setSelectedId(null) }, [wasteLocation?.latitude, wasteLocation?.longitude, points])

  const origin = searchAreaConfirmed ? searchArea : wasteLocation
  const recommendations = origin ? recommendPoints(points, items, origin) : compact ? points.filter(point => point.active !== false)
    .flatMap(point => {
      const materials = [...new Set(items.filter(conditionConfirmedForRecycling).map(item => item.material.trim()).filter(Boolean))]
      const accepted = new Set(point.accepted_materials.map(value => value.trim().toLocaleLowerCase()))
      const matchedMaterials = materials.filter(value => accepted.has(value.toLocaleLowerCase()))
      return matchedMaterials.length ? [{ point, matchedMaterials,
        unmatchedMaterials: materials.filter(value => !accepted.has(value.toLocaleLowerCase())), distanceKm: 0 }] : []
    }).sort((a, b) => a.point.name.localeCompare(b.point.name)) : []
  const selected = recommendations.find(entry => entry.point.id === selectedId)?.point ?? recommendations[0]?.point
  const selectionConfirmed = selected?.id === selectedId

  function captureProofLocation() {
    if (!navigator.geolocation) {
      setProofError('Device location is unavailable. Enter the proof location manually.')
      return
    }
    setCapturing(true)
    setProofError('')
    navigator.geolocation.getCurrentPosition(position => {
      setProofCoordinates({ latitude: position.coords.latitude, longitude: position.coords.longitude })
      setProofSource('gps')
      setCapturing(false)
    }, () => {
      setProofSource('manual')
      setProofCoordinates(null)
      setCapturing(false)
      setProofError('Location permission was denied or unavailable. Enter the proof location manually.')
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 })
  }

  async function submitProof() {
    if (submitting || !selected || !selectionConfirmed || !analysisId) return
    if (!proof) { setProofError('Upload one proof photo before submitting.'); return }
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(proof.type)) {
      setProofError('Use a JPG, PNG, or WEBP proof photo.'); return
    }
    if (proof.size > 10 * 1024 * 1024) { setProofError('The proof photo must be 10 MB or smaller.'); return }
    if (proofSource === 'gps' && !proofCoordinates) { setProofError('Capture your proof location again.'); return }
    if (proofSource === 'manual' && !manualLocation.trim()) { setProofError('Enter the proof location manually.'); return }
    setSubmitting(true)
    setProofError('')
    try {
      await submitRecyclingAction({
        analysis_id: analysisId, recycling_point_id: selected.id,
        confirmed_items: items.filter(item => conditionConfirmedForRecycling(item) && item.name.trim()).map(item => ({ ...item, review_id: item.id })),
        proof_location_source: proofSource,
        ...(proofSource === 'gps' && proofCoordinates
          ? { proof_latitude: proofCoordinates.latitude, proof_longitude: proofCoordinates.longitude }
          : { proof_location: manualLocation.trim() }),
      }, proof)
      onSubmitted()
    } catch (value) {
      setProofError(value instanceof Error ? value.message : 'The recycling action could not be submitted.')
    } finally {
      setSubmitting(false)
    }
  }

  return <div className="recycling-recommendations" role="region" aria-label="Recycling recommendations">
    <p>Recycling at a registered point requires a proof photo and administrator verification.</p>
    <p>{origin ? 'Sorted from the selected location. Distances are approximate straight-line distances.'
      : compact ? 'Stations are listed by name because no origin was selected.' : 'Choose a search origin below. Distances are approximate straight-line distances.'}</p>
    {!compact && <LocationPicker idPrefix="recycling-proof-area" mapLabel="Choose a recycling search area"
      value={searchArea} confirmed={searchAreaConfirmed}
      onChange={value => { setSearchArea(value); setSearchAreaConfirmed(false) }} onConfirm={() => setSearchAreaConfirmed(true)} />}
    {loading && <p role="status">Loading registered points...</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && recommendations.length === 0 && <div>
      <p>No active registered point accepts the confirmed recyclable material.</p>
      <p>Keep recyclable items clean and separate where safe. Ask local staff for disposal guidance or report the waste for collection.</p>
      <button type="button" className="button button--secondary" onClick={onReport}>Report It Instead</button>
    </div>}
    {recommendations.length > 0 && <>
      <ul className="recycling-recommendations__list">
        {recommendations.map(({ point, matchedMaterials, unmatchedMaterials, distanceKm }) => <li key={point.id}>
          <button type="button" className={selected?.id === point.id ? 'recycling-point recycling-point--selected' : 'recycling-point'} onClick={() => setSelectedId(point.id)} aria-pressed={selected?.id === point.id}>
            <strong>{point.name}</strong>
            {point.address && <span>{point.address}</span>}
            {origin && <span>About {distanceKm < 1 ? `${Math.round(distanceKm * 1000)} m` : `${distanceKm.toFixed(1)} km`} straight-line</span>}
            <span>Accepts: {point.accepted_materials.join(', ')}</span>
            <span>Matches your items: {matchedMaterials.join(', ')}</span>
            {unmatchedMaterials.length > 0 && <span>Does not accept from your items: {unmatchedMaterials.join(', ')}</span>}
            {point.access_notes && <span>Access: {point.access_notes}</span>}
            {point.description && <span>{point.description}</span>}
          </button>
        </li>)}
      </ul>
      {selected && (origin || compact) && <>
        {!compact && origin && <GoogleMap location={origin} markers={[{ id: selected.id, name: selected.name, latitude: selected.latitude, longitude: selected.longitude }]} ariaLabel={`Google map showing ${selected.name}`} />}
        <a href={googleMapsNavigationUrl(selected.latitude, selected.longitude)} target="_blank" rel="noopener noreferrer">Open in Google Maps</a>
        <p>Destination coordinates: {selected.latitude.toFixed(6)}, {selected.longitude.toFixed(6)}</p>
        {!allowProof ? <p role="status">{proofUnavailableReason || 'Apply waste rules to every recyclable item before submitting proof.'}</p> :
        !selectionConfirmed ? <p role="status">Select a registered station to confirm its material acceptance before submitting proof.</p> :
        recommendations.find(entry => entry.point.id === selected.id)?.unmatchedMaterials.length ?
          <p role="alert">This point does not accept every confirmed material. Select a point that accepts all items before submitting one recycling action.</p> :
          <div className="recycling-proof">
            <h3>Submit recycling proof</h3>
            <p>Go to the selected point, then add a photo and your location. These support manual review; they do not conclusively prove disposal.</p>
            <div className="field"><label htmlFor="recycling-proof-photo">Proof photo</label>
              <input id="recycling-proof-photo" type="file" accept="image/jpeg,image/png,image/webp" disabled={submitting}
                onChange={event => { setProof(event.target.files?.[0] ?? null); setProofError('') }} />
            </div>
            <button type="button" className="button button--secondary" disabled={capturing || submitting} onClick={captureProofLocation}>
              {capturing ? 'Capturing location...' : 'Capture current GPS at the point'}
            </button>
            {proofSource === 'gps' && proofCoordinates && <p>Proof location: device GPS ({proofCoordinates.latitude.toFixed(6)}, {proofCoordinates.longitude.toFixed(6)}).</p>}
            <div className="field"><label htmlFor="recycling-proof-manual">Manual proof location</label>
              <input id="recycling-proof-manual" value={manualLocation} maxLength={500} disabled={submitting}
                placeholder="Describe where you left the recyclable waste"
                onChange={event => { setManualLocation(event.target.value); setProofSource('manual'); setProofCoordinates(null) }} />
              <span className="field__hint">If GPS is unavailable, enter the location yourself. It will be marked as manually entered.</span>
            </div>
            {proofError && <p role="alert">{proofError}</p>}
            <button type="button" className="button button--primary" disabled={submitting} onClick={() => void submitProof()}>
              {submitting ? 'Submitting for review...' : 'Submit for admin verification'}
            </button>
          </div>}
      </>}
    </>}
  </div>
}
