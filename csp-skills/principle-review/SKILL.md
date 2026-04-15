---
name: principle-review
description: Review and manage principles in the review queue. Approve, reject, or edit principles distilled from execution trajectories. Triggers on "principle review", "review queue", "approve principle".
version: "1.0"
user-invocable: true
context: fork
model: sonnet
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "[action] [principle_id] — list, approve, reject, edit, stats"
---

## EXECUTE NOW

Parse $ARGUMENTS: action, principle_id, reviewer, reason

**Available actions:**
- `list` — Show all pending principles
- `approve <id>` — Approve a principle
- `reject <id>` — Reject a principle
- `edit <id>` — Edit then approve
- `stats` — Show queue statistics

**START NOW.**

---

## Philosophy

**Quality gates protect regulatory integrity.** Principles distilled from trajectories must be reviewed before injection into the principle store. This skill provides a workflow for reviewing, approving, rejecting, or editing pending principles while maintaining a full audit trail.

---

## Review Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Trajectory    │────▶│   Distillation  │────▶│    Validate     │
│   (Recorded)    │     │   (LLM call)    │     │  (Quality Gate) │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        ┌────────────────────────────────┴────────────────────────────────┐
                        │                                                                         │
                        ▼                                                                         ▼
               ┌─────────────────┐                                                      ┌─────────────────┐
               │  Auto-Approve   │                                                      │  Review Queue   │
               │  (if enabled)   │                                                      │  (Manual)       │
               └─────────────────┘                                                      └────────┬────────┘
                                                                                                 │
                        ┌────────────────────────────────────────┬───────────────────────────┤
                        │                                        │                           │
                        ▼                                        ▼                           ▼
               ┌─────────────────┐                      ┌─────────────────┐         ┌─────────────────┐
               │     Approve     │                      │      Edit       │         │     Reject      │
               │  → Add to Store │                      │  → Modify       │         │  → Delete       │
               └─────────────────┘                      └─────────────────┘         └─────────────────┘
```

---

## Script Execution

```bash
# List pending principles
python csp-skills/principle-review/script.py list

# Show queue statistics
python csp-skills/principle-review/script.py stats

# Approve a principle
python csp-skills/principle-review/script.py approve prin_abc123 --reviewer "admin"

# Reject a principle
python csp-skills/principle-review/script.py reject prin_abc123 --reviewer "admin" --reason "Too vague"

# Edit a principle (opens editor, then approves)
python csp-skills/principle-review/script.py edit prin_abc123 --reviewer "admin"
```

---

## Quality Gate Criteria

| Criterion | Threshold | Check Type |
|-----------|-----------|------------|
| Metric score | >= 0.5 | Automatic |
| Usage count | >= 3 | Automatic |
| Description length | 20-200 chars | Automatic |
| No PII | Regex scan | Automatic |
| Applicable nodes | >= 1 | Automatic |
| Regulatory relevance | Manual | Review |

---

## Review Checklist

When reviewing a principle, check:

1. **Clarity**: Is the description clear and actionable?
2. **Relevance**: Does it apply to regulatory workflows?
3. **Accuracy**: Are recommended skills correct?
4. **Safety**: Could following this principle cause issues?
5. **Completeness**: Are validation checks appropriate?

---

## Audit Trail

All review actions are logged with:
- Reviewer ID
- Timestamp
- Action taken (approve/reject/edit)
- Reason (if rejected)
- Original and modified content (if edited)

Audit files stored in: `data/experiences/review_queue/approved/` and `data/experiences/review_queue/rejected/`

---

## Evaluation Criteria

**Mandatory:**
- Principle passes all automatic quality gates
- Reviewer provides valid ID
- Audit trail is complete

**Recommended:**
- Description is concise (<100 words)
- At least 2 applicable nodes specified
- Validation checks are specific
