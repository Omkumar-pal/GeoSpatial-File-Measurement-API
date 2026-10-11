"""FastAPI application factory and process entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.files import router as files_router
from app.core.config import Settings
from app.core.errors import AppError
from app.db.database import Database
from app.schemas import ErrorResponse, HealthResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create a configured app, allowing tests to inject isolated local settings."""
    resolved_settings = settings or Settings.from_env()
    database = Database(resolved_settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_settings.prepare_directories()
        database.create_schema()
        yield
        database.dispose()

    app = FastAPI(
        title="Geospatial File Measurement API",
        version="0.1.0",
        description="Upload KML or Shapefile ZIP files and receive CRS-aware measurements.",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = database
    app.include_router(files_router)

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(error=exc.message, code=exc.code).model_dump(),
        )

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


app = create_app()
