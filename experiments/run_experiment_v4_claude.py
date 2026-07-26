#!/usr/bin/env python3
"""
Week 6.5: Experiment v4 — Claude Code Agent + Production Framework

This version uses CLAUDE CODE (glm-5) as the actual agent via `claude -p` CLI.
The framework augments the agent by injecting APS-loaded SKILL.md content.

Conditions (agent = Claude Code with glm-5):
  - agent_only: Claude Code + bare task prompt (no framework skills)
  - agent_framework: Claude Code + APS-loaded SKILL.md content injected as context
  - agent_framework_distill: Claude Code + APS skills + distilled principles

Judge: DeepSeek (cheap, separate from agent being tested)

Usage:
    python experiments/run_experiment_v4_claude.py --dry-run --tasks 3
    python experiments/run_experiment_v4_claude.py --tasks 10 --conditions 3
"""

import os
import sys
import json
import yaml
import asyncio
import argparse
import random
import subprocess
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, asdict

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

from openai import AsyncOpenAI  # Only for judge (DeepSeek)

# Import production framework components
from principle_store import PrincipleStore

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent
PRINCIPLES_DB_PATH = PROJECT_ROOT / "data" / "experiences" / "principles.db"
REGULATORY_PATTERNS_PATH = PROJECT_ROOT / "graph" / "regulatory-patterns.yaml"
GRAPH_PATH = PROJECT_ROOT / "graph" / "regulatory-graph.yaml"
OUTPUT_DIR = PROJECT_ROOT / "experiments" / "results" / "experiment_v4_claude"

# DeepSeek pricing (for judge only)
PRICE_INPUT = 0.28
PRICE_OUTPUT = 0.42

# All known experimental conditions (original 3 + ablation controls)
ALL_CONDITIONS = [
    "agent_only",              # unconstrained baseline
    "agent_framework",         # APS graph-constrained skill loading
    "agent_framework_distill", # framework + distilled principles
    "agent_skills_flat",       # ablation: full corpus, no graph routing
    "agent_skills_random",     # ablation: random-k skills, no graph routing
]

# Ablation: number of randomly sampled skills (matched to APS mean loaded count)
RANDOM_K_SKILLS = 5

# ============================================================================
# TASK DEFINITIONS (same 10 tasks)
# ============================================================================

QUICK_10_TASKS = [
    "task-01-sap-parse", "task-02-protocol-setup", "task-06-sdtm-dm",
    "task-07-sdtm-ae", "task-10-p21-sdtm", "task-13-adam-adsl",
    "task-14-adam-adae", "task-17-tfl-demographics", "task-20-tfl-ae",
    "task-21-define-sdtm"
]

TASK_PROMPTS = {
    "task-01-sap-parse": """Analyze this SAP excerpt and extract specific data:

STUDY: NCT048 - Phase 3 Trial
PRIMARY ENDPOINT: Change from Baseline in HbA1c (%) at Week 24
SECONDARY: 1) HbA1c < 7.0% at Week 24, 2) Body weight change
POPULATIONS: ITT (randomized + dose), Safety (any dose), PP (no deviations)
METHODS: MMRM for primary

Extract:
1. Primary endpoint with timepoint
2. Secondary endpoints
3. Population definitions (exact criteria)
4. Statistical method""",

    "task-02-protocol-setup": """Create study configuration:

PROTOCOL: PROT-2024-001, Phase 3, Randomized Double-Blind
ARMS: Drug 100mg, Drug 200mg, Placebo (1:1:1)
VISITS: Screening(-1), Baseline(0), Wk2,4,8,12,16,20,24, Follow-up(28)

Output:
1. Study metadata
2. Treatment arm codes
3. Visit schedule with windows""",

    "task-06-sdtm-dm": """Map raw demographics to SDTM DM:

RAW: SUBJID(SITE-001), SITE, BRTHDAT, SEX, RACE, ETHNIC, TRTGRP, COUNTRY

Map to:
1. USUBJID = STUDYID-SITE-SUBJID
2. AGE/AGEU from BRTHDAT
3. SEX, RACE, ETHNIC to CDISC CT
4. ARM/ARMCD from TRTGRP""",

    "task-07-sdtm-ae": """Map adverse events to SDTM AE:

RAW: AETERM_RAW, AESTDAT, AEENDAT, AESEV, AESER, AEREL

Map to:
1. AETERM, AEDECOD (MedDRA)
2. AEBODSYS
3. AESTDTC, AEENDTC (ISO 8601)
4. AESEV, AESER""",

    "task-10-p21-sdtm": """Review P21 validation results:

ERRORS:
1. RFSTDTC missing (5 subjects)
2. Invalid ARMCD "UNKN"
3. AESTDTC > AEENDTC (3 records)
4. AEDECOD null (12 records)

Provide:
1. Severity ranking
2. Resolution steps""",

    "task-13-adam-adsl": """Derive ADSL from SDTM:

SOURCES: DM(USUBJID,ARM,AGE,SEX), EX(dates), DS(disposition)

Derive:
1. SAFFL = received dose
2. ITTFL = randomized
3. TRT01P, TRT01A
4. TRTSDT, TRTEDT""",

    "task-14-adam-adae": """Derive ADAE from AE + ADSL:

Derive:
1. TRTEMFL (treatment-emergent: AESTDTC >= TRTSDT)
2. ASTDT, AENDT
3. AOCCFL, AOCCPFL
4. ADURN""",

    "task-17-tfl-demographics": """Create demographics table shell:

DATA: ADSL(TRT01P, AGE, SEX, RACE)
ARMS: Placebo, Drug 100mg, Drug 200mg

Specifications:
1. Age: mean, SD, median, range
2. Sex: n (%)
3. Race: n (%)""",

    "task-20-tfl-ae": """Create AE overview table shell:

DATA: ADAE(TRT01P, TRTEMFL, AESER)

Specifications:
1. Any AE: n (%)
2. Treatment-emergent AEs
3. Serious AEs
4. AEs by severity""",

    "task-21-define-sdtm": """Create Define.xml spec:

DATASETS: DM, AE

Specify:
1. Dataset-level: name, label, class
2. Variable-level: name, label, type, length
3. Controlled terminology refs"""
}

