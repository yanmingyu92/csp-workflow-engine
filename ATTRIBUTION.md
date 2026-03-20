# Attribution

This project is built on top of **Ars Contexta** (v0.8.0), a Claude Code plugin
for knowledge management.

## Upstream Repository

- **Name:** Ars Contexta
- **Repository:** [agenticnotetaking/arscontexta](https://github.com/agenticnotetaking/arscontexta)
- **License:** MIT
- **Version used:** v0.8.0 (commit `4be327e`)

## What comes from upstream

The following directories and files originate from the upstream Ars Contexta
plugin and are used under the MIT license:

| Directory | Purpose |
|-----------|---------|
| `.claude-plugin/` | Plugin manifest and marketplace listing |
| `skills/` | 10 plugin-level commands (setup, help, tutorial, etc.) |
| `skill-sources/` | 16 generated command templates (reduce, reflect, etc.) |
| `agents/` | Pipeline subagent (knowledge-guide.md) |
| `hooks/` | Hook configuration and scripts |
| `generators/` | CLAUDE.md template and feature blocks |
| `methodology/` | 249 research claims |
| `reference/` | Core reference docs (kernel.yaml, three-spaces.md, etc.) |
| `platforms/` | Platform-specific adapters |
| `presets/` | Pre-validated configurations |

### Modified upstream files

- `hooks/hooks.json` — added graph-router hook to SessionStart
- `reference/workflow-schema.yaml` — extended with layer, skills_bound, mcps_bound
- `skill-sources/workflow/SKILL.md` — updated for graph-router integration

## What we built (entirely custom)

All of the following are original work, not derived from upstream:

| Directory / File | Purpose |
|-----------------|---------|
| `src/csp_engine/` | Python package for the regulatory workflow engine |
| `scripts/evaluation.py` | Graph extension validation & completion checking |
| `scripts/graph-router.py` | Token-efficient skill loading via adjacency |
| `scripts/context-loader.py` | Adaptive priority token budget controller |
| `scripts/graph-validator.py` | DAG structure & layer consistency validation |
| `graph/` | Regulatory task graph (45-node DAG), layer definitions, patterns |
| `csp-skills/` | Clinical trial programming skills (58 skills across 7 layers) |
| `mcps/` | MCP server configurations |
| `docs/regulatory/` | Regulatory reference documents (16 files) |
| `tests/` | Test suite |
| `test-fixtures/` | Test data (valid, invalid, circular node definitions) |
