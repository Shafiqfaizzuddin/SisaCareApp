from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.identity import router as identity_router
from app.api.members import router as members_router
from app.api.reports import router as reports_router
from app.api.waste_analysis import router as waste_analysis_router
from app.api.florence_detection import router as florence_detection_router
from app.api.florence_analysis import router as florence_analysis_router
from app.api.recycling import router as recycling_router
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
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)
app.include_router(identity_router, prefix="/api/identity", tags=["identity"])
app.include_router(members_router, prefix="/api/members", tags=["members"])
app.include_router(florence_analysis_router, prefix="/api/waste", tags=["waste-analysis"])
app.include_router(waste_analysis_router, prefix="/api/waste", tags=["legacy-waste-analysis"])
app.include_router(florence_detection_router, prefix="/api/waste/florence", tags=["florence-detection"])
app.include_router(recycling_router, prefix="/api/recycling", tags=["recycling"])
app.include_router(reports_router, prefix="/api/reports", tags=["reports"])
