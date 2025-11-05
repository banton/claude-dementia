# Tool Instrumentation Plan for Incremental Handovers

## Executive Summary

With the new **incremental handover architecture**, we replace the explicit `wake_up`/`sleep` pattern with automatic, transparent session management. Every tool call updates the session summary in real-time, eliminating the need for post-processing.

**Key Insight:** The handover is built *during* the session, not after.

---

## Current MCP Tools (41 total)

### Category 1: Session Management (7 tools)
**Purpose:** Project and session lifecycle management

| Tool | Current Purpose | New Approach |
|------|----------------|--------------|
| `switch_project` | Change active project | Keep - validates project exists |
| `get_active_project` | Show current project | Keep - reads from session |
| `create_project` | Create new project | Keep - project management |
| `list_projects` | List all projects | Keep - project discovery |
| `get_project_info` | Project details | Keep - project stats |
| `delete_project` | Remove project | Keep - project cleanup |
| **`wake_up`** | **Load previous session** | **REPLACE with auto-load** |
| **`sleep`** | **Create handover** | **REMOVE - auto-finalized** |
| `get_last_handover` | Retrieve last handover | **KEEP - becomes primary loader** |

**Decision:** `wake_up` and `sleep` are obsolete. Replace with automatic handover loading.

---

### Category 2: Context Management (11 tools)
**Purpose:** Lock, recall, search contexts (API specs, rules, etc.)

| Tool | Should Update Summary? | Summary Entry |
|------|----------------------|---------------|
| `lock_context` | ✅ YES | "Locked context: {topic}" |
| `recall_context` | ✅ YES | "Recalled context: {topic}" |
| `unlock_context` | ✅ YES | "Unlocked context: {topic}" |
| `batch_lock_contexts` | ✅ YES | "Locked {count} contexts" |
| `batch_recall_contexts` | ✅ YES | "Recalled {count} contexts" |
| `search_contexts` | ❌ NO | Read-only query |
| `check_contexts` | ❌ NO | Read-only validation |
| `explore_context_tree` | ❌ NO | Read-only browse |
| `context_dashboard` | ❌ NO | Read-only stats |
| `memory_analytics` | ❌ NO | Read-only analysis |
| `memory_status` | ❌ NO | Read-only status |

**Summary:** Write operations update summary, read operations don't.

---

### Category 3: File Semantic Model (5 tools)
**Purpose:** Scan and query project files

| Tool | Should Update Summary? | Summary Entry |
|------|----------------------|---------------|
| `scan_project_files` | ✅ YES | "Scanned {count} files" |
| `query_files` | ❌ NO | Read-only query |
| `get_file_clusters` | ❌ NO | Read-only analysis |
| `file_model_status` | ❌ NO | Read-only status |
| `scan_and_analyze_directory` | ✅ YES | "Analyzed {directory}" |

---

### Category 4: Database Tools (6 tools)
**Purpose:** Direct database access for debugging

| Tool | Should Update Summary? | Summary Entry |
|------|----------------------|---------------|
| `query_database` | ❌ NO | Read-only query |
| `inspect_database` | ❌ NO | Read-only inspection |
| `execute_sql` | ✅ YES | "Executed SQL: {operation}" |
| `manage_workspace_table` | ✅ YES | "Created table: {name}" |
| `get_query_page` | ❌ NO | Pagination helper |

---

### Category 5: Embeddings & AI (8 tools)
**Purpose:** Semantic search and AI features

| Tool | Should Update Summary? | Summary Entry |
|------|----------------------|---------------|
| `generate_embeddings` | ✅ YES | "Generated {count} embeddings" |
| `semantic_search_contexts` | ❌ NO | Read-only search |
| `ai_summarize_context` | ❌ NO | Read-only AI op |
| `embedding_status` | ❌ NO | Read-only status |
| `diagnose_ollama` | ❌ NO | Diagnostic |
| `test_single_embedding` | ❌ NO | Diagnostic test |
| `usage_statistics` | ❌ NO | Read-only stats |
| `cost_comparison` | ❌ NO | Read-only analysis |

