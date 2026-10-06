// @vitest-environment happy-dom

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { TomTomMap } from './TomTomMap'


afterEach(cleanup)

describe('TomTomMap', () => {
  it('shows a configuration message instead of crashing without an API key', () => {
    render(<TomTomMap location={null} apiKey="" />)

    expect(screen.getByRole('alert').textContent).toContain(
      'VITE_TOMTOM_API_KEY',
    )
  })
})
