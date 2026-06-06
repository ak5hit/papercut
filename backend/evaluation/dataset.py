from collections.abc import Iterator
from dataclasses import dataclass


@dataclass
class EvaluationDataset:
    questions: list[str]
    ground_truths: list[str]

    def __post_init__(self) -> None:
        if len(self.questions) != len(self.ground_truths):
            raise ValueError(
                f"questions ({len(self.questions)}) and ground_truths "
                f"({len(self.ground_truths)}) must have the same length"
            )

    def __len__(self) -> int:
        return len(self.questions)

    def __iter__(self) -> Iterator[tuple[str, str]]:
        return iter(zip(self.questions, self.ground_truths))
