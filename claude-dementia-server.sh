#!/usr/bin/env bash
# Claude Dementia MCP Server Launcher
# Runs the hybrid MCP server for Claude Dementia memory system

# Ensure we use the correct Python version
export PATH="/usr/local/bin:/usr/bin:$PATH"

# Set the working directory to where the server files are
# Portable way to get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Preserve debug environment variables
export DEBUG="${DEBUG:-mcp:*}"
export PYTHONUNBUFFERED=1  # Ensure output isn't buffered
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Log startup (to stderr to avoid polluting stdio)
echo "Starting Claude Dementia MCP Server..." >&2
echo "Working directory: $SCRIPT_DIR" >&2
echo "Database: $SCRIPT_DIR/.claude-memory.db" >&2

# Run the server
exec python3 "$SCRIPT_DIR/claude_mcp_hybrid.py" "$@"