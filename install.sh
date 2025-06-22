#!/bin/bash
# Claude Memory System - One-line installer for Claude Code
# Usage: curl -sSL https://raw.githubusercontent.com/banton/claude-dementia/main/install.sh | bash

set -e

echo "🧠 Installing Claude Memory System v3.0..."

# Clone to temp directory
TEMP_DIR="/tmp/claude-memory-$$"
git clone --quiet https://github.com/banton/claude-dementia "$TEMP_DIR" 2>/dev/null || {
    echo "❌ Failed to clone repository"
    exit 1
}

# Copy essential files
cp "$TEMP_DIR/CLAUDE.md" ./ 2>/dev/null || { echo "❌ Failed to copy CLAUDE.md"; exit 1; }
cp -r "$TEMP_DIR/memory" ./ 2>/dev/null || { echo "❌ Failed to copy memory directory"; exit 1; }

# Make scripts executable
chmod +x memory/*.sh

# Initialize memory
cat > memory/active/status.md << EOF
# Current Status

## Project: $(basename $(pwd))
## Started: $(date +"%Y-%m-%d")
## Memory System: v3.0 (installed $(date +"%Y-%m-%d %H:%M"))

### Recent Updates
- Claude memory system installed from GitHub
- Token budget: 10,000 (enforced)
- Automation scripts ready
EOF

cat > memory/active/context.md << EOF
# Working Context

## Current Setup
- Memory system v3.0 installed
- Progressive loading enabled
- Compression automated

## Next Steps
- Read CLAUDE.md for complete guide
- Start work with memory tracking
- Use ./memory/update.sh for updates
EOF

# Clean up
rm -rf "$TEMP_DIR"

# Run initial compression check
echo ""
./memory/compress.sh

echo ""
echo "✅ Installation complete!"
echo ""
echo "📚 Quick Start:"
echo "1. Read CLAUDE.md for the complete guide"
echo "2. Check memory/active/status.md for current state"
echo "3. Update with: ./memory/update.sh \"what changed\""
echo ""
echo "🚀 Ready for development with persistent memory!"
