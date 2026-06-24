"""add ingestion status and chunk metadata

Revision ID: 004
Revises: 002
Create Date: 2026-06-21
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("status", sa.String(20), nullable=False, server_default="completed"))
    op.add_column("documents", sa.Column("model", sa.String(100), nullable=True))
    op.add_column("documents", sa.Column("embedding_model", sa.String(100), nullable=True))
    op.add_column("documents", sa.Column("token_usage", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("processed_chunk", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("node_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("rel_count", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("document_chunks", sa.Column("content_hash", sa.String(40), nullable=True))
    op.add_column("document_chunks", sa.Column("position", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("document_chunks", sa.Column("length", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("document_chunks", sa.Column("content_offset", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("document_chunks", sa.Column("page_number", sa.Integer(), nullable=True))

    op.execute(
        "ALTER TABLE document_chunks "
        "ADD COLUMN tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED"
    )
    op.create_index(
        "ux_document_chunks_content_hash",
        "document_chunks",
        ["content_hash"],
        postgresql_where=sa.text("content_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_document_chunks_tsv",
        "document_chunks",
        ["tsv"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_tsv", table_name="document_chunks")
    op.drop_index("ux_document_chunks_content_hash", table_name="document_chunks")
    op.execute("ALTER TABLE document_chunks DROP COLUMN tsv")
    op.drop_column("document_chunks", "page_number")
    op.drop_column("document_chunks", "content_offset")
    op.drop_column("document_chunks", "length")
    op.drop_column("document_chunks", "position")
    op.drop_column("document_chunks", "content_hash")
    op.drop_column("documents", "rel_count")
    op.drop_column("documents", "node_count")
    op.drop_column("documents", "processed_chunk")
    op.drop_column("documents", "total_chunks")
    op.drop_column("documents", "token_usage")
    op.drop_column("documents", "embedding_model")
    op.drop_column("documents", "model")
    op.drop_column("documents", "status")
