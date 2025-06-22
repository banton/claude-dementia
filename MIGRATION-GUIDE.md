# Migration Guide: v2.0 to v3.0

## Overview
Version 3.0 introduces intelligent token management with automatic compression, reducing the complexity while improving efficiency. The core structure remains familiar, but with automated maintenance.

## Key Changes

### 1. Token Budget System (NEW)
- **Hard limit**: 10,000 tokens total
- **Active memory**: 3,000 tokens (auto-compressed)
- **Reference memory**: 5,000 tokens (weekly compression)
- **Automatic enforcement**: No manual token counting

### 2. Simplified Structure
```bash
# v2.0 Structure (complex)
memory/
├── current-session.md
├── architecture/
├── implementations/
├── fixes/
├── patterns/
├── questions/
├── context/
├── decisions/
working-memory/
├── development-guides/
├── investigation-logs/
├── planning-docs/
.direction/
├── epic-plans/
├── implementation-plans/
└── test-strategies/

# v3.0 Structure (streamlined)
memory/
├── active/           # Current work only
│   ├── status.md    # Dashboard
│   └── context.md   # Task context
├── reference/        # Stable knowledge
│   ├── architecture.md
│   ├── patterns.md
│   ├── features.md
│   └── decisions.md
├── patterns/         # Reusable solutions
├── fixes/           # Problem resolutions
├── implementations/ # Feature tracking
├── questions/       # Clarifications
└── archive/         # Auto-compressed
```

### 3. Automation Scripts (NEW)
- `memory/update.sh` - Quick updates with compression
- `memory/compress.sh` - Token budget enforcement
- `memory/weekly-maintenance.sh` - Automated archival

### 4. Compressed Documentation
- Tables over paragraphs (3:1 compression)
- One-line summaries with bullets
- File path references instead of code
- Automatic truncation when over budget

## Migration Steps

### Step 1: Backup Existing Memory
```bash
cd /your/project
tar -czf memory-v2-backup.tar.gz memory/ working-memory/ .direction/
```

### Step 2: Install v3.0 System
```bash
# Get v3.0
git clone https://github.com/[username]/claude-dementia.git
cd claude-dementia
git checkout v3.0.0

# Copy new structure
cp -r memory /your/project/memory-v3
cp CLAUDE.md /your/project/
chmod +x /your/project/memory-v3/*.sh
```

### Step 3: Migrate Active Content
```bash
# Create compressed summaries
cd /your/project

# Migrate current session
head -50 memory/current-session.md > memory-v3/active/status.md

# Extract current context
grep -A 10 "Current Task" memory/context/current-task.md > memory-v3/active/context.md
```

### Step 4: Consolidate Reference Material
```bash
# Combine architecture files
cat memory/architecture/*.md | head -200 > memory-v3/reference/architecture.md

# Extract key patterns
find memory/patterns -name "*.md" -exec head -20 {} \; > memory-v3/reference/patterns.md

# Consolidate decisions
find memory/decisions -name "*.md" -exec head -10 {} \; > memory-v3/reference/decisions.md
```

### Step 5: Preserve Specialized Content
```bash
# Keep patterns separate
cp memory/patterns/*.md memory-v3/patterns/

# Preserve fixes
cp memory/fixes/*.md memory-v3/fixes/

# Keep open questions
cp memory/questions/*OPEN*.md memory-v3/questions/
```

### Step 6: Archive Old System
```bash
# Move old memory aside
mv memory memory-v2-old
mv memory-v3 memory

# Test compression
./memory/compress.sh
```

### Step 7: Update Workflow
```bash
# Replace verbose session summaries with:
./memory/update.sh "Brief summary of changes"

# Instead of manual architecture updates:
echo "- Decision: [choice]" >> memory/active/status.md

# For weekly cleanup (add to cron):
0 0 * * 0 /your/project/memory/weekly-maintenance.sh
```

## Conversion Examples

### Session Summary (Before/After)

**v2.0 Verbose Format**:
```markdown
# Current Session Summary - Implementing User Authentication

## Session Objectives
The primary goal for this session was to implement a complete user authentication system...
[200+ lines of detailed narrative]
```

**v3.0 Compressed Format**:
```markdown
### Update: 2024-01-20 14:30
- Implemented JWT auth: login/logout/refresh endpoints
- Added password hashing with bcrypt
- 15 tests passing, coverage 92%
- Next: Password reset flow
```

### Architecture Documentation

**v2.0 Verbose**:
```markdown
The system uses a traditional three-tier architecture with clear separation of concerns...
[Multiple paragraphs explaining each layer]
```

**v3.0 Compressed**:
```markdown
## Architecture
| Layer | Purpose | Key Files |
|-------|---------|-----------|
| API | HTTP endpoints | src/api/routes/ |
| Domain | Business logic | src/domain/services/ |
| Data | Persistence | src/infrastructure/db/ |
```

### Pattern Documentation

**v2.0**:
```python
# Complete code example with extensive comments
def repository_pattern_example():
    """
    This demonstrates the repository pattern...
    [50+ lines of code]
    """
```

**v3.0**:
```markdown
## Repository Pattern
- **Use**: Data access abstraction
- **Example**: src/repositories/user_repo.py
- **Benefits**: Testable, swappable backends
```

## Troubleshooting Migration

### "Too much content to migrate"
Focus on active work only:
```bash
# Just last 7 days
find memory -name "*.md" -mtime -7 -exec cat {} \; > recent.md
# Then extract key points to memory-v3/active/status.md
```

### "Lost important documentation"
Check the backup:
```bash
tar -tf memory-v2-backup.tar.gz | grep "important-file"
tar -xzf memory-v2-backup.tar.gz path/to/important-file.md
```

### "Token budget exceeded after migration"
Run aggressive compression:
```bash
# Reduce file sizes
head -50 memory/active/status.md > memory/active/status.tmp
mv memory/active/status.tmp memory/active/status.md

# Force archival
./memory/weekly-maintenance.sh
```

## Benefits After Migration

### Immediate
- ✅ Always within token budget
- ✅ Faster Claude response times
- ✅ No manual maintenance needed
- ✅ Cleaner, focused documentation

### Long-term
- ✅ Sustainable across unlimited sessions
- ✅ Consistent information density
- ✅ Searchable archives
- ✅ Reduced cognitive load

## Quick Reference Card

```bash
# Daily workflow
./memory/update.sh "what I did"    # Throughout day
./memory/compress.sh               # Check tokens
cat memory/active/status.md        # Review status

# Weekly workflow  
./memory/weekly-maintenance.sh     # Archive old content
grep -r "topic" memory/            # Search everything

# Starting sessions
cat CLAUDE.md memory/active/*.md   # Load context

# Ending sessions
./memory/update.sh "Session done: X complete, Y next"
```

---

Migration typically takes 30-60 minutes. The investment pays off immediately through improved efficiency and automated maintenance. Welcome to sustainable AI collaboration!
