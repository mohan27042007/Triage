"""Synthetic classification-evaluation helpers for Triage v2 safety gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CORPUS_PATH = Path(__file__).parent / "evaluations" / "corpus_v1.json"
VALID_CATEGORIES = {"Obligation", "Study Material", "Noise"}
MINIMUM_CORPUS_SIZE = 12


def load_corpus(path: Path = CORPUS_PATH) -> dict[str, Any]:
    """Load and validate the committed synthetic corpus."""
    try:
        corpus = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load evaluation corpus: {exc}") from exc
    validate_corpus(corpus)
    return corpus


def validate_corpus(corpus: object) -> None:
    """Reject malformed, undersized, or unexpectedly sensitive-looking fixtures."""
    if not isinstance(corpus, dict) or not isinstance(corpus.get("version"), str):
        raise ValueError("Evaluation corpus must contain a string version.")
    items = corpus.get("items")
    if not isinstance(items, list) or len(items) < MINIMUM_CORPUS_SIZE:
        raise ValueError(f"Evaluation corpus must contain at least {MINIMUM_CORPUS_SIZE} items.")

    identifiers: set[str] = set()
    must_detect_count = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Evaluation corpus items must be objects.")
        identifier = item.get("id")
        text = item.get("text")
        expected_category = item.get("expected_category")
        must_detect = item.get("must_detect_obligation")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("Evaluation corpus item IDs must be unique non-empty strings.")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Evaluation corpus item {identifier!r} has no text.")
        if expected_category not in VALID_CATEGORIES:
            raise ValueError(f"Evaluation corpus item {identifier!r} has an invalid category.")
        if not isinstance(must_detect, bool):
            raise ValueError(f"Evaluation corpus item {identifier!r} must declare must_detect_obligation.")
        if must_detect and expected_category != "Obligation":
            raise ValueError(f"Only obligations may be marked must_detect_obligation ({identifier!r}).")
        identifiers.add(identifier)
        must_detect_count += int(must_detect)
    if must_detect_count < 4:
        raise ValueError("Evaluation corpus must include at least four must-detect obligations.")


def calculate_metrics(corpus: dict[str, Any], predictions: dict[str, object]) -> dict[str, Any]:
    """Calculate category, obligation-recall, and safety-gate metrics."""
    items = corpus["items"]
    expected_identifiers = {item["id"] for item in items}
    if set(predictions) != expected_identifiers:
        missing = sorted(expected_identifiers - set(predictions))
        unexpected = sorted(set(predictions) - expected_identifiers)
        raise ValueError(f"Predictions must match corpus IDs; missing={missing}, unexpected={unexpected}.")

    correct = 0
    obligation_total = 0
    obligation_recalled = 0
    must_detect_total = 0
    must_detect_recalled = 0
    false_obligations = 0
    invalid_outputs: list[str] = []

    for item in items:
        identifier = item["id"]
        prediction = predictions[identifier]
        category = prediction.get("category") if isinstance(prediction, dict) else prediction
        if category not in VALID_CATEGORIES:
            invalid_outputs.append(identifier)
            continue
        if category == item["expected_category"]:
            correct += 1
        if item["expected_category"] == "Obligation":
            obligation_total += 1
            obligation_recalled += int(category == "Obligation")
        elif category == "Obligation":
            false_obligations += 1
        if item["must_detect_obligation"]:
            must_detect_total += 1
            must_detect_recalled += int(category == "Obligation")

    non_obligation_total = len(items) - obligation_total
    return {
        "corpus_version": corpus["version"],
        "total": len(items),
        "accuracy": correct / len(items),
        "obligation_recall": obligation_recalled / obligation_total if obligation_total else 0.0,
        "must_detect_recall": must_detect_recalled / must_detect_total if must_detect_total else 0.0,
        "false_obligation_rate": false_obligations / non_obligation_total if non_obligation_total else 0.0,
        "invalid_outputs": invalid_outputs,
    }


def quality_gate_failures(metrics: dict[str, Any]) -> list[str]:
    """Return explicit release-blocking failures for autonomous classification."""
    failures: list[str] = []
    if metrics["invalid_outputs"]:
        failures.append(f"Invalid category outputs: {', '.join(metrics['invalid_outputs'])}.")
    if metrics["accuracy"] < 0.90:
        failures.append("Category accuracy is below 90%.")
    if metrics["obligation_recall"] < 0.95:
        failures.append("Obligation recall is below 95%.")
    if metrics["must_detect_recall"] < 1.0:
        failures.append("At least one must-detect obligation was missed.")
    if metrics["false_obligation_rate"] > 0.10:
        failures.append("False-obligation rate is above 10%.")
    return failures
