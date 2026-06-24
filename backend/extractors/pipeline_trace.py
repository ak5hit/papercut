import time
from dataclasses import dataclass, field
from typing import Any

PHASE_READING = "reading"
PHASE_EMBEDDING = "embedding"
PHASE_EXTRACTING = "extracting"
PHASE_BUILDING = "building"
PHASE_LABELS: dict[str, str] = {
    PHASE_READING: "Reading document",
    PHASE_EMBEDDING: "Generating embeddings",
    PHASE_EXTRACTING: "Extracting entities",
    PHASE_BUILDING: "Building knowledge graph",
}


@dataclass
class PipelineTrace:
    extractor: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    _current_phase: str = ""
    _step_start: float = field(default_factory=time.perf_counter, init=False)
    _trace_start: float = field(default_factory=time.perf_counter, init=False)

    def set_phase(self, phase: str) -> None:
        self._current_phase = phase

    def add_step(self, description: str, detail: str | None = None) -> None:
        now = time.perf_counter()
        step: dict[str, Any] = {
            "step": description,
            "duration_ms": round((now - self._step_start) * 1000, 1),
            "phase": self._current_phase,
        }
        if detail:
            step["detail"] = detail
        self.steps.append(step)
        self._step_start = now

    def set_extracted_fields(self, fields: dict[str, Any]) -> None:
        self.extracted_fields = fields

    def to_dict(self) -> dict[str, Any]:
        return {
            "extractor": self.extractor,
            "steps": self.steps,
            "extracted_fields": self.extracted_fields,
            "total_duration_ms": round((time.perf_counter() - self._trace_start) * 1000, 1),
        }
