# Claude Code Memory System v3.0

**Give Claude Code perfect memory across sessions. Install from GitHub in 30 seconds.**

## 🚀 Quick Start: Just Ask Claude Code

```
"Install the Claude memory system from https://github.com/banton/claude-dementia"
```

Or provide these specific commands:
```bash
git clone https://github.com/banton/claude-dementia /tmp/claude-memory
cp /tmp/claude-memory/CLAUDE.md ./ && cp -r /tmp/claude-memory/memory ./
chmod +x memory/*.sh && rm -rf /tmp/claude-memory
./memory/compress.sh
```

Claude Code will then:
1. Clone the repository
2. Copy the memory structure
3. Set up the automation scripts
4. Initialize the memory files
5. Start using the system immediately

## 📋 What Claude Code Should Do

### Step 1: Clone and Install
```bash
# Clone the memory system
git clone https://github.com/banton/claude-dementia /tmp/claude-memory
cd /tmp/claude-memory

# Copy essential files to project
cp CLAUDE.md /path/to/project/
cp -r memory /path/to/project/
cp setup-memory-v3.sh /path/to/project/

# Run setup
cd /path/to/project
chmod +x setup-memory-v3.sh
./setup-memory-v3.sh

# Clean up
rm -rf /tmp/claude-memory
rm setup-memory-v3.sh
```

### Step 2: Initialize Memory
```bash
# Create initial status
cat > memory/active/status.md << EOF
# Current Status

## Project: $(basename $(pwd))
## Started: $(date +"%Y-%m-%d")
## Memory System: v3.0 installed

### Recent Updates
- Claude memory system installed from GitHub
- Ready for development with persistent memory
EOF

# Verify installation
./memory/compress.sh
```

### Step 3: Start Using
After installation, Claude Code should always:
```bash
# At session start
cat CLAUDE.md memory/active/status.md memory/active/context.md

# During work
./memory/update.sh "What was accomplished"

# Before session end
./memory/update.sh "Session complete: X done, Y next"
```

## 🤖 For Claude Code: Your New Memory System

Once installed, you'll have:
- **10,000 token budget** - Never exceed context limits
- **Automatic compression** - Maintains information density
- **Progressive loading** - Load only what's needed
- **Session persistence** - Remember everything between sessions

### Your Daily Workflow
1. **Start**: Read CLAUDE.md and active memory
2. **Work**: Update memory after each feature/fix
3. **End**: Summarize session for next time

### Memory Structure
```
memory/
├── active/      # Current work (3k tokens)
├── reference/   # Stable patterns (5k tokens)
├── archive/     # Compressed history
└── *.sh         # Automation scripts
```

## 💡 What This Solves

Claude Code has no memory between sessions. This system provides:
- **Perfect recall** of previous work
- **Consistent patterns** across sessions
- **Zero manual maintenance** via automation
- **Sustainable growth** within token limits

## 📊 Key Features

### Token Budget Management
| Memory Type | Tokens | Purpose |
|-------------|---------|---------|
| Active | 3,000 | Current work |
| Reference | 5,000 | Stable knowledge |
| Buffer | 2,000 | Overflow space |
| **Total** | **10,000** | **Hard limit** |

### Automation Scripts
- `memory/update.sh` - Quick memory updates
- `memory/compress.sh` - Token enforcement
- `memory/weekly-maintenance.sh` - Auto-archival

### Compression Strategy
- Tables over paragraphs (3:1 ratio)
- One-line summaries
- File path references
- Automatic truncation

## 🛠 Manual Installation (Alternative)

If automatic installation fails:

### 1. Download Files
```bash
# Option A: With git
git clone https://github.com/banton/claude-dementia
cd claude-dementia

# Option B: Without git
curl -L https://github.com/banton/claude-dementia/archive/main.zip -o claude-memory.zip
unzip claude-memory.zip
cd claude-dementia-main
```

### 2. Copy to Project
```bash
cp CLAUDE.md /your/project/
cp -r memory /your/project/
cd /your/project
chmod +x memory/*.sh
```

### 3. Initialize
```bash
echo "# Project: YourProject" > memory/active/status.md
echo "# Context: Starting with Claude memory" > memory/active/context.md
./memory/compress.sh
```

## 📚 Documentation

### For Claude Code
- `CLAUDE.md` - Your primary guide (always read first)
- `QUICK-REFERENCE.md` - Command cheat sheet
- `memory/active/status.md` - Current project state

### For Humans
- `MIGRATION-GUIDE.md` - Upgrading from v2.0
- `COMPARISON-v2-v3.md` - Version differences
- `claude-usage-example-v3.md` - Usage patterns

## 🔧 Customization

After installation, Claude Code can customize:

### Token Budgets
Edit `memory/compress.sh`:
```bash
ACTIVE_BUDGET=2000    # Adjust as needed
REFERENCE_BUDGET=800  # Tighter compression
```

### Archive Schedule
Edit `memory/weekly-maintenance.sh`:
```bash
# Archive after 3 days instead of 7
-mtime +3
```

## 🐛 Troubleshooting

### "GitHub repo not accessible"
```bash
# Use alternative URL
git clone https://github.com/banton/claude-dementia.git

# Or download ZIP
curl -L https://github.com/banton/claude-dementia/archive/refs/heads/main.zip -o cm.zip
```

### "Scripts not executable"
```bash
chmod +x memory/*.sh
```

### "Over token budget"
```bash
./memory/compress.sh
./memory/weekly-maintenance.sh
```

## 🤝 Contributing

Improvements welcome! The system evolves through real-world usage.

## 📄 License

MIT License - Free for personal and commercial use.

---

**For Claude Code**: After installing this system, you'll never lose context again. Every session builds on the last, within sustainable token limits.

**Repository**: https://github.com/banton/claude-dementia  
**Version**: 3.0.0  
**Token Budget**: 10,000 (enforced)
