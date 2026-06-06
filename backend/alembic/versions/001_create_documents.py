"""create documents and document_chunks tables

Revision ID: 001
Revises:
Create Date: 2026-06-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("structured_fields", JSONB, nullable=False, server_default="{}"),
        sa.Column("entities", JSONB, nullable=False, server_default="[]"),
        sa.Column("relationships", JSONB, nullable=False, server_default="[]"),
        sa.Column("extraction_strategy", sa.String(50), nullable=False),
        sa.Column("embedding_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("embedding_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index"),
    )

    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_documents_embedding_status", "documents", ["embedding_status"])


def downgrade() -> None:
    op.drop_index("ix_documents_embedding_status", table_name="documents")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_table("documents")
