# Common Patterns

## Session Management
```bash
# Start session
cat memory/active/status.md
cat memory/active/context.md

# During work
./memory/update.sh "What changed"

# End session
./memory/update.sh "Session complete: X achieved"
```

## Documentation Pattern
- **Summary**: One line max
- **Details**: Bullet points
- **Code**: Reference paths only
- **Decisions**: Table format

## Fix Documentation
```markdown
# YYYY-MM-DD-issue-name.md
## Problem: [Brief description]
## Root Cause: [Why it happened]
## Solution: [What fixed it]
## Prevention: [How to avoid]
```

## Question Tracking
```markdown
# YYYY-MM-DD-topic.md
## Status: OPEN|ANSWERED
## Question: [What needs clarification]
## Context: [Why it matters]
## Answer: [When received]
```
