// @vitest-environment happy-dom
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

const fake = vi.hoisted(() => ({ removed: 0, failNext: false, maps: [] as Array<{ options: Record<string, unknown>; listeners: Record<string, (event: unknown) => void>;
  pans: Array<{ lat: number; lng: number }>; zooms: number[]; fits: unknown[] }>,
  tiles: [] as Array<{ options: Record<string, unknown>; map: unknown; listeners: Record<string, () => void> }>,
  markers: [] as Array<{ position: { lat: number; lng: number }; options: Record<string, unknown>;
    listeners: Record<string, () => void>; map: unknown; content: HTMLElement[] }> }))

vi.mock('../../features/location/google-maps', () => ({
  googleMapId: 'test-map-id',
  loadGoogleMaps: async () => { if (fake.failNext) { fake.failNext = false; throw new Error('offline') }
    return { importLibrary: async (name: string) => name === 'maps'
    ? { Rectangle: class {
      options: Record<string, unknown>; map: unknown
      listeners: Record<string, () => void> = {}
      constructor(options: Record<string, unknown>) { this.options = options; this.map = options.map; fake.tiles.push(this) }
      addListener(name: string, callback: () => void) { this.listeners[name] = callback }
      setMap(value: unknown) { this.map = value }
    }, Map: class {
      options: Record<string, unknown>
      listeners: Record<string, (event: unknown) => void> = {}
      pans: Array<{ lat: number; lng: number }> = []
      zooms: number[] = []
      fits: unknown[] = []
      constructor(_element: HTMLElement, options: Record<string, unknown>) { this.options = options; fake.maps.push(this) }
      addListener(name: string, callback: (event: unknown) => void) {
        this.listeners[name] = callback
        return { remove: () => { delete this.listeners[name]; fake.removed++ } }
      }
      panTo(point: { lat: number; lng: number }) { this.pans.push(point) }
      getZoom() { return 16 }
      setZoom(value: number) { this.zooms.push(value) }
      fitBounds(bounds: unknown) { this.fits.push(bounds) }
    } }
    : { AdvancedMarkerElement: class {
      position: { lat: number; lng: number }
      options: Record<string, unknown>
      listeners: Record<string, () => void> = {}
      map: unknown
      content: HTMLElement[] = []
      constructor(options: Record<string, unknown>) {
        this.options = options
        this.position = options.position as { lat: number; lng: number }
        this.map = options.map
        fake.markers.push(this)
      }
      addEventListener(name: string, callback: () => void) { this.listeners[name] = callback }
      append(element: HTMLElement) { this.content.push(element) }
    }, PinElement: class {} },
  } },
}))

import { GoogleMap } from './GoogleMap'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); fake.maps.length = 0; fake.markers.length = 0; fake.tiles.length = 0; fake.removed = 0; fake.failNext = false })

it('keeps the default centre unselected and reports deliberate clicks and completed drags', async () => {
  const selected = vi.fn()
  const view = render(<GoogleMap location={null} interactive onSelect={selected} />)
  await waitFor(() => expect(fake.maps).toHaveLength(1))
  expect(fake.markers).toHaveLength(0)
  expect(selected).not.toHaveBeenCalled()
  fake.maps[0].listeners.click({ latLng: { lat: () => 6.8, lng: () => 100.3 } })
  expect(selected).toHaveBeenCalledWith(6.8, 100.3)

  view.rerender(<GoogleMap location={{ latitude: 6.8, longitude: 100.3 }} interactive onSelect={selected} />)
  await waitFor(() => expect(fake.markers).toHaveLength(1))
  expect(fake.maps).toHaveLength(1)
  expect(fake.markers[0].options.gmpDraggable).toBe(true)
  fake.markers[0].position = { lat: 6.9, lng: 100.4 }
  fake.markers[0].listeners['gmp-dragend']()
  expect(selected).toHaveBeenLastCalledWith(6.9, 100.4)
  view.unmount()
  expect(fake.removed).toBe(1)
  expect(fake.markers[0].map).toBeNull()
})

it('offers retry after a map load failure', async () => {
  fake.failNext = true
  const view = render(<GoogleMap location={null} interactive />)
  await waitFor(() => expect(view.getByRole('alert').textContent).toContain('could not load'))
  view.getByRole('button', { name: 'Retry map' }).click()
  await waitFor(() => expect(fake.maps).toHaveLength(1))
})

