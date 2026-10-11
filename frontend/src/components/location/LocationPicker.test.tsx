// @vitest-environment happy-dom
import { useState } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { ReportLocation } from '../../types'

const maps = vi.hoisted(() => ({ newPlaceSessionToken: vi.fn(), suggestPlaces: vi.fn(), resolvePlace: vi.fn(), reverseGeocode: vi.fn() }))
vi.mock('../../features/location/google-maps', () => maps)
vi.mock('./GoogleMap', () => ({ GoogleMap: ({ onSelect, location }: {
  onSelect: (latitude: number, longitude: number) => void; location: ReportLocation | null
}) => <div>
  <button type="button" onClick={() => onSelect(6.8, 100.3)}>Click map</button>
  <button type="button" onClick={() => onSelect(6.9, 100.4)}>Drag marker</button>
  <span>Map pin: {location ? `${location.latitude}, ${location.longitude}` : 'none'}</span>
</div> }))

import { LocationPicker } from './LocationPicker'

function Picker() {
  const [value, setValue] = useState<ReportLocation | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [note, setNote] = useState('')
  return <LocationPicker value={value} confirmed={confirmed} note={note} onNoteChange={setNote}
    onChange={next => { setValue(next); setConfirmed(false) }} onConfirm={() => setConfirmed(true)} />
}

beforeEach(() => {
  vi.clearAllMocks()
  maps.newPlaceSessionToken.mockResolvedValue({ token: 'session' })
  maps.suggestPlaces.mockResolvedValue([])
  maps.reverseGeocode.mockResolvedValue('Resolved Road')
  maps.resolvePlace.mockResolvedValue({ latitude: 6.7, longitude: 100.2, address: 'Selected Building' })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('places and drags the selected pin, reverse geocodes, and requires reconfirmation', async () => {
  render(<Picker />)
  expect(screen.getByText('Map pin: none')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Click map' }))
  expect(await screen.findByDisplayValue('Resolved Road')).toBeTruthy()
  expect(screen.getByText('Map pin: 6.8, 100.3')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm selected location' }))
  expect(screen.getByRole('button', { name: 'Location confirmed' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Drag marker' }))
  expect(await screen.findByText('Map pin: 6.9, 100.4')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Confirm selected location' })).toBeTruthy()
  expect(maps.reverseGeocode).toHaveBeenLastCalledWith(6.9, 100.4)
})

it('discards late geocoding after a move or manual address correction', async () => {
  let firstResolve: (value: string) => void = () => undefined
  maps.reverseGeocode.mockReturnValueOnce(new Promise<string>(resolve => { firstResolve = resolve }))
    .mockResolvedValueOnce('New Road')
  render(<Picker />)
  fireEvent.click(screen.getByRole('button', { name: 'Click map' }))
  fireEvent.click(screen.getByRole('button', { name: 'Drag marker' }))
  expect(await screen.findByDisplayValue('New Road')).toBeTruthy()
  firstResolve('Stale Road')
  await waitFor(() => expect(screen.queryByDisplayValue('Stale Road')).toBeNull())
  fireEvent.change(screen.getByLabelText('Readable address or location description'), { target: { value: 'My corrected address' } })
  expect(screen.getByDisplayValue('My corrected address')).toBeTruthy()
  expect(screen.getByText('Map pin: 6.9, 100.4')).toBeTruthy()
  expect(screen.getByText(/Manually edited address/)).toBeTruthy()
})

it('allows denied GPS and failed geocoding to use manual coordinates and a description', async () => {
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition: (_ok: unknown, fail: (value: { code: number; PERMISSION_DENIED: number }) => void) =>
    fail({ code: 1, PERMISSION_DENIED: 1 }) } })
  maps.reverseGeocode.mockRejectedValue(new Error('unavailable'))
  render(<Picker />)
  fireEvent.click(screen.getByRole('button', { name: 'Use my current location' }))
  expect(screen.getByText(/Location permission denied/)).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Latitude'), { target: { value: '6.8' } })
  fireEvent.change(screen.getByLabelText('Longitude'), { target: { value: '100.3' } })
  fireEvent.click(screen.getByRole('button', { name: 'Place pin at coordinates' }))
  expect(await screen.findByText(/Address lookup failed/)).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Landmark or location note (optional)'), { target: { value: 'Behind library bins' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm selected location' }))
  expect(screen.getByRole('button', { name: 'Location confirmed' })).toBeTruthy()
})

it('selects an autocomplete suggestion using the same session token', async () => {
  const prediction = { text: { toString: () => 'Building' } }
  maps.suggestPlaces.mockResolvedValue([{ label: 'Building', prediction }])
  render(<Picker />)
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Building' } })
  const suggestion = await screen.findByRole('button', { name: 'Building' })
  fireEvent.click(suggestion)
  expect(await screen.findByText('Map pin: 6.7, 100.2')).toBeTruthy()
  expect(screen.getByDisplayValue('Selected Building')).toBeTruthy()
  expect(maps.resolvePlace).toHaveBeenCalledWith(prediction)
})
