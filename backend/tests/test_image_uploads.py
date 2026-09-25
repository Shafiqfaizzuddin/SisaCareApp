import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile

from app.services.image_uploads import (
    UploadMetadataError,
    create_unique_upload_path,
    save_image_upload,
    validate_image_upload_metadata,
)


@pytest.mark.parametrize(
    ("filename", "content_type", "extension"),
    [
        ("waste.jpg", "image/jpeg", ".jpg"),
        ("waste.JPEG", "image/jpeg", ".jpg"),
        ("waste.png", "image/png", ".png"),
        ("waste.webp", "image/webp", ".webp"),
    ],
)
def test_supported_upload_metadata_returns_canonical_extension(
    filename: str,
    content_type: str,
    extension: str,
) -> None:
    assert validate_image_upload_metadata(filename, content_type) == extension


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("waste.svg", "image/svg+xml"),
        ("waste.exe", "image/png"),
        ("../waste.png", "image/png"),
        (r"..\waste.png", "image/png"),
        ("waste.jpg", "image/png"),
        (None, "image/png"),
    ],
)
def test_unsafe_or_inconsistent_upload_metadata_is_rejected(
    filename: str | None,
    content_type: str,
) -> None:
    with pytest.raises(UploadMetadataError):
        validate_image_upload_metadata(filename, content_type)


def test_server_upload_paths_are_unique_and_stay_inside_root(tmp_path: Path) -> None:
    first = create_unique_upload_path(
        tmp_path,
        prefix="upload",
        extension=".jpg",
    )
    second = create_unique_upload_path(
        tmp_path,
        prefix="upload",
        extension=".jpg",
    )

    assert first != second
    assert first.parent == tmp_path.resolve()
    assert second.parent == tmp_path.resolve()
    assert first.name.startswith("upload-")
    assert first.suffix == ".jpg"


def test_exclusive_upload_collision_does_not_delete_existing_file(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "upload-existing.jpg"
    destination.write_bytes(b"existing")
    upload = UploadFile(file=BytesIO(b"replacement"), filename="waste.jpg")

    with pytest.raises(FileExistsError):
        asyncio.run(save_image_upload(upload, destination))

    assert destination.read_bytes() == b"existing"