# Maps task_id → (graph_node_id, layer)
TASK_NODES = {
    "task-01-sap-parse": ("sap-review", 0),
    "task-02-protocol-setup": ("protocol-setup", 0),
    "task-06-sdtm-dm": ("sdtm-dm-mapping", 2),
    "task-07-sdtm-ae": ("sdtm-ae-mapping", 2),
    "task-10-p21-sdtm": ("p21-sdtm-validation", 3),
    "task-13-adam-adsl": ("adam-adsl", 4),
    "task-14-adam-adae": ("adam-adae", 4),
    "task-17-tfl-demographics": ("tfl-table-generation", 5),
    "task-20-tfl-ae": ("tfl-table-generation", 5),
    "task-21-define-sdtm": ("define-xml-sdtm", 6)
}

# ============================================================================
# SYSTEM PROMPTS
# ============================================================================

# Framework system prompt: injected via --system-prompt when framework is active
FRAMEWORK_SYSTEM_PROMPT = """You are an AI programming assistant augmented with a domain-specific workflow framework for FDA clinical trial submissions.
You follow CDISC SDTM IG v3.4 and ADaM IG v1.3 standards.
The framework has loaded relevant skills and domain knowledge for your current task position in the regulatory pipeline.
Use the provided skill content and principles to produce precise, regulatory-compliant outputs with proper controlled terminology (CDISC CT), correct variable names, and complete derivation logic.
Always include specific CDISC codelist references (e.g., C66731) and ISO 8601 date formats when applicable."""

# ============================================================================
# TIER 2: Multi-Dimensional Rubric Judge (DeepSeek)
# ============================================================================

MULTI_DIM_JUDGE_PROMPT = """You are a senior regulatory submission quality reviewer with 15+ years of CDISC experience.
Evaluate this clinical data programming output on THREE separate dimensions.

TASK: {task_description}

{domain_criteria}

OUTPUT TO EVALUATE:
{response}

Score EACH dimension independently from 1-5:

**COMPLETENESS**: Are all requested items addressed?
  1 = Missing most items
  2 = Some items addressed, significant gaps
  3 = All requested items present at conceptual level
  4 = All items + implementation details (derivation logic, code snippets)
  5 = All items + edge cases + validation checks

**TERMINOLOGY**: Are CDISC/regulatory terms used correctly?
  1 = No regulatory terminology
  2 = Some terms but incorrect usage
  3 = Correct variable names and concepts (USUBJID, SDTM, ADaM)
  4 = + Codelist references (C66731), controlled terminology, ISO 8601
  5 = + Cross-domain traceability, IG version references

**STRUCTURE**: Is the output machine-readable and actionable?
  1 = Unstructured text only
  2 = Basic formatting (headers, bullets)
  3 = Tables with clear organization
  4 = YAML/JSON/code with derivation logic
  5 = Production-ready spec with schema validation

Respond with ONLY valid JSON, no markdown:
{{"completeness": <1-5>, "terminology": <1-5>, "structure": <1-5>, "reasoning": "<brief explanation>"}}"""

# ============================================================================
# TIER 1: Pairwise Comparison Judge (DeepSeek)
# ============================================================================

PAIRWISE_JUDGE_PROMPT = """You are a senior regulatory submission quality reviewer with 15+ years of CDISC experience.
Compare these two outputs for the SAME clinical data programming task.

TASK: {task_description}

{domain_criteria}

--- OUTPUT A ---
{response_a}

--- OUTPUT B ---
{response_b}

Which output better addresses the regulatory task? Consider:
- Completeness (all items addressed?)
- Regulatory terminology accuracy (CDISC CT, variable names)
- Actionability (can a programmer implement from this?)
- Structure (tables, YAML, code blocks)

Respond with ONLY valid JSON, no markdown:
{{"winner": "A" or "B" or "tie", "reason": "<brief explanation>", "confidence": "high" or "medium" or "low"}}"""

# ============================================================================
# TIER 3: Auto-Metrics
# ============================================================================

CDISC_TERMS = [
    "USUBJID", "STUDYID", "SDTM", "ADaM", "ADSL", "ADAE", "ADLB",
    "CDISC", "CT", "SUPPQUAL", "RELREC", "EPOCH",
    "RFSTDTC", "RFENDTC", "RFXSTDTC", "RFXENDTC",
    "AESTDTC", "AEENDTC", "AEDECOD", "AEBODSYS", "AETERM", "AESEV", "AESER",
    "TRTSDT", "TRTEDT", "TRT01P", "TRT01A", "TRTEMFL",
    "SAFFL", "ITTFL", "PPFL", "RANDFL",
    "ARM", "ARMCD", "AGE", "AGEU", "SEX", "RACE", "ETHNIC",
    "MedDRA", "ISO 8601", "IG v3", "Define.xml",
    "MMRM", "ITT", "PP", "SAF",
    "AOCCFL", "AOCCPFL", "ASTDT", "AENDT", "ADURN",
]

def compute_auto_metrics(response: str) -> dict:
    """Compute objective metrics from response text."""
    import re
    
    # CDISC term count (case-sensitive for variable names)
    cdisc_count = 0
    cdisc_found = []
    for term in CDISC_TERMS:
        count = response.count(term)
        if count > 0:
            cdisc_count += count
            cdisc_found.append(term)
    
    # Code block count
    code_blocks = len(re.findall(r'```(?:yaml|python|json|sas|r|sql|xml)', response, re.IGNORECASE))
    
    # Codelist OID references (C-number pattern like C66731)
    codelist_refs = len(re.findall(r'\bC\d{4,6}\b', response))
    
    # Table count (markdown tables)
    table_rows = len(re.findall(r'^\|.*\|$', response, re.MULTILINE))
    
    return {
        "response_length": len(response),
        "word_count": len(response.split()),
        "cdisc_term_count": cdisc_count,
        "cdisc_terms_found": cdisc_found,
        "code_block_count": code_blocks,
        "codelist_ref_count": codelist_refs,
        "table_row_count": table_rows,
    }

# ============================================================================
# EXPERIMENT RESULT
# ============================================================================

# Error markers for detecting failed responses
ERROR_MARKERS = [
    "[TIMEOUT]", "[EMPTY OUTPUT]", "[MAX_TURNS_EXHAUSTED]",
    "[JSON PARSE ERROR]", "[ERROR]",
]

def is_error_response(response: str) -> bool:
    """Check if a response is an error/timeout/empty."""
    if not response or len(response.strip()) == 0:
        return True
    for marker in ERROR_MARKERS:
        if response.startswith(marker):
            return True
    return False


