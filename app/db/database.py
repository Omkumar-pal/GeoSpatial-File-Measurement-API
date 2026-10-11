"""SQLAlchemy engine and session lifecycle."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base


class Database:
    """Owns the database engine and hands out short-lived unit-of-work sessions."""

    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(database_url, connect_args=connect_args)
        self._sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        self._ensure_measurement_columns()

    def _ensure_measurement_columns(self) -> None:
        """Add measurement columns to pre-existing SQLite databases.

        Fresh databases already have the columns via ``create_all``. Older
        local ``data/geospatial.db`` files do not, so add them idempotently.
        """
        with self.engine.begin() as connection:
            uploaded_cols = {
                row[1] for row in connection.execute(
                    text("PRAGMA table_info(uploaded_files)")
                ).fetchall()
            }
            if "uploaded_files" in {
                row[0]
                for row in connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).fetchall()
            }:
                if "measurement_method" not in uploaded_cols:
                    connection.execute(
                        text(
                            "ALTER TABLE uploaded_files "
                            "ADD COLUMN measurement_method VARCHAR(16) NOT NULL DEFAULT 'auto'"
                        )
                    )
            feature_cols = {
                row[1] for row in connection.execute(
                    text("PRAGMA table_info(feature_measurements)")
                ).fetchall()
            }
            if "measurement_method" not in feature_cols:
                connection.execute(
                    text(
                        "ALTER TABLE feature_measurements "
                        "ADD COLUMN measurement_method VARCHAR(16)"
                    )
                )
            if "accuracy_note" not in feature_cols:
                connection.execute(
                    text("ALTER TABLE feature_measurements ADD COLUMN accuracy_note TEXT")
                )

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()
