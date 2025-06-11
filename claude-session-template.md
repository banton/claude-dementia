# Claude Session Documentation Template

> **Instructions**: Copy this template to `memory/current-session.md` at the start of each project. Update it continuously throughout your session, not just at the end. This is your primary handoff document between sessions.

---

# Current Session Summary - [Brief Description of Main Achievement]

## 🎯 Session Objectives
- **Primary goal**: [What you set out to achieve this session]
- **Success criteria**: [How you measured success]
- **Actual outcome**: [What was actually accomplished]

## 🚀 What Was Built This Session

### 1. **[Feature/Component Name] - [STATUS: COMPLETED|IN_PROGRESS|BLOCKED]**
- **Description**: [What this feature/component does]
- **Files Created/Modified**:
  - `path/to/new/file.ext` - Created: [Purpose of the file]
  - `path/to/modified/file.ext` - Modified: [What was changed and why]
  - `path/to/deleted/file.ext` - Deleted: [Why it was removed]
- **Key Implementation Details**:
  - [Technical approach taken and why]
  - [Important algorithm or pattern used]
  - [Integration points with existing code]
- **Design Decisions**:
  - Chose [approach A] over [approach B] because [reasoning]
  - Used [pattern/library] for [purpose] due to [benefits]
  - Deferred [optimization/feature] until [condition] because [reasoning]
- **Test Coverage**:
  - Unit tests: [X] added in `path/to/tests.ext`
  - Integration tests: [Y] added in `path/to/integration_tests.ext`
  - Coverage: [percentage]% for this component
  - Edge cases tested: [list key edge cases]

### 2. **[Second Feature/Component] - [STATUS]**
[Repeat the above pattern for each significant piece of work]

### 3. **Documentation Updates - COMPLETED**
- Updated `memory/patterns/[pattern-name].md` with [what pattern]
- Created `memory/fixes/YYYY-MM-DD-[issue].md` for [what issue]
- Added implementation notes to `memory/implementations/[feature].md`

