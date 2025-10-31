#!/bin/bash
# Launch script for Dementia MCP snapshot (frozen version)
cd "$(dirname "$0")"
exec python3 claude_mcp_local_snapshot.py
