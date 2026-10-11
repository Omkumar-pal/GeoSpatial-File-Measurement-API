"""Expected application errors with client-safe messages."""


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
