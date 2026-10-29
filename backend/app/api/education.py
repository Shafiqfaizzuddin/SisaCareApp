"""Public learning content and administrator-only editing."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from app.core.auth import AuthenticatedUser, require_admin_user
from app.core.config import get_settings
from app.repositories import education
from app.services.ai.image_validation import ImageValidationError, validate_image
from app.services.image_uploads import (
    UploadMetadataError, create_unique_upload_path, save_image_upload,
    validate_image_upload_metadata,
)

router = APIRouter()
IMAGE_LIMIT = 5 * 1024 * 1024
IMAGE_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class ArticleInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=6000)
    image_alt: str = Field(default="", max_length=250)
    published: bool = True
    sort_order: int = Field(default=0, ge=0, le=10000)

    @field_validator("title", "summary", "body", "image_alt")
    @classmethod
    def trim(cls, value: str) -> str:
        return value.strip()

    @field_validator("title", "summary", "body")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value:
            raise ValueError("This field cannot be blank.")
        return value


def _image_dir() -> Path:
    return get_settings().report_assets_dir / "education"


@router.get("/articles")
async def public_articles() -> list[dict[str, object]]:
    return await run_in_threadpool(education.list_articles, published_only=True)


@router.get("/admin/articles")
async def admin_articles(
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> list[dict[str, object]]:
    return await run_in_threadpool(education.list_articles, published_only=False)


@router.post("/admin/articles", status_code=201)
async def create_article(
    article: ArticleInput,
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> dict[str, object]:
    result = await run_in_threadpool(education.save_article, article.model_dump())
    assert result is not None
    return result


@router.put("/admin/articles/{article_id}")
async def update_article(
    article_id: str,
    article: ArticleInput,
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> dict[str, object]:
    result = await run_in_threadpool(education.save_article, article.model_dump(), article_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Article not found.")
    return result


@router.post("/admin/articles/{article_id}/image")
async def upload_article_image(
    article_id: str,
    image: UploadFile = File(...),
    _admin: AuthenticatedUser = Depends(require_admin_user),
) -> dict[str, object]:
    if await run_in_threadpool(education.get_article, article_id) is None:
        await image.close()
        raise HTTPException(status_code=404, detail="Article not found.")
    try:
        extension = validate_image_upload_metadata(image.filename, image.content_type)
    except UploadMetadataError as exc:
        await image.close()
        raise HTTPException(status_code=415, detail="Use a JPG, PNG or WEBP image with a matching filename.") from exc
    destination = create_unique_upload_path(_image_dir(), prefix="learn", extension=extension)
    try:
        await save_image_upload(image, destination, max_size=IMAGE_LIMIT)
        await run_in_threadpool(validate_image, destination)
        # Old images are retained on disk for audit and rollback.
        await run_in_threadpool(education.set_image, article_id, destination.name,
                                (await run_in_threadpool(education.get_article, article_id))["image_alt"])
    except (ValueError, ImageValidationError) as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=413 if str(exc) == "IMAGE_TOO_LARGE" else 400,
                            detail="The image must be a valid JPG, PNG or WEBP file of at most 5 MB.") from exc
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return {"image_url": f"/api/education/articles/{article_id}/image"}


@router.post("/admin/articles/{article_id}/image/remove")
async def remove_article_image(
    article_id: str,
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> dict[str, object]:
    try:
        await run_in_threadpool(education.set_image, article_id, None, "")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Article not found.") from exc
    return {"image_url": None}


@router.get("/articles/{article_id}/image")
async def article_image(article_id: str) -> FileResponse:
    article = await run_in_threadpool(education.get_article, article_id)
    if article is None or not article["published"] or not article["image_filename"]:
        raise HTTPException(status_code=404, detail="Image not found.")
    return _image_response(article["image_filename"])


@router.get("/admin/articles/{article_id}/image")
async def admin_article_image(
    article_id: str,
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> FileResponse:
    article = await run_in_threadpool(education.get_article, article_id)
    if article is None or not article["image_filename"]:
        raise HTTPException(status_code=404, detail="Image not found.")
    return _image_response(article["image_filename"])


def _image_response(filename: str) -> FileResponse:
    path = (_image_dir() / filename).resolve()
    if path.parent != _image_dir().resolve() or path.suffix.lower() not in IMAGE_TYPES or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(path, media_type=IMAGE_TYPES[path.suffix.lower()], headers={"Cache-Control": "no-store"})
