# Claude Code Memory System v3.0 - Usage Example

## Starting a New Project

### 1. Initial Setup
```bash
# Copy memory system to your project
cp -r claude-dementia/memory /path/to/myproject/
cp claude-dementia/CLAUDE.md /path/to/myproject/

# Make scripts executable
chmod +x /path/to/myproject/memory/*.sh

# Initialize memory
cd /path/to/myproject
echo "# Project: MyProject" > memory/active/status.md
echo "# Context: Initial setup" > memory/active/context.md
```

### 2. First Claude Session
```
You: "Here's your memory system. Read CLAUDE.md and memory/active/status.md first. We're building a task management API with FastAPI."

Claude: [Reads files, understands the system]

You: "Let's start by creating the basic project structure."

Claude: [Creates structure, then updates memory]
```

## During Development

### Quick Memory Updates
```bash
# After implementing a feature
./memory/update.sh "Added user authentication endpoints"

# After fixing a bug
./memory/update.sh "Fixed: JWT token expiration issue"

# After making a decision
./memory/update.sh "Decided: Use PostgreSQL for data persistence"
```

### Tracking Issues and Fixes
```bash
# When you encounter an issue
cat > memory/fixes/2024-01-20-jwt-expiration.md << EOF
# 2024-01-20 JWT Expiration Issue
## Problem: Tokens expiring immediately
## Cause: Timezone mismatch in expiration calculation
## Fix: Use UTC for all token timestamps
## Prevention: Added test_token_expiration_utc()
EOF
```

### Managing Questions
```bash
# When you need clarification
cat > memory/questions/2024-01-20-rate-limiting.md << EOF
# 2024-01-20 Rate Limiting Strategy
## Status: OPEN
## Q: Should rate limiting be per-user or per-IP?
## Context: API abuse prevention
## Options: 
  - Per-user: Better for authenticated APIs
  - Per-IP: Better for public endpoints
## Answer: [Pending]
EOF
```

## Session Management

### Ending a Session
```bash
# Comprehensive update
./memory/update.sh "Session complete: Auth system done, 15 tests passing"

# Update context for next time
cat >> memory/active/context.md << EOF

## Next Session
- Implement password reset flow
- Add email notifications
- Review security with OWASP checklist
EOF

# Check token usage
./memory/compress.sh
# Output: Total: 7,234 tokens (target: 10,000)
# ✓ SUCCESS: Under budget by 2,766 tokens
```

### Starting Next Session
```
You: "Read CLAUDE.md and memory/active/status.md. Let's continue with the password reset flow."

Claude: [Loads context, sees previous work, continues seamlessly]
```

## Real-World Scenario

### Day 1: Project Setup
```bash
./memory/update.sh "Created FastAPI project structure"
./memory/update.sh "Added SQLAlchemy models for User, Task"
./memory/update.sh "Implemented basic CRUD endpoints"
```

### Day 3: Adding Authentication
```bash
./memory/update.sh "Integrated JWT authentication"
echo "## Decision: JWT over sessions" > memory/decisions/2024-01-22-auth-method.md
echo "- Stateless, scalable" >> memory/decisions/2024-01-22-auth-method.md
echo "- 1-hour access + 7-day refresh" >> memory/decisions/2024-01-22-auth-method.md
```

### Day 7: Weekly Maintenance
```bash
./memory/weekly-maintenance.sh
# Output: ✓ Archived old files to memory/archive/2024-01-27.tar.gz
# ✓ Weekly maintenance complete

# Token usage stays optimal
./memory/compress.sh
# Total: 8,122 tokens (target: 10,000)
```

### Day 14: Complex Debugging
```bash
# Load additional context for debugging
cat memory/reference/patterns.md
cat memory/fixes/2024-01-22-jwt-expiration.md
grep -r "authentication" memory/

# Document the investigation
cat > memory/fixes/2024-02-03-refresh-token-race.md << EOF
# 2024-02-03 Refresh Token Race Condition
## Problem: Concurrent refresh requests causing 401s
## Cause: No locking mechanism for token refresh
## Fix: Added Redis-based refresh token locking
## Prevention: Added concurrent request tests
EOF
```

## Advanced Usage

### Pattern Extraction
```bash
# After implementing a reusable solution
cat > memory/patterns/repository-pattern.md << EOF
# Repository Pattern
## Use When: Need data access abstraction
## Solution: Interface + implementation separation
## Example: src/infrastructure/repositories/user_repository.py
## Benefits: Testable, swappable storage backends
EOF
```

### Architecture Documentation
```bash
# Update architecture decisions
cat >> memory/reference/architecture.md << EOF

## API Versioning Strategy
- Path-based: /api/v1/, /api/v2/
- Deprecated versions: 6-month sunset
- Breaking changes: New version required
EOF
```

### Progressive Loading Example
```
# Claude needs specific pattern info
You: "Load memory/patterns/error-handling.md"

Claude: [Loads just that file, applies pattern]

# Claude needs historical context
You: "Search memory/fixes for 'database connection'"

Claude: [Searches without loading everything]
```

## Tips for Success

### 1. Keep Updates Brief
```bash
# Good - concise, informative
./memory/update.sh "Added Redis caching to user endpoints"

# Bad - too verbose
./memory/update.sh "Today I implemented a comprehensive caching solution using Redis..."
```

### 2. Use Tables for Data
```markdown
# Good - compressed format
| Endpoint | Method | Auth | Cache |
|----------|--------|------|-------|
| /users | GET | Yes | 5min |
| /tasks | POST | Yes | No |

# Bad - verbose format
The users endpoint uses GET method and requires authentication...
```

### 3. Reference, Don't Copy
```markdown
# Good
See implementation: src/api/v1/routes/users.py

# Bad
[Entire code listing pasted in memory file]
```

### 4. Trust the Automation
- Let compress.sh handle file sizes
- Let weekly-maintenance.sh manage archives
- Focus on writing good summaries

## Troubleshooting

### "Token budget exceeded"
```bash
# Force compression
./memory/compress.sh

# Archive old content manually
mv memory/active/old-feature.md memory/archive/

# Check what's using space
find memory -name "*.md" -exec wc -w {} + | sort -n
```

### "Lost context"
```bash
# Recovery procedure
cat CLAUDE.md
cat memory/active/status.md
git log --oneline -20
ls -la memory/reference/
```

### "Can't find old information"
```bash
# Search archives
zgrep "search term" memory/archive/*.tar.gz

# Extract specific archive
tar -xzf memory/archive/2024-01-15.tar.gz
cat 2024-01-15/specific-file.md
```

---

This example demonstrates the compressed memory system in action. The key is maintaining high information density within the 10,000 token budget through brief updates, structured data, and automated maintenance.