@dataclass
class ExperimentResult:
    experiment_id: str
    timestamp: str
    task_id: str
    graph_node: str
    layer: int
    condition: str
    prompt_preview: str      # First 500 chars of prompt
    response: str
    skills_loaded: List[str]
    skills_count: int
    skills_tokens: int
    principles_used: List[str]
    principles_count: int
    context_strategy: str
    tokens_in: int
    tokens_out: int
    # Tier 2: Multi-dimensional scores
    dim_completeness: float
    dim_terminology: float
    dim_structure: float
    dim_reasoning: str
    quality_score: float       # Average of 3 dimensions
    # Tier 3: Auto-metrics
    auto_metrics: dict
    # Agent metadata
    cost_usd: float
    agent_model: str
    agent_duration_ms: int
    agent_num_turns: int
    # Run tracking
    run_id: int = 0
    is_error_response: bool = False


# ============================================================================
# CLAUDE CODE INVOCATION
# ============================================================================

import tempfile

_NOHOOKS_SETTINGS_PATH = None


def _get_agent_env() -> dict:
    """
    Build an isolated environment for child `claude -p` agent calls.

    - Strips inherited ANTHROPIC_* variables from any parent Claude Code
      session (a leaked ANTHROPIC_API_KEY causes 401s against the GLM
      endpoint).
    - Routes to the GLM backbone via the Anthropic-compatible endpoint,
      reproducing the backbone used in the original experiment.
    """
    env = dict(os.environ)
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_MODEL"):
        env.pop(var, None)
    glm_key = os.getenv("GLM_API_KEY")
    if glm_key:
        env["ANTHROPIC_BASE_URL"] = os.getenv("GLM_BASE_URL", "https://api.z.ai/api/anthropic")
        env["ANTHROPIC_AUTH_TOKEN"] = glm_key
    return env


def _get_nohooks_settings_path() -> str:
    """Temp settings file disabling user hooks for child agent runs
    (hooks would otherwise inject text into agent outputs)."""
    global _NOHOOKS_SETTINGS_PATH
    if _NOHOOKS_SETTINGS_PATH is None:
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                        delete=False, encoding='utf-8')
        json.dump({"disableAllHooks": True}, f)
        f.close()
        _NOHOOKS_SETTINGS_PATH = f.name
    return _NOHOOKS_SETTINGS_PATH


def invoke_claude_code(prompt: str, system_prompt: str = None,
                       max_turns: int = 6, timeout: int = 300,
                       cwd: str = None) -> dict:
    """
    Invoke Claude Code via CLI `claude -p` and return structured result.

    Writes prompt to a temp file and pipes via `type <file> | claude -p`
    to avoid Windows command line length limits and stdin forwarding issues.

    Returns dict with keys:
        result, total_cost_usd, input_tokens, output_tokens,
        duration_ms, num_turns, model, is_error
    """
    prompt_file = None
    try:
        # Prepend a strong no-tools directive BEFORE the context
        # This is far more effective than appending at the end — Claude
        # processes top-level directives with higher priority
        no_tools_directive = """**CRITICAL: ANSWER DIRECTLY — DO NOT USE TOOLS**
All domain knowledge you need is provided below in the [Skills Context] section.
Do NOT call Read, Grep, Glob, Bash, or any file-system tools. Do NOT explore the project.
Produce your complete answer in a SINGLE text response using ONLY the information provided.
"""
        enhanced_prompt = no_tools_directive + prompt

        # Write prompt to temp file
        prompt_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', delete=False, encoding='utf-8'
        )
        prompt_file.write(enhanced_prompt)
        prompt_file.close()
        prompt_path = prompt_file.name

        # Build command: type <file> | claude -p ...
        # Using 'type' to pipe file content on Windows
        agent_model = os.getenv("AGENT_MODEL", "glm-5")
        claude_args = (f'-p --output-format json --max-turns {max_turns} '
                       f'--model {agent_model} '
                       f'--settings "{_get_nohooks_settings_path()}"')
        if system_prompt:
            # Escape double quotes in system prompt for shell
            escaped_sp = system_prompt.replace('"', '\\"')
            claude_args += f' --system-prompt "{escaped_sp}"'

        cmd = f'type "{prompt_path}" | claude {claude_args}'

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or str(PROJECT_ROOT),
            encoding='utf-8',
            errors='replace',
            shell=True,
            env=_get_agent_env()
        )

        # Parse JSON output from claude CLI
        stdout = proc.stdout.strip()
        if not stdout:
            return {
                "result": f"[EMPTY OUTPUT] stderr: {proc.stderr[:200]}",
                "total_cost_usd": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "duration_ms": 0,
                "num_turns": 0,
                "model": "unknown",
                "is_error": True
            }

        data = json.loads(stdout)

        # Extract model name from modelUsage
        model_usage = data.get("modelUsage", {})
        model_name = list(model_usage.keys())[0] if model_usage else "unknown"

        # Extract token counts
        usage = data.get("usage", {})

        # Check for error_max_turns subtype - agent ran out of turns
        subtype = data.get("subtype", "")
        if subtype == "error_max_turns":
            num_turns = data.get("num_turns", 0)
            return {
                "result": f"[MAX_TURNS_EXHAUSTED] Agent used {num_turns} turns without producing final output. Try increasing max_turns.",
                "total_cost_usd": data.get("total_cost_usd", 0.0),
                "input_tokens": data.get("usage", {}).get("input_tokens", 0),
                "output_tokens": data.get("usage", {}).get("output_tokens", 0),
                "duration_ms": data.get("duration_ms", 0),
                "num_turns": num_turns,
                "model": list(data.get("modelUsage", {}).keys())[0] if data.get("modelUsage") else "unknown",
                "is_error": True
            }

        # Extract result text with fallback
        result_text = data.get("result", "")
        if not result_text:
            # Fallback: try to extract text from content blocks
            content = data.get("content", [])
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                result_text = "\n".join(text_parts)

            # If still empty, dump JSON for debugging
            if not result_text:
                debug_path = OUTPUT_DIR / f"debug_empty_{datetime.now().strftime('%H%M%S')}.json"
                with open(debug_path, 'w') as df:
                    json.dump(data, df, indent=2)

        return {
            "result": result_text,
            "total_cost_usd": data.get("total_cost_usd", 0.0),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "duration_ms": data.get("duration_ms", 0),
            "num_turns": data.get("num_turns", 0),
            "model": model_name,
            "is_error": data.get("is_error", False)
        }

    except subprocess.TimeoutExpired:
        return {
            "result": "[TIMEOUT]",
            "total_cost_usd": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "duration_ms": timeout * 1000,
            "num_turns": 0,
            "model": "timeout",
            "is_error": True
        }
    except json.JSONDecodeError as e:
        return {
            "result": f"[JSON PARSE ERROR] {str(e)[:100]}",
            "total_cost_usd": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "duration_ms": 0,
            "num_turns": 0,
            "model": "parse_error",
            "is_error": True
        }
    except Exception as e:
        return {
            "result": f"[ERROR] {str(e)[:200]}",
            "total_cost_usd": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "duration_ms": 0,
            "num_turns": 0,
            "model": "error",
            "is_error": True
        }
    finally:
        # Clean up temp prompt file
        if prompt_file:
            try:
                os.unlink(prompt_file.name)
            except OSError:
                pass


