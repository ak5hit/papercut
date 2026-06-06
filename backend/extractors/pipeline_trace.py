from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineTrace:
    extractor: str
    steps: list[dict[str, str]] = field(default_factory=list)
    extracted_fields: dict[str, Any] = field(default_factory=dict)

    def add_step(self, description: str, detail: str | None = None) -> None:
        step: dict[str, str] = {"step": description}
        if detail:
            step["detail"] = detail
        self.steps.append(step)

    def set_extracted_fields(self, fields: dict[str, Any]) -> None:
        self.extracted_fields = fields

    def to_dict(self) -> dict[str, Any]:
        return {
            "extractor": self.extractor,
            "steps": self.steps,
            "extracted_fields": self.extracted_fields,
        }
