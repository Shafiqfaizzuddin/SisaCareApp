const apiKey = (import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined)?.trim() ?? ''
export const googleMapId = (import.meta.env.VITE_GOOGLE_MAP_ID as string | undefined)?.trim() || (import.meta.env.DEV ? 'DEMO_MAP_ID' : '')

let loader: Promise<typeof google.maps> | null = null

export function loadGoogleMaps(): Promise<typeof google.maps> {
  const existing = (window as unknown as { google?: typeof google }).google
  if (existing?.maps?.importLibrary) return Promise.resolve(existing.maps)
  if (!apiKey) return Promise.reject(new Error('Google Maps is unavailable. Enter known coordinates below or try again later.'))
  if (!loader) {
    loader = new Promise((resolve, reject) => {
      const callback = '__sisacareGoogleMapsReady'
      const host = window as unknown as Record<string, unknown>
      const script = document.createElement('script')
      let done = false
      const timeout = window.setTimeout(() => fail(), 15000)
      function finish() {
        if (done) return
        done = true
        window.clearTimeout(timeout)
        delete host[callback]
        resolve((window as unknown as { google: typeof google }).google.maps)
      }
      function fail() {
        if (done) return
        done = true
        window.clearTimeout(timeout)
        delete host[callback]
        script.remove()
        loader = null
        reject(new Error('Google Maps could not load. Enter known coordinates below or try again later.'))
      }
      host[callback] = finish
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&v=weekly&loading=async&callback=${callback}`
      script.async = true
      script.onerror = fail
      document.head.appendChild(script)
    })
  }
  return loader
}

export type PlaceSuggestion = { label: string; prediction: google.maps.places.PlacePrediction }

export async function newPlaceSessionToken(): Promise<google.maps.places.AutocompleteSessionToken> {
  const maps = await loadGoogleMaps()
  const { AutocompleteSessionToken } = await maps.importLibrary('places') as google.maps.PlacesLibrary
  return new AutocompleteSessionToken()
}

export async function suggestPlaces(input: string, sessionToken: google.maps.places.AutocompleteSessionToken): Promise<PlaceSuggestion[]> {
  const maps = await loadGoogleMaps()
  const { AutocompleteSuggestion } = await maps.importLibrary('places') as google.maps.PlacesLibrary
  const { suggestions } = await AutocompleteSuggestion.fetchAutocompleteSuggestions({ input, sessionToken })
  return suggestions.flatMap(value => value.placePrediction
    ? [{ label: value.placePrediction.text.toString(), prediction: value.placePrediction }] : [])
}

export async function resolvePlace(prediction: google.maps.places.PlacePrediction) {
  const place = prediction.toPlace()
  await place.fetchFields({ fields: ['location', 'formattedAddress'] })
  if (!place.location) throw new Error('This place has no coordinates. Select another suggestion.')
  return { latitude: place.location.lat(), longitude: place.location.lng(),
    address: place.formattedAddress || prediction.text.toString() }
}

export async function reverseGeocode(latitude: number, longitude: number): Promise<string | null> {
  const maps = await loadGoogleMaps()
  const { Geocoder } = await maps.importLibrary('geocoding') as google.maps.GeocodingLibrary
  const response = await new Geocoder().geocode({ location: { lat: latitude, lng: longitude } })
  return response.results[0]?.formatted_address ?? null
}

export function googleMapsNavigationUrl(latitude: number, longitude: number): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${latitude},${longitude}`
}
