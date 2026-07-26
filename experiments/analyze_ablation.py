"""
Ablation experiment analysis: routing vs corpus access.

Computes per-condition overall means with bootstrap 95% CIs, pairwise
condition contrasts (2-sided bootstrap tests), per-task means, and
pairwise win rates for the 4-condition ablation experiment.

Usage:
    python experiments/analyze_ablation.py --input path/to/experiment.json
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

CONDITIONS = [
    ("agent_only", "Unconstrained baseline"),
    ("agent_framework", "Graph-constrained framework"),
    ("agent_skills_flat", "Flat corpus loading (no routing)"),
    ("agent_skills_random", "Random skill loading (k=5)"),
]

N_BOOT = 10_000
SEED = 42


def bootstrap_mean_ci(values, n_boot=N_BOOT, seed=SEED):
    rng = np.random.RandomState(seed)
    arr = np.array(values, dtype=float)
    boot = [arr[rng.choice(len(arr), len(arr), replace=True)].mean()
            for _ in range(n_boot)]
    return arr.mean(), np.percentile(boot, 2.5), np.percentile(boot, 97.5)


def bootstrap_diff(values_a, values_b, n_boot=N_BOOT, seed=SEED):
    """A - B; returns (diff, lo, hi, two-sided p)."""
    rng = np.random.RandomState(seed)
    a = np.array(values_a, dtype=float)
    b = np.array(values_b, dtype=float)
    boot = []
    for _ in range(n_boot):
        boot.append(a[rng.choice(len(a), len(a), replace=True)].mean()
                    - b[rng.choice(len(b), len(b), replace=True)].mean())
    boot = np.array(boot)
    p = min(1.0, 2.0 * min(float(np.mean(boot <= 0)), float(np.mean(boot >= 0))))
    return (a.mean() - b.mean(), np.percentile(boot, 2.5),
            np.percentile(boot, 97.5), p)


def fmt_p(p):
    if p < 0.001:
        return "<.001"
    return f".{p:.3f}".replace("0.", "").rstrip("0") or f"{p:.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    results = data["results"]
    errors = [r for r in results if r.get("is_error_response")]
    print(f"Loaded {len(results)} results ({len(errors)} errors) "
          f"from {data['metadata'].get('timestamp')}")
    print(f"Agent models: {data['metadata'].get('agent_models')}, "
          f"judge: {data['metadata'].get('judge')}, "
          f"seed: {data['metadata'].get('seed')}, "
          f"budget: {data['metadata'].get('budget')}")

    # run-level and task-level scores per condition
    run_scores = defaultdict(list)
    task_scores = defaultdict(lambda: defaultdict(list))  # cond -> task -> [scores]
    for r in results:
        run_scores[r["condition"]].append(r["quality_score"])
        task_scores[r["condition"]][r["task_id"]].append(r["quality_score"])

    print("\n== Per-condition overall scores (run-level, n per condition) ==")
    means = {}
    for cond, label in CONDITIONS:
        vals = run_scores.get(cond, [])
        if not vals:
            print(f"  {label}: MISSING")
            continue
        m, lo, hi = bootstrap_mean_ci(vals)
        means[cond] = m
        print(f"  {label:<38} n={len(vals):>3}  {m:.2f} [{lo:.2f}, {hi:.2f}]")

    print("\n== Task-level means (averaged over runs; unit of analysis) ==")
    task_means = {}
    tasks = sorted({t for c in task_scores.values() for t in c})
    for cond, _ in CONDITIONS:
        task_means[cond] = [float(np.mean(task_scores[cond][t]))
                            for t in tasks if t in task_scores[cond]]
    header = f"  {'task':<28}" + "".join(f"{c[:12]:>14}" for c, _ in CONDITIONS)
    print(header)
    for t in tasks:
        row = f"  {t:<28}"
        for cond, _ in CONDITIONS:
            v = task_scores[cond].get(t)
            row += f"{np.mean(v):>14.2f}" if v else f"{'--':>14}"
        print(row)

    print("\n== Contrasts (task-level means; 2-sided bootstrap) ==")
    contrasts = [
        ("agent_framework", "agent_only"),
        ("agent_framework", "agent_skills_flat"),
        ("agent_framework", "agent_skills_random"),
        ("agent_skills_flat", "agent_only"),
        ("agent_skills_random", "agent_only"),
    ]
    for a, b in contrasts:
        if a not in task_means or b not in task_means:
            continue
        d, lo, hi, p = bootstrap_diff(task_means[a], task_means[b])
        print(f"  {a} - {b}: {d:+.2f} [{lo:+.2f}, {hi:+.2f}]  P={fmt_p(p)}")

    # Pairwise win rates
    pw = data.get("summary_pairwise", {})
    if pw:
        print("\n== Pairwise win rates (Tier 1 judge) ==")
        for k, v in pw.items():
            print(f"  {k}: {v}")

    # Context stats for ablation conditions
    print("\n== Loaded-context stats per condition ==")
    for cond, label in CONDITIONS:
        cr = [r for r in results if r["condition"] == cond]
        if cr:
            sc = np.mean([r["skills_count"] for r in cr])
            st = np.mean([r["skills_tokens"] for r in cr])
            cost = np.mean([r["cost_usd"] for r in cr])
            print(f"  {label:<38} skills={sc:.1f}  skill_tokens={st:.0f}  cost=${cost:.3f}")


if __name__ == "__main__":
    main()
