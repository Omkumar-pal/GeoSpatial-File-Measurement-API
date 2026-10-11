"""Expected application errors with client-safe messages."""

from __future__ import annotations

import re

_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']*")
_POSIX_PATH_RE = re.compile(r"/[^\s\"']*(?:uploads|data)[^\s\"']*")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def sanitize_error_detail(detail: str, safe_filename: str | None = None) -> str:
    """Remove server-side paths and workspace identifiers from client errors.

    Driver/projection libraries often echo the absolute file they failed on.
    Clients must only ever see the upload filename (or nothing at all), never
    ``C:\\...\\data\\uploads\\<uuid>\\...``.
    """
    cleaned = _WINDOWS_PATH_RE.sub(safe_filename or "<file>", detail)
    cleaned = _POSIX_PATH_RE.sub(safe_filename or "<file>", cleaned)
    cleaned = _UUID_RE.sub("<id>", cleaned)
    # Collapse leakage-prone directory mentions left behind by substitutions.
    cleaned = re.sub(r"\S*uploads\S*", safe_filename or "<file>", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" :.-")


class AppError(Exception):
    """Base class for errors that are safe to report to API clients."""

    status_code = 400
    code = "request_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnsupportedFileError(AppError):
    status_code = 415
    code = "unsupported_file"


class InvalidArchiveError(AppError):
    status_code = 400
    code = "invalid_archive"


class UploadTooLargeError(AppError):
    status_code = 413
    code = "upload_too_large"


class ProcessingError(AppError):
    status_code = 422
    code = "processing_error"
