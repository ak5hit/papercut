from typing import Any

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from models.db_models import DocumentModel


class StructuredRetriever:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self,
        field_filters: dict[str, Any] | None = None,
        entity_name: str | None = None,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        stmt = select(DocumentModel)

        if field_filters:
            for key, value in field_filters.items():
                if isinstance(value, dict | list):
                    stmt = stmt.where(
                        DocumentModel.structured_fields.contains(cast({key: value}, JSONB))
                    )
                else:
                    stmt = stmt.where(
                        DocumentModel.structured_fields[key].astext == str(value)
                    )

        if entity_name:
            stmt = stmt.where(
                DocumentModel.entities.contains(
                    cast([{"name": entity_name}], JSONB)
                )
            )

        if entity_type:
            stmt = stmt.where(
                DocumentModel.entities.contains(
                    cast([{"type": entity_type}], JSONB)
                )
            )

        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        rows = result.scalars().all()

        return [
            {
                "id": str(row.id),
                "metadata": row.metadata_,
                "structured_fields": row.structured_fields,
                "entities": row.entities,
                "extraction_strategy": row.extraction_strategy,
            }
            for row in rows
        ]
