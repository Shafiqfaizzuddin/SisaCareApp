// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AdminLearnPage } from './AdminLearnPage'

const mocks = vi.hoisted(() => ({
  fetchAdminLearnArticles: vi.fn(), saveLearnArticle: vi.fn(),
  uploadLearnImage: vi.fn(), removeLearnImage: vi.fn(),
}))
vi.mock('../features/education/education-api', () => mocks)

beforeEach(() => {
  Object.values(mocks).forEach(mock => mock.mockReset())
  mocks.fetchAdminLearnArticles.mockResolvedValue([])
  mocks.saveLearnArticle.mockResolvedValue({ id: 'new-article' })
})
afterEach(cleanup)

it('lets an administrator publish a new learning article', async () => {
  render(<AdminLearnPage />)
  await screen.findByText('No articles yet.')
  await userEvent.type(screen.getByLabelText('Title'), 'Recycling glass')
  await userEvent.type(screen.getByLabelText('Short introduction'), 'Check local glass acceptance.')
  await userEvent.type(screen.getByLabelText('Information and guidance'), 'Keep broken glass away from collection workers.')
  await userEvent.click(screen.getByRole('button', { name: 'Publish article' }))
  await waitFor(() => expect(mocks.saveLearnArticle).toHaveBeenCalledWith(expect.objectContaining({
    title: 'Recycling glass', published: true,
  }), undefined))
  expect(mocks.uploadLearnImage).not.toHaveBeenCalled()
})
