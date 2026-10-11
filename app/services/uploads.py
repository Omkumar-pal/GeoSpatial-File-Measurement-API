"""Durable upload storage and synchronous processing orchestration."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import UploadTooLargeError
from app.services.archive import extract_shapefile_archive
from app.services.geospatial import ExtractedDataset, read_dataset

_CHUNK_SIZE = 1024 * 1024


async def save_upload(upload: UploadFile, destination: Path, max_upload_bytes: int) -> None:
    """Stream an incoming upload to an application-owned path with a hard size limit."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    received = 0
    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(_CHUNK_SIZE):
                received += len(chunk)
                if received > max_upload_bytes:
                    raise UploadTooLargeError(
                        f"The upload exceeds the {max_upload_bytes // (1024 * 1024)} MB limit."
                    )
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


def process_upload(stored_path: Path, file_type: str, workspace: Path, settings: Settings) -> ExtractedDataset:
    """Resolve an uploaded file to the dataset reader's concrete source path."""
    input_path = stored_path
    if file_type == "shapefile_zip":
        input_path = extract_shapefile_archive(stored_path, workspace / "extracted", settings).shapefile_path
    return read_dataset(input_path, file_type)
