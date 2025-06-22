#!/bin/bash
# Claude Memory System v3.0 - Quick Setup Script
# Can be run directly after cloning from GitHub

echo "🧠 Claude Memory System v3.0 Setup"
echo "🌐 Source: https://github.com/banton/claude-dementia"
echo "=================================="

# Check if we're in a git repository
if [ ! -d .git ]; then
    echo "⚠️  Warning: Not in a git repository. Continue anyway? (y/n)"
    read -r response
    if [ "$response" != "y" ]; then
        echo "Setup cancelled."
        exit 1
    fi
fi

# Create memory structure
echo "📁 Creating memory directories..."
mkdir -p memory/{active,reference,archive,patterns,fixes,implementations,questions}

# Copy memory scripts
echo "📝 Installing memory scripts..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Create update.sh
cat > memory/update.sh << 'EOF'
#!/bin/bash
# Quick memory update script

SUMMARY="$1"
if [ -z "$SUMMARY" ]; then
    echo "Usage: ./update.sh 'Summary of changes'"
    exit 1
fi

DATE=$(date +"%Y-%m-%d %H:%M")
echo "" >> memory/active/status.md
echo "### Update: $DATE" >> memory/active/status.md
echo "- $SUMMARY" >> memory/active/status.md

# Run compression check
./memory/compress.sh

echo "✓ Memory updated"
EOF

# Create compress.sh
cat > memory/compress.sh << 'EOF'
#!/bin/bash
# Memory compression script - maintains 10k token budget

count_tokens() {
    echo $(cat "$1" 2>/dev/null | wc -w | awk '{print int($1 * 1.3)}')
}

compress_file() {
    local file=$1
    local target_tokens=$2
    local current_tokens=$(count_tokens "$file")
    
    if [ $current_tokens -gt $target_tokens ]; then
        echo "Compressing $file from $current_tokens to ~$target_tokens tokens..."
        # Keep most important content (assuming it's at the top)
        head -n $(($target_tokens / 10)) "$file" > "$file.tmp"
        mv "$file.tmp" "$file"
    fi
}

echo "=== Memory Compression Check ==="

# Token budgets
ACTIVE_BUDGET=1500   # Per file in active
REFERENCE_BUDGET=1000 # Per file in reference

# Compress active files
for file in memory/active/*.md; do
    [ -f "$file" ] && compress_file "$file" $ACTIVE_BUDGET
done

# Compress reference files
for file in memory/reference/*.md; do
    [ -f "$file" ] && compress_file "$file" $REFERENCE_BUDGET
done

# Report totals
active_total=$(find memory/active -name "*.md" -exec cat {} + 2>/dev/null | wc -w | awk '{print int($1 * 1.3)}')
reference_total=$(find memory/reference -name "*.md" -exec cat {} + 2>/dev/null | wc -w | awk '{print int($1 * 1.3)}')
total=$((active_total + reference_total))

echo ""
echo "Token Usage Report:"
echo "- Active: $active_total tokens"
echo "- Reference: $reference_total tokens" 
echo "- Total: $total tokens (target: 10,000)"
echo ""

if [ $total -gt 10000 ]; then
    echo "⚠️  WARNING: Over budget by $((total - 10000)) tokens"
else
    echo "✓ SUCCESS: Under budget by $((10000 - total)) tokens"
fi
EOF

# Create weekly-maintenance.sh
cat > memory/weekly-maintenance.sh << 'EOF'
#!/bin/bash
# Weekly memory maintenance

echo "=== Weekly Memory Maintenance ==="
DATE=$(date +%Y-%m-%d)

# Archive files older than 7 days
echo "Archiving old files..."
mkdir -p memory/archive/$DATE
find memory/active -name "*.md" -mtime +7 -exec mv {} memory/archive/$DATE/ \; 2>/dev/null

# Compress archives
if [ "$(ls -A memory/archive/$DATE 2>/dev/null)" ]; then
    tar -czf memory/archive/$DATE.tar.gz -C memory/archive $DATE
    rm -rf memory/archive/$DATE
    echo "✓ Archived old files to memory/archive/$DATE.tar.gz"
else
    rmdir memory/archive/$DATE 2>/dev/null
fi

echo "✓ Weekly maintenance complete"
EOF

# Make scripts executable
chmod +x memory/*.sh

# Initialize memory files
echo "📝 Initializing memory files..."

# Create status.md
cat > memory/active/status.md << EOF
# Current Status

## Project: $(basename $(pwd))
## Started: $(date +"%Y-%m-%d")

### Recent Updates
- Initial memory system setup

### Quick Stats
- Token Budget: 10,000
- Active Memory: 3,000 tokens
- Reference Memory: 5,000 tokens
EOF

# Create context.md
cat > memory/active/context.md << EOF
# Working Context

## Current Task
- Setting up Claude Memory System v3.0

## Next Steps
1. Read CLAUDE.md for system overview
2. Start development with memory tracking
3. Use ./memory/update.sh for updates
EOF

# Create architecture.md
cat > memory/reference/architecture.md << EOF
# Architecture Reference

## System Overview
[Project architecture details]

## Key Components
[Component list]

## Technology Stack
[Technologies used]
EOF

# Create patterns.md
cat > memory/reference/patterns.md << EOF
# Code Patterns

## Common Patterns
[Patterns used in this project]
EOF

# Copy CLAUDE.md if it exists in script directory
if [ -f "$SCRIPT_DIR/CLAUDE.md" ]; then
    echo "📋 Copying CLAUDE.md..."
    cp "$SCRIPT_DIR/CLAUDE.md" ./CLAUDE.md
else
    echo "⚠️  CLAUDE.md not found in script directory"
    echo "   Download from: https://github.com/[username]/claude-dementia"
fi

# Setup git hooks (optional)
echo ""
echo "🔗 Would you like to setup git hooks for automatic memory updates? (y/n)"
read -r response
if [ "$response" = "y" ]; then
    # Post-commit hook
    cat > .git/hooks/post-commit << 'EOF'
#!/bin/bash
# Auto-update memory on commit
if [ -f memory/update.sh ]; then
    COMMIT_MSG=$(git log -1 --pretty=%B)
    ./memory/update.sh "Commit: $COMMIT_MSG"
fi
EOF
    chmod +x .git/hooks/post-commit
    echo "✓ Git hooks installed"
fi

# Add cron job (optional)
echo ""
echo "⏰ Would you like to setup weekly maintenance cron job? (y/n)"
read -r response
if [ "$response" = "y" ]; then
    CRON_CMD="0 0 * * 0 $(pwd)/memory/weekly-maintenance.sh"
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "✓ Weekly maintenance scheduled (Sundays at midnight)"
fi

# Final report
echo ""
echo "✅ Setup Complete!"
echo ""
echo "📚 Quick Start Guide:"
echo "1. Start Claude with: 'Read CLAUDE.md and memory/active/status.md'"
echo "2. Update memory with: ./memory/update.sh \"What you did\""
echo "3. Check tokens with: ./memory/compress.sh"
echo "4. Weekly cleanup: ./memory/weekly-maintenance.sh"
echo ""
echo "📖 Full documentation: https://github.com/[username]/claude-dementia"
echo ""
echo "Happy coding with perfect memory! 🚀"
