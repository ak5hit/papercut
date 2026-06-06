from query.result import QueryResult


class ContextExtractor:
    @staticmethod
    def extract(result: QueryResult) -> list[str]:
        contexts: list[str] = []

        for chunk in result.chunks:
            contexts.append(chunk["text"])

        for doc in result.documents:
            fields = doc.get("structured_fields", {})
            if fields:
                kv_pairs = ", ".join(f"{k}={v}" for k, v in fields.items())
                contexts.append(
                    f"Structured fields from "
                    f"{doc.get('metadata', {}).get('filename', 'unknown')}: "
                    f"{kv_pairs}"
                )
            entities = doc.get("entities", [])
            if entities:
                entity_texts = ", ".join(
                    f"{e.get('name')} ({e.get('type')})" for e in entities
                )
                contexts.append(f"Entities: {entity_texts}")

        if not contexts:
            contexts = ["No context was retrieved for this query."]

        return contexts
