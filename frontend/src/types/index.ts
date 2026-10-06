export type WasteCategory =
  | 'household'
  | 'recyclable'
  | 'construction_debris'
  | 'other'

export type ReportStatus = 'processing' | 'in_progress' | 'completed'

export type UserRole = 'guest' | 'user' | 'admin'

export type ValidationStatus = 'pending' | 'valid' | 'invalid'

export type LocationSource = 'gps' | 'map' | 'search'

export interface ReportLocation {
  latitude: number
  longitude: number
  address: string
  street: string | null
  city: string | null
  state: string | null
  postcode: string | null
  country: string | null
  source: LocationSource
}

export interface LocationSearchResult extends Omit<ReportLocation, 'source'> {
  id: string
  label: string
}

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
  source: 'yolo'
}

export type FinalWasteCategory =
  | 'Non-Recyclable'
  | 'Recyclable Waste'
  | 'Bulky Waste'
  | 'Unknown'

export interface VlmWasteObject {
  name: string
  display_name: string
  suggested_category: FinalWasteCategory
  confidence_level: 'high' | 'medium' | 'low'
  reason: string
}

export interface FusedWasteObject {
  name: string
  display_name: string
  category: FinalWasteCategory
  category_source: 'mapping' | 'vlm' | 'unknown'
  source: 'yolo' | 'vlm' | 'yolo+vlm'
  confidence: number | null
  confidence_level: 'high' | 'medium' | 'low' | null
  supported_by_vlm: boolean
  bounding_box: WasteBoundingBox | null
}

export interface GroupedWasteObject {
  name: string
  label: string
  count: number | null
  category: FinalWasteCategory
  sources: Array<'yolo' | 'vlm'>
  average_yolo_confidence: number | null
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
  analysis_id: string
  original_image: string
  annotated_image: string | null
  detections: FusedWasteObject[]
  grouped_objects: GroupedWasteObject[]
  categories_detected: FinalWasteCategory[]
  scene_description: string
  report: WasteAnalysisReport
}

export interface WasteAnalysisFailure {
  success: false
  code: string
  message: string
  stage?: 'validation' | 'analysis' | 'detection' | 'report_generation'
}

export type WasteAnalysisResponse = WasteAnalysisSuccess | WasteAnalysisFailure

export interface ReportSubmissionPayload {
  analysis_id?: string
  reporter_role: 'guest' | 'user'
  user_id?: string
  guest_name?: string
  guest_email?: string
  title: string
  summary: string
  waste_identified: string
  recommended_action: string
  environmental_concern: string
  category: WasteCategory
  location: string
  latitude: number
  longitude: number
  location_address?: string
  location_street?: string
  location_city?: string
  location_state?: string
  location_postcode?: string
  location_country?: string
  location_source: LocationSource
  site_notes: string
}

export interface ReportSubmissionResult {
  id: string
  reference: string
  status: ReportStatus
  submitted_at: string
  original_image: string
  annotated_image: string
}

export interface AdminWasteDetection {
  id: string
  className: string
  displayName: string
  wasteCategory: string
  material: string
  confidence: number | null
  boundingBox: WasteBoundingBox | null
  source: 'yolo' | 'vlm' | 'yolo+vlm'
  createdAt: string
}

export interface AdminReportDetail {
  id: string
  reference: string
  category: WasteCategory
  location: string
  reportLocation: ReportLocation | null
  siteNotes: string
  status: ReportStatus
  validationStatus: ValidationStatus
  rewardPoints: number
  reporterRole: 'guest' | 'user'
  reporter: string
  title: string
  summary: string
  wasteIdentified: string
  recommendedAction: string
  environmentalConcern: string
  generatedReport: WasteAnalysisReport | null
  finalCategories: FinalWasteCategory[]
  aiAnalysis: Record<string, unknown> | null
  originalImage: string
  annotatedImage: string
  createdAt: string
  updatedAt: string
  detections: AdminWasteDetection[]
}

export interface ReportValidationResult {
  reportId: string
  validationStatus: Exclude<ValidationStatus, 'pending'>
  status: ReportStatus
  rewardAwarded: boolean
  rewardPoints: number
}

export interface MemberReportSummary {
  id: string
  reference: string
  location: string
  submittedAt: string
  status: ReportStatus
  validationStatus: ValidationStatus
}

export interface MemberDashboardData {
  points: number
  validReports: number
  rank?: number
  reports: MemberReportSummary[]
}
