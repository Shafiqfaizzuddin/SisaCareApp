// @vitest-environment happy-dom
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

const { signOut } = vi.hoisted(() => ({ signOut: vi.fn().mockResolvedValue(undefined) }))
vi.mock('../features/authentication/useRole', () => ({ useRole: () => ({ role: 'staff', user: {
  id: 'staff-1', name: 'Collection Worker', email: 'worker@example.com', role: 'staff', points: 0,
}, signOut }) }))
vi.mock('../features/theme/useTheme', () => ({ useTheme: () => ({ theme: 'light', toggleTheme: () => {} }) }))
import { PublicLayout } from './PublicLayout'

afterEach(cleanup)

it('shows the staff dashboard link instead of guest sign-in links for staff', () => {
  render(<MemoryRouter initialEntries={['/']}><Routes>
    <Route element={<PublicLayout />}><Route path="/" element={<p>Home</p>} /></Route>
  </Routes></MemoryRouter>)
  expect(screen.getByRole('link', { name: 'Staff dashboard' }).getAttribute('href')).toBe('/staff')
  expect(screen.queryByRole('link', { name: 'Sign in' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Sign out' })).toBeTruthy()
})
