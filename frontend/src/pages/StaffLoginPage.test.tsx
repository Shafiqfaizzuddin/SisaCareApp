// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const auth = vi.hoisted(() => ({ signIn: vi.fn(), role: 'guest', isAuthLoading: false }))
vi.mock('../features/authentication/useRole', () => ({ useRole: () => auth }))
vi.mock('../components/common/Brand', () => ({ Brand: () => <a href="/" aria-label="SisaCare.AI home">SisaCare.AI</a> }))
vi.mock('../components/common/ThemeToggle', () => ({ ThemeToggle: () => null }))
vi.mock('../features/theme/useTheme', () => ({ useTheme: () => ({ theme: 'light', toggleTheme: () => {} }) }))
import { StaffLoginPage } from './StaffLoginPage'

function renderLogin(returnTo?: string) {
  render(<MemoryRouter initialEntries={[{ pathname: '/staff/login', state: returnTo ? { returnTo } : null }]}>
    <Routes>
      <Route path="/staff/login" element={<StaffLoginPage />} />
      <Route path="/staff" element={<p>Staff dashboard destination</p>} />
      <Route path="/staff/tasks/:reportId" element={<p>Assigned task destination</p>} />
    </Routes>
  </MemoryRouter>)
}

beforeEach(() => { auth.signIn.mockReset().mockResolvedValue(undefined); auth.role = 'guest'; auth.isAuthLoading = false })
afterEach(cleanup)

it('uses the citizen sign-in layout and an accessible password toggle', async () => {
  renderLogin()
  expect(screen.getByRole('heading', { name: 'Staff and driver sign in' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Citizen sign in' }).getAttribute('href')).toBe('/login')
  expect(screen.getByRole('link', { name: 'Forgot password?' }).getAttribute('href')).toBe('/password-reset')
  expect((screen.getByLabelText('Password') as HTMLInputElement).type).toBe('password')
  await userEvent.click(screen.getByRole('button', { name: 'Show password' }))
  expect((screen.getByLabelText('Password') as HTMLInputElement).type).toBe('text')
})

it('signs in with a staff grant and returns to the assigned task', async () => {
  renderLogin('/staff/tasks/report-1')
  await userEvent.type(screen.getByLabelText('Email'), 'worker@example.com')
  await userEvent.type(screen.getByLabelText('Password'), 'strong-password')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in to staff dashboard' }))
  await waitFor(() => expect(auth.signIn).toHaveBeenCalledWith('worker@example.com', 'strong-password', 'staff'))
  expect(await screen.findByText('Assigned task destination')).toBeTruthy()
})

it('keeps a wrong-role account on the sign-in page and rejects an unrelated return path', async () => {
  auth.signIn.mockRejectedValueOnce(new Error('This account does not have a staff or driver grant.'))
  renderLogin('/admin')
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'citizen@example.com' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password123' } })
  await userEvent.click(screen.getByRole('button', { name: 'Sign in to staff dashboard' }))
  expect((await screen.findByRole('alert')).textContent).toContain('staff or driver grant')
  expect(screen.queryByText('Staff dashboard destination')).toBeNull()
  await userEvent.click(screen.getByRole('button', { name: 'Sign in to staff dashboard' }))
  expect(await screen.findByText('Staff dashboard destination')).toBeTruthy()
})

it('takes an already signed-in staff member to the dashboard', async () => {
  auth.role = 'staff'
  renderLogin()
  expect(await screen.findByText('Staff dashboard destination')).toBeTruthy()
  expect(auth.signIn).not.toHaveBeenCalled()
})
