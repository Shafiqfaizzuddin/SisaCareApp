// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const { signIn, signInWithGoogle, refreshMemberData } = vi.hoisted(() => ({
  signIn: vi.fn(), signInWithGoogle: vi.fn(), refreshMemberData: vi.fn(),
}))
vi.mock('../features/authentication/useRole', () => ({
  useRole: () => ({ signIn, refreshMemberData }),
}))
vi.mock('../features/authentication/google', () => ({ signInWithGoogle }))
vi.mock('../components/common/GoogleIdentityButton', () => ({
  GoogleIdentityButton: ({ onCredential, disabled }: { onCredential: (token: string) => Promise<void>; disabled: boolean }) => (
    <button type="button" disabled={disabled} onClick={() => void onCredential('test-google-token')}>
      Continue with Google
    </button>
  ),
}))
vi.mock('../lib/supabase', () => ({ supabaseClient: null }))

import { UserLoginPage } from './UserLoginPage'

function renderLogin(returnTo = '/account') {
  render(<MemoryRouter initialEntries={[{ pathname: '/login', state: { returnTo } }]}>
    <Routes>
      <Route path="/login" element={<UserLoginPage />} />
      <Route path="/account" element={<p>Account destination</p>} />
      <Route path="/report" element={<p>Report destination</p>} />
    </Routes>
  </MemoryRouter>)
}

beforeEach(() => {
  vi.clearAllMocks()
  signIn.mockResolvedValue(undefined)
  signInWithGoogle.mockResolvedValue(undefined)
})

afterEach(() => cleanup())

it('shows the requested form order and an accessible password toggle', () => {
  renderLogin()
  expect(screen.getByRole('heading', { name: 'Sign in to SisaCare.AI' })).toBeTruthy()
  const google = screen.getByRole('button', { name: 'Continue with Google' })
  const email = screen.getByLabelText('Email')
  const password = screen.getByLabelText('Password') as HTMLInputElement
  expect(google.compareDocumentPosition(email) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(email.getAttribute('autocomplete')).toBe('email')
  expect(password.getAttribute('autocomplete')).toBe('current-password')
  expect(password.type).toBe('password')
  fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
  expect(password.type).toBe('text')
  expect(screen.getByRole('button', { name: 'Hide password' }).getAttribute('aria-pressed')).toBe('true')
  expect(screen.getByRole('link', { name: 'Forgot password?' }).getAttribute('href')).toBe('/password-reset')
  expect(screen.getByRole('link', { name: 'Create a SisaCare account' }).getAttribute('href')).toBe('/signup')
})

it('supports keyboard navigation and password visibility control', async () => {
  const user = userEvent.setup()
  renderLogin()
  await user.tab()
  expect(document.activeElement).toBe(screen.getByRole('link', { name: 'SisaCare.AI home' }))
  await user.tab()
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Continue with Google' }))
  await user.tab()
  expect(document.activeElement).toBe(screen.getByLabelText('Email'))
  await user.tab()
  expect(document.activeElement).toBe(screen.getByLabelText('Password'))
  await user.tab()
  const toggle = screen.getByRole('button', { name: 'Show password' })
  expect(document.activeElement).toBe(toggle)
  await user.keyboard('{Enter}')
  expect((screen.getByLabelText('Password') as HTMLInputElement).type).toBe('text')
})

it('prevents repeat password submissions and returns to the intended page', async () => {
  let resolveSignIn: (() => void) | undefined
  signIn.mockReturnValue(new Promise<void>((resolve) => { resolveSignIn = resolve }))
  renderLogin('/report')
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'student@example.com' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret123' } })
  const submit = screen.getByRole('button', { name: 'Sign in' })
  const form = submit.closest('form')!
  fireEvent.submit(form)
  fireEvent.submit(form)
  expect(signIn).toHaveBeenCalledTimes(1)
  expect(submit.hasAttribute('disabled')).toBe(true)
  resolveSignIn?.()
  await waitFor(() => expect(screen.getByText('Report destination')).toBeTruthy())
})

it('routes verified Google sign-in to the same participant destination', async () => {
  renderLogin('/report')
  fireEvent.click(screen.getByRole('button', { name: 'Continue with Google' }))
  await waitFor(() => expect(screen.getByText('Report destination')).toBeTruthy())
  expect(signInWithGoogle).toHaveBeenCalledWith('test-google-token')
})
