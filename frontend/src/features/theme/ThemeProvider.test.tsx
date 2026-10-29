// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it } from 'vitest'
import { ThemeProvider } from './ThemeProvider'
import { ThemeToggle } from '../../components/common/ThemeToggle'

beforeEach(() => {
  window.localStorage.removeItem('sisacare-theme')
  delete document.documentElement.dataset.theme
})
afterEach(cleanup)

it('starts in light mode and saves a user-selected dark mode', () => {
  render(<ThemeProvider><ThemeToggle /></ThemeProvider>)
  expect(screen.getByRole('button', { name: 'Switch to dark mode' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }))
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(window.localStorage.getItem('sisacare-theme')).toBe('dark')
  expect(screen.getByRole('button', { name: 'Switch to light mode' })).toBeTruthy()
})

it('restores the saved preference on a later visit', () => {
  window.localStorage.setItem('sisacare-theme', 'dark')
  render(<ThemeProvider><ThemeToggle compact /></ThemeProvider>)
  expect(screen.getByRole('button', { name: 'Switch to light mode' })).toBeTruthy()
  expect(document.documentElement.dataset.theme).toBe('dark')
})
