#!/bin/bash
# Setup script for Claude Memory Assistant

echo "🚀 Setting up Claude Memory Assistant..."

# Make scripts executable
chmod +x scripts/*.py

# Create memory directories if they don't exist
mkdir -p memory/{architecture,implementations,fixes,patterns,questions,context,decisions}
mkdir -p working-memory/{development-guides,investigation-logs,planning-docs}
mkdir -p .direction/{epic-plans,implementation-plans,test-strategies}

# Create initial current-session.md if it doesn't exist
if [ ! -f memory/current-session.md ]; then
    echo "# Current Session - Initial Setup" > memory/current-session.md
    echo "" >> memory/current-session.md
    echo "Memory system initialized on $(date)" >> memory/current-session.md
fi

# Git hooks setup (optional)
read -p "Do you want to set up git hooks? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Create .git/hooks directory if it doesn't exist
    mkdir -p .git/hooks
    
    # Post-commit hook
    cat > .git/hooks/post-commit << 'EOF'
#!/bin/bash
# Auto-detect patterns after each commit
if [ -f scripts/pattern-detector.py ]; then
    echo "🔍 Detecting patterns in committed code..."
    python scripts/pattern-detector.py
fi
EOF
    chmod +x .git/hooks/post-commit
    
    # Pre-push hook
    cat > .git/hooks/pre-push << 'EOF'
#!/bin/bash
# Check for unanswered questions before push
if [ -f scripts/question-tracker.py ]; then
    echo "❓ Checking question status..."
    python scripts/question-tracker.py
    
    # Check if there are old unanswered questions
    if grep -q "Old Unanswered Questions" memory/questions/status-report.md 2>/dev/null; then
        echo "⚠️  WARNING: You have old unanswered questions!"
        echo "Consider reviewing them before pushing."
    fi
fi
EOF
    chmod +x .git/hooks/pre-push
    
    echo "✅ Git hooks installed!"
fi

# Create convenience aliases
echo ""
echo "💡 Add these aliases to your shell configuration (.bashrc/.zshrc):"
echo ""
echo "alias claude-start='python scripts/memory-assistant.py start'"
echo "alias claude-end='python scripts/memory-assistant.py end'"
echo "alias claude-search='python scripts/memory-assistant.py search'"
echo "alias claude-questions='python scripts/question-tracker.py'"
echo "alias claude-patterns='python scripts/pattern-detector.py'"
echo ""

echo "✅ Setup complete!"
echo ""
echo "🎯 Quick start:"
echo "  1. Start a session:  python scripts/memory-assistant.py start"
echo "  2. End a session:    python scripts/memory-assistant.py end"
echo "  3. Search memory:    python scripts/memory-assistant.py search 'your query'"
echo ""
