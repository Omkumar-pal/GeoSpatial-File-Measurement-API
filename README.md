<h1 align="center">🌍 Geospatial File Measurement API</h1>

<p align="center">
  <b>A production-ready, CRS-aware FastAPI service for ingesting KML and Shapefile archives, extracting geographic features, transforming coordinates into appropriate projected metric systems, and calculating accurate geometry measurements.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%20|%203.12%20|%203.13-3776AB?style=flat&logo=python&logoColor=white" alt="Python Versions" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/GeoPandas-1.0+-139C5A?style=flat&logo=geopandas&logoColor=white" alt="GeoPandas" />
  <img src="https://img.shields.io/badge/PyProj-3.6+-005571?style=flat" alt="PyProj" />
  <img src="https://img.shields.io/badge/Tests-20%20Passing-brightgreen?style=flat" alt="Tests" />
  <a href="https://geospatial-file-measurement-api-k51h.onrender.com/docs"><img src="https://img.shields.io/badge/Render-Live%20Demo-46E3B7?style=flat&logo=render&logoColor=white" alt="Render Live Demo" /></a>
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat" alt="License" />
</p>

<p align="center">
  <a href="https://geospatial-file-measurement-api-k51h.onrender.com/docs"><b>🚀 Live Demo (Render)</b></a> •
  <a href="#-project-overview--assignment-context">Overview</a> •
  <a href="#-requirements-traceability">Requirements</a> •
  <a href="#-architectural--design-decisions">Design Decisions</a> •
  <a href="#-system-architecture--data-flows">Architecture & Flows</a> •
  <a href="#-quick-start--setup">Setup</a> •
  <a href="#-api-documentation">API Reference</a> •
  <a href="#-learnings--future-scope">Learnings & Future Scope</a>
</p>

---

## 🌐 Live Deployment & Interactive Docs

The API is fully deployed and accessible on Render:

