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

export interface WasteBoundingBox {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface WasteDetection {
  class_name: string
  class_id: number
  confidence: number
  bounding_box: WasteBoundingBox
  display_name: string
  waste_category: string
  material: string
  recyclable: boolean
  recommended_handling: string
}

export interface WasteAnalysisReport {
  title: string
  summary: string
  waste_identified: string
  recommended_action: string
  environmental_concern: string
}

export interface WasteAnalysisSuccess {
  success: true
  original_image: string
  annotated_image: string
  detection: {
    total_objects: number
    counts: Record<string, number>
    detections: WasteDetection[]
  }
  report: WasteAnalysisReport
}

export interface WasteAnalysisFailure {
  success: false
  code: string
  message: string
  stage?: 'detection' | 'report_generation'
}

export type WasteAnalysisResponse = WasteAnalysisSuccess | WasteAnalysisFailure
