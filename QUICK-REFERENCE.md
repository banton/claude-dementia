# Claude Memory System v3.0 - Quick Reference Card

## 🚀 Session Start
```bash
cat CLAUDE.md memory/active/status.md memory/active/context.md
```

## 💾 Memory Updates
```bash
./memory/update.sh "Brief description of what changed"
```

## 📊 Token Check
```bash
./memory/compress.sh
```

## 🗓 Weekly Maintenance
```bash
./memory/weekly-maintenance.sh
```

## 📁 Directory Structure
```
memory/
├── active/      (3k tokens) Current work
├── reference/   (5k tokens) Stable info
├── patterns/    Code patterns
├── fixes/       Problem solutions
├── questions/   Clarifications
└── archive/     Compressed old files
```

## 📝 File Templates

### Fix: `memory/fixes/YYYY-MM-DD-name.md`
```markdown
# YYYY-MM-DD Issue Name
## Problem: [One line]
## Cause: [Root cause]
## Fix: [Solution]
## Prevention: [Test/check added]
```

### Question: `memory/questions/YYYY-MM-DD-topic.md`
```markdown
# YYYY-MM-DD Topic
## Status: OPEN|ANSWERED
## Q: [Specific question]
## Context: [Why needed]
## Answer: [When received]
```

### Pattern: `memory/patterns/pattern-name.md`
```markdown
# Pattern Name
## Use When: [Scenario]
## Solution: [Approach]
## Example: path/to/file
## Trade-offs: [Considerations]
```

## 🔍 Search Commands
```bash
# Search all memory
grep -r "term" memory/

# Search archives
zgrep "term" memory/archive/*.tar.gz

# Find recent updates
grep -A2 "Update:" memory/active/status.md | tail -20
```

## 📋 Best Practices

### ✅ DO
- Update after each feature/fix
- Use tables over paragraphs
- Reference file paths
- Keep summaries to one line
- Trust automation

### ❌ DON'T
- Store full code
- Write narratives
- Skip updates
- Fight compression
- Exceed budgets

## 🚨 Emergency Commands

### Over Token Budget
```bash
./memory/compress.sh
./memory/weekly-maintenance.sh
head -50 memory/active/status.md > temp && mv temp memory/active/status.md
```

### Lost Context
```bash
cat CLAUDE.md
cat memory/active/status.md
git log --oneline -20
ls -la memory/reference/
```

### Find Old Info
```bash
find memory -name "*.md" -exec grep -l "search term" {} \;
zgrep "search term" memory/archive/*.tar.gz
```

## 📊 Token Budgets
| Category | Tokens | Purpose |
|----------|---------|---------|
| CLAUDE.md | 1,000 | Core guide |
| Active | 3,000 | Current work |
| Reference | 5,000 | Stable info |
| Buffer | 1,000 | Overflow |
| **Total** | **10,000** | **Hard limit** |

## 🎯 Compression Tips
- Tables = 3:1 vs prose
- Bullets = 2:1 vs paragraphs  
- One-line summaries
- Path references only
- No decorative formatting

## 🔄 Git Integration
```bash
# Post-commit hook
echo './memory/update.sh "Commit: $(git log -1 --pretty=%B)"' > .git/hooks/post-commit
chmod +x .git/hooks/post-commit
```

## ⏰ Cron Setup
```bash
# Add to crontab
0 0 * * 0 /path/to/project/memory/weekly-maintenance.sh
```

---

**Remember**: Information density > Verbosity | Automation > Manual | Progress > Perfection

**Version**: 3.0.0 | **Budget**: 10,000 tokens | **Updated**: 2024-06-22
