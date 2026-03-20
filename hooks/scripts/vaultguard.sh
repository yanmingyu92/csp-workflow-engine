#!/bin/bash
# CSP Workflow Engine — Vault Guard
# Checks if the current directory is an CSP Workflow Engine vault.
# Called by all hooks to skip execution in non-vault repos.
#
# Exit 0 = vault detected (safe to proceed)
# Exit 1 = not a vault (caller should exit)

MARKER=".csp-workflow"

# Primary check: marker file
if [ -f "$MARKER" ]; then
  # Migrate old cat-face format to YAML config
  if grep -q '(\^\.\^)' "$MARKER" 2>/dev/null; then
    cat > "$MARKER" << 'EOF'
# CSP Workflow Engine vault marker + config
# This file identifies the directory as an CSP Workflow Engine vault.
# Do not delete — hooks only run when this file exists.

git: true
session_capture: true
EOF
  fi
  exit 0
fi

# Fallback: legacy vault detection + auto-migrate
if [ -f ops/config.yaml ] || [ -f .claude/hooks/session-orient.sh ]; then
  cat > "$MARKER" << 'EOF'
# CSP Workflow Engine vault marker + config
# This file identifies the directory as an CSP Workflow Engine vault.
# Do not delete — hooks only run when this file exists.

git: true
session_capture: true
EOF
  exit 0
fi

# Not a vault
exit 1
