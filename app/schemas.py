"""Public API contracts independent from persistence implementation details."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str
    code: str


class FileResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    feature_count: int
    crs: str | None
    status: str
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class MeasurementResponse(BaseModel):
    feature_index: int
    feature_id: str | None
    geometry_type: str | None
    geometry: dict[str, Any] | None
    properties: dict[str, Any]
    source_crs: str | None
    measurement_crs: str | None
    area_sqm: float | None = Field(default=None, description="Polygon area in square metres.")
    length_m: float | None = Field(default=None, description="Line length in metres.")
    warning: str | None = None


class MeasurementsResponse(BaseModel):
    file_id: str
    feature_count: int
    measurements: list[MeasurementResponse]


class HealthResponse(BaseModel):
    status: str
