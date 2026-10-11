// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

const authenticatedFetch = vi.hoisted(() => vi.fn())
vi.mock('../../features/authentication/authenticated-fetch', () => ({ authenticatedFetch }))

vi.mock('./LocationPicker', () => ({
  LocationPicker: ({ onChange, onConfirm }: { onChange: (value: unknown) => void; onConfirm: () => void }) => <div>
    <button type="button" onClick={() => onChange({ latitude: 6.8, longitude: 100.3, address: 'Manual area', source: 'map' })}>Choose area on map</button>
    <button type="button" onClick={onConfirm}>Confirm search area</button>
  </div>,
}))
vi.mock('./TomTomMap', () => ({ TomTomMap: () => <div>Result map</div> }))

import { NearbyRecyclingMap } from './NearbyRecyclingMap'

afterEach(() => { cleanup(); authenticatedFetch.mockReset() })

it('searches the manually chosen area without GPS and shows unknown materials', async () => {
  authenticatedFetch.mockResolvedValue({ ok: true, json: async () => ({ results: [{
    id: 'poi-1', name: 'Real listing', latitude: 6.801, longitude: 100.301,
    address: 'Test Road', accepted_materials: null, source: 'tomtom',
  }] }) })
  render(<NearbyRecyclingMap registeredPoints={[]} />)
  fireEvent.click(screen.getByRole('button', { name: 'Choose area on map' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm search area' }))
  await waitFor(() => expect(authenticatedFetch).toHaveBeenCalledWith(
    '/api/location/recycling/nearby?latitude=6.8&longitude=100.3', expect.any(Object),
  ))
  expect(await screen.findByText(/Accepted materials unknown/)).toBeTruthy()
  expect(screen.getByText('Result map')).toBeTruthy()
})

it('keeps registered points visible when nearby place search fails', async () => {
  authenticatedFetch.mockResolvedValue({ ok: false })
  render(<NearbyRecyclingMap registeredPoints={[{
    id: 'registered-1', name: 'Registered point', latitude: 6.801, longitude: 100.301,
    accepted_materials: ['Plastic'], description: 'Test Road', active: true,
  }]} />)
  fireEvent.click(screen.getByRole('button', { name: 'Choose area on map' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm search area' }))
  expect(await screen.findByText(/Nearby place search is unavailable/)).toBeTruthy()
  expect(screen.getByText('Accepted materials: Plastic')).toBeTruthy()
})
