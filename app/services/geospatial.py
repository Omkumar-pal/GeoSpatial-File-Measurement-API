"""Read geospatial datasets and convert features into persistence-ready records."""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping

from app.core.errors import ProcessingError, sanitize_error_detail
from app.services.measurements import MeasurementMethod, measure_geometry

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExtractedFeature:
    feature_index: int
    source_feature_id: str | None
    geometry_type: str | None
    geometry: dict[str, Any] | None
    properties: dict[str, Any]
    source_crs: str | None
    measurement_crs: str | None
    area_sqm: float | None
    length_m: float | None
    warning: str | None
    measurement_method: str | None
    accuracy_note: str | None


@dataclass(frozen=True, slots=True)
class ExtractedDataset:
    source_crs: str | None
    features: list[ExtractedFeature]


def read_dataset(
    path: Path, file_type: str, measurement_method: MeasurementMethod = "auto"
) -> ExtractedDataset:
    """Load a KML or Shapefile and extract all features without dropping attributes."""
    safe_name = path.name or "upload"
    try:
        if file_type == "kml":
            dataset = gpd.read_file(path, driver="KML")
            # KML is defined in WGS84. Some GDAL builds omit this metadata, so restore it.
            if dataset.crs is None:
                dataset = dataset.set_crs("EPSG:4326", allow_override=True)
        else:
            dataset = gpd.read_file(path)
    except Exception as exc:
        # Log the full server-side detail (absolute path, workspace id) for
        # operators, but never echo it to API clients.
        logger.warning("Failed to read %s file %s: %s", file_type, path, exc)
        detail = sanitize_error_detail(str(exc), safe_filename=safe_name)
        if file_type == "kml":
            message = (
                f"The KML file '{safe_name}' could not be parsed. "
                "Verify it is valid KML with supported geometries."
            )
        else:
            message = (
                f"The Shapefile '{safe_name}' could not be read. "
                "Verify the archive contains one complete .shp/.shx/.dbf set."
            )
        if detail:
            message = f"{message} Details: {detail}"
        raise ProcessingError(message) from exc

    source_crs = dataset.crs.to_string() if dataset.crs is not None else None
    geometry_column = dataset.geometry.name
    features: list[ExtractedFeature] = []
    for position, (_, row) in enumerate(dataset.iterrows()):
        geometry = row[geometry_column]
        result = measure_geometry(geometry, source_crs, measurement_method)
        properties = {
            str(key): to_json_value(value)
            for key, value in row.drop(labels=[geometry_column]).to_dict().items()
        }
        source_feature_id = _source_feature_id(properties)
        features.append(
            ExtractedFeature(
                feature_index=position,
                source_feature_id=source_feature_id,
                geometry_type=geometry.geom_type if geometry is not None else None,
                geometry=to_json_value(mapping(geometry)) if geometry is not None else None,
                properties=properties,
                source_crs=source_crs,
                measurement_crs=result.measurement_crs,
                area_sqm=result.area_sqm,
                length_m=result.length_m,
                warning=result.warning,
                measurement_method=result.method,
                accuracy_note=result.accuracy_note,
            )
        )
    return ExtractedDataset(source_crs=source_crs, features=features)


def _source_feature_id(properties: dict[str, Any]) -> str | None:
    """Choose a source identifier that remains meaningful outside this upload.

    Natural Earth country layers expose ISO_A3 and NE_ID. Prefer those stable values
    over a row position, while retaining common identifiers for generic KML and
    Shapefile uploads.
    """
    for key in ("ISO_A3", "iso_a3", "NE_ID", "ne_id", "id", "ID", "fid", "FID"):
        value = properties.get(key)
        if value is not None and str(value).strip() and str(value) != "-99":
            return str(value)
    for key in ("NAME_EN", "NAME", "name", "Name"):
        value = properties.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def to_json_value(value: Any) -> Any:
    """Convert GeoPandas, NumPy, and temporal values to valid JSON data."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_json_value(item) for item in value]
    if hasattr(value, "item"):
        try:
            return to_json_value(value.item())
        except ValueError:
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    # The final serialization check makes unexpected driver values explicit and deterministic.
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)
