from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def multilabel_micro_f1(expected: Iterable[set[str]], actual: Iterable[set[str]]) -> float:
    true_positive = false_positive = false_negative = 0
    for expected_labels, actual_labels in zip(expected, actual, strict=True):
        true_positive += len(expected_labels & actual_labels)
        false_positive += len(actual_labels - expected_labels)
        false_negative += len(expected_labels - actual_labels)
    denominator = 2 * true_positive + false_positive + false_negative
    return 1.0 if denominator == 0 else 2 * true_positive / denominator


def dependency_accuracy(
    expected: Iterable[set[tuple[str, str]]],
    actual: Iterable[set[tuple[str, str]]],
) -> float:
    scores = [1.0 if left == right else 0.0 for left, right in zip(expected, actual, strict=True)]
    return sum(scores) / len(scores) if scores else 1.0


def evaluate_manager_cases(cases: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, float]:
    if len(cases) != len(predictions):
        raise ValueError("评测样本与预测数量不一致。")
    expected_domains = [set(case["expected"]["domains"]) for case in cases]
    actual_domains = [set(item.get("domains") or []) for item in predictions]
    expected_operations = [set(case["expected"]["operations"]) for case in cases]
    actual_operations = [set(item.get("operation_classes") or []) for item in predictions]
    clarification_matches = [
        bool(case["expected"].get("needs_clarification"))
        == bool(prediction.get("needs_clarification"))
        for case, prediction in zip(cases, predictions, strict=True)
    ]
    return {
        "domain_micro_f1": multilabel_micro_f1(expected_domains, actual_domains),
        "operation_micro_f1": multilabel_micro_f1(expected_operations, actual_operations),
        "clarification_accuracy": sum(clarification_matches) / len(clarification_matches)
        if clarification_matches
        else 1.0,
    }
