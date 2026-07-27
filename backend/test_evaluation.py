"""Focused checks for the committed synthetic classification safety corpus."""

import unittest

from evaluation import calculate_metrics, load_corpus, quality_gate_failures


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = load_corpus()

    def test_corpus_has_synthetic_must_detect_obligations(self) -> None:
        items = self.corpus["items"]
        self.assertGreaterEqual(len(items), 12)
        self.assertGreaterEqual(sum(item["must_detect_obligation"] for item in items), 4)

    def test_perfect_predictions_pass_the_quality_gate(self) -> None:
        predictions = {item["id"]: item["expected_category"] for item in self.corpus["items"]}
        metrics = calculate_metrics(self.corpus, predictions)
        self.assertEqual(quality_gate_failures(metrics), [])

    def test_missed_must_detect_obligation_blocks_release(self) -> None:
        predictions = {item["id"]: item["expected_category"] for item in self.corpus["items"]}
        must_detect_item = next(item for item in self.corpus["items"] if item["must_detect_obligation"])
        predictions[must_detect_item["id"]] = "Noise"
        failures = quality_gate_failures(calculate_metrics(self.corpus, predictions))
        self.assertIn("At least one must-detect obligation was missed.", failures)


if __name__ == "__main__":
    unittest.main()
