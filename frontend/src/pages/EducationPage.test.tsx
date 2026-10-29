// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { EducationPage } from './EducationPage'

const mocks = vi.hoisted(() => ({ fetchLearnArticles: vi.fn() }))
vi.mock('../features/education/education-api', () => ({ fetchLearnArticles: mocks.fetchLearnArticles }))

beforeEach(() => mocks.fetchLearnArticles.mockReset())
afterEach(cleanup)

it('renders published knowledge from the API with an accessible image', async () => {
  mocks.fetchLearnArticles.mockResolvedValue([{
    id: 'a1', title: 'Sorting paper', summary: 'Check the paper condition.',
    body: 'Ask your local collection point what it accepts.',
    image_url: '/api/education/articles/a1/image', image_alt: 'Sorted paper in a collection bin',
    published: true, sort_order: 0,
  }])
  render(<EducationPage />)
  await waitFor(() => expect(screen.getByText('Sorting paper')).toBeTruthy())
  expect(screen.getByAltText('Sorted paper in a collection bin').getAttribute('src')).toBe('/api/education/articles/a1/image')
  expect(screen.getByText('Ask your local collection point what it accepts.')).toBeTruthy()
})

it('shows an honest empty state', async () => {
  mocks.fetchLearnArticles.mockResolvedValue([])
  render(<EducationPage />)
  await waitFor(() => expect(screen.getByText('No learning articles have been published yet.')).toBeTruthy())
})
