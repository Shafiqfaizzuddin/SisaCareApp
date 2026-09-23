from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.waste_analysis import UPLOAD_DIR, router as waste_analysis_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.services.ai.image_annotator import ANNOTATED_OUTPUT_DIR

settings = get_settings()

app = FastAPI(title=settings.app_name)
app.include_router(api_router, prefix=settings.api_v1_prefix)
app.include_router(waste_analysis_router, prefix="/api/waste", tags=["waste-analysis"])

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ANNOTATED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/api/waste/uploads",
    StaticFiles(directory=UPLOAD_DIR),
    name="waste-uploads",
)
app.mount(
    "/api/waste/annotated",
    StaticFiles(directory=ANNOTATED_OUTPUT_DIR),
    name="waste-annotated",
)
