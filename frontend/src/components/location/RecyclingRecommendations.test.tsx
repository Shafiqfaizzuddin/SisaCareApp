// @vitest-environment happy-dom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RecyclingRecommendations } from './RecyclingRecommendations'

vi.mock('./GoogleMap', () => ({ GoogleMap: () => <div>Google map</div> }))
const actionMocks = vi.hoisted(() => ({ submit: vi.fn() }))
vi.mock('../../features/reporting/recycling-actions', () => ({ submitRecyclingAction: actionMocks.submit }))

const wasteLocation = { latitude: 6.4, longitude: 100.2, address: 'Campus', source: 'map' as const,
  street: '', city: '', state: '', postcode: '', country: 'Malaysia' }
const items = [{ name: 'Plastic Bottle', material: 'Plastic', category: 'Recyclable Waste' as const, stationMaterialKey: 'Plastic' }]
const point = { id: 'one', name: 'Registered point', latitude: 6.401, longitude: 100.2,
  accepted_materials: ['Plastic'], description: '', active: true, public_verified: true }

describe('recycling recommendation location fallback', () => {
  afterEach(cleanup)
  beforeEach(() => {
    actionMocks.submit.mockReset()
    Object.defineProperty(navigator, 'geolocation', { configurable: true, value: {
      getCurrentPosition: (_success: unknown, failure: () => void) => failure(),
    } })
  })

  it('identifies the waste-location fallback and displays approximate straight-line distance', async () => {
    render(<RecyclingRecommendations points={[point]} items={items} wasteLocation={wasteLocation}
      loading={false} error="" analysisId="draft" onReport={vi.fn()} onSubmitted={vi.fn()} />)
    expect(await screen.findByText(/Sorted from the selected location/)).toBeTruthy()
    expect(screen.getAllByText(/straight-line/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Google map').length).toBeGreaterThan(0)
  })

  it('offers guidance and reporting when there is no matching point', async () => {
    render(<RecyclingRecommendations points={[]} items={items} wasteLocation={wasteLocation}
      loading={false} error="" analysisId="draft" onReport={vi.fn()} onSubmitted={vi.fn()} />)
    expect(await screen.findByText(/No active registered point accepts/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Report It Instead' })).toBeTruthy()
  })

  it('requires one proof photo and manual location, and blocks repeated submission', async () => {
    const onSubmitted = vi.fn()
    let resolveSubmission: (value: unknown) => void = () => undefined
    actionMocks.submit.mockImplementation(() => new Promise(resolve => { resolveSubmission = resolve }))
    render(<RecyclingRecommendations points={[point]} items={items} wasteLocation={wasteLocation}
      loading={false} error="" analysisId="draft" onReport={vi.fn()} onSubmitted={onSubmitted} />)
    fireEvent.click(screen.getByRole('button', { name: /Registered point/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit for admin verification' }))
    expect(screen.getByText('Upload one proof photo before submitting.')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Proof photo'), { target: { files: [new File(['photo'], 'proof.png', { type: 'image/png' })] } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit for admin verification' }))
    expect(screen.getByText('Enter the proof location manually.')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Manual proof location'), { target: { value: 'By the registered point' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit for admin verification' }))
    expect(actionMocks.submit).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Submitting for review...' }).hasAttribute('disabled')).toBe(true)
    resolveSubmission({ id: 'action' })
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1))
  })
})
