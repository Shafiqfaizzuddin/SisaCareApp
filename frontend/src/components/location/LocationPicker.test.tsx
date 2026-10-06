// @vitest-environment happy-dom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReportLocation } from '../../types'
import { LocationPicker } from './LocationPicker'


const apiMocks = vi.hoisted(() => ({
  reverseGeocode: vi.fn(),
  searchLocations: vi.fn(),
}))

vi.mock('../../features/location/tomtom-api', async () => {
  const actual = await vi.importActual<
    typeof import('../../features/location/tomtom-api')
  >('../../features/location/tomtom-api')
  return { ...actual, ...apiMocks }
})

vi.mock('./TomTomMap', () => ({
  TomTomMap: ({
    onSelect,
  }: {
    onSelect?: (latitude: number, longitude: number) => void
  }) => (
    <button type="button" onClick={() => onSelect?.(6.447, 100.278)}>
      Select map point
    </button>
  ),
}))

const RESOLVED_LOCATION = {
  latitude: 6.447,
  longitude: 100.278,
  address: 'UiTM Arau, Perlis',
  street: null,
  city: 'Arau',
  state: 'Perlis',
  postcode: '02600',
  country: 'Malaysia',
}

function Harness() {
  const [location, setLocation] = useState<ReportLocation | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  return (
    <LocationPicker
      value={location}
      confirmed={confirmed}
      onChange={(nextLocation) => {
        setLocation(nextLocation)
        setConfirmed(false)
      }}
      onConfirm={() => setConfirmed(true)}
    />
  )
}

function installGeolocation(
  implementation: Geolocation['getCurrentPosition'],
): void {
  Object.defineProperty(navigator, 'geolocation', {
    configurable: true,
    value: { getCurrentPosition: implementation },
  })
}

beforeEach(() => {
  apiMocks.reverseGeocode.mockReset()
  apiMocks.searchLocations.mockReset()
  apiMocks.searchLocations.mockResolvedValue([])
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('LocationPicker', () => {
  it('requests GPS only after the user clicks and reverse geocodes the result', async () => {
    const getCurrentPosition = vi.fn<Geolocation['getCurrentPosition']>(
      (success) => {
        success({
          coords: {
            latitude: 6.447,
            longitude: 100.278,
            accuracy: 20,
          },
        } as GeolocationPosition)
      },
    )
    installGeolocation(getCurrentPosition)
    apiMocks.reverseGeocode.mockResolvedValue(RESOLVED_LOCATION)
    render(<Harness />)

    expect(getCurrentPosition).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: /use my current location/i }))

    expect(getCurrentPosition).toHaveBeenCalledOnce()
    expect(await screen.findByText('UiTM Arau, Perlis')).toBeTruthy()
  })

  it('updates coordinates and address after a map selection', async () => {
    apiMocks.reverseGeocode.mockResolvedValue(RESOLVED_LOCATION)
    render(<Harness />)

    await userEvent.click(screen.getByRole('button', { name: 'Select map point' }))

    expect(apiMocks.reverseGeocode).toHaveBeenCalledWith(
      6.447,
      100.278,
      expect.any(AbortSignal),
    )
    expect(await screen.findByText('UiTM Arau, Perlis')).toBeTruthy()
  })

  it('debounces search and applies the selected result', async () => {
    apiMocks.searchLocations.mockResolvedValue([
      { ...RESOLVED_LOCATION, id: 'uitm-arau', label: 'UiTM Arau, Perlis' },
    ])
    render(<Harness />)

    fireEvent.change(screen.getByLabelText(/search address or place/i), {
      target: { value: 'UiTM Arau' },
    })
    expect(apiMocks.searchLocations).not.toHaveBeenCalled()

    await waitFor(() => expect(apiMocks.searchLocations).toHaveBeenCalledOnce())
    fireEvent.click(
      await screen.findByRole('button', { name: /uitm arau, perlis/i }),
    )
    expect(screen.getByText('UiTM Arau, Perlis')).toBeTruthy()
  })

  it('keeps manual selection available when GPS permission is denied', async () => {
    installGeolocation(
      vi.fn((_success, failure) => {
        failure?.({
          code: 1,
          message: 'Denied',
          PERMISSION_DENIED: 1,
          POSITION_UNAVAILABLE: 2,
          TIMEOUT: 3,
        } as GeolocationPositionError)
      }),
    )
    render(<Harness />)

    await userEvent.click(screen.getByRole('button', { name: /use my current location/i }))

    expect(await screen.findByText(/location permission was denied/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Select map point' })).toBeTruthy()
    expect(screen.getByLabelText(/search address or place/i)).toBeTruthy()
  })

  it('warns when the device location is inaccurate', async () => {
    installGeolocation(
      vi.fn((success) => {
        success({
          coords: {
            latitude: 6.447,
            longitude: 100.278,
            accuracy: 275,
          },
        } as GeolocationPosition)
      }),
    )
    apiMocks.reverseGeocode.mockResolvedValue(RESOLVED_LOCATION)
    render(<Harness />)

    await userEvent.click(screen.getByRole('button', { name: /use my current location/i }))

    expect(await screen.findByText(/within about 275 metres/i)).toBeTruthy()
  })

  it('retains usable coordinates when reverse geocoding fails', async () => {
    apiMocks.reverseGeocode.mockRejectedValue(new Error('Unavailable'))
    render(<Harness />)

    await userEvent.click(screen.getByRole('button', { name: 'Select map point' }))

    expect(await screen.findByText(/coordinates were selected/i)).toBeTruthy()
    expect(screen.getByText('6.447000, 100.278000')).toBeTruthy()
    expect(
      screen.getByRole('button', { name: /confirm location/i }).hasAttribute('disabled'),
    ).toBe(false)
  })
})