---

### Category 6: Advanced Features (4 tools)
**Purpose:** Sync and project initialization

| Tool | Should Update Summary? | Summary Entry |
|------|----------------------|---------------|
| `sync_project_memory` | ✅ YES | "Synced project memory" |
| `_extract_project_overview` | Internal | N/A |
| `_extract_critical_rules` | Internal | N/A |

---

## Summary Statistics

| Category | Total Tools | Write Ops | Read Ops |
|----------|------------|-----------|----------|
| Session Management | 9 | 2 | 7 |
| Context Management | 11 | 5 | 6 |
| File Semantic | 5 | 2 | 3 |
| Database | 5 | 2 | 3 |
| Embeddings & AI | 8 | 1 | 7 |
| Advanced | 4 | 1 | 3 |
| **TOTAL** | **41** | **13** | **28** |

**Instrumentation Target:** 13 tools need summary updates (32% of all tools)

---

## Implementation Strategy

### Phase 1: Replace wake_up/sleep Pattern

**Current Flow (Explicit):**
```python
# User must manually call these
wake_up()              # Load previous session
# ... work ...
sleep()                # Create handover
```

**New Flow (Automatic):**
```python
# Middleware handles everything
First tool call → Auto-load previous handover
Every tool call → Update session_summary incrementally
120 min inactive → Auto-finalize handover
```

**Changes Required:**

1. **Remove `sleep` tool entirely**
   - No longer needed - handover built during session
   - Middleware finalizes on inactivity

2. **Deprecate `wake_up` tool**
   - Keep for backward compatibility (but mark deprecated)
   - Internally: just calls `get_last_handover()`

3. **Make `get_last_handover` the primary loader**
   - Already fetches previous handover
   - Call automatically on first tool execution of new session

---

### Phase 2: Instrument Tool Calls

**Option A: Decorator Pattern (Recommended)**

```python
from functools import wraps
from typing import Callable

def track_in_summary(description_fn: Callable[[dict], str]):
    """Decorator to automatically update session_summary after tool execution."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Execute tool
            result = await func(*args, **kwargs)

            # Update session summary
            try:
                session_id = _get_current_session_id()  # From context
                if session_id:
                    # Generate description
                    tool_args = {k: v for k, v in kwargs.items()}
                    description = description_fn(tool_args)

                    # Update summary
                    from mcp_session_store import PostgreSQLSessionStore
                    adapter = _get_db_adapter()
                    store = PostgreSQLSessionStore(adapter.pool)
                    store.update_session_summary(
                        session_id=session_id,
                        tool_name=func.__name__,
                        tool_args=tool_args,
                        result_summary=description
                    )
            except Exception as e:
                logger.warning(f"Failed to update session summary: {e}")
                # Don't fail the tool call

            return result
        return wrapper
    return decorator
```

**Usage Example:**

```python
@mcp.tool()
@track_in_summary(lambda args: f"Locked context: {args['topic']}")
async def lock_context(content: str, topic: str, ...):
    # Implementation
    pass

@mcp.tool()
@track_in_summary(lambda args: f"Scanned {args.get('count', 'unknown')} files")
async def scan_project_files(...):
    # Implementation
    pass
```

**Pros:**
- Clean, declarative
- Easy to add to existing tools
- Centralized error handling
- No impact on tool logic

**Cons:**
- Need session context passing
- Slightly more complex decorator

---

**Option B: Explicit Calls (Simpler)**

```python
@mcp.tool()
async def lock_context(content: str, topic: str, ...):
    # Implementation
    result = _do_lock_context(content, topic, ...)

    # Update summary
    _update_summary(
        tool_name='lock_context',
        description=f"Locked context: {topic}"
    )

    return result
```

**Pros:**
- Simple, explicit
- Easy to understand
- No decorator magic

**Cons:**
- Repetitive code
- Easy to forget
- Error handling duplicated

---

### Phase 3: Session Context Management