# ============================================================================
# EXPERIMENT RUNNER
# ============================================================================

class ExperimentRunner:
    def __init__(self, dry_run: bool = False, seed: int = 42, budget: int = 8000):
        self.dry_run = dry_run
        self.seed = seed
        self.budget = budget
        # DeepSeek client — ONLY used for judging (cheap)
        self.judge_client = AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        )
        self.judge_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.total_cost = 0.0
        self.total_agent_cost = 0.0
        self.total_judge_cost = 0.0
        self.results: List[ExperimentResult] = []
        self.seen_pairs: set = set()
        # Ablation: occurrence counter for reproducible per-run random sampling
        self._random_occurrence: Dict[str, int] = {}

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # --- Load Production Framework Components ---

        # 1. Graph Router
        self.graph_data = {}
        if GRAPH_PATH.exists():
            try:
                with open(GRAPH_PATH, 'r', encoding='utf-8') as f:
                    self.graph_data = yaml.safe_load(f)
                self.nodes = {n["id"]: n for n in self.graph_data.get("nodes", [])}
                print(f"Loaded graph: {len(self.nodes)} nodes")
            except Exception as e:
                print(f"Graph unavailable: {e}")
                self.nodes = {}
        else:
            self.nodes = {}

        # 2. Regulatory Patterns (for judge criteria)
        self.regulatory_patterns = {}
        if REGULATORY_PATTERNS_PATH.exists():
            try:
                with open(REGULATORY_PATTERNS_PATH) as f:
                    data = yaml.safe_load(f)
                self.regulatory_patterns = data.get("patterns", {})
                print(f"Loaded {len(self.regulatory_patterns)} regulatory patterns")
            except Exception as e:
                print(f"Regulatory patterns unavailable: {e}")

        # 3. Context Builder (APS + Skill Loader)
        import importlib.util
        cl_path = SCRIPTS_DIR / "context-loader.py"
        spec = importlib.util.spec_from_file_location("context_loader", cl_path)
        self.cl_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cl_module)

        # 4. Principle Store
        self.principle_store = None
        if PRINCIPLES_DB_PATH.exists():
            try:
                self.principle_store = PrincipleStore(str(PRINCIPLES_DB_PATH))
                print(f"Loaded {self.principle_store.count_principles()} principles")
            except Exception as e:
                print(f"Principle store unavailable: {e}")

        # 5. Create ContextBuilder instance
        self.context_builder = self.cl_module.ContextBuilder(
            project_root=PROJECT_ROOT,
            budget=self.budget,
            principle_store=self.principle_store
        )

        skill_count = len(self.context_builder.skill_locator.skill_cache)
        print(f"Indexed {skill_count} SKILL.md files")

    def _get_router_result(self, node_id: str) -> Dict[str, Any]:
        """Build a router_result dict from the graph data."""
        node = self.nodes.get(node_id, {})
        layer = node.get("layer", 0)

        predecessors = []
        successors = []
        for nid, ndata in self.nodes.items():
            deps = ndata.get("dependencies", [])
            dep_ids = []
            for d in deps:
                if isinstance(d, dict):
                    dep_ids.append(d.get("node", ""))
                elif isinstance(d, str):
                    dep_ids.append(d)
            if node_id in dep_ids:
                successors.append(nid)
        deps = node.get("dependencies", [])
        for d in deps:
            if isinstance(d, dict):
                predecessors.append(d.get("node", ""))
            elif isinstance(d, str):
                predecessors.append(d)

        layer_names = {
            0: "Protocol & Planning", 1: "Raw Data Management",
            2: "SDTM Creation", 3: "SDTM Quality Control",
            4: "ADaM Creation", 5: "TFL Generation",
            6: "Define.xml & Submission"
        }

        return {
            "layer": layer,
            "layer_name": layer_names.get(layer, f"Layer {layer}"),
            "predecessors": predecessors,
            "successors": successors,
        }

    def _get_node_skills(self, node_id: str) -> List[str]:
        """Get skills bound to a node from the graph."""
        node = self.nodes.get(node_id, {})
        skills = node.get("skills_bound", [])
        return [s.lstrip("/") for s in skills]

    def _get_judge_criteria(self, node_id: str) -> str:
        """Load domain-specific judge criteria from regulatory-patterns.yaml."""
        for pattern_name, pattern in self.regulatory_patterns.items():
            valid_nodes = pattern.get("valid_node_ids", [])
            if node_id in valid_nodes:
                eval_template = pattern.get("evaluation_template", {})
                mandatory = eval_template.get("mandatory", [])
                recommended = eval_template.get("recommended", [])
                if mandatory or recommended:
                    lines = ["DOMAIN-SPECIFIC CRITERIA FOR THIS TASK:"]
                    lines.append("A score of 4+ REQUIRES meeting these mandatory criteria:")
                    for m in mandatory:
                        lines.append(f"  - {m}")
                    if recommended:
                        lines.append("A score of 5 also requires:")
                        for r in recommended:
                            lines.append(f"  - {r}")
                    return "\n".join(lines)
        return ""

    def _judge_cost(self, tin: int, tout: int) -> float:
        return (tin / 1_000_000) * PRICE_INPUT + (tout / 1_000_000) * PRICE_OUTPUT

    def _all_corpus_skills(self) -> List[str]:
        """Full SKILL.md corpus (deduplicated, deterministic order)."""
        return sorted(set(self.context_builder.skill_locator.skill_cache.keys()))

    def _build_uniform_context(self, node_id: str, skill_names: List[str],
                               strategy_label: str):
        """
        Build context WITHOUT graph routing (ablation conditions).

        All skills receive a uniform priority band (GLOBAL) with no hub or
        query bonus, so ranking degenerates to alphabetical order. The same
        token budget, single-skill cap, and truncation cascade as the APS
        are applied, isolating the graph-routing signal from the corpus
        content and the budget machinery.
        """
        cl = self.cl_module
        cb = self.context_builder
        router_result = self._get_router_result(node_id)

        result = cl.ContextResult(
            node_id=node_id,
            layer=router_result["layer"],
            layer_name=router_result["layer_name"],
            budget=self.budget,
        )

        skill_infos = [cb.load_skill(name) for name in skill_names]
        for info in skill_infos:
            info.band = cl.PriorityBand.GLOBAL  # uniform band: no routing signal
            info.priority_score = cb.scheduler.compute_priority(
                info.band, info.name, hub_degree=0, query_match=0.0
            )

        scheduled = cb.scheduler.schedule(skill_infos, ref_tokens=0)
        result.skills = scheduled

        for s in scheduled:
            if s.status == "loaded":
                result.skills_loaded += 1
                result.skill_tokens += s.token_estimate
            elif s.status == "truncated":
                result.skills_truncated += 1
                result.skill_tokens += s.token_estimate
            elif s.status == "dropped":
                result.skills_dropped += 1
            elif s.status == "missing":
                result.skills_missing += 1

        result.total_tokens = result.skill_tokens
        result.budget_used = result.total_tokens
        result.budget_strategy = (
            f"{strategy_label}: {result.skills_loaded} loaded | "
            f"{result.skills_truncated} truncated | "
            f"{result.skills_dropped} dropped | "
            f"{result.budget_used}/{self.budget} tokens"
        )
        return result

    async def run_task(self, task_id: str, condition: str) -> Optional[ExperimentResult]:
        pair = (task_id, condition)
        if pair in self.seen_pairs:
            return None
        self.seen_pairs.add(pair)

        node_id, layer = TASK_NODES.get(task_id, ("unknown", 0))
        base_prompt = TASK_PROMPTS.get(task_id, "Complete the task.")
        skills_loaded = []
        skills_count = 0
        skills_tokens = 0
        principles_used = []
        principles_count = 0
        context_strategy = "none"
        system_prompt = None
        agent_only_cwd = None

        if condition == "agent_only":
            # Condition 1: Claude Code agent with bare task prompt — no framework
            # Run from an ISOLATED temp directory to prevent the agent from
            # browsing project SKILL.md files, ensuring a pure baseline.
            import tempfile as _tf
            agent_only_cwd = _tf.mkdtemp(prefix='csp_baseline_')
            prompt = base_prompt

        elif condition == "agent_framework":
            # Condition 2: Claude Code + framework skills (APS-loaded)
            system_prompt = FRAMEWORK_SYSTEM_PROMPT
            router_result = self._get_router_result(node_id)
            all_skills = self._get_node_skills(node_id)

            global_skills = self.graph_data.get("global_skills", [])
            all_skills_set = set(all_skills)
            for gs in global_skills:
                gs_clean = gs.lstrip("/")
                if gs_clean not in all_skills_set:
                    all_skills.append(gs_clean)

            ctx_result = self.context_builder.build_context(
                node_id=node_id,
                router_result=router_result,
                all_skills=all_skills,
                regulatory_refs=[],
                task_description=base_prompt,
                with_principles=False,
            )

            context_text = self.cl_module.OutputFormatter.format_context(
                ctx_result, include_content=True
            )
            prompt = f"{context_text}\n\n## Task\n{base_prompt}"

            skills_loaded = [s.name for s in ctx_result.skills if s.status in ("loaded", "truncated")]
            skills_count = ctx_result.skills_loaded + ctx_result.skills_truncated
            skills_tokens = ctx_result.skill_tokens
            context_strategy = ctx_result.budget_strategy

        elif condition == "agent_framework_distill":
            # Condition 3: Claude Code + framework skills + distilled principles
            system_prompt = FRAMEWORK_SYSTEM_PROMPT
            router_result = self._get_router_result(node_id)
            all_skills = self._get_node_skills(node_id)

            global_skills = self.graph_data.get("global_skills", [])
            all_skills_set = set(all_skills)
            for gs in global_skills:
                gs_clean = gs.lstrip("/")
                if gs_clean not in all_skills_set:
                    all_skills.append(gs_clean)

            ctx_result = self.context_builder.build_context(
                node_id=node_id,
                router_result=router_result,
                all_skills=all_skills,
                regulatory_refs=[],
                task_description=base_prompt,
                with_principles=True,
            )

            context_text = self.cl_module.OutputFormatter.format_context(
                ctx_result, include_content=True
            )
            prompt = f"{context_text}\n\n## Task\n{base_prompt}"

            skills_loaded = [s.name for s in ctx_result.skills if s.status in ("loaded", "truncated")]
            skills_count = ctx_result.skills_loaded + ctx_result.skills_truncated
            skills_tokens = ctx_result.skill_tokens
            principles_used = ctx_result.principles_retrieved_ids
            principles_count = len(ctx_result.principles)
            context_strategy = ctx_result.budget_strategy

        elif condition == "agent_skills_flat":
            # Ablation A: same 59-skill corpus, NO graph routing.
            # All skills offered with uniform priority under the same token
            # budget and truncation cascade; fill order is alphabetical.
            system_prompt = FRAMEWORK_SYSTEM_PROMPT
            corpus = self._all_corpus_skills()
            ctx_result = self._build_uniform_context(node_id, corpus, "FLAT")

            context_text = self.cl_module.OutputFormatter.format_context(
                ctx_result, include_content=True
            )
            prompt = f"{context_text}\n\n## Task\n{base_prompt}"

            skills_loaded = [s.name for s in ctx_result.skills if s.status in ("loaded", "truncated")]
            skills_count = ctx_result.skills_loaded + ctx_result.skills_truncated
            skills_tokens = ctx_result.skill_tokens
            context_strategy = ctx_result.budget_strategy

        elif condition == "agent_skills_random":
            # Ablation B: random k skills from the corpus (k matched to the
            # APS mean loaded count), fixed derived seed per (task, occurrence)
            # so each of the 3 replicate runs draws a different but
            # reproducible sample.
            system_prompt = FRAMEWORK_SYSTEM_PROMPT
            corpus = self._all_corpus_skills()
            occurrence = self._random_occurrence.get(task_id, 0)
            self._random_occurrence[task_id] = occurrence + 1
            rng = random.Random(f"{self.seed}:{task_id}:{occurrence}")
            sampled = sorted(rng.sample(corpus, min(RANDOM_K_SKILLS, len(corpus))))
            ctx_result = self._build_uniform_context(node_id, sampled, "RANDOM")

            context_text = self.cl_module.OutputFormatter.format_context(
                ctx_result, include_content=True
            )
            prompt = f"{context_text}\n\n## Task\n{base_prompt}"

            skills_loaded = [s.name for s in ctx_result.skills if s.status in ("loaded", "truncated")]
            skills_count = ctx_result.skills_loaded + ctx_result.skills_truncated
            skills_tokens = ctx_result.skill_tokens
            context_strategy = ctx_result.budget_strategy

        else:
            raise ValueError(f"Unknown condition: {condition}")

        # --- Execute via Claude Code ---
        agent_model = "dry-run"
        agent_duration = 0
        agent_turns = 0

        if self.dry_run:
            response = "[DRY RUN]"
            tin, tout = 100, 200
            agent_cost = 0.0
            dim_c, dim_t, dim_s = 4.0, 4.0, 4.0
            dim_reason = "Dry run"
            print(f"    Condition: {condition}")
            print(f"    Skills loaded: {skills_count} ({', '.join(skills_loaded[:5])}{'...' if len(skills_loaded)>5 else ''})")
            print(f"    Skills tokens: {skills_tokens}")
            print(f"    Principles: {principles_count}")
            print(f"    System prompt: {'Yes' if system_prompt else 'No'}")
            print(f"    Prompt length: {len(prompt)} chars")
            print(f"    Strategy: {context_strategy}")
            print(f"    Agent: Claude Code (dry run)")
        else:
            # Determine CWD: agent_only uses isolated temp dir, others use project root
            run_cwd = agent_only_cwd if condition == 'agent_only' else None

            # --- Phase 1: Invoke Claude Code via CLI ---
            claude_result = invoke_claude_code(
                prompt=prompt,
                system_prompt=system_prompt,
                max_turns=6,
                timeout=420,
                cwd=run_cwd
            )

            # Retry once on TIMEOUT (Windows piping hang — zero tokens)
            if claude_result["is_error"] and claude_result["input_tokens"] == 0:
                import time
                time.sleep(5)
                claude_result = invoke_claude_code(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_turns=6,
                    timeout=420,
                    cwd=run_cwd
                )

            # Clean up agent_only temp dir
            if condition == 'agent_only' and agent_only_cwd:
                import shutil
                shutil.rmtree(agent_only_cwd, ignore_errors=True)

            response = claude_result["result"]
            tin = claude_result["input_tokens"]
            tout = claude_result["output_tokens"]
            agent_cost = claude_result["total_cost_usd"]
            agent_model = claude_result["model"]
            agent_duration = claude_result["duration_ms"]
            agent_turns = claude_result["num_turns"]
            self.total_agent_cost += agent_cost

            resp_is_error = claude_result["is_error"] or is_error_response(response)
            if resp_is_error:
                print(f"  AGENT ERROR: {response[:100]}")

            # --- Phase 2: Tier 2 Multi-Dimensional Judge ---
            dim_c, dim_t, dim_s = 3.0, 3.0, 3.0
            dim_reason = "Default"

            # Skip judge for error responses — assign score 1.0 directly
            if resp_is_error:
                dim_c, dim_t, dim_s = 1.0, 1.0, 1.0
                dim_reason = f"Error response: {response[:80]}"
                print(f"  Skipping judge (error response) — scored 1.0")
            else:
                try:
                    domain_criteria = self._get_judge_criteria(node_id)
                    judge_content = MULTI_DIM_JUDGE_PROMPT.format(
                        task_description=base_prompt,
                        response=response[:4000],
                        domain_criteria=domain_criteria
                    )
                    judge_resp = await self.judge_client.chat.completions.create(
                        model=self.judge_model,
                        messages=[{"role": "user", "content": judge_content}],
                        temperature=0.0,
                        max_tokens=300
                    )
                    content = judge_resp.choices[0].message.content

                    # Parse multi-dim scores
                    c_match = re.search(r'"completeness"\s*:\s*([1-5])', content)
                    t_match = re.search(r'"terminology"\s*:\s*([1-5])', content)
                    s_match = re.search(r'"structure"\s*:\s*([1-5])', content)
                    r_match = re.search(r'"reasoning"\s*:\s*"([^"]+)"', content)

                    if c_match: dim_c = float(c_match.group(1))
                    if t_match: dim_t = float(t_match.group(1))
                    if s_match: dim_s = float(s_match.group(1))
                    if r_match: dim_reason = r_match.group(1)[:200]

                except Exception as e:
                    dim_reason = f"Judge error: {str(e)[:100]}"

        # Tier 3: Auto-metrics (always computed, even dry-run)
        auto_metrics = compute_auto_metrics(response)

        judge_cost = self._judge_cost(tin, tout) if not self.dry_run else 0.0
        total_cost = agent_cost + judge_cost
        self.total_cost += total_cost
        self.total_judge_cost += judge_cost

        avg_score = round((dim_c + dim_t + dim_s) / 3.0, 2)

        return ExperimentResult(
            experiment_id=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_id}_{condition}",
            timestamp=datetime.now().isoformat(),
            task_id=task_id,
            graph_node=node_id,
            layer=layer,
            condition=condition,
            prompt_preview=prompt[:500],
            response=response,
            skills_loaded=skills_loaded,
            skills_count=skills_count,
            skills_tokens=skills_tokens,
            principles_used=principles_used,
            principles_count=principles_count,
            context_strategy=context_strategy,
            tokens_in=tin,
            tokens_out=tout,
            dim_completeness=dim_c,
            dim_terminology=dim_t,
            dim_structure=dim_s,
            dim_reasoning=dim_reason,
            quality_score=avg_score,
            auto_metrics=auto_metrics,
            cost_usd=total_cost,
            agent_model=agent_model,
            agent_duration_ms=agent_duration,
            agent_num_turns=agent_turns,
            is_error_response=resp_is_error if not self.dry_run else False,
        )

    async def run_pairwise(self, task_id: str,
                           cond_a: str, cond_b: str) -> dict:
        """Tier 1: Pairwise comparison between two conditions for the same task."""
        result_a = next((r for r in self.results
                         if r.task_id == task_id and r.condition == cond_a), None)
        result_b = next((r for r in self.results
                         if r.task_id == task_id and r.condition == cond_b), None)

        if not result_a or not result_b:
            return {"winner": "error", "reason": "Missing result", "confidence": "low"}

        # Skip judge if one side errored — auto-win for the non-error side
        if result_a.is_error_response and not result_b.is_error_response:
            return {
                "task_id": task_id, "pair": f"{cond_a}_vs_{cond_b}",
                "winner": cond_b, "reason": f"{cond_a} errored",
                "confidence": "high", "flipped": False, "raw_winner": "B"
            }
        if result_b.is_error_response and not result_a.is_error_response:
            return {
                "task_id": task_id, "pair": f"{cond_a}_vs_{cond_b}",
                "winner": cond_a, "reason": f"{cond_b} errored",
                "confidence": "high", "flipped": False, "raw_winner": "A"
            }
        if result_a.is_error_response and result_b.is_error_response:
            return {
                "task_id": task_id, "pair": f"{cond_a}_vs_{cond_b}",
                "winner": "tie", "reason": "Both errored",
                "confidence": "low", "flipped": False, "raw_winner": "tie"
            }

        node_id = result_a.graph_node
        base_prompt = TASK_PROMPTS.get(task_id, "")
        domain_criteria = self._get_judge_criteria(node_id)

        # Randomize presentation order to avoid position bias
        import random as _rnd
        flip = _rnd.random() < 0.5
        if flip:
            resp_a_text, resp_b_text = result_b.response[:4000], result_a.response[:4000]
        else:
            resp_a_text, resp_b_text = result_a.response[:4000], result_b.response[:4000]

        try:
            judge_content = PAIRWISE_JUDGE_PROMPT.format(
                task_description=base_prompt,
                domain_criteria=domain_criteria,
                response_a=resp_a_text,
                response_b=resp_b_text
            )
            judge_resp = await self.judge_client.chat.completions.create(
                model=self.judge_model,
                messages=[{"role": "user", "content": judge_content}],
                temperature=0.0,
                max_tokens=200
            )
            content = judge_resp.choices[0].message.content

            w_match = re.search(r'"winner"\s*:\s*"(A|B|tie)"', content, re.IGNORECASE)
            r_match = re.search(r'"reason"\s*:\s*"([^"]+)"', content)
            c_match = re.search(r'"confidence"\s*:\s*"(high|medium|low)"', content, re.IGNORECASE)

            raw_winner = w_match.group(1) if w_match else "parse_error"
            reason = r_match.group(1) if r_match else content[:100]
            confidence = c_match.group(1) if c_match else "low"

            # Un-flip the winner
            if raw_winner == "tie":
                actual_winner = "tie"
            elif flip:
                actual_winner = cond_a if raw_winner == "B" else cond_b
            else:
                actual_winner = cond_a if raw_winner == "A" else cond_b

            return {
                "task_id": task_id,
                "pair": f"{cond_a}_vs_{cond_b}",
                "winner": actual_winner,
                "reason": reason[:200],
                "confidence": confidence,
                "flipped": flip,
                "raw_winner": raw_winner
            }

        except Exception as e:
            return {
                "task_id": task_id,
                "pair": f"{cond_a}_vs_{cond_b}",
                "winner": "error",
                "reason": str(e)[:100],
                "confidence": "low",
                "flipped": False,
                "raw_winner": "error"
            }

    def save(self, pairwise_results: List[dict] = None) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = OUTPUT_DIR / f"experiment_{ts}.json"

        # Tier 2 summary: multi-dimensional scores per condition
        summary = {}
        for cond in ALL_CONDITIONS:
            cr = [r for r in self.results if r.condition == cond]
            if cr:
                summary[cond] = {
                    "n": len(cr),
                    "mean_overall": round(sum(r.quality_score for r in cr) / len(cr), 2),
                    "mean_completeness": round(sum(r.dim_completeness for r in cr) / len(cr), 2),
                    "mean_terminology": round(sum(r.dim_terminology for r in cr) / len(cr), 2),
                    "mean_structure": round(sum(r.dim_structure for r in cr) / len(cr), 2),
                    "avg_response_length": round(sum(r.auto_metrics["response_length"] for r in cr) / len(cr), 0),
                    "avg_cdisc_terms": round(sum(r.auto_metrics["cdisc_term_count"] for r in cr) / len(cr), 1),
                    "avg_code_blocks": round(sum(r.auto_metrics["code_block_count"] for r in cr) / len(cr), 1),
                    "avg_skills_loaded": round(sum(r.skills_count for r in cr) / len(cr), 1),
                    "avg_duration_ms": round(sum(r.agent_duration_ms for r in cr) / len(cr), 0),
                }

        # Tier 1 summary: pairwise win rates
        pairwise_summary = {}
        if pairwise_results:
            for pair_key in set(p["pair"] for p in pairwise_results):
                pair_rows = [p for p in pairwise_results if p["pair"] == pair_key]
                parts = pair_key.split("_vs_")
                if len(parts) == 2:
                    cond_a, cond_b = parts
                    wins_a = sum(1 for p in pair_rows if p["winner"] == cond_a)
                    wins_b = sum(1 for p in pair_rows if p["winner"] == cond_b)
                    ties = sum(1 for p in pair_rows if p["winner"] == "tie")
                    total = len(pair_rows)
                    pairwise_summary[pair_key] = {
                        "total": total,
                        f"{cond_a}_wins": wins_a,
                        f"{cond_b}_wins": wins_b,
                        "ties": ties,
                        f"{cond_b}_win_rate": round(wins_b / total, 2) if total > 0 else 0,
                    }

        # Identify model used
        models_used = set(r.agent_model for r in self.results if r.agent_model != "dry-run")

        conds_present = set(r.condition for r in self.results)
        is_ablation = bool(conds_present & {"agent_skills_flat", "agent_skills_random"})
        data = {
            "metadata": {
                "version": "v4-claude-ablation" if is_ablation else "v4-claude-3tier",
                "timestamp": datetime.now().isoformat(),
                "agent": "Claude Code (claude -p)",
                "agent_models": list(models_used),
                "judge": self.judge_model,
                "evaluation": "3-tier: pairwise + multi-dim + auto-metrics",
                "dry_run": self.dry_run,
                "seed": self.seed,
                "budget": self.budget,
                "total_cost": round(self.total_cost, 4),
                "agent_cost": round(self.total_agent_cost, 4),
                "judge_cost": round(self.total_judge_cost, 4),
                "framework_components": {
                    "graph_nodes": len(self.nodes),
                    "skill_files": len(self.context_builder.skill_locator.skill_cache),
                    "principles": self.principle_store.count_principles() if self.principle_store else 0,
                    "regulatory_patterns": len(self.regulatory_patterns),
                }
            },
            "results": [asdict(r) for r in self.results],
            "pairwise_results": pairwise_results or [],
            "summary_multidim": summary,
            "summary_pairwise": pairwise_summary
        }

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        return path


