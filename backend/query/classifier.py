import json
from dataclasses import dataclass
from typing import Any

from llm.base import LLMProvider


@dataclass
class ClassificationResult:
    category: str = "SEMANTIC"
    document_type: str | None = None
    field_filters: dict[str, Any] | None = None
    entity_name: str | None = None


class QueryClassifier:
    _PROMPT = (
        "Classify this query and extract any filters. Return ONLY valid JSON:\n"
        "{{\n"
        '  "category": "STRUCTURED" | "SEMANTIC" | "HYBRID",\n'
        '  "document_type": "resume" | null,\n'
        '  "field_filters": {{"key": "value"}} | null,\n'
        '  "entity_name": "org or person" | null\n'
        "}}\n"
        "\n"
        "CATEGORY RULES:\n"
        "- STRUCTURED: Asking for a specific value from fields — email, phone, "
        "skills, name, company, role, dates, counts. Answer is a lookup.\n"
        "- SEMANTIC: Asking to explain, summarize, describe, or interpret "
        "WITHOUT targeting a specific entity. "
        "Answer requires natural language synthesis.\n"
        "- HYBRID: The question mentions a specific company or organization "
        "(e.g., 'at CRED', 'at Google', 'worked at Udaan'). "
        "Always classify as HYBRID and set entity_name.\n"
        "\n"
        "FILTER RULES:\n"
        "- field_filters ONLY for concrete fields: skills, email, phone, "
        "name, location, current_role, document_type.\n"
        "- entity_name: extract ONLY the organization name that is explicitly "
        "mentioned in the question after 'at', 'at company', 'worked at', "
        "'work at', or 'role at'. Use the EXACT name from the question.\n"
        "- If no specific company is mentioned, set entity_name to null.\n"
        "- CRITICAL: Do NOT guess, hallucinate, or invent entity names. "
        "Use null if the question does not explicitly contain a company name.\n"
        "\n"
        "EXAMPLES:\n"
        '"What is Akshit email?" -> '
        '{{"category": "STRUCTURED", "document_type": null, '
        '"field_filters": null, "entity_name": null}}\n'
        '"Show candidates with Python skills" -> '
        '{{"category": "STRUCTURED", "document_type": "resume", '
        '"field_filters": {{"skills": "Python"}}, "entity_name": null}}\n'
        '"Summarize the work experience" -> '
        '{{"category": "SEMANTIC", "document_type": null, '
        '"field_filters": null, "entity_name": null}}\n'
        '"What did John do at Google?" -> '
        '{{"category": "HYBRID", "document_type": null, '
        '"field_filters": null, "entity_name": "Google"}}\n'
        '"List responsibilities at Udaan" -> '
        '{{"category": "HYBRID", "document_type": null, '
        '"field_filters": null, "entity_name": "Udaan"}}\n'
        '"What did this person do at CRED?" -> '
        '{{"category": "HYBRID", "document_type": null, '
        '"field_filters": null, "entity_name": "CRED"}}\n'
        '"How long has Akshit been a software engineer?" -> '
        '{{"category": "SEMANTIC", "document_type": null, '
        '"field_filters": null, "entity_name": null}}\n'
        '"List the responsibilities at Udaan" -> '
        '{{"category": "HYBRID", "document_type": "resume", '
        '"field_filters": null, "entity_name": "Udaan"}}\n'
        '"How long has Akshit been a software engineer?" -> '
        '{{"category": "SEMANTIC", "document_type": null, '
        '"field_filters": null, "entity_name": null}}\n'
        "\n"
        "IMPORTANT: Output ONLY the raw JSON object. Do NOT wrap it in "
        "```json fences. Do NOT add any text before or after the JSON.\n"
        "\n"
        "QUESTION: {question}\n"
    )

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    async def classify(self, question: str) -> ClassificationResult:
        prompt = self._PROMPT.format(question=question)
        response = await self._llm.complete(prompt, max_tokens=300)
        try:
            data = json.loads(response)
            return ClassificationResult(
                category=data.get("category", "SEMANTIC"),
                document_type=data.get("document_type"),
                field_filters=data.get("field_filters"),
                entity_name=data.get("entity_name"),
            )
        except json.JSONDecodeError:
            print(f"\n[CLASSIFIER] JSON parse failed for: {question!r}")
            print(f"[CLASSIFIER] Raw LLM response: {response!r}\n")
            return ClassificationResult()
