from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionTrace:
    strategy: str
    steps: list[str] = field(default_factory=list)
    structured_results_count: int = 0
    semantic_results_count: int = 0

    def add_step(self, description: str) -> None:
        self.steps.append(description)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "steps": self.steps,
            "structured_results_count": self.structured_results_count,
            "semantic_results_count": self.semantic_results_count,
        }