**Problem:** Tools need access to current `session_id` to update summaries.

**Solution: FastMCP Context**

FastMCP provides request context. We need to:

1. **Extract session_id from middleware**
   ```python
   # In mcp_session_middleware.py
   if new_session_id:
       # Store in request context for tools to access
       request.state.mcp_session_id = new_session_id
   ```

2. **Access in tools**
   ```python
   from starlette.requests import Request
   from contextvars import ContextVar

   # Global context var
   current_session: ContextVar[Optional[str]] = ContextVar('current_session', default=None)

   def _get_current_session_id() -> Optional[str]:
       return current_session.get()
   ```

3. **Set context in middleware**
   ```python
   # Before calling tool
   current_session.set(session_id)
   ```

---

### Phase 4: Auto-load Previous Handover

**On First Tool Call Detection:**

```python
# In tool wrapper or middleware
if is_first_tool_call_of_session(session_id):
    # Auto-load previous handover
    handover = await get_last_handover(project_name)

    # Add to session_summary as "context loaded"
    update_session_summary(
        session_id=session_id,
        tool_name='_system',
        tool_args={},
        result_summary=f"Loaded previous session handover: {handover['session_id'][:8]}"
    )
```

**Detection Strategy:**

```python
def is_first_tool_call_of_session(session_id: str) -> bool:
    """Check if this is the first tool call."""
    # Check if work_done is empty
    session = session_store.get_session(session_id)
    summary = session.get('session_summary', {})
    return len(summary.get('work_done', [])) == 0
```

---

## Implementation Checklist

### Step 1: Core Infrastructure (DONE ✅)
- [x] Add `session_summary` JSONB column
- [x] Implement `update_session_summary()` method
- [x] Implement `finalize_handover()` method
- [x] Add lazy inactivity checking

### Step 2: Session Context Passing (Next)
- [ ] Add `current_session` ContextVar
- [ ] Set session_id in middleware
- [ ] Create `_get_current_session_id()` helper
- [ ] Test context propagation

### Step 3: Tool Instrumentation (Core)
- [ ] Create `@track_in_summary` decorator
- [ ] Instrument 13 write-operation tools:
  - [ ] `lock_context`
  - [ ] `unlock_context`
  - [ ] `batch_lock_contexts`
  - [ ] `recall_context`
  - [ ] `batch_recall_contexts`
  - [ ] `scan_project_files`
  - [ ] `scan_and_analyze_directory`
  - [ ] `execute_sql`
  - [ ] `manage_workspace_table`
  - [ ] `generate_embeddings`
  - [ ] `sync_project_memory`

### Step 4: Auto-load Handover (UX)
- [ ] Detect first tool call of session
- [ ] Auto-call `get_last_handover()`
- [ ] Add to session_summary
- [ ] Test with real client

### Step 5: Deprecate Old Pattern (Breaking)
- [ ] Mark `wake_up` as deprecated
- [ ] Remove `sleep` tool
- [ ] Update documentation
- [ ] Migration guide for users

### Step 6: Testing & Validation
- [ ] Unit tests for summary updates
- [ ] Integration test: Full session lifecycle
- [ ] Test handover continuity
- [ ] Test 120-minute expiration
- [ ] Test project switching

---

## Expected User Experience

### Old Pattern (Explicit)
```python
# User must remember to call wake_up/sleep
wake_up()                           # Manual step
lock_context("API spec", "api_v1")
scan_project_files()
recall_context("api_v1")
sleep()                             # Manual step - easy to forget!
```

### New Pattern (Automatic)
```python
# Just use tools - everything automatic
lock_context("API spec", "api_v1")  # Auto-loads previous handover on first call
scan_project_files()                # Updates summary
recall_context("api_v1")            # Updates summary
# Session expires after 120 min → Auto-finalizes handover
```

**Benefits:**
- ✅ Zero cognitive overhead
- ✅ Can't forget to create handover
- ✅ Real-time summary building
- ✅ Handover always up-to-date
- ✅ Seamless multi-session experience

---

## Migration Path

