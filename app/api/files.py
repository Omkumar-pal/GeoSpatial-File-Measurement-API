"""Endpoints for geospatial uploads and measurement retrieval."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.core.errors import AppError
from app.db.models import FeatureMeasurement, ProcessingStatus, UploadedFile
from app.schemas import (
    FeatureResponse,
    FeaturesResponse,
    FileLinks,
    FileResponse,
    Measurement,
    MeasurementResponse,
    MeasurementsResponse,
    MeasurementSummary,
)
from app.services.archive import classify_upload, safe_upload_name
from app.services.uploads import process_upload, save_upload

router = APIRouter(prefix="/api/files", tags=["files"])
logger = logging.getLogger(__name__)
UploadField = Annotated[
    UploadFile,
    File(..., description="A .kml or .zip containing one Shapefile."),
]
DatabaseSession = Annotated[Session, Depends(get_db_session)]
MeasurementMethodParam = Annotated[
    Literal["auto", "projected", "geodesic"],
    Query(
        description=(
            "Backend measurement strategy. auto projects compact local features "
            "and uses a geodesic fallback for large/global features."
        ),
    ),
]
PageLimit = Annotated[int, Query(ge=1, le=100, description="Maximum items to return.")]
PageOffset = Annotated[int, Query(ge=0, description="Number of items to skip.")]
IncludeOptions = Annotated[
    list[str] | None,
    Query(
        description=(
            "Optional detail sections: geometry and/or properties. Comma-separated values work."
        ),
    ),
]

_DISPLAY_ATTRIBUTES = ("NAME_EN", "ISO_A3", "CONTINENT")
_GEODESIC_ACCURACY_NOTE = (
    "Ellipsoidal area on WGS 84; accuracy is limited by the source geometry and is not "
    "a legal or official statistical boundary claim."
)
_PROJECTED_ACCURACY_NOTE = "Measured in a feature-local projected CRS suitable for local use."


@router.post("/", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadField,
    session: DatabaseSession,
    measurement_method: MeasurementMethodParam = "auto",
) -> FileResponse:
    """Store, validate, and synchronously process a geospatial upload."""
    file_type = classify_upload(file.filename)
    filename = safe_upload_name(file.filename, "upload")
    uploaded_file = UploadedFile(
        original_filename=filename,
        stored_path="",
        file_type=file_type,
        status=ProcessingStatus.PROCESSING.value,
        measurement_method=measurement_method,
    )
    session.add(uploaded_file)
    session.flush()

    workspace = request.app.state.settings.upload_dir / uploaded_file.id
    stored_path = workspace / filename
    uploaded_file.stored_path = str(stored_path)

    try:
        await save_upload(file, stored_path, request.app.state.settings.max_upload_bytes)
        dataset = process_upload(
            stored_path, file_type, workspace, request.app.state.settings, measurement_method
        )
        uploaded_file.source_crs = dataset.source_crs
        uploaded_file.feature_count = len(dataset.features)
        uploaded_file.status = ProcessingStatus.COMPLETED.value
        uploaded_file.completed_at = datetime.now(UTC)
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
                    measurement_method=feature.measurement_method,
                    accuracy_note=feature.accuracy_note,
                )
            )
        session.commit()
    except AppError as exc:
        _mark_failed(session, uploaded_file, exc.message)
        raise
    except Exception as exc:
        logger.exception("Unexpected failure while processing upload %s", uploaded_file.id)
        _mark_failed(
            session,
            uploaded_file,
            "Unexpected error while processing the geospatial file.",
        )
        raise HTTPException(
            status_code=500,
            detail="Unexpected error while processing the file.",
        ) from exc

    return _file_response(session, uploaded_file)


@router.get("/{file_id}/", response_model=FileResponse)
def get_file(file_id: str, session: DatabaseSession) -> FileResponse:
    """Return upload status and high-level metadata."""
    return _file_response(session, _get_file_or_404(session, file_id))


@router.get(
    "/{file_id}/measurements",
    response_model=MeasurementsResponse,
    response_model_exclude_none=True,
)
def get_measurements(
    file_id: str,
    session: DatabaseSession,
    limit: PageLimit = 25,
    offset: PageOffset = 0,
    include: IncludeOptions = None,
) -> MeasurementsResponse:
    """Return compact, paginated feature measurements."""
    _get_file_or_404(session, file_id)
    includes = _parse_includes(include)
    features = session.scalars(
        select(FeatureMeasurement)
        .where(FeatureMeasurement.uploaded_file_id == file_id)
        .order_by(FeatureMeasurement.feature_index)
        .offset(offset)
        .limit(limit)
    ).all()
    return MeasurementsResponse(
        items=[_measurement_response(feature, includes) for feature in features],
        limit=limit,
        offset=offset,
        total=_feature_total(session, file_id),
    )


@router.get(
    "/{file_id}/features",
    response_model=FeaturesResponse,
    response_model_exclude_none=True,
)
def get_features(
    file_id: str,
    session: DatabaseSession,
    limit: PageLimit = 25,
    offset: PageOffset = 0,
    include: IncludeOptions = None,
) -> FeaturesResponse:
    """Return compact source-feature metadata, with raw data on explicit request."""
    _get_file_or_404(session, file_id)
    includes = _parse_includes(include)
    features = session.scalars(
        select(FeatureMeasurement)
        .where(FeatureMeasurement.uploaded_file_id == file_id)
        .order_by(FeatureMeasurement.feature_index)
        .offset(offset)
        .limit(limit)
    ).all()
    return FeaturesResponse(
        items=[_feature_response(feature, includes) for feature in features],
        limit=limit,
        offset=offset,
        total=_feature_total(session, file_id),
    )


@router.get(
    "/{file_id}/features/{feature_id}",
    response_model=FeatureResponse,
    response_model_exclude_none=True,
)
def get_feature(file_id: str, feature_id: str, session: DatabaseSession) -> FeatureResponse:
    """Return one feature's complete source data by its stable source or persisted ID."""
    _get_file_or_404(session, file_id)
    feature = session.scalar(
        select(FeatureMeasurement).where(
            FeatureMeasurement.uploaded_file_id == file_id,
            FeatureMeasurement.source_feature_id == feature_id,
        )
    )
    if feature is None:
        persisted_feature = session.get(FeatureMeasurement, feature_id)
        if persisted_feature is not None and persisted_feature.uploaded_file_id == file_id:
            feature = persisted_feature
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature was not found in this upload.")
    return _feature_response(feature, {"geometry", "properties"})


