import csv
from pathlib import Path

from evaluation.harness import EvaluationResult


class EvaluationReporter:
    def print_summary(self, result: EvaluationResult) -> None:
        print("\n" + "=" * 50)
        print("EVALUATION RESULTS")
        print("=" * 50)

        for metric, score in result.overall_scores.items():
            print(f"  {metric}: {score}")

        print("\nPer-question breakdown:")
        for item in result.per_question:
            print(
                f"  Q: {item['question'][:60]}... "
                f"F={item['faithfulness']} CP={item['context_precision']}"
            )

        print("=" * 50)

    def save_csv(self, result: EvaluationResult, path: str | Path) -> None:
        path = Path(path)
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "question",
                    "answer",
                    "ground_truth",
                    "faithfulness",
                    "context_precision",
                ],
            )
            writer.writeheader()
            for item in result.per_question:
                writer.writerow(item)
        print(f"Saved detailed results to {path}")
