// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const { signUp, resend } = vi.hoisted(() => ({ signUp: vi.fn(), resend: vi.fn() }))
vi.mock('../features/authentication/useRole', () => ({ useRole: () => ({ signUp }) }))
vi.mock('../lib/supabase', () => ({ supabaseClient: { auth: { resend } } }))
vi.mock('../features/theme/useTheme', () => ({ useTheme: () => ({ theme: 'light', toggleTheme: () => {} }) }))

import { UserSignupPage } from './UserSignupPage'

beforeEach(() => {
  vi.clearAllMocks()
  signUp.mockResolvedValue({ requiresEmailConfirmation: true })
  resend.mockResolvedValue({ error: null })
})
afterEach(() => cleanup())

it('keeps the responsive signup grid and shows verification with a resend action', async () => {
  render(<MemoryRouter initialEntries={['/signup']}><Routes>
    <Route path="/signup" element={<UserSignupPage />} />
    <Route path="/account" element={<p>Account destination</p>} />
  </Routes></MemoryRouter>)
  expect(document.querySelector('main')?.classList.contains('member-login-page')).toBe(false)
  expect(document.querySelector('main')?.classList.contains('signup-page')).toBe(true)
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Community Resident' } })
  fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'resident@gmail.com' } })
  fireEvent.change(screen.getByLabelText('Password', { exact: true }), { target: { value: 'password123' } })
  fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'password123' } })
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
  await waitFor(() => expect(screen.getByRole('status').textContent).toContain('resident@gmail.com'))
  expect(signUp).toHaveBeenCalledWith('Community Resident', 'resident@gmail.com', 'password123')
  fireEvent.click(screen.getByRole('button', { name: 'Resend verification email' }))
  await waitFor(() => expect(resend).toHaveBeenCalledWith({ type: 'signup', email: 'resident@gmail.com',
    options: { emailRedirectTo: `${window.location.origin}/login` } }))
})