### Phase 1: Parallel Operation (Safe)
- Keep `wake_up` and `sleep` working
- Add instrumentation to tools
- Both patterns work simultaneously
- Users can migrate gradually

### Phase 2: Deprecation Warning (3 months)
- `wake_up()` returns: "⚠️ Deprecated: Handover auto-loaded"
- `sleep()` returns: "⚠️ Deprecated: Handover auto-finalized"
- Document new pattern
- Update examples

### Phase 3: Removal (6 months)
- Remove `sleep` tool entirely
- Convert `wake_up` to alias of `get_last_handover`
- Clean up legacy code

---

## Performance Considerations

**Summary Update Cost:**
- **Per tool call:** 1 UPDATE query (~5ms)
- **Frequency:** Every write operation (13 tools)
- **Impact:** Negligible (already updating `last_active`)

**Combined Query:**
```sql
-- Current: 1 query
UPDATE mcp_sessions SET last_active = NOW() WHERE session_id = ?

-- New: Same 1 query (combine updates)
UPDATE mcp_sessions
SET last_active = NOW(),
    session_summary = ?
WHERE session_id = ?
```

**Network Overhead:** None (same connection, combined query)

**Benefit:** Handover finalization is instant (no processing needed)

---

## Error Handling

**Principle:** Summary updates should NEVER fail the tool call.

```python
@track_in_summary(...)
async def some_tool(...):
    try:
        result = await _tool_logic()
        return result
    finally:
        # Summary update in finally block
        try:
            _update_summary(...)
        except Exception as e:
            logger.warning(f"Summary update failed: {e}")
            # Continue - don't fail tool
```

**Fallback:** If summary updates fail consistently:
- Session still works (last_active still updated)
- Handover will be minimal but valid
- Better than losing all session state

---

## Recommended Implementation Order

1. **Add session context passing** (1 hour)
   - ContextVar setup
   - Middleware integration
   - Helper functions

2. **Implement decorator** (2 hours)
   - `@track_in_summary` decorator
   - Error handling
   - Testing

3. **Instrument top 5 tools** (2 hours)
   - `lock_context`
   - `scan_project_files`
   - `recall_context`
   - `execute_sql`
   - `sync_project_memory`

4. **Test end-to-end** (2 hours)
   - Create session
   - Use tools
   - Check summary
   - Wait for expiration
   - Verify handover

5. **Instrument remaining 8 tools** (1 hour)

6. **Add auto-load logic** (1 hour)

**Total Estimated Time:** 9 hours for complete implementation

---

## Questions for Discussion

1. **Decorator vs Explicit?**
   - Decorator is cleaner but adds complexity
   - Explicit is simpler but repetitive
   - Recommendation: Decorator

2. **Auto-load on every session or opt-in?**
   - Auto-load: Zero-friction UX
   - Opt-in: More control
   - Recommendation: Auto-load with flag to disable

3. **Session context via ContextVar or Request.state?**
   - ContextVar: Cleaner but more setup
   - Request.state: FastMCP native
   - Recommendation: ContextVar for async safety

4. **Keep wake_up/sleep deprecated or remove immediately?**
   - Keep deprecated: Safe migration
   - Remove: Clean codebase
   - Recommendation: Keep for 6 months then remove

---

## Success Metrics

**After Implementation:**

1. **Handover Coverage:** 100% of sessions have handovers
2. **User Friction:** Zero manual wake_up/sleep calls needed
3. **Summary Quality:** 80%+ of work captured in summaries
4. **Performance:** <10ms overhead per tool call
5. **Reliability:** 99%+ handover generation success rate

---

## Conclusion

The incremental handover architecture fundamentally changes how we think about session management:

- **Before:** Sessions are ephemeral, handovers are post-processed
- **After:** Sessions are the source of truth, handovers are just snapshots

By instrumenting tool calls to update summaries in real-time, we eliminate the need for explicit wake_up/sleep patterns and provide a seamless, automatic experience.

**Next Step:** Implement session context passing and decorator pattern.
