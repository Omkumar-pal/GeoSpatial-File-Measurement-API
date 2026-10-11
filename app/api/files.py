"""Endpoints for geospatial uploads and measurement retrieval."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.core.errors import AppError
from app.db.models import FeatureMeasurement, ProcessingStatus, UploadedFile
from app.schemas import FileResponse, MeasurementResponse, MeasurementsResponse
from app.services.archive import classify_upload, safe_upload_name
from app.services.uploads import process_upload, save_upload

router = APIRouter(prefix="/api/files", tags=["files"])
logger = logging.getLogger(__name__)


@router.post("/", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(..., description="A .kml or .zip containing one Shapefile."),
    session: Session = Depends(get_db_session),
) -> FileResponse:
    """Store, validate, and synchronously process a geospatial upload."""
    file_type = classify_upload(file.filename)
    filename = safe_upload_name(file.filename, "upload")
    uploaded_file = UploadedFile(
        original_filename=filename,
        stored_path="",
        file_type=file_type,
        status=ProcessingStatus.PROCESSING.value,
    )
    session.add(uploaded_file)
    session.flush()

    workspace = request.app.state.settings.upload_dir / uploaded_file.id
    stored_path = workspace / filename
    uploaded_file.stored_path = str(stored_path)

    try:
        await save_upload(file, stored_path, request.app.state.settings.max_upload_bytes)
        dataset = process_upload(stored_path, file_type, workspace, request.app.state.settings)
        uploaded_file.source_crs = dataset.source_crs
        uploaded_file.feature_count = len(dataset.features)
        uploaded_file.status = ProcessingStatus.COMPLETED.value
        uploaded_file.completed_at = datetime.now(timezone.utc)
        for feature in dataset.features:
            session.add(
                FeatureMeasurement(
                    uploaded_file_id=uploaded_file.id,
                    feature_index=feature.feature_index,
                    source_feature_id=feature.source_feature_id,
                    geometry_type=feature.geometry_type,
                    geometry=feature.geometry,
                    properties=feature.properties,
                    source_crs=feature.source_crs,
                    measurement_crs=feature.measurement_crs,
                    area_sqm=feature.area_sqm,
                    length_m=feature.length_m,
                    warning=feature.warning,
                )
            )
        session.commit()
    except AppError as exc:
        _mark_failed(session, uploaded_file, exc.message)
        raise
    except Exception as exc:
        logger.exception("Unexpected failure while processing upload %s", uploaded_file.id)
        _mark_failed(session, uploaded_file, "Unexpected error while processing the geospatial file.")
        raise HTTPException(status_code=500, detail="Unexpected error while processing the file.") from exc

    return _file_response(uploaded_file)


@router.get("/{file_id}/", response_model=FileResponse)
def get_file(file_id: str, session: Session = Depends(get_db_session)) -> FileResponse:
    """Return upload status and high-level metadata."""
    return _file_response(_get_file_or_404(session, file_id))


@router.get("/{file_id}/measurements/", response_model=MeasurementsResponse)
def get_measurements(file_id: str, session: Session = Depends(get_db_session)) -> MeasurementsResponse:
    """Return the normalized source geometry and results for every feature."""
    uploaded_file = _get_file_or_404(session, file_id)
    features = session.scalars(
        select(FeatureMeasurement)
        .where(FeatureMeasurement.uploaded_file_id == file_id)
        .order_by(FeatureMeasurement.feature_index)
    ).all()
    return MeasurementsResponse(
        file_id=uploaded_file.id,
        feature_count=uploaded_file.feature_count,
        measurements=[_measurement_response(feature) for feature in features],
    )


def _mark_failed(session: Session, uploaded_file: UploadedFile, error_message: str) -> None:
    uploaded_file.status = ProcessingStatus.FAILED.value
    uploaded_file.error_message = error_message
    uploaded_file.completed_at = datetime.now(timezone.utc)
    session.commit()


def _get_file_or_404(session: Session, file_id: str) -> UploadedFile:
    uploaded_file = session.get(UploadedFile, file_id)
    if uploaded_file is None:
        raise HTTPException(status_code=404, detail="Uploaded file was not found.")
    return uploaded_file


def _file_response(uploaded_file: UploadedFile) -> FileResponse:
    return FileResponse(
        id=uploaded_file.id,
        filename=uploaded_file.original_filename,
        file_type=uploaded_file.file_type,
        feature_count=uploaded_file.feature_count,
        crs=uploaded_file.source_crs,
        status=uploaded_file.status,
        error_message=uploaded_file.error_message,
        created_at=uploaded_file.created_at,
        completed_at=uploaded_file.completed_at,
    )


def _measurement_response(feature: FeatureMeasurement) -> MeasurementResponse:
    return MeasurementResponse(
        feature_index=feature.feature_index,
        feature_id=feature.source_feature_id,
        geometry_type=feature.geometry_type,
        geometry=feature.geometry,
        properties=feature.properties,
        source_crs=feature.source_crs,
        measurement_crs=feature.measurement_crs,
        area_sqm=feature.area_sqm,
        length_m=feature.length_m,
        warning=feature.warning,
    )
