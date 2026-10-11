"""FastAPI dependencies shared by API routers."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session


def get_db_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.database.session() as session:
        yield session
