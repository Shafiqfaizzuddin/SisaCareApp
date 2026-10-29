import { expect, it } from 'vitest'
import { displayInitials } from './display-initials'

it('keeps long names inside two-letter avatars', () => {
  expect(displayInitials('Test Administrator With A Very Long Name')).toBe('TN')
  expect(displayInitials('  Shafiq  ')).toBe('S')
})
