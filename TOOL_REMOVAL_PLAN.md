# Tool Removal Plan - Consolidation Phase

**Date:** 2025-01-15
**Purpose:** Remove 12 redundant tools identified in MCP_TOOLS_AUDIT.md
**Goal:** Simplify tool suite from 24 → 12 tools without losing functionality

---

## Tools to Remove (12 total)

### Category 1: Context Management Redundancy (5 tools)

#### 1. `update_context()` - Line 1751
**Why remove:** Completely redundant with `lock_context()`
- `lock_context()` already auto-increments version when same topic is locked
- The `change_type` parameter (major/minor/patch) is unused
- Users can just call `lock_context(topic, new_content)` to update
**Replacement:** Document pattern in `lock_context()` description

#### 2. `get_context_preview()` - Line 3260
**Why remove:** `recall_context()` already includes preview
- RLM system generates preview automatically
- Separate tool adds no value
**Replacement:** None needed, already in `recall_context()`

#### 3. `list_topics()` - Line 3032
**Why remove:** Redundant with `explore_context_tree()`
- Both show list of locked contexts
- `explore_context_tree()` can be enhanced with flat mode
**Replacement:** Add `flat=True` parameter to `explore_context_tree()`

#### 4. `ask_memory()` - Line 3165
**Why remove:** Inferior version of `check_contexts()`
- `ask_memory()` searches unstructured memory_entries
- `check_contexts()` searches locked contexts (more important)
- Natural language search doesn't work well without semantic embeddings
**Replacement:** Use `check_contexts()` instead

#### 5. `memory_update()` - Line 1352
**Why remove:** Redundant with `lock_context()`
- Important information should be locked contexts
- Trivial logs don't need to be stored
- memory_entries table becomes cluttered with unused data
**Replacement:** Use `lock_context()` for important info

---

### Category 2: File Tagging System (7 tools) - DISABLED IN v4.0.0-rc1

All file tagging tools were disabled in v4.0.0-rc1 for stability. Removing entirely.

#### 6. `project_update()` - Line 3514
**Why remove:** Disabled in v4.0.0-rc1, low value
- Slow on large codebases
- Tags stored in SQLite (not portable)
- Standard grep/search is better
**Impact:** None (already disabled)

#### 7. `project_status()` - Line 3711
**Why remove:** Depends on `project_update()`
**Impact:** None (already disabled)

#### 8. `tag_path()` - Line 3788
**Why remove:** Part of disabled file tagging system
**Impact:** None (already disabled)

#### 9. `search_by_tags()` - Line 3826
**Why remove:** Part of disabled file tagging system
**Impact:** None (already disabled)

#### 10. `file_insights()` - Line 3914
**Why remove:** Part of disabled file tagging system
**Impact:** None (already disabled)

#### 11. `get_tags()` - Line 4065
**Why remove:** Part of disabled file tagging system
**Impact:** None (already disabled)

#### 12. `search_tags()` - Line 4092
**Why remove:** Part of disabled file tagging system
**Impact:** None (already disabled)

---

## Impact Analysis

### User Impact
**Lost functionality:** None
- All removed tools have better alternatives
- File tagging already disabled

**Gained benefits:**
- Simpler tool selection (50% reduction)
- Clearer tool purposes
- Less confusion
- Better documentation focus

### Code Impact
**Lines removed:** ~1,500 lines (estimated)
**Files affected:**
- claude_mcp_hybrid.py (main changes)
- Documentation updates needed

### Migration Path
**For existing users:**
1. `update_context()` → Use `lock_context()` with same topic
2. `get_context_preview()` → Use `recall_context()` (preview included)
3. `list_topics()` → Use `explore_context_tree()` (will add flat mode)
4. `ask_memory()` → Use `check_contexts()`
5. `memory_update()` → Use `lock_context()` for important info
6. File tagging → Use standard grep/search tools

---

## Implementation Plan

### Phase 1: Remove Tools (30 min)
1. Remove tool definitions from claude_mcp_hybrid.py
2. Remove helper functions if only used by removed tools
3. Test MCP server starts without errors

### Phase 2: Enhance Remaining Tools (15 min)
1. Add `flat=True` parameter to `explore_context_tree()`
2. Update tool descriptions with migration guidance

### Phase 3: Update Documentation (15 min)
1. Update README with new tool list
2. Add migration guide for removed tools
3. Update MCP_TOOLS_AUDIT.md with "completed" status

### Phase 4: Testing (30 min)
1. Test server starts
2. Test remaining context tools work
3. Test database tools still work
4. Verify no import errors

---

## Verification Checklist

Before committing:
- [ ] Server starts without errors
- [ ] `wake_up()` works
- [ ] `lock_context()` works
- [ ] `recall_context()` works
- [ ] `check_contexts()` works
- [ ] `explore_context_tree()` works
- [ ] `query_database()` works
- [ ] `inspect_database()` works
- [ ] `execute_sql()` works
- [ ] No import errors
- [ ] No undefined function references

---

## Expected Outcome

**Before:** 24 tools (9 redundant, 7 disabled)
**After:** 12 tools (all useful, all enabled)

**Tool count by category:**
- Session Management: 2 (wake_up, sleep)
- Context Management: 5 (lock, recall, unlock, check, explore)
- Database Operations: 3 (query, inspect, execute)
- System Management: 2 (memory_status, sync_project_memory)

**Result:** Clean, focused tool suite ready for cloud migration.
