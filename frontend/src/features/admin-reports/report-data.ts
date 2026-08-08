import type { ReportSummary } from '../../types'

export const reportSummaries: ReportSummary[] = [
  {
    id: 'rpt-1048',
    reference: 'SCA-1048',
    category: 'construction_debris',
    location: 'Jalan Tasik Selatan 8, Kuala Lumpur',
    submittedAt: '8 Aug 2026, 09:42',
    status: 'processing',
    confidence: 94,
    description:
      'Broken concrete, timber, and several bags of renovation waste left beside the service road.',
    reporter: 'Aiman Rahman',
    reporterRole: 'user',
    validationStatus: 'pending',
  },
  {
    id: 'rpt-1047',
    reference: 'SCA-1047',
    category: 'household',
    location: 'Persiaran Setia Alam, Shah Alam',
    submittedAt: '8 Aug 2026, 08:15',
    status: 'in_progress',
    confidence: 88,
    description:
      'Discarded sofa, mattress, and mixed household rubbish blocking part of the pedestrian path.',
    reporter: 'Nur A.',
    reporterRole: 'user',
    validationStatus: 'valid',
  },
  {
    id: 'rpt-1046',
    reference: 'SCA-1046',
    category: 'recyclable',
    location: 'Lorong Sentosa 3, Klang',
    submittedAt: '7 Aug 2026, 17:26',
    status: 'completed',
    confidence: 91,
    description:
      'Large pile of cardboard boxes and plastic packaging beside the communal bins.',
    reporter: 'Public submission',
    reporterRole: 'guest',
    validationStatus: 'valid',
  },
  {
    id: 'rpt-1045',
    reference: 'SCA-1045',
    category: 'other',
    location: 'Jalan PJU 1A/4, Petaling Jaya',
    submittedAt: '7 Aug 2026, 14:03',
    status: 'in_progress',
    confidence: 72,
    description:
      'Unidentified bags and containers placed near the drainage reserve.',
    reporter: 'Public submission',
    reporterRole: 'guest',
    validationStatus: 'pending',
  },
]