def _mark_failed(session: Session, uploaded_file: UploadedFile, error_message: str) -> None:
    uploaded_file.status = ProcessingStatus.FAILED.value
    uploaded_file.error_message = error_message
    uploaded_file.completed_at = datetime.now(UTC)
    session.commit()


def _get_file_or_404(session: Session, file_id: str) -> UploadedFile:
    uploaded_file = session.get(UploadedFile, file_id)
    if uploaded_file is None:
        raise HTTPException(status_code=404, detail="Uploaded file was not found.")
    return uploaded_file


def _file_response(session: Session, uploaded_file: UploadedFile) -> FileResponse:
    requested = getattr(uploaded_file, "measurement_method", "auto") or "auto"
    if requested not in ("auto", "projected", "geodesic"):
        requested = "auto"
    return FileResponse(
        id=uploaded_file.id,
        filename=uploaded_file.original_filename,
        source_crs=uploaded_file.source_crs,
        feature_count=uploaded_file.feature_count,
        measurement_method=requested,  # type: ignore[arg-type]
        summary=_measurement_summary(session, uploaded_file.id),
        links=FileLinks(
            measurements=f"/api/files/{uploaded_file.id}/measurements?limit=25",
            features=f"/api/files/{uploaded_file.id}/features",
        ),
        file_type=uploaded_file.file_type,
        status=uploaded_file.status,
        error_message=uploaded_file.error_message,
        created_at=uploaded_file.created_at,
        completed_at=uploaded_file.completed_at,
    )


