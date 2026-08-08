export type WasteCategory =
  | 'household'
  | 'recyclable'
  | 'construction_debris'
  | 'other'

export type ReportStatus = 'processing' | 'in_progress' | 'completed'

export type UserRole = 'guest' | 'user' | 'admin'

export type ValidationStatus = 'pending' | 'valid' | 'invalid'

export interface UserProfile {
  id: string
  name: string
  email: string
  role: Exclude<UserRole, 'guest'>
  points: number
  title: string
  rank?: number
  validReports?: number
}

export interface Achievement {
  id: string
  name: string
  description: string
  pointsRequired: number
  title: string
}

export interface LeaderboardEntry {
  id: string
  name: string
  title: string
  points: number
  validReports: number
  isCurrentUser?: boolean
}

export interface ReportSummary {
  id: string
  reference: string
  category: WasteCategory
  location: string
  submittedAt: string
  status: ReportStatus
  confidence: number
  description: string
  reporter: string
  reporterRole: 'guest' | 'user'
  validationStatus: ValidationStatus
}
