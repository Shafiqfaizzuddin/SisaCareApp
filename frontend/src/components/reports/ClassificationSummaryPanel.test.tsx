// @vitest-environment happy-dom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { ClassificationSummaryPanel } from './ClassificationSummaryPanel'
import type { ClassificationSummary } from '../../types'

afterEach(cleanup)

it('labels detection shares and unavailable confidence separately from citizen and admin review', () => {
  const summary: ClassificationSummary = {
    version: '1.0.0', source: 'florence2_detections_plus_rules',
    denominator_definition: 'Non-background Florence detection observations, including Unknown.',
    total_detections: 3, background_excluded: 1, denominator: 2, unknown_count: 1,
    uncertain_count: 1,
    distribution: [{ category: 'Plastic', count: 1, percentage: 50 },
      { category: 'Unknown', count: 1, percentage: 50 }],
    dominant_category: 'Unknown', dominant_reason: 'The largest detection shares are tied.',
    severity: { level: 'Unknown', method: 'rule_based_handling_priority_v1',
      reason: 'The image leaves one item unresolved.', is_physical_measurement: false },
    confidence: { florence_detection_score: null, category_probability: null,
      explanation: 'No calibrated confidence is available.' }, limitations: [],
  }
  render(<ClassificationSummaryPanel summary={summary} />)
  expect(screen.getByText('Original photo analysis')).toBeDefined()
  expect(screen.getAllByText('1 / 2 · 50.0%')).toHaveLength(2)
  expect(screen.getByText(/detection shares, not confidence, mass, volume/)).toBeDefined()
  expect(screen.getByText(/Citizen corrections are recorded separately/)).toBeDefined()
  expect(screen.getByText(/No calibrated confidence is available/)).toBeDefined()
})
