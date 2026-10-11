"""CRS-aware measurements for individual Shapely geometries.

Assignment-first design with a documented geodesic extension:

- The default ``auto`` mode satisfies the assignment wording: compact local
  polygons and lines are transformed to an appropriate projected CRS (local
  UTM, polar stereographic for polar data) before measuring in SI units.
- ``auto`` switches polygon areas (and very large / multi-zone /
  antimeridian lines) to a geodesic fallback on the WGS 84 ellipsoid. This
  keeps Fiji-like antimeridian MultiPolygons, multi-part and multi-zone
  features, and continent-scale geometries correct instead of silently
  dropping them or reporting heavily distorted projected values.
- Explicit ``projected`` forces a local projection; explicit ``geodesic``
  forces ellipsoidal measurement. Both are exposed on upload as
  ``measurement_method=auto|projected|geodesic`` for reproducibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pyproj import CRS, Geod, Transformer
from shapely import make_valid, transform
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient

from app.core.errors import sanitize_error_detail

MeasurementMethod = Literal["auto", "projected", "geodesic"]

_WGS84 = CRS.from_epsg(4326)
_GEOD = Geod(ellps="WGS84")
_GEODESIC_ACCURACY_NOTE = (
    "Ellipsoidal area on WGS 84; accuracy is limited by the source geometry and is not "
    "a legal or official statistical boundary claim."
)
_GEODESIC_LENGTH_NOTE = (
    "Ellipsoidal length on WGS 84; accuracy is limited by the source geometry and is not "
    "a legal or official statistical boundary claim."
)
_PROJECTED_ACCURACY_NOTE = "Measured in a feature-local projected CRS suitable for local use."

# A compact local feature comfortably fits inside one UTM zone (6 deg wide).
# Beyond this, projection distortion grows and a single zone choice becomes
# arbitrary, so ``auto`` prefers the geodesic fallback for polygons.
_AUTO_MAX_DEG_SPAN = 4.0


@dataclass(frozen=True, slots=True)
class MeasurementResult:
    area_sqm: float | None
    length_m: float | None
    measurement_crs: str | None
    warning: str | None
    method: str | None
    accuracy_note: str | None


def measure_geometry(
    geometry: BaseGeometry | None,
    source_crs: str | None,
    measurement_method: MeasurementMethod = "auto",
) -> MeasurementResult:
    """Return SI measurements, projecting compact local geometry first.

    ``measurement_method`` is backend-chosen by default (``auto``) so callers
    do not need to select a method. ``projected`` forces a feature-local
    projection; ``geodesic`` forces WGS 84 ellipsoidal math.
    """
    if geometry is None or geometry.is_empty:
        return MeasurementResult(
            None, None, None, "The feature has no non-empty geometry.", None, None
        )

    if measurement_method not in ("auto", "projected", "geodesic"):
        return MeasurementResult(
            None, None, None,
            "Unsupported measurement method. Use auto, projected, or geodesic.",
            None, None,
        )

    geometry_type = geometry.geom_type
    if geometry_type in {"Point", "MultiPoint"}:
        return MeasurementResult(
            None, None, None, "Points do not require a measurement.", None, None
        )
    if geometry_type not in {"Polygon", "MultiPolygon", "LineString", "MultiLineString"}:
        return MeasurementResult(
            None,
            None,
            None,
            f"Geometry type '{geometry_type}' is not supported for measurement.",
            None,
            None,
        )
    if not source_crs:
        return MeasurementResult(
            None, None, None, "Measurements require a declared source CRS.", None, None
        )

    try:
        input_crs = CRS.from_user_input(source_crs)
    except Exception:
        return MeasurementResult(
            None, None, None, f"The source CRS '{source_crs}' is invalid.", None, None
        )

    warnings: list[str] = []
    valid_geometry = geometry
    if not geometry.is_valid:
        valid_geometry = make_valid(geometry)
        warnings.append("The invalid geometry was repaired before measurement.")
    if valid_geometry.is_empty:
        return MeasurementResult(
            None, None, None, "The geometry is empty after validation.", None, None
        )

    warning = _join_warnings(warnings)
    is_polygon = geometry_type in {"Polygon", "MultiPolygon"}

    try:
        to_wgs84 = Transformer.from_crs(input_crs, _WGS84, always_xy=True)
        geographic = transform(valid_geometry, to_wgs84.transform, interleaved=False)
    except Exception as exc:
        detail = sanitize_error_detail(str(exc))
        return MeasurementResult(
            None, None, None, f"Geometry could not be transformed: {detail}", None, None
        )

    # Decide the effective method. Explicit modes win; auto applies the
    # compact-local-projected vs large/global-geodesic rule.
    effective: str = measurement_method
    if measurement_method == "auto":
        if is_polygon:
            use_geodesic = _needs_geodesic_polygon(valid_geometry, geographic)
            effective = "geodesic" if use_geodesic else "projected"
        else:
            effective = "geodesic" if _needs_geodesic_line(geographic) else "projected"

    if is_polygon:
        if effective == "geodesic":
            try:
                area_sqm = _geodesic_area_from_geographic(geographic)
            except Exception as exc:
                detail = sanitize_error_detail(str(exc))
                return MeasurementResult(
                    None, None, None,
                    f"Geometry could not be transformed for geodesic measurement: {detail}",
                    None, None,
                )
            return MeasurementResult(
                area_sqm, None, None, warning, "geodesic", _GEODESIC_ACCURACY_NOTE
            )
        try:
            metric_crs, metric_geometry = _project(valid_geometry, input_crs)
        except Exception as exc:
            detail = sanitize_error_detail(str(exc))
            return MeasurementResult(
                None, None, None, f"Geometry could not be projected: {detail}", None, None
            )
        return MeasurementResult(
            metric_geometry.area, None, metric_crs.to_string(),
            warning, "projected", _PROJECTED_ACCURACY_NOTE,
        )

    # LineString / MultiLineString
    if effective == "geodesic":
        try:
            length_m = _geodesic_length_from_geographic(geographic)
        except Exception as exc:
            detail = sanitize_error_detail(str(exc))
            return MeasurementResult(
                None, None, None,
                f"Geometry could not be transformed for geodesic measurement: {detail}",
                None, None,
            )
        return MeasurementResult(
            None, length_m, None, warning, "geodesic", _GEODESIC_LENGTH_NOTE
        )
    try:
        metric_crs, metric_geometry = _project(valid_geometry, input_crs)
    except Exception as exc:
        detail = sanitize_error_detail(str(exc))
        return MeasurementResult(
            None, None, None, f"Geometry could not be projected: {detail}", None, None
        )
    return MeasurementResult(
        None, metric_geometry.length, metric_crs.to_string(),
        warning, "projected", _PROJECTED_ACCURACY_NOTE,
    )


def _needs_geodesic_polygon(valid_geometry: BaseGeometry, geographic: BaseGeometry) -> bool:
    """Auto rule: compact single-part local polygons stay projected."""
    # Polar data has a dedicated projected CRS, so keep it projected.
    reference = geographic.representative_point()
    if reference.y >= 84 or reference.y <= -80:
        return False
    # Multi-part polygons (including GeometryCollections from make_valid)
    # are summed geodesically to avoid sign cancellation and zone ambiguity.
    if len(_polygon_parts(geographic)) > 1:
        return True
    if _crosses_antimeridian(geographic):
        return True
    if _spans_multiple_utm_zones(geographic):
        return True
    minx, miny, maxx, maxy = geographic.bounds
    return (maxx - minx) > _AUTO_MAX_DEG_SPAN or (maxy - miny) > _AUTO_MAX_DEG_SPAN


def _needs_geodesic_line(geographic: BaseGeometry) -> bool:
    """Auto rule: compact local lines stay projected."""
    reference = geographic.representative_point()
    if reference.y >= 84 or reference.y <= -80:
        return False
    if _crosses_antimeridian(geographic):
        return True
    if _spans_multiple_utm_zones(geographic):
        return True
    minx, miny, maxx, maxy = geographic.bounds
    return (maxx - minx) > _AUTO_MAX_DEG_SPAN or (maxy - miny) > _AUTO_MAX_DEG_SPAN


def _crosses_antimeridian(geographic: BaseGeometry) -> bool:
    minx, _, maxx, _ = geographic.bounds
    return (maxx - minx) > 180.0


def _utm_zone(longitude: float) -> int:
    return min(60, max(1, int((longitude + 180) // 6) + 1))


def _spans_multiple_utm_zones(geographic: BaseGeometry) -> bool:
    minx, _, maxx, _ = geographic.bounds
    if (maxx - minx) > 180.0:
        return True
    return _utm_zone(minx) != _utm_zone(maxx)


def _project(geometry: BaseGeometry, source_crs: CRS) -> tuple[CRS, BaseGeometry]:
    metric_crs = _select_metric_crs(geometry, source_crs)
    transformer = Transformer.from_crs(source_crs, metric_crs, always_xy=True)
    return metric_crs, transform(geometry, transformer.transform, interleaved=False)


def _geodesic_area_from_geographic(geographic_geometry: BaseGeometry) -> float:
    """Calculate the summed absolute WGS 84 ellipsoidal area of polygon components."""
    polygons = list(_polygon_parts(geographic_geometry))
    if not polygons:
        raise ValueError("The validated geometry contains no polygonal components.")

    # Calculate each component independently. This avoids sign cancellation between
    # parts and supports antimeridian-spanning MultiPolygons such as Fiji.
    return sum(
        abs(_GEOD.geometry_area_perimeter(orient(polygon, sign=1.0))[0]) for polygon in polygons
    )


def _geodesic_length_from_geographic(geographic_geometry: BaseGeometry) -> float:
    """Calculate WGS 84 ellipsoidal length, supporting multi-part lines."""
    return float(_GEOD.geometry_length(geographic_geometry))


def _polygon_parts(geometry: BaseGeometry) -> list[Polygon]:
    """Extract polygon components, including those produced by ``make_valid``."""
    if isinstance(geometry, Polygon):
        return [geometry]
    if geometry.geom_type == "MultiPolygon":
        return list(geometry.geoms)
    if geometry.geom_type == "GeometryCollection":
        return [polygon for part in geometry.geoms for polygon in _polygon_parts(part)]
    return []


def _select_metric_crs(geometry: BaseGeometry, source_crs: CRS) -> CRS:
    """Select a feature-local UTM CRS, or a suitable polar stereographic CRS."""
    to_wgs84 = Transformer.from_crs(source_crs, _WGS84, always_xy=True)
    geographic_geometry = transform(geometry, to_wgs84.transform, interleaved=False)
    reference = geographic_geometry.representative_point()
    longitude, latitude = reference.x, reference.y

    if latitude >= 84:
        return CRS.from_epsg(3413)
    if latitude <= -80:
        return CRS.from_epsg(3031)

    zone = _utm_zone(longitude)
    return CRS.from_epsg((32600 if latitude >= 0 else 32700) + zone)


def _join_warnings(warnings: list[str]) -> str | None:
    return " ".join(warnings) if warnings else None
