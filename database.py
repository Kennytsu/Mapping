"""Database setup with SQLAlchemy async engine for PostgreSQL."""

import os
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean, ForeignKey, UniqueConstraint,
    DateTime, create_engine, text,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None

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
    embedding = Column(Vector(1536), nullable=True) if Vector else Column(Text, nullable=True)

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
    implementation_status = Column(String(20), default="not_assessed")  # not_assessed, implemented, partial, not_implemented
    owner = Column(String(200), default="")
    review_date = Column(String(20), default="")
    evidence_notes = Column(Text, default="")

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


# ---------------------------------------------------------------------------
# Compliance Checking Models (ARC + RAG frameworks)
# ---------------------------------------------------------------------------


class RegulationDocument(Base):
    __tablename__ = "regulation_documents"

    id = Column(Integer, primary_key=True)
    name = Column(String(500), nullable=False)
    short_name = Column(String(100), nullable=False)
    version = Column(String(50), default="")
    jurisdiction = Column(String(200), default="")
    full_text = Column(Text, default="")
    language = Column(String(10), default="en")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    tuples = relationship("ArcTuple", back_populates="regulation", cascade="all, delete-orphan")
    eventic_nodes = relationship("EventicGraphNode", back_populates="regulation", cascade="all, delete-orphan")
    term_definitions = relationship("TermDefinition", back_populates="regulation", cascade="all, delete-orphan")


class ArcTuple(Base):
    """Structured representation of regulatory statements (ARC framework).

    Three types: data_flow, definition, right.
    """
    __tablename__ = "arc_tuples"

    id = Column(Integer, primary_key=True)
    regulation_id = Column(Integer, ForeignKey("regulation_documents.id"), nullable=False)
    tuple_type = Column(String(20), nullable=False)  # data_flow | definition | right
    source_statement = Column(Text, default="")
    verb = Column(String(100), default="")
    deontic_modal = Column(String(50), default="")  # obligation | permission | prohibition

    # Data Flow Tuple attributes (CI framework)
    sender_phrase = Column(Text, default="")
    sender_clause = Column(Text, default="")
    receiver_phrase = Column(Text, default="")
    receiver_clause = Column(Text, default="")
    data_phrase = Column(Text, default="")
    data_clause = Column(Text, default="")
    transmission_principle = Column(Text, default="")

    # Definition Tuple attributes
    definiendum = Column(Text, default="")  # term being defined
    definiens = Column(Text, default="")    # description/definition

    # Right Tuple attributes
    right_entity = Column(Text, default="")
    right_statement = Column(Text, default="")

    regulation = relationship("RegulationDocument", back_populates="tuples")


class EventicGraphNode(Base):
    """Nodes in the eventic knowledge graph (RAG framework dynamic layer).

    Node types: organization, person, regulatory_document, category, action, state.
    """
    __tablename__ = "eventic_graph_nodes"

    id = Column(Integer, primary_key=True)
    regulation_id = Column(Integer, ForeignKey("regulation_documents.id"), nullable=True)
    node_type = Column(String(50), nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=True) if Vector else Column(Text, nullable=True)

    regulation = relationship("RegulationDocument", back_populates="eventic_nodes")
    outgoing_edges = relationship(
        "EventicGraphEdge", foreign_keys="EventicGraphEdge.source_node_id",
        back_populates="source_node", cascade="all, delete-orphan",
    )
    incoming_edges = relationship(
        "EventicGraphEdge", foreign_keys="EventicGraphEdge.target_node_id",
        back_populates="target_node", cascade="all, delete-orphan",
    )


class EventicGraphEdge(Base):
    """Edges in the eventic knowledge graph.

    Relation types: publish, work_for, duty, prohibited, right, classified_to, cite.
    """
    __tablename__ = "eventic_graph_edges"

    id = Column(Integer, primary_key=True)
    source_node_id = Column(Integer, ForeignKey("eventic_graph_nodes.id"), nullable=False)
    target_node_id = Column(Integer, ForeignKey("eventic_graph_nodes.id"), nullable=False)
    relation_type = Column(String(50), nullable=False)

    source_node = relationship("EventicGraphNode", foreign_keys=[source_node_id], back_populates="outgoing_edges")
    target_node = relationship("EventicGraphNode", foreign_keys=[target_node_id], back_populates="incoming_edges")


class TermDefinition(Base):
    """Term definitions extracted from regulatory documents (static layer)."""
    __tablename__ = "term_definitions"

    id = Column(Integer, primary_key=True)
    regulation_id = Column(Integer, ForeignKey("regulation_documents.id"), nullable=False)
    term = Column(String(500), nullable=False)
    definition = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=True) if Vector else Column(Text, nullable=True)

    regulation = relationship("RegulationDocument", back_populates="term_definitions")


class BusinessProcessDocument(Base):
    """Business process documents to check for compliance."""
    __tablename__ = "business_process_documents"

    id = Column(Integer, primary_key=True)
    name = Column(String(500), nullable=False)
    full_text = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    chunks = relationship("BusinessProcessChunk", back_populates="document", cascade="all, delete-orphan")


class BusinessProcessChunk(Base):
    """Chunked business process text with embeddings for vector search."""
    __tablename__ = "business_process_chunks"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("business_process_documents.id"), nullable=False)
    text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    embedding = Column(Vector(768), nullable=True) if Vector else Column(Text, nullable=True)

    document = relationship("BusinessProcessDocument", back_populates="chunks")


class ComplianceCheck(Base):
    """Results of compliance checking (computational layer output)."""
    __tablename__ = "compliance_checks"

    id = Column(Integer, primary_key=True)
    business_process_chunk = Column(Text, nullable=False)
    regulation_id = Column(Integer, ForeignKey("regulation_documents.id"), nullable=False)
    result = Column(String(20), nullable=False)  # compliant | non_compliant | undetermined
    explanation = Column(Text, default="")
    conflicting_triples = Column(Text, default="")  # JSON of conflicting knowledge
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    regulation = relationship("RegulationDocument")


async def ensure_pgvector():
    """Enable the pgvector extension if available."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


async def init_db():
    """Create pgvector extension and all tables."""
    await ensure_pgvector()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def init_db_sync():
    """Create all tables synchronously (for seed script)."""
    with sync_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(sync_engine)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
