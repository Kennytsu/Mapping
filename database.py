"""Database setup with SQLAlchemy async engine for PostgreSQL."""

import os
from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean, ForeignKey, UniqueConstraint,
    create_engine, text,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://compliance:compliance_dev@localhost:5432/compliance_mapping",
)
DATABASE_URL_SYNC = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql+psycopg2://compliance:compliance_dev@localhost:5432/compliance_mapping",
)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

sync_engine = create_engine(DATABASE_URL_SYNC, echo=False)
SyncSession = sessionmaker(bind=sync_engine)


class Base(DeclarativeBase):
    pass


class Framework(Base):
    __tablename__ = "frameworks"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    short_name = Column(String(50), nullable=False, unique=True)
    version = Column(String(50), nullable=False)
    description = Column(Text, default="")
    is_active = Column(Boolean, default=True)

    controls = relationship("Control", back_populates="framework", cascade="all, delete-orphan")


class Control(Base):
    __tablename__ = "controls"

    id = Column(Integer, primary_key=True)
    framework_id = Column(Integer, ForeignKey("frameworks.id"), nullable=False)
    control_id = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False, default="")
    description = Column(Text, default="")
    category = Column(String(100), default="")

    framework = relationship("Framework", back_populates="controls")

    __table_args__ = (
        UniqueConstraint("framework_id", "control_id", name="uq_framework_control"),
    )


class Mapping(Base):
    __tablename__ = "mappings"

    id = Column(Integer, primary_key=True)
    source_control_id = Column(Integer, ForeignKey("controls.id"), nullable=False)
    target_control_id = Column(Integer, ForeignKey("controls.id"), nullable=False)
    confidence = Column(Float, default=1.0)
    source_type = Column(String(50), default="official")
    source_document = Column(String(200), default="")
    notes = Column(Text, default="")

    source_control = relationship("Control", foreign_keys=[source_control_id])
    target_control = relationship("Control", foreign_keys=[target_control_id])


class VersionChange(Base):
    __tablename__ = "version_changes"

    id = Column(Integer, primary_key=True)
    framework_id = Column(Integer, ForeignKey("frameworks.id"), nullable=False)
    old_version = Column(String(50), nullable=False)
    new_version = Column(String(50), nullable=False)
    change_type = Column(String(50), nullable=False)
    old_control_id = Column(String(50), default="")
    new_control_id = Column(String(50), default="")
    description = Column(Text, default="")
    category = Column(String(100), default="")

    framework = relationship("Framework")


async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def init_db_sync():
    """Create all tables synchronously (for seed script)."""
    Base.metadata.create_all(sync_engine)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
