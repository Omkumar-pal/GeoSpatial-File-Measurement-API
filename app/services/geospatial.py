"""Read geospatial datasets and convert features into persistence-ready records."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping

from app.core.errors import ProcessingError
from app.services.measurements import measure_geometry


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


@dataclass(frozen=True, slots=True)
class ExtractedDataset:
    source_crs: str | None
    features: list[ExtractedFeature]


def read_dataset(path: Path, file_type: str) -> ExtractedDataset:
    """Load a KML or Shapefile and extract all features without dropping attributes."""
    try:
        if file_type == "kml":
            dataset = gpd.read_file(path, driver="KML")
            # KML is defined in WGS84. Some GDAL builds omit this metadata, so restore it.
            if dataset.crs is None:
                dataset = dataset.set_crs("EPSG:4326", allow_override=True)
        else:
            dataset = gpd.read_file(path)
    except Exception as exc:
        raise ProcessingError(f"The geospatial file could not be read: {exc}") from exc

    source_crs = dataset.crs.to_string() if dataset.crs is not None else None
    geometry_column = dataset.geometry.name
    features: list[ExtractedFeature] = []
    for position, (source_index, row) in enumerate(dataset.iterrows()):
        geometry = row[geometry_column]
        result = measure_geometry(geometry, source_crs)
        properties = {
            str(key): to_json_value(value)
            for key, value in row.drop(labels=[geometry_column]).to_dict().items()
        }
        source_feature_id = _source_feature_id(properties, source_index)
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
            )
        )
    return ExtractedDataset(source_crs=source_crs, features=features)


def _source_feature_id(properties: dict[str, Any], source_index: Any) -> str:
    for key in ("id", "ID", "fid", "FID", "name", "Name"):
        if key in properties and properties[key] is not None:
            return str(properties[key])
    return str(source_index)


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
