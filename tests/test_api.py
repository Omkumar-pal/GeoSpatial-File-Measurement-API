from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import geopandas as gpd
from fastapi.testclient import TestClient
from shapely.geometry import MultiPolygon, Polygon

from app.core.config import Settings
from app.main import create_app

KML_DOCUMENT = b"\n".join(
    [
        b'<?xml version="1.0" encoding="UTF-8"?>',
        b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
        b"  <Placemark><name>Parcel A</name><Polygon><outerBoundaryIs><LinearRing>",
        b"    <coordinates>",
        b"      77.590,12.960,0 77.600,12.960,0 77.600,12.970,0",
        b"      77.590,12.970,0 77.590,12.960,0",
        b"    </coordinates>",
        b"  </LinearRing></outerBoundaryIs></Polygon></Placemark>",
        b"  <Placemark><name>Route A</name><LineString>",
        b"    <coordinates>77.590,12.960,0 77.600,12.960,0</coordinates>",
        b"  </LineString></Placemark>",
        b"  <Placemark><name>Marker A</name><Point>",
        b"    <coordinates>77.590,12.960,0</coordinates>",
        b"  </Point></Placemark>",
        b"</Document></kml>",
    ]
)


def test_root_redirects_to_docs(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/docs"


def test_health_endpoint(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_kml_upload_persists_measurements(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.post(
            "/api/files/",
            files={"file": ("survey.kml", KML_DOCUMENT, "application/vnd.google-earth.kml+xml")},
        )
        assert response.status_code == 201, response.text
        file_data = response.json()

        assert file_data["status"] == "COMPLETED"
        assert file_data["feature_count"] == 3
        assert file_data["source_crs"] == "EPSG:4326"
        assert file_data["measurement_method"] == "auto"
        assert file_data["summary"] == {
            "measured": 2,
            "warnings": 1,
            "measurement_method": "projected",
        }
        assert file_data["links"]["measurements"].endswith("/measurements?limit=25")

        info_response = client.get(f"/api/files/{file_data['id']}/")
        measurements_response = client.get(f"/api/files/{file_data['id']}/measurements")
        first_page_response = client.get(
            f"/api/files/{file_data['id']}/measurements?limit=1&include=geometry,properties"
        )
        features_response = client.get(f"/api/files/{file_data['id']}/features?limit=1")

    assert info_response.status_code == 200
    assert measurements_response.status_code == 200
    measurements_payload = measurements_response.json()
    measurements = measurements_payload["items"]
    assert len(measurements) == 3
    assert measurements_payload["limit"] == 25
    assert measurements_payload["offset"] == 0
    assert measurements_payload["total"] == 3
    assert "geometry" not in measurements[0]
    assert "properties" not in measurements[0]
    assert measurements[0]["measurement"]["area_m2"] is not None
    assert measurements[0]["measurement"]["method"] == "projected"
    assert measurements[0]["measurement"]["measurement_crs"] == "EPSG:32643"
    assert measurements[1]["measurement"]["length_m"] is not None
    assert measurements[1]["measurement"]["method"] == "projected"
    assert measurements[2]["measurement"]["status"] == "not_applicable"

    assert first_page_response.status_code == 200
    first_item = first_page_response.json()["items"][0]
    assert first_page_response.json()["total"] == 3
    assert first_item["geometry"]["type"] == "Polygon"
    assert first_item["properties"]["Name"] == "Parcel A"

    assert features_response.status_code == 200
    assert "geometry" not in features_response.json()["items"][0]
    assert "properties" not in features_response.json()["items"][0]


def test_unknown_file_type_is_rejected(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.post("/api/files/", files={"file": ("notes.txt", b"hello", "text/plain")})

    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_file"


def test_unreadable_kml_does_not_leak_server_paths(tmp_path: Path) -> None:
    bad_kml = ("plot.kml", b"this is not kml", "application/vnd.google-earth.kml+xml")
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.post("/api/files/", files={"file": bad_kml})

    assert response.status_code == 422
    error = response.json()["error"]
    assert "plot.kml" in error
    for leaked in ("C:", "\\", "uploads", "data/", ".db"):
        assert leaked not in error, error
    # No workspace UUID may appear in the client-facing message.
    import re

    assert not re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        error,
    ), error


def test_shapefile_zip_upload_persists_measurement(tmp_path: Path) -> None:
    shapefile_directory = tmp_path / "shapefile"
    shapefile_directory.mkdir()
    dataset = gpd.GeoDataFrame(
        {"ISO_A3": ["FJI"], "NAME_EN": ["Fiji"], "CONTINENT": ["Oceania"]},
        geometry=[
            MultiPolygon(
                [
                    Polygon([(178, -18), (179, -18), (179, -17), (178, -17), (178, -18)]),
                    Polygon(
                        [(-179, -18), (-178, -18), (-178, -17), (-179, -17), (-179, -18)]
                    ),
                ]
            )
        ],
        crs="EPSG:4326",
    )
    shapefile_path = shapefile_directory / "parcel.shp"
    dataset.to_file(shapefile_path)
    archive_path = tmp_path / "parcel.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for component in shapefile_directory.iterdir():
            archive.write(component, component.name)

    with TestClient(create_app(_settings(tmp_path))) as client, archive_path.open("rb") as archive:
        response = client.post(
            "/api/files/",
            files={"file": ("parcel.zip", archive, "application/zip")},
        )
        measurements_response = client.get(
            f"/api/files/{response.json()['id']}/measurements?include=geometry"
        )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["file_type"] == "shapefile_zip"
    assert payload["feature_count"] == 1
    assert payload["status"] == "COMPLETED"
    assert payload["summary"]["measured"] == 1
    assert payload["summary"]["measurement_method"] == "geodesic"
    assert measurements_response.status_code == 200
    item = measurements_response.json()["items"][0]
    assert item["feature_id"] == "FJI"
    assert item["attributes"] == {
        "NAME_EN": "Fiji",
        "ISO_A3": "FJI",
        "CONTINENT": "Oceania",
    }
    assert item["measurement"]["method"] == "geodesic"
    assert item["measurement"]["area_m2"] > 20_000_000_000
    assert item["geometry"]["type"] == "MultiPolygon"


def test_upload_measurement_method_is_persisted_and_forced(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        auto_response = client.post(
            "/api/files/",
            files={"file": ("survey.kml", KML_DOCUMENT, "application/vnd.google-earth.kml+xml")},
        )
        assert auto_response.status_code == 201, auto_response.text
        assert auto_response.json()["measurement_method"] == "auto"
        assert auto_response.json()["summary"]["measurement_method"] == "projected"

        geodesic_response = client.post(
            "/api/files/?measurement_method=geodesic",
            files={"file": ("survey.kml", KML_DOCUMENT, "application/vnd.google-earth.kml+xml")},
        )
        assert geodesic_response.status_code == 201, geodesic_response.text
        geodesic_data = geodesic_response.json()
        assert geodesic_data["measurement_method"] == "geodesic"
        assert geodesic_data["summary"]["measurement_method"] == "geodesic"

        items = client.get(f"/api/files/{geodesic_data['id']}/measurements").json()["items"]
        assert items[0]["measurement"]["method"] == "geodesic"
        assert items[0]["measurement"].get("measurement_crs") is None
        assert items[1]["measurement"]["method"] == "geodesic"

        invalid_response = client.post(
            "/api/files/?measurement_method=utm",
            files={"file": ("survey.kml", KML_DOCUMENT, "application/vnd.google-earth.kml+xml")},
        )
        assert invalid_response.status_code == 422


def _settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        data_dir=data_dir,
        upload_dir=data_dir / "uploads",
        database_url=f"sqlite:///{(data_dir / 'test.db').as_posix()}",
        max_upload_bytes=10 * 1024 * 1024,
        max_zip_members=10,
        max_zip_uncompressed_bytes=10 * 1024 * 1024,
    )
