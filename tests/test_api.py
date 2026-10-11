from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import geopandas as gpd
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

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
        assert file_data["crs"] == "EPSG:4326"

        info_response = client.get(f"/api/files/{file_data['id']}/")
        measurements_response = client.get(f"/api/files/{file_data['id']}/measurements/")

    assert info_response.status_code == 200
    assert measurements_response.status_code == 200
    measurements = measurements_response.json()["measurements"]
    assert len(measurements) == 3
    assert measurements[0]["area_sqm"] is not None
    assert measurements[1]["length_m"] is not None
    assert measurements[2]["area_sqm"] is None


def test_unknown_file_type_is_rejected(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.post("/api/files/", files={"file": ("notes.txt", b"hello", "text/plain")})

    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_file"


def test_shapefile_zip_upload_persists_measurement(tmp_path: Path) -> None:
    shapefile_directory = tmp_path / "shapefile"
    shapefile_directory.mkdir()
    dataset = gpd.GeoDataFrame(
        {"site_id": ["parcel-1"]},
        geometry=[Polygon([(77.59, 12.96), (77.60, 12.96), (77.60, 12.97), (77.59, 12.96)])],
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

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["file_type"] == "shapefile_zip"
    assert payload["feature_count"] == 1
    assert payload["status"] == "COMPLETED"


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
