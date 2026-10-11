"""Runtime settings with safe local defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """All application settings required by the first local deployment."""

    data_dir: Path
    upload_dir: Path
    database_url: str
    max_upload_bytes: int
    max_zip_members: int
    max_zip_uncompressed_bytes: int

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = Path(os.getenv("DATA_DIR", "data")).expanduser().resolve()
        database_url = os.getenv(
            "DATABASE_URL", f"sqlite:///{(data_dir / 'geospatial.db').as_posix()}"
        )
        return cls(
            data_dir=data_dir,
            upload_dir=data_dir / "uploads",
            database_url=database_url,
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))),
            max_zip_members=int(os.getenv("MAX_ZIP_MEMBERS", "500")),
            max_zip_uncompressed_bytes=int(
                os.getenv("MAX_ZIP_UNCOMPRESSED_BYTES", str(500 * 1024 * 1024))
            ),
        )

    def prepare_directories(self) -> None:
        """Create only the application-owned directories required at runtime."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
