"""add compliance checking tables

Revision ID: 001_compliance_tables
Revises:
Create Date: 2026-05-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "001_compliance_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "regulation_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("short_name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), server_default=""),
        sa.Column("jurisdiction", sa.String(200), server_default=""),
        sa.Column("full_text", sa.Text(), server_default=""),
        sa.Column("language", sa.String(10), server_default="en"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "arc_tuples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("regulation_id", sa.Integer(), sa.ForeignKey("regulation_documents.id"), nullable=False),
        sa.Column("tuple_type", sa.String(20), nullable=False),
        sa.Column("source_statement", sa.Text(), server_default=""),
        sa.Column("verb", sa.String(100), server_default=""),
        sa.Column("deontic_modal", sa.String(50), server_default=""),
        sa.Column("sender_phrase", sa.Text(), server_default=""),
        sa.Column("sender_clause", sa.Text(), server_default=""),
        sa.Column("receiver_phrase", sa.Text(), server_default=""),
        sa.Column("receiver_clause", sa.Text(), server_default=""),
        sa.Column("data_phrase", sa.Text(), server_default=""),
        sa.Column("data_clause", sa.Text(), server_default=""),
        sa.Column("transmission_principle", sa.Text(), server_default=""),
        sa.Column("definiendum", sa.Text(), server_default=""),
        sa.Column("definiens", sa.Text(), server_default=""),
        sa.Column("right_entity", sa.Text(), server_default=""),
        sa.Column("right_statement", sa.Text(), server_default=""),
    )

    op.create_table(
        "eventic_graph_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("regulation_id", sa.Integer(), sa.ForeignKey("regulation_documents.id"), nullable=True),
        sa.Column("node_type", sa.String(50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
    )
    op.execute("ALTER TABLE eventic_graph_nodes ALTER COLUMN embedding TYPE vector(768) USING embedding::vector(768)")

    op.create_table(
        "eventic_graph_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_node_id", sa.Integer(), sa.ForeignKey("eventic_graph_nodes.id"), nullable=False),
        sa.Column("target_node_id", sa.Integer(), sa.ForeignKey("eventic_graph_nodes.id"), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
    )

    op.create_table(
        "term_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("regulation_id", sa.Integer(), sa.ForeignKey("regulation_documents.id"), nullable=False),
        sa.Column("term", sa.String(500), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
    )
    op.execute("ALTER TABLE term_definitions ALTER COLUMN embedding TYPE vector(768) USING embedding::vector(768)")

    op.create_table(
        "business_process_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("full_text", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "business_process_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("business_process_documents.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
    )
    op.execute("ALTER TABLE business_process_chunks ALTER COLUMN embedding TYPE vector(768) USING embedding::vector(768)")

    op.create_table(
        "compliance_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_process_chunk", sa.Text(), nullable=False),
        sa.Column("regulation_id", sa.Integer(), sa.ForeignKey("regulation_documents.id"), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("explanation", sa.Text(), server_default=""),
        sa.Column("conflicting_triples", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("compliance_checks")
    op.drop_table("business_process_chunks")
    op.drop_table("business_process_documents")
    op.drop_table("term_definitions")
    op.drop_table("eventic_graph_edges")
    op.drop_table("eventic_graph_nodes")
    op.drop_table("arc_tuples")
    op.drop_table("regulation_documents")