- **🚀 Interactive Swagger API:** [https://geospatial-file-measurement-api-k51h.onrender.com/docs](https://geospatial-file-measurement-api-k51h.onrender.com/docs)
- **📖 Live ReDoc Documentation:** [https://geospatial-file-measurement-api-k51h.onrender.com/redoc](https://geospatial-file-measurement-api-k51h.onrender.com/redoc)
- **💓 Live Health Check:** [https://geospatial-file-measurement-api-k51h.onrender.com/health](https://geospatial-file-measurement-api-k51h.onrender.com/health)

> [!NOTE]
> Hosted on Render's free tier. If the service has been idle for 15+ minutes, the first request may take ~30–45 seconds while the Docker container wakes up.

---

## 📌 Project Overview & Assignment Context

This backend service was built to solve the **Geospatial File Measurement API** assignment: an evaluation of the ability to develop clean, maintainable backend APIs, handle complex geospatial file ingestion, perform mathematically rigorous coordinate system transformations, and write production-grade Python code.

The service accepts geospatial uploads (**`.kml`** or **`.zip`** archives containing a Shapefile), extracts all vector features without attribute loss, normalizes coordinate reference systems (CRS), and calculates accurate physical measurements (**area in $m^2$** and **length in $m$**).

---

## 🎯 Requirements Traceability

The implementation satisfies and exceeds all core assignment specifications:

| Requirement | Assignment Specification | Implementation in This Project |
| :--- | :--- | :--- |
| **1. Backend Framework** | Django + DRF or FastAPI | **FastAPI** — high performance, native async streaming, Pydantic v2 validation, and auto-generated OpenAPI / Swagger docs. |
| **2. File Upload** | `POST /api/files/` accepting `.kml` and `.zip` (Shapefile) | Validates uploads with byte-quota enforcement, classifies file format, and performs safe archive extraction. |
| **3. File Processing** | Extract ID, Geometry Type, Geometry, CRS, and Attributes; handle unsupported gracefully | Extracts all metadata; validates with Shapely `make_valid`; assigns stable domain IDs (`ISO_A3`, `NE_ID`); stores warnings without crashing. |
| **4. Measurements** | Polygon $\rightarrow$ Area; LineString $\rightarrow$ Length; Point $\rightarrow$ No measurement | Calculates Polygon area ($m^2$ / $km^2$) and LineString length ($m$); marks Points as `not_applicable` with zero errors. |
| **5. CRS Handling** | Never calculate degrees directly in EPSG:4326; transform to projected CRS | Automatically projects local features into feature-local metric UTM or Polar Stereographic CRS; includes geodesic fallback for wide features. |
| **6. API Design** | Upload `POST /api/files/`, Details `GET /api/files/{id}/`, Measurements `GET /api/files/{id}/measurements` | All endpoints implemented with clean two-tier summaries, pagination (`limit`/`offset`), and opt-in detail flags (`?include=`). |
| **7. Documentation** | Setup, API reference, Architecture, Design decisions | Comprehensive README including real-world failure analyses, design decisions, and system diagrams. |
| **8. Submission** | Learnings and Future Scope | Fully documented below. |

---

## 💡 Architectural & Design Decisions

Beyond the minimum requirements, real-world geospatial data (such as [Natural Earth's 110m Admin 0 Countries](https://www.naturalearthdata.com/downloads/110m-cultural-vectors/110m-admin-0-countries/)) introduces severe edge cases that directed our key design decisions:

### 1. Framework Choice: FastAPI over Django
- **Decision:** Built with **FastAPI** rather than Django + Django REST Framework.
- **Rationale:** The application is a specialized REST API focused on file streaming, geometry computation, and JSON serialization. FastAPI provides exceptional request throughput, native async support, fine-grained dependency injection, and automatic Swagger/OpenAPI documentation without the overhead of Django's ORM, template engine, or admin panel.

### 2. Two-Tier Response Model (Solving the 1 MB Payload Problem)
- **Problem:** Returning all raw coordinates and 100+ attributes for 177 countries in a single response creates a **1.04 MB JSON payload**, degrading mobile client performance.
- **Decision:** Implemented a clean two-tier API:
  - `POST /api/files/` returns a compact summary with counts of measured features, warnings, and hypermedia links.
  - `GET /api/files/{id}/measurements` returns paginated measurements (25 per page by default).
  - Heavy fields (`geometry` and raw `properties`) are **opt-in** via `?include=geometry,properties`.
  - Single feature inspection is supported via `GET /api/files/{id}/features/{feature_id}`.

### 3. Intelligent Dual-Strategy CRS Engine (`auto`, `projected`, `geodesic`)
- **Problem:** A rigid local-UTM projection failed on **60% of countries** in global datasets:
  - Island archipelagos (`MultiPolygon`) were skipped by single-part projection assumptions.
  - Large countries (Canada, Russia, Tanzania) or antimeridian-crossing island nations (Fiji) span multiple 6° UTM zones, causing severe distortion or projection rejection.
- **Decision:** Implemented an adaptive measurement pipeline with three modes:
  - **`auto` (Default):**
    - **Compact local polygons & lines** (< 4° span): Transformed to the feature's local UTM zone (e.g. `EPSG:32643`) or polar stereographic (`EPSG:3413` / `EPSG:3031`) before measuring in SI units ($m^2$ / $m$).
    - **MultiPolygons, wide extents, and antimeridian features (> 180° span):** Fall back to WGS 84 ellipsoidal math (**geodesic**). Multi-part polygon components are oriented and summed independently without sign cancellation.
  - **`projected`:** Forces local projection across all features for strict UTM testing.
  - **`geodesic`:** Forces WGS 84 ellipsoidal calculation across all features for mathematical reproducibility.

### 4. Semantic Measurement Status & Provenance
- **Decision:** Replaced blanket "error" responses with descriptive statuses:
  - `calculated`: Geometry successfully measured (includes method, values in $m^2$ / $km^2$ / $m$, and accuracy notes).
  - `not_applicable`: Geometries that semantically have no area or length (Points, MultiPoints).
  - `unavailable`: Unparseable CRS or broken geometries.
  - Every geodesic measurement carries an `accuracy_note` clarifying that 1:110m cartographic boundaries are visual approximations, not legal border arbitrations.

### 5. Stable Identifiers vs. Fragile Row Indices
- **Decision:** Features prioritize stable domain identifiers (`ISO_A3` like `FJI`, `NE_ID`, or source feature IDs) instead of brittle zero-based array positions (`0`, `1`, `2`).

### 6. Defense-in-Depth for Shapefile Archives (ZIP)
- **Decision:** Hardened the archive extraction pipeline:
  - **Zip-Slip Protection:** Path traversal attempts (`../../`) are blocked using strict `is_relative_to` path verification.
  - **Nested Folder Extraction:** Recursively searches subdirectories for the required `.shp` file (e.g., `archive.zip -> data/natural_earth/countries.shp`).
  - **Integrity Validation:** Enforces the companion triad (`.shp`, `.shx`, `.dbf`), rejects multi-shapefile archives, encrypted ZIPs, and oversized decompression bombs.

### 7. Zero Information Leakage in Error Handling
- **Decision:** Sanitized all client-facing exceptions via `sanitize_error_detail`. Raw GDAL/OGR exceptions containing internal Windows drive letters, user directories, and workspace UUIDs (`C:\Users\...\data\uploads\<uuid>\...`) are scrubbed before reaching API responses, while complete tracebacks remain safely in server logs.

---

## 🏗️ System Architecture & Data Flows

### Application Structure
```text
GeoSpatial File Measurement API/
├── app/
│   ├── api/
│   │   ├── dependencies.py     # Database session injection
│   │   └── files.py            # Upload, measurement, and feature endpoints
│   ├── core/
│   │   ├── config.py           # App settings & directory management
│   │   └── errors.py           # Custom exceptions & path sanitization
│   ├── db/
│   │   ├── database.py         # SQLAlchemy engine, session maker, SQLite migrations
│   │   └── models.py           # UploadedFile & FeatureMeasurement ORM models
│   ├── services/
│   │   ├── archive.py          # Secure ZIP extraction & Zip-Slip defense
│   │   ├── geospatial.py       # GeoPandas/PyOGRIO dataset parsing & feature normalization
│   │   ├── measurements.py     # Dual-strategy (UTM Projected vs Geodesic) engine
│   │   └── uploads.py          # Upload streaming & persistence orchestration
│   ├── main.py                 # FastAPI app factory, lifespan, & exception handlers
│   └── schemas.py              # Pydantic v2 request & response schemas
├── tests/
│   ├── test_api.py             # End-to-end API upload and pagination tests
│   ├── test_archive.py         # ZIP validation, traversal, & corruption tests
│   └── test_measurements.py    # UTM selection, polar, geodesic, & antimeridian tests
├── Dockerfile                  # Production container definition
├── docker-compose.yml          # Container orchestration
└── pyproject.toml              # Dependencies & build configuration
```

### 1. File-Processing Flow
```text
Client Upload (KML or ZIP)
         │
         ▼
[Validate Size Quota] ──► (Exceeds Limit? ──► 413 Payload Too Large)
         │
         ▼
[Format Classification] ──► (Unknown Extension? ──► 415 Unsupported Media Type)
         │
    ┌────┴────────────────────────┐
    │ (ZIP)                       │ (KML)
    ▼                             ▼
[Safe Archive Extraction]   [Verify WGS 84 CRS]
 ├── Zip-Slip check                │
 ├── Companion files check         │
 └── Nested path resolution        │
    │                             │
    └──────────────┬──────────────┘
                   │
                   ▼
        [GeoPandas / PyOGRIO]
      Read Layer into GeoDataFrame
                   │
                   ▼
    [Iterate Features & Normalize]
 ├── Extract stable ID (ISO_A3 / NE_ID)
 ├── Validate geometry (make_valid)
 └── Store raw attributes dictionary
```

### 2. Measurement Calculation Flow & CRS Strategy
```text
           Input Geometry (Polygon / LineString / Point)
                                │
                                ▼
                       [Point / MultiPoint?]
                             ├── Yes ──► Status: "not_applicable" (No measurement)
                             └── No
                                  │
                                  ▼
                         [Check Source CRS]
                             ├── Missing? ──► Status: "unavailable"
                             └── Declared CRS
                                  │
                                  ▼
                     [Measurement Mode Switch]
       ┌──────────────────────────┼──────────────────────────┐
       │ (Explicit: "geodesic")   │ (Default: "auto")        │ (Explicit: "projected")
       │                          ▼                          │
       │               [Evaluate Geometry Type]              │
       │               ├── Polygon/MultiPolygon?             │
       │               │    ├── Multi-part (MultiPolygon)?   │
       │               │    ├── Spans Antimeridian (>180°)?  │
       │               │    ├── Spans Multiple UTM Zones?    │
       │               │    └── Coordinate span > 4°?        │
       │               └── LineString?                       │
       │                    └── Spans > 4° or Antimeridian?  │
       │                          │                          │
       │                   Any true? ────┐                   │
       │                          │ No   │ Yes               │
       │                          ▼      ▼                   │
       │             ┌────────────────┐  ┌────────────────┐  │
       └────────────►│  WGS 84        │  │ Feature-Local  │◄─┘
                     │  Geodesic Math │  │ Projected CRS  │
                     └───────┬────────┘  └───────┬────────┘
                             │                   │
                             ▼                   ▼
                     Ellipsoidal Area/   Local UTM (or Polar
                     Length on WGS 84    Stereographic) Area/
                     (No CRS required)   Length in Metres
                             │                   │
                             └──────────┬────────┘
                                        │
                                        ▼
                             Persist in Database &
                             Return Measurement Result
```

---

## 🛠️ Built With

- **Framework:** [FastAPI](https://fastapi.tiangolo.com/) with [Uvicorn](https://www.uvicorn.org/)
- **Spatial Processing:** [GeoPandas](https://geopandas.org/), [Shapely 2.0](https://shapely.readthedocs.io/), [PyProj](https://pyproj4.github.io/pyproj/), [PyOGRIO](https://pyogrio.readthedocs.io/)
- **Data Validation:** [Pydantic v2](https://docs.pydantic.dev/)
- **Database & ORM:** [SQLAlchemy 2.0](https://www.sqlalchemy.org/) with SQLite
- **Testing & Quality:** [Pytest](https://pytest.org/), [Ruff](https://astral.sh/ruff), [HTTPX](https://www.python-httpx.org/)

---

## 🚀 Quick Start & Setup

### Prerequisites
- Python 3.11+
- Git

### 1. Local Environment Setup

```powershell
# Clone the repository and enter the directory
cd "GeoSpatial File Measurement API"

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install package with development dependencies
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### 2. Start the Server

```powershell
uvicorn app.main:app --reload
```

- **Base URL:** `http://127.0.0.1:8000`
- **Interactive Swagger Docs:** `http://127.0.0.1:8000/docs`
- **ReDoc Documentation:** `http://127.0.0.1:8000/redoc`

### 3. Alternative: Run via Docker

```powershell
docker compose up --build
```

---

## ⌨️ Available Commands

| Command | Purpose |
| :--- | :--- |
| `uvicorn app.main:app --reload` | Run the live development server |
| `pytest` | Execute the full test suite (19 test cases) |
| `ruff check .` | Run static code analysis and linting |
| `docker compose up --build` | Build and start containerized application |

---

## 📡 API Documentation

### 1. Upload & Process File
`POST /api/files/`

Uploads and processes a geospatial file (`.kml` or `.zip`).

- **Query Parameters:**
  - `measurement_method` *(optional, default: `auto`)*: `auto`, `projected`, or `geodesic`.
- **Form Data:**
  - `file`: Binary file upload.

#### Example Request:
```powershell
# Live Deployment:
curl.exe -X POST "https://geospatial-file-measurement-api-k51h.onrender.com/api/files/?measurement_method=auto" `
  -F "file=@survey.kml"

# Local Server:
curl.exe -X POST "http://127.0.0.1:8000/api/files/?measurement_method=auto" `
  -F "file=@survey.kml"
```

#### Example Response (`201 Created`):
```json
{
  "id": "ee0f29e1-0031-4082-838d-d35df83f3a58",
  "filename": "ne_110m_admin_0_countries.zip",
  "source_crs": "EPSG:4326",
  "feature_count": 177,
  "measurement_method": "auto",
  "summary": {
    "measured": 177,
    "warnings": 0,
    "measurement_method": "geodesic"
  },
  "links": {
    "measurements": "/api/files/ee0f29e1-0031-4082-838d-d35df83f3a58/measurements?limit=25",
    "features": "/api/files/ee0f29e1-0031-4082-838d-d35df83f3a58/features"
  },
  "file_type": "shapefile_zip",
  "status": "COMPLETED",
  "error_message": null,
  "created_at": "2026-10-11T10:00:00Z",
  "completed_at": "2026-10-11T10:00:02Z"
}
```

---

### 2. Get File Information
`GET /api/files/{id}/`

Returns file metadata, processing status, and summary metrics.

---

### 3. Get Paginated Measurements
`GET /api/files/{id}/measurements`

- **Query Parameters:**
  - `limit` *(int, default: 25, max: 100)*: Items per page.
  - `offset` *(int, default: 0)*: Number of items to skip.
  - `include` *(optional)*: `geometry`, `properties`, or `geometry,properties`.

#### Example Response:
```json
{
  "items": [
    {
      "feature_id": "FJI",
      "name": "Fiji",
      "geometry_type": "MultiPolygon",
      "attributes": {
        "NAME_EN": "Fiji",
        "ISO_A3": "FJI",
        "CONTINENT": "Oceania"
      },
      "measurement": {
        "status": "calculated",
        "method": "geodesic",
        "area_m2": 18344321045.2,
        "area_km2": 18344.32,
        "accuracy_note": "Ellipsoidal area on WGS 84; accuracy is limited by the source geometry and is not a legal or official statistical boundary claim."
      }
    }
  ],
  "limit": 25,
  "offset": 0,
  "total": 177
}
```

---

### 4. Browse Features
`GET /api/files/{id}/features`

Returns source features without measurement overhead. Supports `limit`, `offset`, and `?include=geometry,properties`.

---

### 5. Inspect Single Feature
`GET /api/files/{id}/features/{feature_id}`

Fetches full raw GeoJSON coordinates and the complete source attributes dictionary for a single entity (e.g. `FJI`).

---

### 6. Health Check
`GET /health`

Returns liveness status:
```json
{
  "status": "ok"
}
```

---

## 🧪 Testing & Validation

Run the automated test suite:
```powershell
pytest
ruff check .
```

### Test Suite Highlights (19 Tests Passing)
- **Compact Local Projection:** Asserts small polygons and lines are transformed to local UTM (`EPSG:32643`).
- **Polar Coordinate Handling:** Asserts features at extreme latitudes ($\ge 84^\circ$ or $\le -80^\circ$) transform to Polar Stereographic (`EPSG:3413` / `EPSG:3031`).
- **Antimeridian & MultiPolygon:** Asserts Fiji-like island geometries crossing $180^\circ$ longitude receive accurate ellipsoidal areas.
- **Archive Security:** Asserts rejection of Zip-Slip path traversal (`../../`), missing `.dbf`/`.shx` companion files, and multi-shapefile archives.
- **Error Path Sanitization:** Asserts that malformed KML/Shapefile uploads return clean, human-readable errors without leaking internal server paths or drive letters.

---

## 📚 Learnings & Future Scope

### Key Learnings
1. **The Distortion of Planar Projections:** Local projected coordinate systems (like UTM) are exceptional for small cities or farm plots, but attempting to project continental-scale geometries or antimeridian-spanning island chains into a single 2D plane introduces massive distortion or math failure. A hybrid architecture combining projected metric CRS for local extents and ellipsoidal geodesic math for wide extents is essential for real-world resilience.
2. **Defensive Geospatial Parsing:** C-backed GIS libraries (GDAL/GEOS) frequently throw verbose exceptions containing server-side paths. A dedicated error sanitization layer is vital to prevent security disclosures.
3. **Payload Optimization:** Geospatial coordinates balloon JSON payload sizes rapidly. Two-tier APIs with opt-in geometry parameters prevent unnecessary network overhead.

### Future Scope & Roadmap
- [x] Stream uploads with byte-size quotas
- [x] Safe ZIP extraction with Zip-Slip defense
- [x] Dual-strategy calculation (Local UTM + Geodesic fallback)
- [x] MultiPolygon area summation without sign cancellation
- [x] Two-tier API design with pagination and opt-in parameters
- [x] Error sanitization scrubbing internal server paths
- [ ] **Asynchronous Task Queue:** Integrate Celery or Redis Queue for processing multi-gigabyte files asynchronously with status polling.
- [ ] **PostgreSQL / PostGIS Backend:** Replace local SQLite with PostGIS for native spatial indexing and bounding-box queries.
- [ ] **Expanded Geospatial Formats:** Add direct ingestion support for GeoJSON, FlatGeobuf, and GeoPackage (`.gpkg`).
- [ ] **Cloud Storage:** Offload uploaded files to AWS S3 or Google Cloud Storage.

---

## 🤝 Support & Contribution

Contributions, issues, and feature requests are welcome!

- Feel free to check the repository issues page.
- Give a ⭐️ if you like this project!
