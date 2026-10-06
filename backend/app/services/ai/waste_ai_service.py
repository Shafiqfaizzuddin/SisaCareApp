"""Compatibility exports for the hybrid waste analysis service."""

from app.services.ai.hybrid_analysis_service import (
    AnalysisMode,
    AnalysisServiceError,
    HybridAnalysis,
    VlmAnalysisSummary,
    WasteAnalysisFailure,
    WasteAnalysisResponse,
    WasteAnalysisResult,
    YoloAnalysis,
    analyze_waste_image,
)


__all__ = [
    "AnalysisMode",
    "AnalysisServiceError",
    "HybridAnalysis",
    "VlmAnalysisSummary",
    "WasteAnalysisFailure",
    "WasteAnalysisResponse",
    "WasteAnalysisResult",
    "YoloAnalysis",
    "analyze_waste_image",
]
