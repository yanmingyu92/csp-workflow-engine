"""
Re-judge stored ablation experiment responses (Tier 2 multi-dim + Tier 1 pairwise).

Used when agent runs succeeded but judge calls failed (eg, expired API key).
Loads the saved experiment JSON, re-runs the identical judge protocol on the
stored responses, and writes an updated JSON alongside the original.

Usage:
    python experiments/rejudge_ablation.py --input results/.../experiment_X.json
"""
import argparse
import asyncio
import importlib.util
import json
import os
import random
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from openai import AsyncOpenAI  # noqa: E402

# Reuse prompts and helpers from the runner
spec = importlib.util.spec_from_file_location(
    "runner", Path(__file__).parent / "run_experiment_v4_claude.py")
runner = importlib.util.module_from_spec(spec)
sys.modules["runner"] = runner
spec.loader.exec_module(runner)

MULTI_DIM_JUDGE_PROMPT = runner.MULTI_DIM_JUDGE_PROMPT
PAIRWISE_JUDGE_PROMPT = runner.PAIRWISE_JUDGE_PROMPT
TASK_PROMPTS = runner.TASK_PROMPTS
TASK_NODES = runner.TASK_NODES

PAIRWISE_PAIRS = [
    ("agent_only", "agent_framework"),
    ("agent_skills_flat", "agent_framework"),
    ("agent_skills_random", "agent_framework"),
    ("agent_only", "agent_skills_flat"),
]


