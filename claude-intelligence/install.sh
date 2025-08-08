#!/bin/bash
# Claude Intelligence Installation Script
# One-line installer for MCP server

set -e

echo "🧠 Claude Intelligence Installer"
echo "================================"
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    echo "   Please install Python 3.8+ and try again."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.8"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
    echo "❌ Python $PYTHON_VERSION found, but 3.8+ is required."
    exit 1
fi

echo "✓ Python $PYTHON_VERSION detected"

# Create installation directory
INSTALL_DIR="$HOME/.claude-intelligence"
echo ""
echo "📁 Installing to: $INSTALL_DIR"

if [ -d "$INSTALL_DIR" ]; then
    echo ""
    read -p "⚠️  Directory exists. Overwrite? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 1
    fi
    rm -rf "$INSTALL_DIR"
fi

mkdir -p "$INSTALL_DIR"

# Download the server
echo ""
echo "⬇️  Downloading Claude Intelligence..."
# For development/testing, use feature branch
# For production, change to 'main' branch
BRANCH="${CLAUDE_INTEL_BRANCH:-feature/claude-intelligence}"
curl -sSL "https://raw.githubusercontent.com/banton/claude-dementia/$BRANCH/claude-intelligence/mcp_server.py" \
    -o "$INSTALL_DIR/mcp_server.py"

# Install optional dependency
echo ""
echo "📦 Installing optional xxhash for better performance..."
python3 -m pip install --quiet xxhash 2>/dev/null || {
    echo "   Note: xxhash not installed, using fallback MD5"
}

# Create launcher script
cat > "$INSTALL_DIR/claude-intelligence" << 'EOF'
#!/bin/bash
# Claude Intelligence launcher
cd "$(dirname "$0")"
python3 mcp_server.py "$@"
EOF

chmod +x "$INSTALL_DIR/claude-intelligence"

# Create MCP config snippet
MCP_CONFIG="$INSTALL_DIR/mcp-config.json"
cat > "$MCP_CONFIG" << EOF
{
  "claude-intelligence": {
    "command": "python3",
    "args": ["$INSTALL_DIR/mcp_server.py"],
    "description": "Project memory for Claude Code"
  }
}
EOF

echo ""
echo "✅ Installation complete!"
echo ""
echo "To activate Claude Intelligence:"
echo ""
echo "1. Add to your MCP configuration:"
echo "   cat $MCP_CONFIG"
echo ""
echo "2. Or run standalone:"
echo "   $INSTALL_DIR/claude-intelligence"
echo ""
echo "3. Quick test:"
echo "   cd your-project && python3 $INSTALL_DIR/mcp_server.py"
echo ""
echo "For more info: https://github.com/banton/claude-dementia"