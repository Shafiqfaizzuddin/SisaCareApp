import { useEffect, useRef, useState } from 'react'
import type { ReportLocation, LocationSource } from '../../types'
import { GoogleMap } from './GoogleMap'
import { newPlaceSessionToken, resolvePlace, reverseGeocode, suggestPlaces, type PlaceSuggestion } from '../../features/location/google-maps'

interface LocationPickerProps {
  value: ReportLocation | null
  confirmed: boolean
  onChange: (location: ReportLocation) => void
  onConfirm: () => void
  idPrefix?: string
  mapLabel?: string
  note?: string
  onNoteChange?: (note: string) => void
  noteLabel?: string
  incidentHint?: boolean
  onCancel?: () => void
  confirmLabel?: string
  showCoordinates?: boolean
}

function coordinateText(latitude: number, longitude: number) { return `${latitude.toFixed(6)}, ${longitude.toFixed(6)}` }
function location(latitude: number, longitude: number, address: string, source: LocationSource,
  addressSource: 'google' | 'manual' | 'coordinates'): ReportLocation {
  return { latitude, longitude, address, source, addressSource, street: null, city: null,
    state: null, postcode: null, country: null }
}

export function LocationPicker({ value, confirmed, onChange, onConfirm, idPrefix = 'location',
  mapLabel = 'Select a location on Google Maps', note, onNoteChange, noteLabel = 'Landmark or location note (optional)',
  incidentHint = false, onCancel, confirmLabel, showCoordinates = true }: LocationPickerProps) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([])
  const [activeIndex, setActiveIndex] = useState(-1)
  const [searching, setSearching] = useState(false)
  const [resolving, setResolving] = useState(false)
  const [locating, setLocating] = useState(false)
  const [error, setError] = useState('')
  const [hint, setHint] = useState('')
  const [latitudeInput, setLatitudeInput] = useState(value ? String(value.latitude) : '')
  const [longitudeInput, setLongitudeInput] = useState(value ? String(value.longitude) : '')
  const token = useRef<Promise<google.maps.places.AutocompleteSessionToken> | null>(null)
  const revision = useRef(0)
  const mounted = useRef(true)
  useEffect(() => {
    const pendingRevision = revision
    mounted.current = true
    return () => { mounted.current = false; ++pendingRevision.current }
  }, [])
  const valueRef = useRef(value)
  valueRef.current = value
  const selectedLatitude = value?.latitude
  const selectedLongitude = value?.longitude

  useEffect(() => {
    setLatitudeInput(selectedLatitude === undefined ? '' : String(selectedLatitude))
    setLongitudeInput(selectedLongitude === undefined ? '' : String(selectedLongitude))
  }, [selectedLatitude, selectedLongitude])

  useEffect(() => {
    if (query.trim().length < 3) { setSuggestions([]); token.current = null; return }
    let active = true
    const timer = window.setTimeout(() => {
      setSearching(true)
      token.current ??= newPlaceSessionToken()
      void token.current.then(session => suggestPlaces(query.trim(), session)).then(result => {
        if (!active) return
        setSuggestions(result)
        setActiveIndex(-1)
      }).catch(() => { if (active) { token.current = null; setSuggestions([]); setError('Place search is unavailable. Use the map or known coordinates.') } })
        .finally(() => { if (active) setSearching(false) })
    }, 350)
    return () => { active = false; window.clearTimeout(timer) }
  }, [query])

  async function selectSuggestion(item: PlaceSuggestion) {
    const request = ++revision.current
    setSearching(true)
    setSuggestions([])
    token.current = null
    try {
      const place = await resolvePlace(item.prediction)
      if (request !== revision.current) return
      setQuery('')
      onChange(location(place.latitude, place.longitude, place.address, 'search', 'google'))
      setError('')
      setHint('Place selected. Confirm that the pin identifies the intended location.')
    } catch (value) {
      if (request === revision.current) setError(value instanceof Error ? value.message : 'Place details are unavailable.')
    } finally { if (request === revision.current) setSearching(false) }
  }

  async function selectCoordinates(latitude: number, longitude: number, source: Exclude<LocationSource, 'search'>) {
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
      setError('Enter valid latitude (−90 to 90) and longitude (−180 to 180).')
      return
    }
    if (valueRef.current?.latitude === latitude && valueRef.current.longitude === longitude
      && valueRef.current.addressSource !== 'coordinates') return
    const request = ++revision.current
    setError('')
    setResolving(true)
    setSuggestions([])
    onChange(location(latitude, longitude, coordinateText(latitude, longitude), source, 'coordinates'))
    try {
      const address = await reverseGeocode(latitude, longitude)
      if (request !== revision.current) return
      if (address && valueRef.current?.addressSource !== 'manual') {
        onChange(location(latitude, longitude, address, source, 'google'))
      } else if (!address) setHint('No address was found. Enter a description below and confirm the coordinates.')
    } catch {
      if (request === revision.current) setHint('Address lookup failed. Enter a description below; the selected coordinates can still be confirmed.')
    } finally { if (request === revision.current) setResolving(false) }
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) { setError('Device location is unavailable. Search or place the pin manually.'); return }
    setLocating(true)
    setError('')
    navigator.geolocation.getCurrentPosition(position => {
      if (!mounted.current) return
      setLocating(false)
      setHint(position.coords.accuracy > 150
        ? `GPS is approximate within ${Math.round(position.coords.accuracy)} metres. Adjust the pin to the actual site.` : '')
      void selectCoordinates(position.coords.latitude, position.coords.longitude, 'gps')
    }, failure => {
      if (!mounted.current) return
      setLocating(false)
      setError(failure.code === failure.PERMISSION_DENIED ? 'Location permission denied. Search, click the map, or enter coordinates.'
        : failure.code === failure.TIMEOUT ? 'GPS timed out. Search, click the map, or enter coordinates.'
          : 'GPS is unavailable. Search, click the map, or enter coordinates.')
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 })
  }

  function editAddress(text: string) {
    if (!value) return
    ++revision.current
    setResolving(false)
    onChange({ ...value, address: text, addressSource: 'manual' })
  }

  const unresolved = value?.addressSource === 'coordinates' && !!onNoteChange && !(note ?? '').trim()
  return <div className="location-picker">
    {incidentHint && <p>The report pin must identify the waste incident. Your current position may be different.</p>}
    <div className="field location-search">
      <label htmlFor={`${idPrefix}-search`}>Search address or place</label>
      <input id={`${idPrefix}-search`} role="combobox" aria-expanded={suggestions.length > 0}
        aria-controls={`${idPrefix}-suggestions`} aria-autocomplete="list" autoComplete="off"
        value={query} onChange={event => { setQuery(event.target.value); setError('') }}
        onKeyDown={event => {
          if (event.key === 'ArrowDown' && suggestions.length) { event.preventDefault(); setActiveIndex(index => (index + 1) % suggestions.length) }
          if (event.key === 'ArrowUp' && suggestions.length) { event.preventDefault(); setActiveIndex(index => (index + suggestions.length - 1) % suggestions.length) }
          if (event.key === 'Escape') setSuggestions([])
          if (event.key === 'Enter' && activeIndex >= 0 && suggestions[activeIndex]) { event.preventDefault(); void selectSuggestion(suggestions[activeIndex]) }
        }} placeholder="Search an area, building, or address" />
      {searching && <p role="status">Searching places...</p>}
      {suggestions.length > 0 && <ul id={`${idPrefix}-suggestions`} role="listbox" className="location-search__results">
        {suggestions.map((item, index) => <li key={`${item.label}-${index}`} role="option" aria-selected={index === activeIndex}>
          <button type="button" onClick={() => void selectSuggestion(item)}>{item.label}</button>
        </li>)}
      </ul>}
    </div>
    <button type="button" className="button button--secondary" onClick={useCurrentLocation} disabled={locating}>
      {locating ? 'Getting your location...' : 'Use my current location'}
    </button>
    <GoogleMap location={value} interactive onSelect={(latitude, longitude) => void selectCoordinates(latitude, longitude, 'map')} ariaLabel={mapLabel} />
    <details className="location-coordinate-fallback"><summary>Enter coordinates manually</summary>
    <fieldset className="location-coordinate-fields"><legend>Known coordinates</legend>
      <div className="field"><label htmlFor={`${idPrefix}-latitude`}>Latitude</label>
        <input id={`${idPrefix}-latitude`} type="number" step="any" min={-90} max={90} value={latitudeInput} onChange={event => setLatitudeInput(event.target.value)} /></div>
      <div className="field"><label htmlFor={`${idPrefix}-longitude`}>Longitude</label>
        <input id={`${idPrefix}-longitude`} type="number" step="any" min={-180} max={180} value={longitudeInput} onChange={event => setLongitudeInput(event.target.value)} /></div>
      <button type="button" className="button button--secondary" onClick={() => void selectCoordinates(Number(latitudeInput), Number(longitudeInput), 'map')}
        disabled={!latitudeInput.trim() || !longitudeInput.trim()}>Place pin at coordinates</button>
    </fieldset></details>
    <div className="field"><label htmlFor={`${idPrefix}-address`}>Readable address or location description</label>
      <input id={`${idPrefix}-address`} value={value?.address ?? ''} disabled={!value} maxLength={500}
        onChange={event => editAddress(event.target.value)} placeholder="Select a pin, then correct this description if needed" />
      {value?.addressSource === 'manual' && <span className="field__hint">Manually edited address; the map pin remains at the selected coordinates.</span>}
    </div>
    {onNoteChange && <div className="field"><label htmlFor={`${idPrefix}-note`}>{noteLabel}</label>
      <input id={`${idPrefix}-note`} value={note ?? ''} maxLength={500} onChange={event => onNoteChange(event.target.value)}
        placeholder="For example, behind the library near the bins" /></div>}
    {resolving && <p role="status">Finding an address for the selected pin...</p>}
    {hint && <p role="status">{hint}</p>}
    {error && <p role="alert">{error}</p>}
    <div className="selected-location"><strong>{value ? (showCoordinates ? `Pin: ${coordinateText(value.latitude, value.longitude)}` : value.address || 'Add a location description') : 'No location selected'}</strong>
      {value && showCoordinates && <p>{value.address || 'Add an address or location description.'}</p>}
      <button type="button" className="button button--primary" disabled={!value || !value.address.trim() || unresolved}
        onClick={onConfirm}>{confirmLabel ?? (confirmed ? 'Location confirmed' : 'Confirm selected location')}</button>
      {onCancel && <button type="button" className="button button--secondary" onClick={onCancel}>Cancel</button>}
      {unresolved && <p>Add a landmark or location note to describe these coordinates before confirming.</p>}
    </div>
  </div>
}
