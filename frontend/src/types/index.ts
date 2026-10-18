export type WasteCategory =
  | 'household'
  | 'recyclable'
  | 'construction_debris'
  | 'other'
  | 'Recyclable Waste'
  | 'Non-Recyclable Waste'
  | 'Bulky Waste'
  | 'Hazardous Waste'
  | 'Needs Confirmation'

export type CampusWasteCategory = 'Recyclable Waste' | 'Non-Recyclable Waste' | 'Bulky Waste' | 'Hazardous Waste'
export type ReportWasteCategory = CampusWasteCategory | 'Needs Confirmation'

export type ReportStatus = 'submitted' | 'verified' | 'in_progress' | 'resolved' | 'rejected' | 'processing' | 'completed'

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
  addressSource?: 'google' | 'manual' | 'coordinates'
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
  confidence: number | null
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

export type DetectionReviewStatus = 'likely_waste' | 'background' | 'needs_confirmation'

export interface FlorenceDetection {
  id: string
  label: string
    original_label?: string
  name: string
    canonical_name?: string
  display_name: string
  bounding_box: WasteBoundingBox
  confidence: null
  review_status: DetectionReviewStatus
  suggested_category: CampusWasteCategory | null
    waste_category?: CampusWasteCategory | null
    needs_confirmation?: boolean
    confirmation_question?: string | null
    classification_source?: 'rule' | 'user_confirmed'
  material: string
  recommended_handling: string
  confirmation_reason?: string | null
  questions?: Array<{ key: string; prompt: string }>
  station_material_key?: string | null
    rule_id?: string | null
  bulky?: boolean
}

export interface FlorenceAnalysisSuccess {
  success: true
  analysis_id: string
  original_image: string
  display_image: string | null
  image_width: number
  image_height: number
  provider: 'florence2'
  model_id: string
  model_revision: string
  detections: FlorenceDetection[]
  processing_time_ms: number
  warnings: string[]
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
  | 'Non-Recyclable Waste'
  | 'Recyclable Waste'
  | 'Bulky Waste'
  | 'Hazardous Waste'
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
  source: 'yolo' | 'vlm' | 'yolo+vlm' | 'florence2'
  confidence: number | null
  confidence_level: 'high' | 'medium' | 'low' | null
  supported_by_vlm: boolean
  bounding_box: WasteBoundingBox | null
  material?: string
  recyclable?: boolean
  recommended_handling?: string
  rule_known?: boolean
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
  rule_version?: '1.0.0' | '1.1.0' | '1.2.0'
  reporter_role: 'guest' | 'user'
  user_id?: string
  guest_name?: string
  guest_email?: string
  title: string
  summary: string
  waste_identified: string
  recommended_action: string
  environmental_concern: string
  category: ReportWasteCategory
  draft_source?: 'ollama' | 'template' | 'user'
  draft_model_id?: string | null
  user_edited_fields?: Array<keyof WasteAnalysisReport>
  confirmed_items: Array<{ review_id?: string; name: string; category: CampusWasteCategory | null; material: string; quantity?: number; condition_answers?: Record<string, boolean> }>
  split_recycling_review_ids?: string[]
  reviewed_detections?: Array<{ id: string; source_detection_id: string | null; disposition: 'waste' | 'background' | 'removed' | 'attached_component' | 'needs_confirmation'; corrected_label: string; material: string; category: CampusWasteCategory | null; quantity?: number; condition_answers: Record<string, boolean>; component_relation: 'attached' | 'detached' | 'unclear' | null }>
  location: string
  latitude: number
  longitude: number
  location_address?: string
  location_address_source?: 'google' | 'manual' | 'coordinates'
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
  source: 'yolo' | 'vlm' | 'yolo+vlm' | 'florence2'
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
  assignedTeam?: string | null
  resolutionDetails?: string | null
  afterPhoto?: string | null
  statusEvents?: Array<{ previousStatus: string; newStatus: string; reason: string | null; assignedTeam: string | null; resolutionDetails: string | null; createdAt: string }>
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
  confirmedItems: Array<{ name: string; category: CampusWasteCategory | null; material: string; classification_source?: 'rule' | 'user_confirmed' }>
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
