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
        '"What did this person do at CRED?" -> '
        '{{"category": "HYBRID", "document_type": null, '
        '"field_filters": null, "entity_name": "CRED"}}\n'
        "\n"
        "CRITICAL: Your entire response must be ONLY a valid JSON object. "
        "Start directly with {{ and end with }}. "
        "No reasoning, no explanation, no markdown, no other text.\n"
        "\n"
        "QUESTION: {question}\n"
    )

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    async def classify(self, question: str) -> ClassificationResult:
        lower = question.lower()
        if any(kw in lower for kw in ["email", "phone", "linkedin", "url", "github", "twitter"]):
            return ClassificationResult(category="STRUCTURED")

        prompt = self._PROMPT.format(question=question)
        response = await self._llm.complete(prompt, max_tokens=500)
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}")
            if start != -1 and end > start:
                try:
                    data = json.loads(response[start:end + 1])
                except json.JSONDecodeError:
                    print(f"\n[CLASSIFIER] JSON extraction failed for: {question!r}")
                    print(f"[CLASSIFIER] Raw LLM response: {response!r}\n")
                    return ClassificationResult()
            else:
                print(f"\n[CLASSIFIER] No JSON found in response for: {question!r}")
                print(f"[CLASSIFIER] Raw LLM response: {response!r}\n")
                return ClassificationResult()
        return ClassificationResult(
            category=data.get("category", "SEMANTIC"),
            document_type=data.get("document_type"),
            field_filters=data.get("field_filters"),
            entity_name=data.get("entity_name"),
        )
