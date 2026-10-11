// @vitest-environment happy-dom
import { cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

const fake = vi.hoisted(() => ({ removed: 0, failNext: false, maps: [] as Array<{ options: Record<string, unknown>; listeners: Record<string, (event: unknown) => void> }>,
  markers: [] as Array<{ position: { lat: number; lng: number }; options: Record<string, unknown>;
    listeners: Record<string, () => void>; map: unknown }> }))

vi.mock('../../features/location/google-maps', () => ({
  googleMapId: 'test-map-id',
  loadGoogleMaps: async () => { if (fake.failNext) { fake.failNext = false; throw new Error('offline') }
    return { importLibrary: async (name: string) => name === 'maps'
    ? { Map: class {
      options: Record<string, unknown>
      listeners: Record<string, (event: unknown) => void> = {}
      constructor(_element: HTMLElement, options: Record<string, unknown>) { this.options = options; fake.maps.push(this) }
      addListener(name: string, callback: (event: unknown) => void) {
        this.listeners[name] = callback
        return { remove: () => { delete this.listeners[name]; fake.removed++ } }
      }
      panTo() {}
      getZoom() { return 16 }
      setZoom() {}
    } }
    : { AdvancedMarkerElement: class {
      position: { lat: number; lng: number }
      options: Record<string, unknown>
      listeners: Record<string, () => void> = {}
      map: unknown
      constructor(options: Record<string, unknown>) {
        this.options = options
        this.position = options.position as { lat: number; lng: number }
        this.map = options.map
        fake.markers.push(this)
      }
      addEventListener(name: string, callback: () => void) { this.listeners[name] = callback }
      append() {}
    }, PinElement: class {} },
  } },
}))

import { GoogleMap } from './GoogleMap'

afterEach(() => { cleanup(); fake.maps.length = 0; fake.markers.length = 0; fake.removed = 0; fake.failNext = false })

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
