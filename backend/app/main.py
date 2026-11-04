import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.api.identity import router as identity_router
from app.api.members import router as members_router
from app.api.browser_session import router as browser_session_router
from app.api.reports import router as reports_router
from app.api.waste_analysis import router as waste_analysis_router
from app.api.florence_detection import router as florence_detection_router
from app.api.florence_analysis import router as florence_analysis_router
from app.api.recycling import router as recycling_router
from app.api.education import router as education_router
from app.api.v1.router import api_router
from app.core.config import PROJECT_ROOT, get_settings
from app.core.logging import configure_logging
from app.services.report_email import dispatch_pending_report_emails

settings = get_settings()
configure_logging(settings.log_level)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async def email_worker() -> None:
        while True:
            try:
                await asyncio.to_thread(dispatch_pending_report_emails)
            except Exception as exc:
                logger.warning("report_email_worker_failed error_type=%s", type(exc).__name__)
            await asyncio.sleep(60)

    worker = asyncio.create_task(email_worker())
    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)
app.include_router(browser_session_router, prefix="/api/auth", tags=["browser-session"])
app.include_router(identity_router, prefix="/api/identity", tags=["identity"])
app.include_router(members_router, prefix="/api/members", tags=["members"])
app.include_router(florence_analysis_router, prefix="/api/waste", tags=["waste-analysis"])
app.include_router(waste_analysis_router, prefix="/api/waste", tags=["legacy-waste-analysis"])
app.include_router(florence_detection_router, prefix="/api/waste/florence", tags=["florence-detection"])
app.include_router(recycling_router, prefix="/api/recycling", tags=["recycling"])
app.include_router(education_router, prefix="/api/education", tags=["education"])
app.include_router(reports_router, prefix="/api/reports", tags=["reports"])


class FrontendFiles(StaticFiles):
    """Serve the built SPA while preserving real 404s for API and asset URLs."""

    async def get_response(self, path: str, scope):
        requested_path = scope["path"].lstrip("/")
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            response = None
        if response is not None and response.status_code != 404:
            return response
        if (requested_path == "api" or requested_path.startswith("api/")
                or "." in requested_path.rsplit("/", 1)[-1]):
            if response is not None:
                return response
            raise HTTPException(status_code=404)
        return await super().get_response("index.html", scope)


if settings.serve_frontend:
    app.mount("/", FrontendFiles(directory=PROJECT_ROOT / "frontend" / "dist", html=True), name="frontend")
