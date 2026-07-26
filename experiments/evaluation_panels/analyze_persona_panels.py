#!/usr/bin/env python3
"""Reproduce pooled persona-panel scores and interpanel agreement."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from pathlib import Path


EXPECTED = {
    "baseline_mean": 3.60,
    "framework_mean": 4.35,
    "difference": 0.75,
    "choice_kappa": 0.76,
    "score_correlation": 0.95,
}


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def pearson(x: list[float], y: list[float]) -> float:
    x_mean = mean(x)
    y_mean = mean(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y))
    denominator = math.sqrt(
        sum((value - x_mean) ** 2 for value in x)
        * sum((value - y_mean) ** 2 for value in y)
    )
    return numerator / denominator


def cohen_kappa(first: list[str], second: list[str]) -> float:
    observed = sum(a == b for a, b in zip(first, second)) / len(first)
    first_counts = Counter(first)
    second_counts = Counter(second)
    expected = sum(
        first_counts[label] * second_counts[label]
        for label in set(first_counts) | set(second_counts)
    ) / (len(first) ** 2)
    return (observed - expected) / (1 - expected)


def analyze(path: Path) -> dict[str, float]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 20:
        raise ValueError(f"Expected 20 panel rows, found {len(rows)}")

    condition_scores: dict[str, list[float]] = {"baseline": [], "framework": []}
    per_panel: dict[int, dict[tuple[int, str], float]] = {1: {}, 2: {}}
    choices: dict[int, list[str]] = {1: [], 2: []}

    for row in rows:
        panel = int(row["panel"])
        pair = int(row["pair"])
        a_score = mean(
            [float(row["a_structure"]), float(row["a_completeness"]), float(row["a_terminology"])]
        )
        b_score = mean(
            [float(row["b_structure"]), float(row["b_completeness"]), float(row["b_terminology"])]
        )
        condition_scores[row["a_condition"]].append(a_score)
        condition_scores[row["b_condition"]].append(b_score)
        per_panel[panel][(pair, "A")] = a_score
        per_panel[panel][(pair, "B")] = b_score
        choices[panel].append(row["choice"])

    first_scores: list[float] = []
    second_scores: list[float] = []
    for pair in range(1, 11):
        for side in ("A", "B"):
            first_scores.append(per_panel[1][(pair, side)])
            second_scores.append(per_panel[2][(pair, side)])

    baseline = mean(condition_scores["baseline"])
    framework = mean(condition_scores["framework"])
    return {
        "baseline_mean": baseline,
        "framework_mean": framework,
        "difference": framework - baseline,
        "choice_kappa": cohen_kappa(choices[1], choices[2]),
        "score_correlation": pearson(first_scores, second_scores),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).with_name("persona_panel_scores.csv"),
    )
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    results = analyze(args.input)
    for name, value in results.items():
        print(f"{name}={value:.6f}")
    if args.verify:
        for name, expected in EXPECTED.items():
            if round(results[name], 2) != expected:
                raise SystemExit(
                    f"Verification failed for {name}: {results[name]:.6f} != {expected:.2f}"
                )
        print("Verified persona-panel statistics")


if __name__ == "__main__":
    main()
