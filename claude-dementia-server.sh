#!/usr/bin/env bash
# Claude Dementia MCP Server Launcher
# Runs the hybrid MCP server for Claude Dementia memory system

# Ensure we use the correct Python version
export PATH="/usr/local/bin:/usr/bin:$PATH"

# CRITICAL: Capture the original working directory (where Claude is running)
# This is the project directory we need to work with
export CLAUDE_PROJECT_DIR="$(pwd)"

# Get the directory where the MCP server is installed
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Add the MCP server directory to Python path so imports work
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Preserve debug environment variables
export DEBUG="${DEBUG:-mcp:*}"
export PYTHONUNBUFFERED=1  # Ensure output isn't buffered

# Log startup (to stderr to avoid polluting stdio)
echo "Starting Claude Dementia MCP Server..." >&2
echo "Project directory: $CLAUDE_PROJECT_DIR" >&2
echo "Server location: $SCRIPT_DIR" >&2

# Run the server from the PROJECT directory, not the server directory
# This ensures all file operations happen in the right place
cd "$CLAUDE_PROJECT_DIR"
exec python3 "$SCRIPT_DIR/claude_mcp_hybrid.py" "$@"