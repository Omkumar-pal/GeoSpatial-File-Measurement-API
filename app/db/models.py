"""Persistent representation of uploaded files and their extracted features."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class ProcessingStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default=ProcessingStatus.PENDING.value)
    feature_count: Mapped[int] = mapped_column(Integer, default=0)
    source_crs: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    features: Mapped[list[FeatureMeasurement]] = relationship(
        back_populates="uploaded_file",
        cascade="all, delete-orphan",
        order_by="FeatureMeasurement.feature_index",
    )


class FeatureMeasurement(Base):
    __tablename__ = "feature_measurements"
    __table_args__ = (UniqueConstraint("uploaded_file_id", "feature_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    uploaded_file_id: Mapped[str] = mapped_column(ForeignKey("uploaded_files.id"), index=True)
    feature_index: Mapped[int] = mapped_column(Integer)
    source_feature_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geometry_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    source_crs: Mapped[str | None] = mapped_column(String(128), nullable=True)
    measurement_crs: Mapped[str | None] = mapped_column(String(128), nullable=True)
    area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_file: Mapped[UploadedFile] = relationship(back_populates="features")
