# Geospatial File Measurement API

FastAPI service for uploading a KML file or a ZIP archive containing one complete Shapefile, extracting every feature, and returning CRS-aware area and length measurements.

## What it does

- Accepts `.kml` and `.zip` files containing the `.shp`, `.shx`, and `.dbf` files of one Shapefile.
- Persists upload metadata and every normalized feature in local SQLite by default.
- Returns geometry type, GeoJSON-like geometry, all feature properties, source CRS, measurement CRS, and measurements.
- Calculates polygon area in square metres and line length in metres.
- Does not calculate directly from latitude/longitude degrees. It selects a feature-local UTM projection from the feature location; polar stereographic CRSs are used for polar data.
- Stores a clear warning instead of crashing for points, unsupported geometries, empty features, unknown CRSs, or unreadable files.

## Local setup

Requires Python 3.11 or newer and GDAL-compatible wheels for the GeoPandas stack.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The service starts on `http://127.0.0.1:8000`; interactive API documentation is at `http://127.0.0.1:8000/docs`.

Alternatively, use Docker:

```powershell
docker compose up --build
```

Copy `.env.example` to `.env` if you need different upload or ZIP expansion limits. Runtime data is created in `data/` and excluded from Git.

## API

### Upload and process a file

`POST /api/files/` accepts multipart form-data with a required `file` field.

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/files/ `
  -F "file=@C:\data\survey.kml"
```

Example response:

```json
{
  "id": "e22e0c5c-ef75-4e45-91ca-1d6e0e5d8a7f",
  "filename": "survey.kml",
  "file_type": "kml",
  "feature_count": 120,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error_message": null,
  "created_at": "2026-10-11T10:00:00Z",
  "completed_at": "2026-10-11T10:00:01Z"
}
```

### Get file information

`GET /api/files/{id}/` returns the persisted upload status and metadata.

### Get measurements

`GET /api/files/{id}/measurements/` returns each feature. Polygon rows include `area_sqm`; LineString rows include `length_m`; point rows have neither measurement and include a warning explaining why.

### Health check

`GET /health` returns `{ "status": "ok" }`.

## Architecture

```text
FastAPI route
  -> stream upload with a byte limit
  -> validate and safely extract archive when needed
  -> GeoPandas reads the layer
  -> Shapely normalizes each geometry
  -> PyProj transforms each measurable feature to a local metric CRS
  -> SQLAlchemy persists file and feature records in SQLite
  -> API returns stored metadata and measurement results
```

`app/api` contains HTTP routes, `app/services` owns validation, extraction, parsing, and measurement logic, `app/db` owns SQLAlchemy models, and `app/schemas.py` defines the public response contracts. The application factory accepts custom settings, making tests run against isolated temporary SQLite databases.

## Design decisions

- **FastAPI over Django:** the service is API-only, benefits from generated OpenAPI documentation, and does not need Django's admin or template layers.
- **Feature-local metric CRS:** all measurements use metres instead of source coordinate units. This avoids mistakenly reporting degrees as distance or area and also avoids source CRSs that use feet.
- **Synchronous processing:** the requested scope processes a file before returning `201 Created`, which is simple and transparent for normal uploads. A background worker is the next step for large files.
- **SQLite locally:** it makes the project runnable immediately. PostgreSQL/PostGIS can be introduced by changing `DATABASE_URL` and adding migrations when spatial querying becomes necessary.
- **Graceful feature failures:** measurement limitations are stored on each feature as `warning`, rather than discarding the record or failing the entire upload.
- **Defence in depth for ZIP files:** the service rejects traversal paths, encrypted archives, oversized expanded content, excessive member counts, empty archives, multiple `.shp` files, and incomplete Shapefile sets.

## Testing

```powershell
pytest
ruff check .
```

The test suite covers CRS-aware polygon and line measurements, point/no-CRS behaviour, ZIP traversal and component validation, health checks, unsupported file rejection, and end-to-end KML upload persistence.

## Learning and future scope

This project demonstrates the difference between geographic and projected coordinates, local CRS selection, secure archive handling, geometry validation, API lifecycle design, and persistence of processing results.

Future improvements include background workers for large uploads, PostgreSQL/PostGIS, object storage, authentication and per-user quotas, pagination, GeoJSON/GeoPackage support, multi-layer KML handling, geodesic calculations for continent-scale datasets, output exports, observability, and database migrations.
