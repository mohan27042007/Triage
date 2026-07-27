"""Run the synthetic Triage classification corpus against the configured model."""

from __future__ import annotations

import json

from classifier import classify
from evaluation import calculate_metrics, load_corpus, quality_gate_failures


def main() -> None:
    corpus = load_corpus()
    predictions = {
        item["id"]: classify(item["text"])
        for item in corpus["items"]
    }
    metrics = calculate_metrics(corpus, predictions)
    failures = quality_gate_failures(metrics)
    print(json.dumps(metrics, indent=2, sort_keys=True))
    if failures:
        raise SystemExit("Evaluation gate failed:\n- " + "\n- ".join(failures))
    print("Evaluation gate passed.")


if __name__ == "__main__":
    main()
