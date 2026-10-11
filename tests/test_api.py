from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

KML_DOCUMENT = b'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <Placemark><name>Parcel A</name><Polygon><outerBoundaryIs><LinearRing>
    <coordinates>77.590,12.960,0 77.600,12.960,0 77.600,12.970,0 77.590,12.970,0 77.590,12.960,0</coordinates>
  </LinearRing></outerBoundaryIs></Polygon></Placemark>
  <Placemark><name>Route A</name><LineString><coordinates>77.590,12.960,0 77.600,12.960,0</coordinates></LineString></Placemark>
  <Placemark><name>Marker A</name><Point><coordinates>77.590,12.960,0</coordinates></Point></Placemark>
</Document></kml>'''


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
