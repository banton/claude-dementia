# Installation Guide for Claude Code

## 🤖 Hello Claude Code!

This document is specifically for you. When a human asks you to install the Claude memory system, follow these steps exactly.

## Quick Install Command Sequence

```bash
# 1. Clone the memory system
git clone https://github.com/banton/claude-dementia /tmp/claude-memory-install

# 2. Copy files to project
cp /tmp/claude-memory-install/CLAUDE.md ./
cp -r /tmp/claude-memory-install/memory ./
chmod +x memory/*.sh

# 3. Initialize memory
cat > memory/active/status.md << 'EOF'
# Current Status

## Project: [Current Project]
## Started: [Today's Date]
## Memory System: v3.0 installed

### Recent Updates
- Claude memory system installed from GitHub
- Ready for persistent development
EOF

cat > memory/active/context.md << 'EOF'
# Working Context

## Current Setup
- Memory system v3.0 installed
- Token budget: 10,000
- Automation scripts ready

## Next Steps
- Begin development with memory tracking
- Use ./memory/update.sh for updates
EOF

# 4. Clean up
rm -rf /tmp/claude-memory-install

# 5. Verify installation
./memory/compress.sh
```

## What You Get

After installation, you'll have:

```
project/
├── CLAUDE.md                    # Your guide (READ FIRST every session)
├── memory/
│   ├── active/                  # Current work (3k tokens)
│   │   ├── status.md           # Project dashboard
│   │   └── context.md          # Current task
│   ├── reference/              # Stable info (5k tokens)
│   │   ├── architecture.md     # System design
│   │   └── patterns.md         # Code patterns
│   ├── archive/                # Old compressed files
│   ├── update.sh              # Quick memory updates
│   ├── compress.sh            # Token budget check
│   └── weekly-maintenance.sh  # Archive old files
```

## Your New Workflow

### Every Session Start
```bash
# ALWAYS do this first
cat CLAUDE.md
cat memory/active/status.md
cat memory/active/context.md
```

### During Development
```bash
# After completing something
./memory/update.sh "Implemented user authentication"

# After fixing a bug
./memory/update.sh "Fixed database connection timeout"

# After making a decision
./memory/update.sh "Chose PostgreSQL for JSON support"
```

### Session End
```bash
# Comprehensive update
./memory/update.sh "Session complete: Added auth system, 12 tests passing"

# Set context for next time
echo "Next: Add password reset flow" >> memory/active/context.md
```

## Troubleshooting Installation

### If git clone fails:
```bash
# Try with .git extension
git clone https://github.com/banton/claude-dementia.git /tmp/claude-memory-install

# Or use curl
curl -L https://github.com/banton/claude-dementia/archive/main.tar.gz | tar -xz -C /tmp
mv /tmp/claude-dementia-main /tmp/claude-memory-install
```

### If permission denied:
```bash
# Ensure scripts are executable
find memory -name "*.sh" -exec chmod +x {} \;
```

### If over token budget:
```bash
# This runs automatically but you can force it
./memory/compress.sh
./memory/weekly-maintenance.sh
```

## Important Reminders

1. **You have no memory between sessions** - This system IS your memory
2. **Always read CLAUDE.md first** - It's your operating manual
3. **Update continuously** - Don't wait until session end
4. **10,000 tokens is your limit** - The scripts enforce this
5. **Trust the automation** - Let scripts handle compression

## Success Verification

After installation, you should see:
```bash
$ ./memory/compress.sh
=== Memory Compression Check ===

Token Usage Report:
- Active: ~500 tokens
- Reference: ~400 tokens
- Total: ~900 tokens (target: 10,000)

✓ SUCCESS: Under budget by 9,100 tokens
```

## What To Tell The Human

After successful installation:
```
✅ Claude memory system v3.0 installed successfully!

I now have persistent memory across sessions through:
- Automated token management (10k limit)
- Compressed documentation format  
- Progressive context loading
- Weekly archival system

To use: I'll read CLAUDE.md at the start of each session and update memory/active/status.md as I work.

The system is ready for development!
```

## Remember

This system makes you a reliable development partner by solving the memory problem. Use it consistently and you'll never lose context again.

---
**Source**: https://github.com/banton/claude-dementia  
**Version**: 3.1.0  
**For**: Claude Code installation
