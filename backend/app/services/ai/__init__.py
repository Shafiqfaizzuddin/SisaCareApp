"""AI waste analysis services."""

from app.services.ai.category_mapping import (
    WasteCategoryMetadata,
    get_category_metadata,
    reload_category_mapping,
)
from app.services.ai.ollama_report_generator import (
    ReportGenerationFailure,
    WasteReport,
    WasteReportResponse,
    generate_waste_report,
)
from app.services.ai.waste_ai_service import (
    AnalysisDetection,
    WasteAnalysisFailure,
    WasteAnalysisResponse,
    WasteAnalysisResult,
    analyze_waste_image,
)
from app.services.ai.yolo_detector import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DetectionFailure,
    WasteDetectionResponse,
    WasteDetectionResult,
    detect_waste,
)

__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "AnalysisDetection",
    "DetectionFailure",
    "ReportGenerationFailure",
    "WasteCategoryMetadata",
    "WasteAnalysisFailure",
    "WasteAnalysisResponse",
    "WasteAnalysisResult",
    "WasteDetectionResponse",
    "WasteDetectionResult",
    "WasteReport",
    "WasteReportResponse",
    "analyze_waste_image",
    "detect_waste",
    "generate_waste_report",
    "get_category_metadata",
    "reload_category_mapping",
]