def _measurement_summary(session: Session, file_id: str) -> MeasurementSummary:
    rows = session.execute(
        select(
            FeatureMeasurement.area_sqm,
            FeatureMeasurement.length_m,
            FeatureMeasurement.measurement_method,
            FeatureMeasurement.measurement_crs,
            FeatureMeasurement.warning,
        ).where(FeatureMeasurement.uploaded_file_id == file_id)
    ).all()
    calculated = [row for row in rows if row.area_sqm is not None or row.length_m is not None]
    methods = set()
    for row in calculated:
        stored = getattr(row, "measurement_method", None)
        if stored in ("geodesic", "projected"):
            methods.add(stored)
        elif row.area_sqm is not None and row.measurement_crs is None:
            # Backwards compatibility for rows persisted before per-feature
            # measurement_method existed.
            methods.add("geodesic")
        else:
            methods.add("projected")
    return MeasurementSummary(
        measured=len(calculated),
        warnings=sum(row.warning is not None for row in rows),
        measurement_method=methods.pop() if len(methods) == 1 else ("mixed" if methods else "none"),
    )


def _feature_total(session: Session, file_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(FeatureMeasurement).where(
            FeatureMeasurement.uploaded_file_id == file_id
        )
    ) or 0


def _parse_includes(include: list[str] | None) -> set[str]:
    includes = {
        value.strip().lower()
        for group in include or []
        for value in group.split(",")
        if value.strip()
    }
    unsupported = includes - {"geometry", "properties"}
    if unsupported:
        choices = ", ".join(sorted(unsupported))
        raise HTTPException(status_code=422, detail=f"Unsupported include value: {choices}.")
    return includes


def _measurement_response(
    feature: FeatureMeasurement, includes: set[str]
) -> MeasurementResponse:
    return MeasurementResponse(
        **_feature_response_data(feature, includes),
        measurement=_measurement(feature),
    )


def _feature_response(feature: FeatureMeasurement, includes: set[str]) -> FeatureResponse:
    return FeatureResponse(**_feature_response_data(feature, includes))


def _feature_response_data(feature: FeatureMeasurement, includes: set[str]) -> dict[str, object]:
    properties = feature.properties or {}
    return {
        "feature_id": feature.source_feature_id or feature.id,
        "name": _display_name(properties),
        "geometry_type": feature.geometry_type,
        "attributes": {key: properties[key] for key in _DISPLAY_ATTRIBUTES if key in properties},
        "geometry": feature.geometry if "geometry" in includes else None,
        "properties": properties if "properties" in includes else None,
    }


def _display_name(properties: dict) -> str | None:
    for key in ("NAME_EN", "NAME", "name", "Name", "ADMIN"):
        value = properties.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _measurement(feature: FeatureMeasurement) -> Measurement:
    stored_method = getattr(feature, "measurement_method", None)
    stored_note = getattr(feature, "accuracy_note", None)
    if feature.area_sqm is not None:
        method = stored_method if stored_method in ("projected", "geodesic") else (
            "projected" if feature.measurement_crs else "geodesic"
        )
        return Measurement(
            status="calculated",
            method=method,  # type: ignore[arg-type]
            measurement_crs=feature.measurement_crs,
            area_m2=feature.area_sqm,
            area_km2=round(feature.area_sqm / 1_000_000, 2),
            accuracy_note=stored_note
            or (_PROJECTED_ACCURACY_NOTE if method == "projected" else _GEODESIC_ACCURACY_NOTE),
            warning=feature.warning,
        )
    if feature.length_m is not None:
        method = stored_method if stored_method in ("projected", "geodesic") else "projected"
        fallback_note = (
            _PROJECTED_ACCURACY_NOTE
            if method == "projected"
            else (
                "Ellipsoidal length on WGS 84; accuracy is limited by the source geometry and "
                "is not a legal or official statistical boundary claim."
            )
        )
        return Measurement(
            status="calculated",
            method=method,  # type: ignore[arg-type]
            measurement_crs=feature.measurement_crs,
            length_m=feature.length_m,
            accuracy_note=stored_note or fallback_note,
            warning=feature.warning,
        )

    status_value = (
        "not_applicable"
        if feature.geometry_type in {"Point", "MultiPoint"}
        or (feature.warning or "").startswith("Geometry type")
        else "unavailable"
    )
    return Measurement(status=status_value, warning=feature.warning)
