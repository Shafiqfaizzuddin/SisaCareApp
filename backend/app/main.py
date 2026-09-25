from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.reports import router as reports_router
from app.api.waste_analysis import router as waste_analysis_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)
app.include_router(waste_analysis_router, prefix="/api/waste", tags=["waste-analysis"])
app.include_router(reports_router, prefix="/api/reports", tags=["reports"])