## 🧪 Test Results
- ✅ **Overall**: [X/Y] tests passing
- ❌ **Failures**: 
  - `test_name` in `file` - [Reason for failure, if any]
  - Plan to fix: [How you'll address it next session]
- 📊 **Coverage**: 
  - Overall: [X]%
  - New code: [Y]%
  - Critical paths: [Z]%
- 🎯 **Test Strategy**:
  - Focused on [what aspects were tested]
  - Deferred [what tests] until [when] because [why]

## 📁 Complete File Inventory This Session

### Created Files
```
path/to/new/component.py          # Core implementation of [feature]
path/to/new/component_test.py     # Comprehensive tests for [feature]
path/to/new/types.py              # Type definitions for [what]
memory/fixes/2024-01-20-bug.md    # Documentation of [issue] fix
```

### Modified Files
```
path/to/existing/api.py           # Added endpoint for [feature]
path/to/existing/models.py        # Updated model to include [fields]
path/to/existing/config.yaml      # Added configuration for [what]
.github/workflows/ci.yml          # Updated to test [new component]
```

### Deleted Files
```
path/to/old/deprecated.py         # Removed because [replaced by what]
path/to/temp/scaffold.py          # Temporary file no longer needed
```

## 🔧 Technical Decisions & Rationale

### Architecture Decisions
1. **Decision**: [What architectural choice was made]
   - **Context**: [Why this decision was needed]
   - **Options considered**:
     - Option A: [Description] - Rejected because [reason]
     - Option B: [Description] - **Chosen** because [reason]
   - **Trade-offs accepted**: [What downsides we accepted]
   - **ADR created**: `memory/decisions/YYYY-MM-DD-[decision].md`

2. **Pattern Selection**: Implemented [pattern name] for [component]
   - **Reasoning**: [Why this pattern fits]
   - **Alternative**: Could have used [other pattern] but [why not]
   - **Documented in**: `memory/patterns/[pattern-name].md`

### Database Changes
- **Migration created**: `migrations/YYYY_MM_DD_description.py`
  - Added table: `[table_name]` for [purpose]
  - Modified table: `[table_name]` - added columns [list]
  - Index added: `[index_name]` on [columns] for [performance reason]
- **Rollback plan**: [How to rollback if needed]

### API Changes
- **New endpoints**:
  - `POST /api/v1/[resource]` - [What it does]
  - `GET /api/v1/[resource]/{id}` - [What it returns]
- **Modified endpoints**:
  - `PUT /api/v1/[resource]/{id}` - Now accepts [new fields]
- **Deprecated endpoints**:
  - `GET /api/[old-endpoint]` - Use [new endpoint] instead
- **Breaking changes**: [List any, or "None"]

## 🐛 Issues Encountered & Resolutions

### Issue 1: [Brief Description]
- **Symptoms**: [What was visibly wrong]
- **Investigation process**:
  1. First tried [what] - didn't work because [why]
  2. Then discovered [what] using [method]
  3. Root cause was [explanation]
- **Solution**: [How it was fixed]
- **Prevention**: 
  - Added test `test_name` to prevent regression
  - Updated pattern in `memory/patterns/[pattern].md`
  - Created fix documentation: `memory/fixes/YYYY-MM-DD-[issue].md`
- **Time spent**: [Approximate time to help size future similar issues]

### Issue 2: [If applicable, repeat pattern]

## 📋 Task Status Dashboard

### ✅ Completed This Session
- [x] Implement [feature A] with full test coverage
- [x] Fix [bug B] and add regression tests
- [x] Update documentation for [component C]
- [x] Refactor [module D] to use [pattern]
- [x] Deploy [service E] to [environment]

### 🔄 In Progress (Handoff Details)
- [ ] Feature: [Name]
  - **Progress**: [60]% complete
  - **What's done**: [Completed parts]
  - **What remains**: [Specific remaining tasks]
  - **Next step**: Open `file.py` and implement `function_name()`
  - **Context**: The function should [specific behavior]

### ⏳ Blocked Items
- [ ] Task: [Name]
  - **Blocked on**: [Specific blocker]
  - **Question filed**: `memory/questions/YYYY-MM-DD-[topic].md`
  - **Workaround**: Can proceed with [alternative] in meantime
  - **Impact**: This blocks [what features/tasks]

### 📅 Ready for Next Session
1. **High Priority**: [Task] - [Why it's important]
2. **Medium Priority**: [Task] - [Context needed]
3. **Low Priority**: [Task] - [Can wait until X]
4. **Tech Debt**: [Refactoring needed] - [Impact if delayed]

## 💡 Key Insights & Learnings

### Technical Insights
- **Discovery**: [Something learned about the system]
  - **Implication**: This means we should [action/consideration]
  - **Pattern documented**: `memory/patterns/[name].md`

- **Performance**: Found that [component] is slow when [condition]
  - **Measurement**: Takes [X]ms under [condition]
  - **Optimization planned**: [Approach to improve]

- **Security**: Identified that [component] needs [security measure]
  - **Risk**: [What could happen]
  - **Mitigation**: [How to address]

### Process Improvements
- **What worked well**: [Process/approach that was effective]
- **What didn't work**: [Process/approach that was inefficient]
- **Suggestion**: Next time, try [improved approach]

### Architecture Insights
- **Realization**: The current design of [component] limits [what]
- **Impact**: This will affect [future features]
- **Recommendation**: Consider refactoring to [approach] when [condition]

## 📊 Session Metrics

### Time & Productivity
- **Session duration**: [Start time] - [End time] ([Total hours])
- **Focused work time**: [Hours excluding breaks/research]
- **Context switches**: [Number of times switched between features]

### Code Metrics
- **Commits**: [Number] commits
  ```
  abc1234 feat(api): Add user authentication endpoint
  def5678 fix(db): Resolve connection pool timeout
  ghi9012 test: Add integration tests for auth flow
  jkl3456 docs: Update API documentation
  ```
- **Files touched**: [Number] files
- **Lines changed**: +[Added] / -[Removed]
- **Test coverage delta**: [+X%|-Y%]

### Quality Metrics
- **Code review items**: [Number of issues self-identified]
- **Refactoring**: [Number of files improved]
- **Documentation**: [Number of docs updated]
- **Technical debt**: [Increased|Decreased|Unchanged]

## 🔗 Memory System Updates

### Patterns Documented
- `memory/patterns/error-handling-[specific].md` - New pattern for [what]
- `memory/patterns/testing-[type].md` - Enhanced with [what examples]

### Questions Filed
- `memory/questions/YYYY-MM-DD-authentication.md` - About [what aspect]
- `memory/questions/YYYY-MM-DD-performance.md` - Regarding [what concern]

### Fixes Recorded
- `memory/fixes/YYYY-MM-DD-timeout-error.md` - Solved [what issue]
- `memory/fixes/YYYY-MM-DD-test-flakiness.md` - Stabilized [what tests]

### Implementation Updates
- `memory/implementations/user-auth.md` - Updated to 75% complete
- `memory/implementations/data-pipeline.md` - Marked as COMPLETED

### Architecture Updates
- `memory/architecture/database-schema.md` - Added [what tables/changes]
- `memory/architecture/api-design.md` - Documented [what patterns]

### Decisions Recorded
- `memory/decisions/YYYY-MM-DD-use-redis-cache.md` - Chose Redis for [why]
- `memory/decisions/YYYY-MM-DD-api-versioning.md` - Decided on [approach]

## ⚠️ Warnings & Gotchas for Next Session

### Environment Setup
- **Required**: Set environment variable `CONFIG_PATH=/path/to/config`
- **Service dependency**: Ensure Redis is running on port 6379
- **Database state**: Run migration `xyz` before starting

### Known Issues
- **Flaky test**: `test_concurrent_updates` fails ~10% of time
  - **Workaround**: Run tests with `--no-parallel` flag
  - **Root cause**: Race condition in [component]
  - **Fix planned**: [Approach to fix]

### Performance Considerations
- **Slow operation**: [Operation] takes ~30s in dev environment
- **Memory usage**: [Component] uses 2GB RAM with default settings
- **API rate limit**: External service allows 100 requests/minute

### Security Notes
- **Credential location**: API keys in `.env` file (not committed)
- **Pending security update**: Need to update [library] to patch CVE-XXXX
- **Access control**: [Component] currently lacks proper authorization

## 🚀 Next Session Startup Checklist

When you start the next session, do these in order:

1. **Read these files first**:
   - [ ] `CLAUDE.md` - For overall context
   - [ ] This session summary - For immediate context
   - [ ] `memory/context/current-task.md` - For specific task details

2. **Check system state**:
   ```bash
   git status                    # Check for uncommitted changes
   git log --oneline -5         # Review recent commits
   [test command]               # Ensure tests still pass
   docker-compose ps            # Verify services are running
   ```

3. **Load progressive context**:
   - Start with files listed in "In Progress" section
   - Add related test files as needed
   - Reference patterns in `memory/patterns/` as required

4. **Review and address**:
   - [ ] Any BLOCKED items that might be unblocked
   - [ ] Questions that might have been answered
   - [ ] High priority tasks from the ready list

5. **Before coding**:
   - [ ] Check if any dependencies need updating
   - [ ] Ensure development environment matches requirements
   - [ ] Review any security warnings above

## 📝 Raw Notes / Scratch Pad

[Any additional notes, code snippets, or thoughts that don't fit above categories but might be useful]

```
# Example code snippet to remember
def important_pattern():
    # This approach worked well for [problem]
    pass
```

---

## 🎯 Handoff Summary

**For the next session, in one paragraph**: [Summarize the absolute most important things to know, what to work on first, and any critical warnings or blockers. This should be scannable in 30 seconds.]

**Critical first action**: [The very first thing to do next session]

**Session ended**: [Date and time]
**Next session should start with**: [Specific file and function/task]

---

*Remember: This document is your memory. The more detail you provide, the more effective your next session will be.*
