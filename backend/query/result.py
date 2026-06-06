from dataclasses import dataclass, field
from typing import Any

from query.execution_trace import ExecutionTrace


@dataclass
class QueryResult:
    trace: ExecutionTrace
    documents: list[dict[str, Any]] = field(default_factory=list)
    chunks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace": self.trace.to_dict(),
            "documents": self.documents,
            "chunks": self.chunks,
        }