class Rejudger:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        # judge criteria come from regulatory patterns, mirroring the runner
        self.patterns = {}
        pat_path = ROOT / "methodology" / "regulatory-patterns.yaml"
        if not pat_path.exists():
            pat_path = getattr(runner, "REGULATORY_PATTERNS_PATH", pat_path)
        try:
            import yaml
            with open(pat_path, encoding="utf-8") as f:
                self.patterns = yaml.safe_load(f).get("patterns", {})
        except Exception as e:
            print(f"regulatory patterns unavailable: {e}")

    def criteria(self, node_id: str) -> str:
        for _, pattern in self.patterns.items():
            if node_id in pattern.get("valid_node_ids", []):
                t = pattern.get("evaluation_template", {})
                mand, rec = t.get("mandatory", []), t.get("recommended", [])
                if mand or rec:
                    lines = ["DOMAIN-SPECIFIC CRITERIA FOR THIS TASK:",
                             "A score of 4+ REQUIRES meeting these mandatory criteria:"]
                    lines += [f"  - {m}" for m in mand]
                    if rec:
                        lines.append("A score of 5 also requires:")
                        lines += [f"  - {r}" for r in rec]
                    return "\n".join(lines)
        return ""

    async def judge_multidim(self, task_id, node_id, response):
        content = MULTI_DIM_JUDGE_PROMPT.format(
            task_description=TASK_PROMPTS.get(task_id, ""),
            response=response[:4000],
            domain_criteria=self.criteria(node_id))
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            temperature=0.0, max_tokens=300)
        text = resp.choices[0].message.content
        out = {"completeness": 3.0, "terminology": 3.0, "structure": 3.0,
               "reasoning": "parse_default"}
        for dim in ("completeness", "terminology", "structure"):
            m = re.search(rf'"{dim}"\s*:\s*([1-5])', text)
            if m:
                out[dim] = float(m.group(1))
        m = re.search(r'"reasoning"\s*:\s*"([^"]+)"', text)
        if m:
            out["reasoning"] = m.group(1)[:200]
        return out

    async def judge_pairwise(self, task_id, node_id, resp_a, resp_b,
                             cond_a, cond_b, rng):
        flip = rng.random() < 0.5
        ra, rb = (resp_b, resp_a) if flip else (resp_a, resp_b)
        content = PAIRWISE_JUDGE_PROMPT.format(
            task_description=TASK_PROMPTS.get(task_id, ""),
            domain_criteria=self.criteria(node_id),
            response_a=ra[:4000], response_b=rb[:4000])
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            temperature=0.0, max_tokens=200)
        text = resp.choices[0].message.content
        w = re.search(r'"winner"\s*:\s*"(A|B|tie)"', text, re.IGNORECASE)
        r = re.search(r'"reason"\s*:\s*"([^"]+)"', text)
        c = re.search(r'"confidence"\s*:\s*"(high|medium|low)"', text, re.IGNORECASE)
        raw = w.group(1) if w else "parse_error"
        if raw.lower() == "tie":
            winner = "tie"
        elif raw in ("A", "B"):
            if flip:
                winner = cond_a if raw == "B" else cond_b
            else:
                winner = cond_a if raw == "A" else cond_b
        else:
            winner = "error"
        return {"task_id": task_id, "pair": f"{cond_a}_vs_{cond_b}",
                "winner": winner,
                "reason": (r.group(1) if r else text[:100])[:200],
                "confidence": c.group(1) if c else "low",
                "flipped": flip, "raw_winner": raw}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    path = Path(args.input)
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data["results"]
    print(f"Loaded {len(results)} stored results")

    rj = Rejudger()
    rng = random.Random(args.seed)

    # sanity check credentials with one tiny call
    ping = await rj.client.chat.completions.create(
        model=rj.model, messages=[{"role": "user", "content": "Say OK"}],
        max_tokens=5)
    print("Judge auth OK:", ping.choices[0].message.content[:20])

    # --- Tier 2: multi-dim re-judging ---
    sem = asyncio.Semaphore(4)

    async def rejudge_one(i, r):
        async with sem:
            if r.get("is_error_response"):
                return
            for attempt in range(3):
                try:
                    out = await rj.judge_multidim(
                        r["task_id"], r["graph_node"], r["response"])
                    r["dim_completeness"] = out["completeness"]
                    r["dim_terminology"] = out["terminology"]
                    r["dim_structure"] = out["structure"]
                    r["dim_reasoning"] = out["reasoning"]
                    r["quality_score"] = round(
                        (out["completeness"] + out["terminology"]
                         + out["structure"]) / 3.0, 2)
                    print(f"  [{i+1}/{len(results)}] {r['task_id']} x "
                          f"{r['condition']}: {r['quality_score']}")
                    return
                except Exception as e:
                    print(f"  [{i+1}] retry {attempt+1}: {str(e)[:80]}")
                    await asyncio.sleep(3 * (attempt + 1))
            r["dim_reasoning"] = "Rejudge failed after retries"

    await asyncio.gather(*(rejudge_one(i, r) for i, r in enumerate(results)))

    # --- Tier 1: pairwise (first run per task per condition pair) ---
    pairwise = []
    tasks = sorted({r["task_id"] for r in results})
    for t in tasks:
        node = TASK_NODES.get(t, ("unknown", 0))[0]
        for ca, cb in PAIRWISE_PAIRS:
            ra = next((r for r in results
                       if r["task_id"] == t and r["condition"] == ca), None)
            rb = next((r for r in results
                       if r["task_id"] == t and r["condition"] == cb), None)
            if not ra or not rb:
                continue
            try:
                pw = await rj.judge_pairwise(
                    t, node, ra["response"], rb["response"], ca, cb, rng)
            except Exception as e:
                pw = {"task_id": t, "pair": f"{ca}_vs_{cb}",
                      "winner": "error", "reason": str(e)[:100],
                      "confidence": "low", "flipped": False,
                      "raw_winner": "error"}
            pairwise.append(pw)
            print(f"  pairwise {t} {ca} vs {cb}: {pw['winner']}")

    data["pairwise_results"] = pairwise

    # --- Summaries (mirroring runner.save) ---
    summary = {}
    for cond in sorted({r["condition"] for r in results}):
        cr = [r for r in results if r["condition"] == cond]
        summary[cond] = {
            "n": len(cr),
            "mean_overall": round(sum(r["quality_score"] for r in cr) / len(cr), 2),
            "mean_completeness": round(sum(r["dim_completeness"] for r in cr) / len(cr), 2),
            "mean_terminology": round(sum(r["dim_terminology"] for r in cr) / len(cr), 2),
            "mean_structure": round(sum(r["dim_structure"] for r in cr) / len(cr), 2),
        }
    data["summary_multidim"] = summary

    pw_summary = {}
    for pair_key in sorted({p["pair"] for p in pairwise}):
        rows = [p for p in pairwise if p["pair"] == pair_key]
        ca, cb = pair_key.split("_vs_")
        wa = sum(1 for p in rows if p["winner"] == ca)
        wb = sum(1 for p in rows if p["winner"] == cb)
        ties = sum(1 for p in rows if p["winner"] == "tie")
        pw_summary[pair_key] = {
            "total": len(rows), f"{ca}_wins": wa, f"{cb}_wins": wb,
            "ties": ties,
            f"{cb}_win_rate": round(wb / len(rows), 2) if rows else 0}
    data["summary_pairwise"] = pw_summary
    data["metadata"]["rejudged"] = True

    out = path.with_name(path.stem + "_rejudged.json")
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\nSaved: {out}")
    for cond, s in summary.items():
        print(f"  {cond}: overall={s['mean_overall']}")


if __name__ == "__main__":
    asyncio.run(main())
