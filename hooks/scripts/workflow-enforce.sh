#!/bin/bash
# workflow-enforce.sh
# Validates workflow constraints on file writes
# Part of arscontexta workflow enforcement system
#
# Hook: PostToolUse (Write)
# Purpose:
#   1. Detect when workflow outputs are modified
#   2. Invalidate validation gates for affected stage
#   3. Provide context about workflow implications

set -e

# Read stdin for hook input
INPUT=$(cat)

# Extract file path from input
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")

# Guard: No file path
if [ -z "$FILE_PATH" ]; then
    echo '{"additionalContext": ""}'
    exit 0
fi

# Guard: Check if this is a vault
if [ ! -f ".arscontexta" ]; then
    echo '{"additionalContext": ""}'
    exit 0
fi

# Guard: Check if workflow is active
if [ ! -f "ops/workflow-state.yaml" ]; then
    echo '{"additionalContext": ""}'
    exit 0
fi

WORKFLOW_STATE="ops/workflow-state.yaml"
WORKFLOW_DEF=""

# Get workflow ID and find definition
WORKFLOW_ID=$(grep "^  id:" "$WORKFLOW_STATE" | head -1 | awk '{print $2}')
if [ -n "$WORKFLOW_ID" ]; then
    for def_path in "ops/workflows/${WORKFLOW_ID}.yaml" "templates/workflows/${WORKFLOW_ID}.yaml"; do
        if [ -f "$def_path" ]; then
            WORKFLOW_DEF="$def_path"
            break
        fi
    done
fi

# If no definition, we can't check outputs
if [ -z "$WORKFLOW_DEF" ]; then
    echo '{"additionalContext": ""}'
    exit 0
fi

# Get current stage
CURRENT_STAGE=$(grep "current_stage:" "$WORKFLOW_STATE" | awk '{print $2}')

# Check if the modified file matches any output pattern for current stage
# This is a simplified check - in production, use proper YAML parsing
IS_STAGE_OUTPUT=false
OUTPUT_PATTERNS=$(grep -A20 "id: $CURRENT_STAGE" "$WORKFLOW_DEF" 2>/dev/null | grep -A10 "outputs:" | grep "path_pattern:" | awk '{print $2}' || echo "")

for pattern in $OUTPUT_PATTERNS; do
    # Convert glob pattern to regex-ish check
    if [[ "$FILE_PATH" == *${pattern//\*/}* ]] 2>/dev/null; then
        IS_STAGE_OUTPUT=true
        break
    fi
done

# If file is a stage output, invalidate gates
if [ "$IS_STAGE_OUTPUT" = true ]; then
    # Generate context message
    MESSAGE="⚠️ Workflow output modified: $FILE_PATH"
    MESSAGE="$MESSAGE\nValidation gates for stage '$CURRENT_STAGE' may need re-validation."
    MESSAGE="$MESSAGE\nRun /workflow gates to check status."

    # In a full implementation, we would update the state file here
    # For now, just provide the context

    echo "{\"additionalContext\": \"$MESSAGE\"}"
    exit 0
fi

# Check if file is in ops/ directory (workflow management)
if [[ "$FILE_PATH" == ops/* ]]; then
    # Provide minimal context for ops files
    echo '{"additionalContext": "ℹ️ Workflow management file modified."}'
    exit 0
fi

# Default: no workflow context needed
echo '{"additionalContext": ""}'
