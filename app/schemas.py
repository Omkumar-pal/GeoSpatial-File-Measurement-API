"""Public API contracts independent from persistence implementation details."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str
    code: str


class MeasurementSummary(BaseModel):
    measured: int
    warnings: int
    measurement_method: str


class FileLinks(BaseModel):
    measurements: str
    features: str


class FileResponse(BaseModel):
    id: str
    filename: str
    source_crs: str | None
    feature_count: int
    measurement_method: Literal["auto", "projected", "geodesic"] = "auto"
    summary: MeasurementSummary
    links: FileLinks
    # Processing metadata is retained so a caller can safely poll an upload.
    file_type: str
    status: str
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class Measurement(BaseModel):
    status: Literal["calculated", "not_applicable", "unavailable"]
    method: Literal["geodesic", "projected"] | None = None
    measurement_crs: str | None = None
    area_m2: float | None = Field(default=None, description="Polygon area in square metres.")
    area_km2: float | None = Field(default=None, description="Polygon area in square kilometres.")
    length_m: float | None = Field(default=None, description="Line length in metres.")
    accuracy_note: str | None = None
    warning: str | None = None


class FeatureResponse(BaseModel):
    feature_id: str
    name: str | None = None
    geometry_type: str | None
    attributes: dict[str, Any]
    geometry: dict[str, Any] | None = None
    properties: dict[str, Any] | None = None


class MeasurementResponse(FeatureResponse):
    measurement: Measurement


class MeasurementsResponse(BaseModel):
    items: list[MeasurementResponse]
    limit: int
    offset: int
    total: int


class FeaturesResponse(BaseModel):
    items: list[FeatureResponse]
    limit: int
    offset: int
    total: int


class HealthResponse(BaseModel):
    status: str