async def main():
    parser = argparse.ArgumentParser(description="Experiment v4: Claude Code Agent + 3-Tier Evaluation")
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--tasks', type=int, default=10)
    parser.add_argument('--conditions', type=int, default=3)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--budget', type=int, default=8000,
                        help='Token budget for APS context loading')
    parser.add_argument('--runs', type=int, default=1,
                        help='Number of repeated runs per task×condition (increases n)')
    parser.add_argument('--condition-list', type=str, default=None,
                        help='Comma-separated condition names (overrides --conditions). '
                             f'Known: {",".join(ALL_CONDITIONS)}')
    args = parser.parse_args()

    if args.condition_list:
        conditions = [c.strip() for c in args.condition_list.split(",") if c.strip()]
        unknown = [c for c in conditions if c not in ALL_CONDITIONS]
        if unknown:
            parser.error(f"Unknown condition(s): {unknown}. Known: {ALL_CONDITIONS}")
    else:
        conditions = ALL_CONDITIONS[:args.conditions]
    tasks = QUICK_10_TASKS[:args.tasks]

    # Build all (task, condition, run_id) triples
    triples = [(t, c, run_id)
                for run_id in range(args.runs)
                for t in tasks
                for c in conditions]
    random.seed(args.seed)
    random.shuffle(triples)

    total_calls = len(triples)
    print("=" * 60)
    print(f"Experiment v4 (Claude Code + 3-Tier Evaluation)")
    print(f"  Tasks: {len(tasks)}, Conditions: {len(conditions)}, Runs: {args.runs}")
    print(f"  Total agent calls: {total_calls}")
    print(f"  Agent: Claude Code (glm-5) via 'claude -p'")
    print(f"  Judge: DeepSeek (multi-dim + pairwise)")
    print(f"  Token budget: {args.budget}")
    print(f"  Dry run: {args.dry_run}")
    print("=" * 60)

    runner = ExperimentRunner(dry_run=args.dry_run, seed=args.seed, budget=args.budget)

    # =========================================
    # Phase 1: Run all tasks via Claude Code
    # =========================================
    print(f"\n--- Phase 1: Agent Execution ({total_calls} calls) ---")
    for i, (task_id, cond, run_id) in enumerate(triples, 1):
        run_label = f" (run {run_id+1}/{args.runs})" if args.runs > 1 else ""
        print(f"[{i}/{total_calls}] {task_id} x {cond}{run_label}...")
        try:
            # Reset seen_pairs tracking for each run
            runner.seen_pairs.discard((task_id, cond))
            result = await runner.run_task(task_id, cond)
            if result:
                result.run_id = run_id
                runner.results.append(result)
                if not args.dry_run:
                    err_flag = " [ERROR]" if result.is_error_response else ""
                    print(f"  C={result.dim_completeness} T={result.dim_terminology} S={result.dim_structure} "
                          f"avg={result.quality_score}, Model: {result.agent_model}, "
                          f"CDISC={result.auto_metrics['cdisc_term_count']}, "
                          f"Duration: {result.agent_duration_ms}ms{err_flag}")
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

    # =========================================
    # Phase 2: Pairwise Comparisons
    # =========================================
    pairwise_results = []
    if not args.dry_run and len(conditions) >= 2:
        comparisons = []
        for task_id in tasks:
            if "agent_only" in conditions and "agent_framework" in conditions:
                comparisons.append((task_id, "agent_only", "agent_framework"))
            if "agent_only" in conditions and "agent_framework_distill" in conditions:
                comparisons.append((task_id, "agent_only", "agent_framework_distill"))
            # Ablation pairwise: routing vs non-routed skill loading
            if "agent_skills_flat" in conditions and "agent_framework" in conditions:
                comparisons.append((task_id, "agent_skills_flat", "agent_framework"))
            if "agent_skills_random" in conditions and "agent_framework" in conditions:
                comparisons.append((task_id, "agent_skills_random", "agent_framework"))
            if "agent_skills_flat" in conditions and "agent_only" in conditions:
                comparisons.append((task_id, "agent_only", "agent_skills_flat"))

        print(f"\n--- Phase 2: Pairwise Comparisons ({len(comparisons)} pairs) ---")
        for i, (tid, ca, cb) in enumerate(comparisons, 1):
            print(f"[{i}/{len(comparisons)}] {tid}: {ca} vs {cb}...")
            pw = await runner.run_pairwise(tid, ca, cb)
            pairwise_results.append(pw)
            print(f"  Winner: {pw['winner']} ({pw['confidence']}) — {pw['reason'][:60]}")

    # =========================================
    # Save and Print Summary
    # =========================================
    path = runner.save(pairwise_results)
    print(f"\nSaved: {path}")
    print(f"Total cost: ${runner.total_cost:.4f} (Agent: ${runner.total_agent_cost:.4f}, Judge: ${runner.total_judge_cost:.4f})")

    # Print Tier 2 summary (multi-dim)
    print("\n--- Tier 2: Multi-Dimensional Scores ---")
    print(f"{'Condition':<30} {'C':>4} {'T':>4} {'S':>4} {'Avg':>5} {'CDISC':>6} {'Len':>7}")
    for cond in conditions:
        cr = [r for r in runner.results if r.condition == cond]
        if cr:
            mc = sum(r.dim_completeness for r in cr) / len(cr)
            mt = sum(r.dim_terminology for r in cr) / len(cr)
            ms = sum(r.dim_structure for r in cr) / len(cr)
            ma = sum(r.quality_score for r in cr) / len(cr)
            cd = sum(r.auto_metrics["cdisc_term_count"] for r in cr) / len(cr)
            ln = sum(r.auto_metrics["response_length"] for r in cr) / len(cr)
            print(f"  {cond:<28} {mc:>4.1f} {mt:>4.1f} {ms:>4.1f} {ma:>5.2f} {cd:>6.1f} {ln:>7.0f}")

    # Print Tier 1 summary (pairwise)
    if pairwise_results:
        print("\n--- Tier 1: Pairwise Win Rates ---")
        for pair_key in set(p["pair"] for p in pairwise_results):
            rows = [p for p in pairwise_results if p["pair"] == pair_key]
            parts = pair_key.split("_vs_")
            if len(parts) == 2:
                ca, cb = parts
                wa = sum(1 for p in rows if p["winner"] == ca)
                wb = sum(1 for p in rows if p["winner"] == cb)
                ties = sum(1 for p in rows if p["winner"] == "tie")
                print(f"  {pair_key}: {ca}={wa}, {cb}={wb}, ties={ties} "
                      f"-> {cb} win rate: {wb/len(rows):.0%}")


if __name__ == "__main__":
    asyncio.run(main())
