from shapely.geometry import LineString, Point, Polygon

from app.services.measurements import measure_geometry


def test_polygon_in_geographic_crs_is_measured_in_square_metres() -> None:
    geometry = Polygon([(77.59, 12.96), (77.60, 12.96), (77.60, 12.97), (77.59, 12.97)])

    result = measure_geometry(geometry, "EPSG:4326")

    assert result.area_sqm is not None
    assert 1_000_000 < result.area_sqm < 1_500_000
    assert result.length_m is None
    assert result.measurement_crs == "EPSG:32643"


def test_linestring_in_geographic_crs_is_measured_in_metres() -> None:
    result = measure_geometry(LineString([(0, 0), (1, 0)]), "EPSG:4326")

    assert result.length_m is not None
    assert 110_000 < result.length_m < 112_000
    assert result.area_sqm is None


def test_points_do_not_receive_a_measurement() -> None:
    result = measure_geometry(Point(77.59, 12.96), "EPSG:4326")

    assert result.area_sqm is None
    assert result.length_m is None
    assert result.warning == "Points do not require a measurement."


def test_missing_crs_does_not_silently_measure_coordinates() -> None:
    result = measure_geometry(Polygon([(0, 0), (1, 0), (1, 1), (0, 0)]), None)

    assert result.area_sqm is None
    assert result.warning == "Measurements require a declared source CRS."