it('draws exact observed cell bounds, selects a cell and retains coarse forecast bounds', async () => {
  const selected = vi.fn()
  const bounds = { south: 3.07, north: 3.08, west: 101.52, east: 101.53 }
  const point = [{ latitude: 3.075, longitude: 101.525, weight: 4, cellKey: 'g1km:1:2', bounds }]
  const view = render(<GoogleMap location={null} heatPoints={point} heatTone="observed" onHeatCellSelect={selected} />)
  await waitFor(() => expect(fake.tiles).toHaveLength(1))
  expect(fake.tiles[0].options.fillColor).toBe('#fee08b')
  expect(fake.tiles[0].options.bounds).toEqual(bounds)
  fake.tiles[0].listeners.click()
  expect(selected).toHaveBeenCalledWith('g1km:1:2')
  expect(fake.maps[0].pans.at(-1)).toEqual({ lat: point[0].latitude, lng: point[0].longitude })
  expect(fake.maps[0].zooms.at(-1)).toBe(15)
  view.rerender(<GoogleMap location={null} heatPoints={[{ latitude: 3.075, longitude: 101.525, weight: 4 }]} heatTone="forecast" />)
  await waitFor(() => expect(fake.tiles).toHaveLength(2))
  expect(fake.tiles[0].map).toBeNull()
  expect(fake.tiles[1].options.fillColor).toBe('#3769b0')
  const forecastBounds = fake.tiles[1].options.bounds as { south: number; north: number; west: number; east: number }
  expect(forecastBounds.south).toBeCloseTo(3.05)
  expect(forecastBounds.north).toBeCloseTo(3.1)
  expect(forecastBounds.west).toBeCloseTo(101.5)
  expect(forecastBounds.east).toBeCloseTo(101.55)
})

it('shows counts and finds the admin location without changing report coordinates', async () => {
  let resolveLocation: PositionCallback = () => {}
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition: (success: PositionCallback) => { resolveLocation = success } } })
  const selected = vi.fn()
  const point = [{ latitude: 3.075, longitude: 101.525, weight: 3, cellKey: 'g1km:1:2',
    bounds: { south: 3.07, north: 3.08, west: 101.52, east: 101.53 } }]
  const view = render(<GoogleMap location={null} heatPoints={point} heatTone="observed"
    onHeatCellSelect={selected} showHeatControls />)
  await waitFor(() => expect(fake.markers).toHaveLength(1))
  expect(fake.markers[0].content[0].textContent).toBe('3')
  expect(fake.markers[0].options.title).toBe('3 reports in this area')
  fake.markers[0].listeners['gmp-click']()
  expect(selected).toHaveBeenCalledWith('g1km:1:2')
  expect(fake.maps[0].pans.at(-1)).toEqual({ lat: point[0].latitude, lng: point[0].longitude })
  expect(fake.maps[0].zooms.at(-1)).toBe(15)
  await waitFor(() => expect(view.getByRole('status').textContent).toContain('selected 1 km report area'))
  fireEvent.click(view.getByRole('button', { name: 'Find my location' }))
  resolveLocation({ coords: { latitude: 3.12, longitude: 101.62, accuracy: 220 } } as GeolocationPosition)
  await waitFor(() => expect(fake.maps[0].pans.at(-1)).toEqual({ lat: 3.12, lng: 101.62 }))
  expect(view.getByRole('status').textContent).toContain('approximate location')
  await waitFor(() => expect(fake.markers).toHaveLength(2))
  expect(fake.markers[1].options.title).toBe('Your current location')
  fireEvent.click(view.getByRole('button', { name: 'Show all areas' }))
  expect(fake.maps[0].pans.at(-1)).toEqual({ lat: point[0].latitude, lng: point[0].longitude })
})

it('explains denied location permission and keeps forecast counts approximate', async () => {
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition: (_success: PositionCallback, failure: PositionErrorCallback) =>
    failure({ code: 1, PERMISSION_DENIED: 1 } as GeolocationPositionError) } })
  const view = render(<GoogleMap location={null} heatPoints={[{ latitude: 3.075, longitude: 101.525, weight: 2.34 }]}
    heatTone="forecast" showHeatControls />)
  await waitFor(() => expect(fake.markers).toHaveLength(1))
  expect(fake.markers[0].content[0].textContent).toBe('≈2.3')
  expect(fake.markers[0].options.gmpClickable).toBe(true)
  fake.markers[0].listeners['gmp-click']()
  expect(fake.maps[0].pans.at(-1)).toEqual({ lat: 3.075, lng: 101.525 })
  expect(fake.maps[0].zooms.at(-1)).toBe(12)
  await waitFor(() => expect(view.getByRole('status').textContent).toContain('selected forecast area'))
  fireEvent.click(view.getByRole('button', { name: 'Find my location' }))
  expect(view.getByRole('status').textContent).toContain('permission denied')
})
