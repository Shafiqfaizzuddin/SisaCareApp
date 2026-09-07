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
  criteriaType?: 'points' | 'valid_reports'
  criteriaValue?: number
  bonusPoints?: number
  unlocked?: boolean
}

export interface LeaderboardEntry {
  id: string
  name: string
  title: string
  points: number
  validReports: number
  isCurrentUser?: boolean
}

export interface CommunityImpact {
  totalPoints: number
  verifiedReports: number
  casesResolved: number
  locationsCurrentlyHandled: number
  achievementsUnlocked: number
  currentTitle: string
  unreadImpactNotifications: number
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
  reporterEmail?: string
  userId?: string
  imagePath?: string
  latitude?: number
  longitude?: number
  generatedReport?: string
  riskLevel?: string
  modelName?: string
  statusHistory?: ReportStatusHistoryEntry[]
  validations?: ReportValidationEntry[]
}

export interface ReportStatusHistoryEntry {
  id: string
  previousStatus: ReportStatus
  newStatus: ReportStatus
  note?: string
  changedAt: string
  changedBy: string
}

export interface ReportValidationEntry {
  id: string
  status: Exclude<ValidationStatus, 'pending'>
  note?: string
  validatedAt: string
  adminName: string
}

export interface RewardTransaction {
  id: string
  points: number
  description: string
  awardedAt: string
  reportId?: string
  rewardType: string
}

export interface TitleDefinition {
  id: string
  name: string
  description: string
  minimumPoints: number
}

export interface EducationalContent {
  id: string
  title: string
  content: string
  category: WasteCategory
  imageUrl?: string
  status: 'draft' | 'published'
  publishedAt?: string
  createdAt: string
  updatedAt: string
}
