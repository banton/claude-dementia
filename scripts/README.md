# Claude Memory Assistant Tools

These lightweight tools provide the lowest-hanging fruit for enhancing the Claude memory system with semi-automated assistance.

## 🎯 Quick Value Proposition

Each tool addresses a specific pain point with minimal setup:

1. **Session Logger** (🏆 Highest ROI) - Auto-generates session summaries from git commits
2. **Pattern Detector** - Finds reusable patterns in your code automatically  
3. **Question Tracker** - Ensures important questions don't get forgotten
4. **Memory Search** - Quickly find solutions to problems you've solved before
5. **Memory Assistant** - Orchestrates all tools with simple commands

## 🚀 Installation

```bash
# Make setup script executable
chmod +x setup-memory-tools.sh

# Run setup (creates directories, optionally installs git hooks)
./setup-memory-tools.sh

# Test that everything works
python scripts/memory-assistant.py help
```

## 🛠️ Tool Details

### 1. Session Logger (`session-logger.py`)
**Problem**: Manually writing session summaries is tedious and often skipped  
**Solution**: Auto-generate from git activity

```bash
# Run at end of session
python scripts/session-logger.py

# Creates/updates memory/current-session.md with:
# - Commit list
# - Files changed (created/modified/deleted)
# - Test files touched
# - Memory updates made
```

**Time saved**: 5-10 minutes per session  
**Accuracy gain**: Never miss documenting a change

### 2. Pattern Detector (`pattern-detector.py`)
**Problem**: Patterns emerge but aren't documented  
**Solution**: Automatically detect and document patterns

```bash
# Detect patterns in recent changes
python scripts/pattern-detector.py

# Finds:
# - Error handling patterns
# - Validation patterns  
# - API endpoint patterns
# - Test patterns (AAA format)
# - Common exceptions used
```

**Value**: Builds your pattern library automatically

### 3. Question Tracker (`question-tracker.py`)
**Problem**: Questions get asked but answers are forgotten  
**Solution**: Track all questions and remind about old ones

```bash
# Check question status
python scripts/question-tracker.py

# Reports:
# - Total open questions
# - Questions older than 7 days
# - Blocked questions to revisit
# - Potential questions in code comments (TODO: ask, etc.)
```

**Value**: Never lose important clarifications

### 4. Memory Search (`memory-search.py`)
**Problem**: Solving the same problem multiple times  
**Solution**: Fast search through all memory files

```bash
# Search for specific topics
python scripts/memory-search.py "error handling"
python scripts/memory-search.py "api authentication" --type pattern
python scripts/memory-search.py "timeout" --type fix

# Features:
# - Weighted search (fixes weighted higher than general mentions)
# - Preview of matching content
# - Type-specific search (fix/pattern/question)
# - Auto-rebuilds stale index
```

**Value**: Find previous solutions in seconds

### 5. Memory Assistant (`memory-assistant.py`)
**Problem**: Running multiple tools is cumbersome  
**Solution**: Single interface to all tools

```bash
# Start of session routine
python scripts/memory-assistant.py start
# Shows: unanswered questions, last session summary

# End of session routine  
python scripts/memory-assistant.py end
# Runs: session logger, pattern detector, question check, index rebuild

# Quick search
python scripts/memory-assistant.py search "database connection"
```

## 🪝 Git Hook Integration

The setup script can install git hooks for you:

### Post-Commit Hook
- Automatically runs pattern detector after each commit
- Helps build pattern library without manual effort

### Pre-Push Hook  
- Checks for old unanswered questions
- Reminds you to address blockers before pushing

## 💡 Usage Patterns

### Daily Workflow
```bash
# Morning
claude-start  # Alias for: python scripts/memory-assistant.py start

# During work - search when you hit a familiar problem
claude-search "cors error"

# End of day
claude-end    # Alias for: python scripts/memory-assistant.py end
# Then spend 2 minutes adding context to the auto-generated session summary
```

### Weekly Maintenance
```bash
# Review patterns detected during the week
cat memory/patterns/detected-patterns-*.md

# Check question backlog
python scripts/question-tracker.py

# Maybe consolidate similar patterns into clean documentation
```

## 🎯 ROI Analysis

### Time Investment
- Initial setup: 5 minutes
- Daily usage: 2-3 minutes
- Weekly review: 10 minutes

### Time Saved
- Session documentation: 5-10 minutes/day
- Finding previous solutions: 10-30 minutes per incident  
- Avoiding repeated work: Hours per month
- Question tracking: Prevents blocked work

### Quality Improvements
- Consistent session documentation
- Growing pattern library
- No lost context between sessions
- Faster problem resolution

## 🔧 Customization

Each tool is a simple Python script that can be customized:

- Add more pattern detection rules
- Customize search weights
- Add new file type support
- Integrate with your specific workflow

## 🚦 Next Steps

1. **Start Small**: Just use the session logger for a week
2. **Add Search**: When you think "I've solved this before..."
3. **Track Questions**: When you have more than 3 open questions
4. **Detect Patterns**: After you've got 20+ commits
5. **Full Integration**: Use the assistant for daily routines

## 🤝 Contributing

These tools are intentionally simple. Feel free to:
- Add new pattern detection rules
- Improve search algorithms  
- Add new tools to the suite
- Share your customizations

---

**Remember**: The goal is to make memory management effortless, not perfect. Even using just one tool will improve your Claude Code experience significantly.
