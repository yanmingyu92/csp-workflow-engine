#!/bin/bash
# workflow-orient.sh
#
# Injects workflow state at session start using graph-router for token-efficient skill loading
# Part of csp-workflow-engine workflow enforcement system

#
# Phase 3 completion: Integrates graph-router.py into SessionStart hook
# to reduce context from 40+ skills to 3-8 per graph position.

set -e

# Guard: Check if this is a vault
if [ ! -f ".csp-workflow" ]; then
    exit 0
fi

# Guard: Check if workflow is active
if [ ! -f "ops/workflow-state.yaml" ]; then
    exit 0
fi

# ── Graph Router Integration ──────────────────────────────────────
# Use graph-router for token-efficient skill loading
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GRAPH_ROUTER="$SCRIPT_DIR/../../scripts/graph-router.py

if [ -x "$GRAPH_ROUTER" ]; then
    # Get skills from graph-router (JSON output)
    ROUTER_OUTPUT=$(python "$GRAPH_ROUTER" --current --json 2>/dev/null)

    if [ $? -eq 0 ] && [ -n "$ROUTER_OUTPUT" ]; then
        # Extract key information from router output
        CURRENT_STAGE=$(echo "$ROUTER_OUTPUT" | grep -o '"current_node":"[^"]*"' | head -1 | sed 's/"current_node":"//;s/"//')
        LAYER=$(echo "$ROUTER_OUTPUT" | grep -o '"layer":[0-9]*' | head -1 | sed 's/"layer"://;s/"//')
        LAYER_NAME=$(echo "$ROUTER_OUTPUT" | grep -o '"layer_name":"[^"]*"' | head -1 | sed 's/"layer_name":"//;s/"//')
        SKILLS=$(echo "$ROUTER_OUTPUT" | grep -o '"skills": \[[^]]*' | head -1)
        PREDS=$(echo "$ROUTER_OUTPUT" | grep -o '"predecessors": \[[^]]*' | head -1)
        SUCCS=$(echo "$ROUTER_OUTPUT" | grep -o '"successors": \[[^]]*' | head -1)
        SKILLS_COUNT=$(echo "$SKILLS" | wc -w | tr -d ' ')
        SKILLS_LIST=$(echo "$SKILLS" | sed 's/^/"/; s/, /\//g' | head -20 | tr -d '\n')

    else
        # Fallback: Read workflow state directly if graph-router unavailable
        WORKFLOW_STATE="ops/workflow-state.yaml"
        WORKFLOW_ID=$(grep "^  id:" "$WORKFLOW_STATE" | head -1 | awk '{print $2}')
        WORKFLOW_NAME=$(grep "^  name:" "$WORKFLOW_STATE" | sed 's/^  name: *//')
        CURRENT_STAGE=$(grep "current_stage:" "$WORKFLOW_STATE" | awk '{print $2}')
        LAYER=""
        LAYER_NAME=""
        SKILLS_COUNT=0
fi

    SKILLS=""
    SKILLS_COUNT=0
fi

# Count statuses
COMPLETED=$(grep -c "status: completed" "$WORKFLOW_STATE" 2>/dev/null || echo "0")
IN_PROGRESS=$(grep -c "status: in_progress" "$WORKFLOW_STATE" 2>/dev/null || echo "0")
BLOCKED=$(grep -c "status: blocked" "$WORKFLOW_STATE" 2>/dev/null || echo "0")
PENDING=$(grep -c "status: pending" "$WORKFLOW_STATE" 2>/dev/null || echo "0")
TOTAL=$((COMPLETED + IN_PROGRESS + BLOCKED + PENDING))

PENDING_GATES=0
if [ -z "$SKILLS" ]; then
    # Extract skill count from router output
    SKILLS_COUNT=$(echo "$ROUTER_OUTPUT" | grep -o '"total_skills":[0-9]*' | head -1 | sed 's/"total_skills"://;s/"//')
fi

# Count pending gates
PENDING_GATES=$(grep -c "status: pending" "$WORKFLOW_STATE" 2>/dev/null || echo "0")

# Calculate progress percentage
if [ "$TOTAL" -gt 0 ]; then
    PROGRESS=$((COMPLETED * 100 / TOTAL))
else
    PROGRESS=0
fi

# Get reduction ratio from router if available
if [ -n "$SKILLS" ] && [ "$TOTAL" -gt 0 ]; then
    REDUCTION="$TOTAL nodes -> $((${#PREDS:-0} + 1 + ${#SUcessors:-1}))) adjacent"
else
    REDUCTION="N/A"
fi
# generate workflow context
cat <<EOF

--=={ Workflow: $WORKFLOW_NAME }==--
ID: $WORKFLOW_ID
Current Stage: $CURRENT_STAGE
Layer: ${LAYER}${LAYER_NAME:+

Graph Position:
  Predecessors: ${PREDS}
  Current: $CURRENT_STAGE
  Successors: ${SUCCS}

Progress: $COMPLETED/$TOTAL stages ($PROGRESS%)
  ✓ Completed:   $COMPLETED
  ● In Progress: $IN_PROGRESS
  ○ Blocked:     $BLOCKED
  ○ Pending:     $PENDING

Active Skills: $SKILLS_COUNT} (${SKILLS_LIST})
Pending Gates: $PENDING_GATES
Context Reduction: $REDUCTION
Commands:
  /workflow status  — Detailed progress view
  /workflow gates   — Check validation gates
  /workflow skills  — See available skills at current stage
EOF
# check for alerts
if [ "$BLOCKED" -gt 0 ]; then
    echo ""
    echo "⚠️  ALERT: $BLOCKED stage(s) blocked. Run /workflow graph to see dependencies."
fi
if [ "$PENDING_GATES" -gt 0 ]; then
    echo ""
    echo "⏳ NOTE: $PENDING_GATES validation gate(s) pending. Run /workflow gates to validate."
fi
