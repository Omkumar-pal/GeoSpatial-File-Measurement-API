from shapely.geometry import LineString, MultiPolygon, Point, Polygon

from app.services.measurements import measure_geometry


def test_compact_polygon_in_geographic_crs_is_projected_before_measuring() -> None:
    """Auto mode must project small local polygons (assignment wording)."""
    geometry = Polygon([(77.59, 12.96), (77.60, 12.96), (77.60, 12.97), (77.59, 12.97)])

    result = measure_geometry(geometry, "EPSG:4326", "auto")

    assert result.area_sqm is not None
    assert 1_000_000 < result.area_sqm < 1_500_000
    assert result.length_m is None
    assert result.measurement_crs is not None
    assert result.measurement_crs == "EPSG:32643"
    assert result.method == "projected"


def test_explicit_geodesic_polygon_skips_projection() -> None:
    geometry = Polygon([(77.59, 12.96), (77.60, 12.96), (77.60, 12.97), (77.59, 12.97)])

    result = measure_geometry(geometry, "EPSG:4326", "geodesic")

    assert result.area_sqm is not None
    assert 1_000_000 < result.area_sqm < 1_500_000
    assert result.measurement_crs is None
    assert result.method == "geodesic"


def test_explicit_projected_polygon_forces_local_crs() -> None:
    geometry = MultiPolygon(
        [
            Polygon([(178, -18), (179, -18), (179, -17), (178, -17), (178, -18)]),
            Polygon([(-179, -18), (-178, -18), (-178, -17), (-179, -17), (-179, -18)]),
        ]
    )

    result = measure_geometry(geometry, "EPSG:4326", "projected")

    assert result.area_sqm is not None
    assert result.method == "projected"
    assert result.measurement_crs is not None


def test_large_polygon_falls_back_to_geodesic_in_auto() -> None:
    """A 10x10 degree polygon spans multiple UTM zones, so auto uses geodesic."""
    geometry = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])

    result = measure_geometry(geometry, "EPSG:4326", "auto")

    assert result.area_sqm is not None
    assert result.method == "geodesic"
    assert result.measurement_crs is None


def test_polar_polygon_uses_polar_projection_in_auto() -> None:
    geometry = Polygon([(0, 85), (10, 85), (10, 86), (0, 86), (0, 85)])

    result = measure_geometry(geometry, "EPSG:4326", "auto")

    assert result.area_sqm is not None
    assert result.method == "projected"
    assert result.measurement_crs == "EPSG:3413"


def test_linestring_in_geographic_crs_is_measured_in_metres() -> None:
    result = measure_geometry(LineString([(0, 0), (1, 0)]), "EPSG:4326")

    assert result.length_m is not None
    assert 110_000 < result.length_m < 112_000
    assert result.area_sqm is None
    assert result.method == "projected"


def test_large_line_falls_back_to_geodesic_in_auto() -> None:
    result = measure_geometry(LineString([(0, 0), (10, 0)]), "EPSG:4326", "auto")

    assert result.length_m is not None
    assert result.method == "geodesic"
    assert result.measurement_crs is None


def test_explicit_geodesic_line_has_no_projected_crs() -> None:
    result = measure_geometry(LineString([(0, 0), (1, 0)]), "EPSG:4326", "geodesic")

    assert result.length_m is not None
    assert 110_000 < result.length_m < 112_000
    assert result.method == "geodesic"
    assert result.measurement_crs is None


def test_antimeridian_multipolygon_receives_a_geodesic_area() -> None:
    """Fiji-like components on either side of the antimeridian must not be skipped."""
    geometry = MultiPolygon(
        [
            Polygon([(178, -18), (179, -18), (179, -17), (178, -17), (178, -18)]),
            Polygon([(-179, -18), (-178, -18), (-178, -17), (-179, -17), (-179, -18)]),
        ]
    )

    result = measure_geometry(geometry, "EPSG:4326")

    assert result.area_sqm is not None
    assert result.area_sqm > 20_000_000_000
    assert result.method == "geodesic"
    assert result.measurement_crs is None


def test_points_do_not_receive_a_measurement() -> None:
    result = measure_geometry(Point(77.59, 12.96), "EPSG:4326")

    assert result.area_sqm is None
    assert result.length_m is None
    assert result.warning == "Points do not require a measurement."


def test_missing_crs_does_not_silently_measure_coordinates() -> None:
    result = measure_geometry(Polygon([(0, 0), (1, 0), (1, 1), (0, 0)]), None)

    assert result.area_sqm is None
    assert result.warning == "Measurements require a declared source CRS."
