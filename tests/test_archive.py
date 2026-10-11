from pathlib import Path
from zipfile import ZipFile

import pytest

from app.core.config import Settings
from app.core.errors import InvalidArchiveError
from app.services.archive import extract_shapefile_archive


def test_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", "not allowed")

    with pytest.raises(InvalidArchiveError, match="unsafe path"):
        extract_shapefile_archive(archive_path, tmp_path / "extracted", _settings(tmp_path))


def test_archive_requires_complete_shapefile_components(tmp_path: Path) -> None:
    archive_path = tmp_path / "incomplete.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("survey.shp", "placeholder")
        archive.writestr("survey.dbf", "placeholder")

    with pytest.raises(InvalidArchiveError, match="missing required component"):
        extract_shapefile_archive(archive_path, tmp_path / "extracted", _settings(tmp_path))


def _settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        data_dir=data_dir,
        upload_dir=data_dir / "uploads",
        database_url=f"sqlite:///{(data_dir / 'test.db').as_posix()}",
        max_upload_bytes=1024 * 1024,
        max_zip_members=10,
        max_zip_uncompressed_bytes=1024 * 1024,
    )
