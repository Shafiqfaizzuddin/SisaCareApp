import {
  AlertCircle,
  CheckCircle2,
  Crosshair,
  LoaderCircle,
  MapPin,
  Search,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type {
  LocationSearchResult,
  LocationSource,
  ReportLocation,
} from '../../types'
import {
  LocationRequestError,
  reverseGeocode,
  searchLocations,
} from '../../features/location/tomtom-api'
import { TomTomMap } from './TomTomMap'


interface LocationPickerProps {
  value: ReportLocation | null
  confirmed: boolean
  onChange: (location: ReportLocation) => void
  onConfirm: () => void
}

function coordinateAddress(latitude: number, longitude: number): string {
  return `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`
}

function geolocationMessage(error: GeolocationPositionError): string {
  if (error.code === error.PERMISSION_DENIED) {
    return 'Location permission was denied. You can still search or select the location on the map.'
  }
  if (error.code === error.TIMEOUT) {
    return 'Getting your location timed out. Try again or select the location manually.'
  }
  if (error.code === error.POSITION_UNAVAILABLE) {
    return 'Your device could not determine its location. Use search or the map instead.'
  }
  return 'Your location could not be retrieved. Use search or the map instead.'
}

export function LocationPicker({
  value,
  confirmed,
  onChange,
  onConfirm,
}: LocationPickerProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<LocationSearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [isLocating, setIsLocating] = useState(false)
  const [isReverseGeocoding, setIsReverseGeocoding] = useState(false)
  const [error, setError] = useState('')
  const [warning, setWarning] = useState('')
  const reverseRequest = useRef<AbortController | null>(null)
  const valueRef = useRef(value)
  const skipNextSearch = useRef(false)
  valueRef.current = value

  useEffect(() => {
    const normalizedQuery = query.trim()
    if (skipNextSearch.current) {
      skipNextSearch.current = false
      return
    }
    if (normalizedQuery.length < 3) {
      setResults([])
      setIsSearching(false)
      return
    }
    const controller = new AbortController()
    const timeout = window.setTimeout(() => {
      setIsSearching(true)
      setError('')
      const bias = valueRef.current
        ? {
            latitude: valueRef.current.latitude,
            longitude: valueRef.current.longitude,
          }
        : null
      void searchLocations(normalizedQuery, controller.signal, bias)
        .then((searchResults) => {
          setResults(searchResults)
          if (searchResults.length === 0) {
            setWarning('No matching locations were found. Try a broader search.')
          } else {
            setWarning('')
          }
        })
        .catch((requestError: unknown) => {
          if (requestError instanceof DOMException && requestError.name === 'AbortError') return
          setResults([])
          setError(
            requestError instanceof LocationRequestError
              ? requestError.message
              : 'Location search failed. Please try again.',
          )
        })
        .finally(() => {
          if (!controller.signal.aborted) setIsSearching(false)
        })
    }, 400)
    return () => {
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [query])

  useEffect(
    () => () => {
      reverseRequest.current?.abort()
    },
    [],
  )

  function updateFromSearch(result: LocationSearchResult) {
    reverseRequest.current?.abort()
    setResults([])
    skipNextSearch.current = true
    setQuery(result.label)
    setError('')
    setWarning('')
    onChange({
      latitude: result.latitude,
      longitude: result.longitude,
      address: result.address,
      street: result.street,
      city: result.city,
      state: result.state,
      postcode: result.postcode,
      country: result.country,
      source: 'search',
    })
  }

  async function updateCoordinates(
    latitude: number,
    longitude: number,
    source: Exclude<LocationSource, 'search'>,
    selectionWarning = '',
  ) {
    reverseRequest.current?.abort()
    const controller = new AbortController()
    reverseRequest.current = controller
    setError('')
    setWarning(selectionWarning)
    setIsReverseGeocoding(true)
    onChange({
      latitude,
      longitude,
      address: coordinateAddress(latitude, longitude),
      street: null,
      city: null,
      state: null,
      postcode: null,
      country: null,
      source,
    })
    try {
      const resolved = await reverseGeocode(latitude, longitude, controller.signal)
      if (!controller.signal.aborted) onChange({ ...resolved, source })
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === 'AbortError') return
      setWarning(
        'Coordinates were selected, but the address could not be found. You can still confirm this location.',
      )
    } finally {
      if (reverseRequest.current === controller) {
        reverseRequest.current = null
        setIsReverseGeocoding(false)
      }
    }
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setError('This browser does not support device location. Use search or the map instead.')
      return
    }
    setIsLocating(true)
    setError('')
    setWarning('')
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setIsLocating(false)
        const accuracyWarning =
          position.coords.accuracy > 150
            ? `Your device location is approximate (within about ${Math.round(position.coords.accuracy)} metres). Adjust the marker if needed.`
            : ''
        void updateCoordinates(
          position.coords.latitude,
          position.coords.longitude,
          'gps',
          accuracyWarning,
        )
      },
      (geolocationError) => {
        setIsLocating(false)
        setError(geolocationMessage(geolocationError))
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 0 },
    )
  }

  return (
    <div className="location-picker">
      <div className="location-picker__actions">
        <button
          className="button button--secondary"
          type="button"
          disabled={isLocating}
          onClick={useCurrentLocation}
        >
          {isLocating ? <LoaderCircle className="spin" size={17} /> : <Crosshair size={17} />}
          {isLocating ? 'Getting your location...' : 'Use my current location'}
        </button>
      </div>

      <div className="field location-search">
        <label htmlFor="location-search">Search address or place</label>
        <div className="input-with-icon">
          {isSearching ? <LoaderCircle className="spin" size={18} /> : <Search size={18} />}
          <input
            id="location-search"
            autoComplete="off"
            value={query}
            placeholder="e.g. UiTM Arau or Jalan Kangar"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        {results.length > 0 && (
          <ul className="location-search__results" aria-label="Location search results">
            {results.map((result) => (
              <li key={result.id}>
                <button type="button" onClick={() => updateFromSearch(result)}>
                  <MapPin size={16} />
                  <span>{result.label}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <TomTomMap
        interactive
        location={value}
        ariaLabel="Select the waste location on the TomTom map"
        onSelect={(latitude, longitude) => {
          void updateCoordinates(latitude, longitude, 'map')
        }}
      />

      {isReverseGeocoding && (
        <p className="location-picker__status">
          <LoaderCircle className="spin" size={15} /> Finding address...
        </p>
      )}
      {error && (
        <p className="location-picker__message location-picker__message--error" role="alert">
          <AlertCircle size={16} /> {error}
        </p>
      )}
      {warning && (
        <p className="location-picker__message" role="status">
          <AlertCircle size={16} /> {warning}
        </p>
      )}

      <div className="selected-location">
        <div>
          <span>Selected location</span>
          <strong>{value?.address ?? 'No location selected'}</strong>
        </div>
        {value && (
          <dl>
            <div><dt>Latitude</dt><dd>{value.latitude.toFixed(6)}</dd></div>
            <div><dt>Longitude</dt><dd>{value.longitude.toFixed(6)}</dd></div>
          </dl>
        )}
        <button
          className="button button--primary"
          type="button"
          disabled={!value || isReverseGeocoding}
          onClick={onConfirm}
        >
          <CheckCircle2 size={17} />
          {confirmed ? 'Location confirmed' : 'Confirm location'}
        </button>
      </div>
    </div>
  )
}
