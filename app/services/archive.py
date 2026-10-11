"""Safe validation and extraction of Shapefile ZIP archives."""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.core.config import Settings
from app.core.errors import InvalidArchiveError, UnsupportedFileError


@dataclass(frozen=True, slots=True)
class ArchiveContents:
    """The validated primary Shapefile inside a safely extracted archive."""

    shapefile_path: Path


def classify_upload(filename: str | None) -> str:
    """Return the supported type identified by filename, or reject the upload."""
    clean_name = (filename or "").strip()
    suffix = Path(clean_name).suffix.lower()
    if suffix == ".kml":
        return "kml"
    if suffix == ".zip":
        return "shapefile_zip"
    raise UnsupportedFileError("Upload a .kml file or a .zip archive containing one Shapefile.")


def safe_upload_name(filename: str | None, fallback: str) -> str:
    """Strip directory components so a client never controls the storage path."""
    raw_name = (filename or fallback).replace("\\", "/")
    name = PurePosixPath(raw_name).name
    return name or fallback


def extract_shapefile_archive(
    archive_path: Path, destination: Path, settings: Settings
) -> ArchiveContents:
    """Validate a ZIP archive then extract exactly one complete Shapefile set."""
    if not zipfile.is_zipfile(archive_path):
        raise InvalidArchiveError("The .zip upload is not a valid ZIP archive.")

    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        members = _validate_members(archive, settings)
        for member in members:
            relative = PurePosixPath(member.filename)
            target = destination.joinpath(*relative.parts).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise InvalidArchiveError("The archive contains an unsafe path.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)

    shapefiles = sorted(destination.rglob("*.shp"))
    if len(shapefiles) != 1:
        raise InvalidArchiveError("The archive must contain exactly one .shp file.")

    shapefile = shapefiles[0]
    required_suffixes = {".shp", ".shx", ".dbf"}
    available_suffixes = {path.suffix.lower() for path in shapefile.parent.glob(f"{shapefile.stem}.*")}
    missing_suffixes = required_suffixes - available_suffixes
    if missing_suffixes:
        missing = ", ".join(sorted(missing_suffixes))
        raise InvalidArchiveError(f"The Shapefile is incomplete; missing required component(s): {missing}.")

    return ArchiveContents(shapefile_path=shapefile)


def _validate_members(archive: zipfile.ZipFile, settings: Settings) -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    uncompressed_size = 0
    for member in archive.infolist():
        if member.is_dir():
            continue
        if member.flag_bits & 0x1:
            raise InvalidArchiveError("Password-protected archives are not supported.")
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or not path.name:
            raise InvalidArchiveError("The archive contains an unsafe path.")
        members.append(member)
        uncompressed_size += member.file_size

        if len(members) > settings.max_zip_members:
            raise InvalidArchiveError("The archive contains too many files.")
        if uncompressed_size > settings.max_zip_uncompressed_bytes:
            raise InvalidArchiveError("The archive expands beyond the configured size limit.")

    if not members:
        raise InvalidArchiveError("The archive is empty.")
    return members
