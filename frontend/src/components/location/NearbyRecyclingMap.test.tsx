// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

vi.mock('./LocationPicker', () => ({ LocationPicker: ({ onChange, onConfirm }: {
  onChange: (value: unknown) => void; onConfirm: () => void
}) => <div><button type="button" onClick={() => onChange({ latitude: 6.8, longitude: 100.3, address: 'Manual origin', source: 'map' })}>Choose origin</button>
  <button type="button" onClick={onConfirm}>Confirm origin</button></div> }))
vi.mock('./GoogleMap', () => ({ GoogleMap: ({ markers, onMarkerSelect }: {
  markers: Array<{ id: string; name: string }>; onMarkerSelect: (id: string) => void
}) => <div>{markers.map(point => <button key={point.id} type="button" onClick={() => onMarkerSelect(point.id)}>{`Marker ${point.name}`}</button>)}</div> }))
import { NearbyRecyclingMap } from './NearbyRecyclingMap'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('shows only database stations, ranks from confirmed origin, and navigates with saved coordinates', () => {
  vi.stubGlobal('fetch', vi.fn())
  render(<NearbyRecyclingMap registeredPoints={[
    { id: 'far', name: 'Far station', latitude: 7.5, longitude: 100.3, accepted_materials: [], description: '', active: true },
    { id: 'near', name: 'Near station', latitude: 6.801, longitude: 100.301, accepted_materials: ['Plastic'], description: '', active: true, address: 'Near Road' },
    { id: 'off', name: 'Inactive', latitude: 6.8, longitude: 100.3, accepted_materials: ['Plastic'], description: '', active: false },
  ]} />)
  expect(screen.queryByText('Inactive')).toBeNull()
  expect(screen.queryByText(/straight-line/, { selector: 'span' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Choose origin' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm origin' }))
  const entries = screen.getAllByRole('button', { name: /station/i })
  expect(entries[0].textContent).toContain('Near station')
  expect(screen.getByText('Accepted materials unknown')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Marker Near station' }))
  expect(screen.getByRole('link', { name: 'Open in Google Maps' }).getAttribute('href'))
    .toContain('destination=6.801,100.301')
  expect(globalThis.fetch).not.toHaveBeenCalled()
})
