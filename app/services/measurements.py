"""CRS-aware, metre-based measurements for individual Shapely geometries."""

from __future__ import annotations

from dataclasses import dataclass

from pyproj import CRS, Transformer
from shapely import make_valid
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform


@dataclass(frozen=True, slots=True)
class MeasurementResult:
    area_sqm: float | None
    length_m: float | None
    measurement_crs: str | None
    warning: str | None


def measure_geometry(geometry: BaseGeometry | None, source_crs: str | None) -> MeasurementResult:
    """Measure supported geometries after projecting them into a local metric CRS.

    Measurements are intentionally always returned in SI units. The geometry's centroid is
    transformed to WGS84 and used to select a UTM zone, with polar stereographic fallbacks.
    """
    if geometry is None or geometry.is_empty:
        return MeasurementResult(None, None, None, "The feature has no non-empty geometry.")

    geometry_type = geometry.geom_type
    if geometry_type in {"Point", "MultiPoint"}:
        return MeasurementResult(None, None, None, "Points do not require a measurement.")
    if geometry_type not in {"Polygon", "MultiPolygon", "LineString", "MultiLineString"}:
        return MeasurementResult(
            None,
            None,
            None,
            f"Geometry type '{geometry_type}' is not supported for measurement.",
        )
    if not source_crs:
        return MeasurementResult(None, None, None, "Measurements require a declared source CRS.")

    try:
        input_crs = CRS.from_user_input(source_crs)
    except Exception:
        return MeasurementResult(None, None, None, f"The source CRS '{source_crs}' is invalid.")

    warnings: list[str] = []
    valid_geometry = geometry
    if not geometry.is_valid:
        valid_geometry = make_valid(geometry)
        warnings.append("The invalid geometry was repaired before measurement.")
    if valid_geometry.is_empty:
        return MeasurementResult(None, None, None, "The geometry is empty after validation.")

    try:
        metric_crs = _select_metric_crs(valid_geometry, input_crs)
        transformer = Transformer.from_crs(input_crs, metric_crs, always_xy=True)
        metric_geometry = transform(transformer.transform, valid_geometry)
    except Exception as exc:
        return MeasurementResult(None, None, None, f"Geometry could not be projected: {exc}")

    measurement_crs = metric_crs.to_string()
    if geometry_type in {"Polygon", "MultiPolygon"}:
        return MeasurementResult(metric_geometry.area, None, measurement_crs, _join_warnings(warnings))
    return MeasurementResult(None, metric_geometry.length, measurement_crs, _join_warnings(warnings))


def _select_metric_crs(geometry: BaseGeometry, source_crs: CRS) -> CRS:
    """Select a feature-local UTM CRS, or a suitable polar stereographic CRS."""
    to_wgs84 = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True)
    geographic_geometry = transform(to_wgs84.transform, geometry)
    reference = geographic_geometry.representative_point()
    longitude, latitude = reference.x, reference.y

    if latitude >= 84:
        return CRS.from_epsg(3413)
    if latitude <= -80:
        return CRS.from_epsg(3031)

    zone = min(60, max(1, int((longitude + 180) // 6) + 1))
    return CRS.from_epsg((32600 if latitude >= 0 else 32700) + zone)


def _join_warnings(warnings: list[str]) -> str | None:
    return " ".join(warnings) if warnings else None
