# Project Selection Implementation Plan

## Problem Statement

**Current Gap:** When a new MCP session starts, the system doesn't know which project the user wants to work on. Sessions are created with `project_name='default'` by default, bypassing the project selection UX we designed.

**User Requirement:**
> "I think we should always ASK the user when starting a new session... and give the user clickable options (showing: a. project 1, 124 context locks, last used 2 days ago, b. Project 2, 4 context locks, last used 4 hours ago...)"

---

## Current Flow (Broken)

```
1. Client connects → MCP initialize request
2. Middleware creates session: project_name='default' ❌
3. First tool call: lock_context(...)
4. Which project? System doesn't know! ❌
5. get_last_handover() - for which project? ❌
```

**Issue:** No project selection happens.

---

## Solution Options

### Option A: Sentinel Value + First Tool Interception (Recommended)

**Flow:**
```
1. Client connects → MCP initialize
2. Middleware creates session: project_name='__SELECT__' (sentinel)
3. First tool call arrives (any tool)
4. Middleware detects project='__SELECT__'
5. Returns error: "PROJECT_SELECTION_REQUIRED"
6. Client must call select_project_for_session() tool
7. Tool shows project options → User selects
8. Session updated with selected project
9. Load previous handover for that project
10. First tool call can now be retried
```

**Pros:**
- Works with any first tool call
- Clear error message guides user
- Explicit project selection step
- Client has full control

**Cons:**
- Requires client retry logic
- Two round-trips for first tool

---

### Option B: Mandatory First Tool (Simpler)

**Flow:**
```
1. Client connects → MCP initialize
2. Middleware creates session: project_name='__SELECT__'
3. Client MUST call initialize_session() as first tool
4. initialize_session() shows project options
5. User selects project
6. Session updated, handover loaded
7. Returns: "Ready. Loaded handover from {project}"
8. Subsequent tool calls work normally
```

**Pros:**
- Simple, predictable flow
- Single round-trip
- Clear contract: "initialize_session must be first"
- Easier error handling

**Cons:**
- Requires client awareness
- Can't call other tools first (will error)

---

### Option C: Auto-prompt in wake_up (Hybrid)

**Flow:**
```
1. Client connects → MCP initialize
2. Middleware creates session: project_name='__SELECT__'
3. Client calls wake_up() (already convention)
4. wake_up() detects project='__SELECT__'
5. Shows project selection prompt
6. User selects project
7. Session updated, handover loaded
8. Returns handover + project info
```

**Pros:**
- Leverages existing wake_up() convention
- Smooth UX (feels natural)
- No breaking changes
- Backward compatible

**Cons:**
- Keeps wake_up() (we wanted to deprecate it)
- Not truly automatic

---

## Recommended Approach: Option A + B Hybrid

**Best of both worlds:**

1. **Session created with sentinel:** `project_name='__PENDING__'`

2. **First tool call** (any tool except `select_project`):
   - Middleware detects `project='__PENDING__'`
   - Returns special error with project list embedded:

   ```json
   {
     "error": {
       "code": "PROJECT_SELECTION_REQUIRED",
       "message": "Please select a project to continue",
       "data": {
         "projects": [
           {
             "name": "innkeeper",
             "context_locks": 124,
             "last_used": "2 days ago"
           },
           {
             "name": "linkedin",
             "context_locks": 4,
             "last_used": "4 hours ago"
           },
           {
             "name": "default",
             "context_locks": 0,
             "last_used": "never"
           }
         ],
         "instructions": "Call select_project('project_name') to continue"
       }
     }
   }
   ```

3. **Client calls:** `select_project('innkeeper')`

4. **Tool execution:**
   - Validates project exists
   - Updates session: `project_name='innkeeper'`
   - Loads previous handover for that project
   - Returns: "✅ Project 'innkeeper' selected. Loaded previous session handover."

5. **Subsequent tools work normally**

---

## Implementation Details

### 1. New Tool: `select_project_for_session`

```python
@mcp.tool()
async def select_project_for_session(project_name: str) -> str:
    """
    Select which project to work on for this session.

    This must be called when starting a new session before other tools.

    Args:
        project_name: Project name to work on (from list of available projects)

    Returns:
        Confirmation with loaded handover summary
    """
    session_id = _get_current_session_id()
    if not session_id:
        return "❌ No active session found"

    adapter = _get_db_adapter()
    session_store = PostgreSQLSessionStore(adapter.pool)

    # Get current session
    session = session_store.get_session(session_id)
    if not session:
        return "❌ Session not found"

    # Check if project exists (create if 'default' or new)
    if project_name not in ['default'] and not _project_exists(project_name):
        # Offer to create new project
        return f"⚠️  Project '{project_name}' doesn't exist. Call create_project('{project_name}') first."

    # Update session with selected project
    conn = adapter.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE mcp_sessions
                SET project_name = %s
                WHERE session_id = %s
            """, (project_name, session_id))
            conn.commit()
    finally:
        adapter.pool.putconn(conn)

    # Switch active project
    _set_active_project(project_name)

    # Load previous handover for this project
    try:
        handover = await get_last_handover(project=project_name)

        return f"""✅ Project '{project_name}' selected

{handover}

You can now use other tools."""

    except Exception as e:
        return f"""✅ Project '{project_name}' selected (no previous handover)

This is a new session for this project. You can now use other tools."""
```

---

### 2. Middleware Enhancement

```python
# In mcp_session_middleware.py

# When creating new session (line 101-104)
result = self.session_store.create_session(
    session_id=new_session_id,
    project_name='__PENDING__',  # Sentinel value
    client_info={'user_agent': request.headers.get('user-agent', 'unknown')}
)

# When checking existing session (line 111+)
pg_session = self.session_store.get_session(session_id)

if pg_session is None:
    # ... existing not found logic

# NEW: Check if project selection pending
elif pg_session.get('project_name') == '__PENDING__':
    # Get available projects
    projects = self.session_store.get_projects_with_stats()

    # Check if this is the select_project call itself
    if method == 'select_project_for_session':
        # Allow it through
        return await call_next(request)

    # Any other tool → require project selection first
    logger.info(f"Project selection required for session: {session_id[:8]}")

    return JSONResponse(
        status_code=400,
        content={
            "jsonrpc": "2.0",
            "error": {
                "code": "PROJECT_SELECTION_REQUIRED",
                "message": "Please select a project before using tools",
                "data": {
                    "projects": projects,
                    "instructions": "Call select_project_for_session('project_name') to continue",
                    "tool_name": "select_project_for_session"
                }
            },
            "id": body.get('id')
        }
    )

# ... rest of existing logic
```

---

### 3. Helper Function for Project List

```python
def _get_projects_for_selection() -> List[Dict[str, Any]]:
    """Get formatted project list for selection prompt."""
    adapter = _get_db_adapter()
    session_store = PostgreSQLSessionStore(adapter.pool)

    projects = session_store.get_projects_with_stats()

    # Always include 'default' option
    if not any(p['project_name'] == 'default' for p in projects):
        projects.append({
            'project_name': 'default',
            'context_locks': 0,
            'last_used': 'never',
            'last_used_timestamp': None
        })

    return projects
```

---

### 4. Client Integration

**Claude Desktop / CLI clients need to:**

```python
# Pseudo-code for client
try:
    result = call_tool("lock_context", {...})
except MCPError as e:
    if e.code == "PROJECT_SELECTION_REQUIRED":
        # Show project selection UI
        projects = e.data['projects']
        selected = prompt_user_selection(projects)

        # Select project
        call_tool("select_project_for_session", {"project_name": selected})

        # Retry original tool call
        result = call_tool("lock_context", {...})
```

**OR simpler for now:**

Just document that users should call `select_project_for_session('project_name')` first.

---

## Alternative: Automatic Prompt (Future Enhancement)

**If MCP protocol supports prompts:**

```python
# In middleware, instead of returning error:
from mcp.types import Prompt

prompt = Prompt(
    type="select",
    message="Select a project to work on:",
    options=[
        {"label": "innkeeper (124 locks, 2 days ago)", "value": "innkeeper"},
        {"label": "linkedin (4 locks, 4 hours ago)", "value": "linkedin"},
        {"label": "default (new session)", "value": "default"}
    ]
)

# MCP client shows native UI, returns selection
selected = await prompt.show()

# Update session and continue
...
```

**Status:** Check if FastMCP supports this pattern.

---

## Migration Strategy

### Phase 1: Implement with Sentinel (This Sprint)

1. **Add sentinel value:** `__PENDING__`
2. **Create tool:** `select_project_for_session`
3. **Update middleware:** Detect pending, return error with project list
4. **Test manually:** New session → call select_project → use tools

### Phase 2: Client Integration (Next Sprint)

1. **Update Claude Code integration:**
   - Auto-detect `PROJECT_SELECTION_REQUIRED` error
   - Show native prompt
   - Auto-call `select_project_for_session`

2. **Update documentation:**
   - Quick start guide: "First call select_project_for_session"
   - Examples with project selection

### Phase 3: Smart Default (Future)

1. **Single-project users:** Skip selection
   - If only one project exists → auto-select
   - If user always uses 'default' → auto-select

2. **Remember last project:**
   - Store user preference
   - Auto-select last used project
   - Show "Press Enter for {last_project} or choose different"

---

## User Experience Examples

### Example 1: New User (No Projects)

```
User: [connects]
System: [creates session with project='__PENDING__']

User: lock_context("API spec", "api")
System: ❌ PROJECT_SELECTION_REQUIRED
        Available projects:
        - default (new session)

        Call: select_project_for_session('default')

User: select_project_for_session('default')
System: ✅ Project 'default' selected (no previous handover)
        You can now use other tools.

User: lock_context("API spec", "api")
System: ✅ Context locked successfully
```

### Example 2: Existing User (Multiple Projects)

```
User: [connects]
System: [creates session with project='__PENDING__']

User: wake_up()  # Or any tool
System: ❌ PROJECT_SELECTION_REQUIRED
        Available projects:
        1. innkeeper (124 locks, last used 2 days ago)
        2. linkedin (4 locks, last used 4 hours ago)
        3. default (0 locks, never used)

        Call: select_project_for_session('innkeeper')

User: select_project_for_session('innkeeper')
System: ✅ Project 'innkeeper' selected

        📦 Previous Session Handover:
        ---
        Work Done:
        - Analyzed authentication flow
        - Fixed JWT token validation bug

        Tools Used: read_file, edit_file, bash

        Next Steps:
        - Add unit tests for auth fix
        - Deploy to staging
        ---

        You can now continue your work.

User: lock_context(...)
System: ✅ Works!
```

### Example 3: Claude Code (Automated)

```
User: [starts Claude Code session]
Claude: [Detects PROJECT_SELECTION_REQUIRED]
        [Shows native dropdown:]

        Select project:
        ┌─────────────────────────────────────┐
        │ ○ innkeeper (124 locks, 2d ago)    │
        │ ○ linkedin (4 locks, 4h ago)       │
        │ ○ default (new)                    │
        └─────────────────────────────────────┘

User: [Clicks "innkeeper"]
Claude: [Auto-calls select_project_for_session('innkeeper')]
        ✅ Selected 'innkeeper'

        📦 Loading previous session...

        Last session: You were working on authentication bug.

        Ready! What would you like to do?

User: Continue fixing the auth issue
Claude: [Tools work normally]
```

---

## Implementation Checklist

### Core Changes (2-3 hours)

- [ ] Add `select_project_for_session` tool
- [ ] Update middleware to:
  - [ ] Create sessions with `project_name='__PENDING__'`
  - [ ] Detect pending project
  - [ ] Return `PROJECT_SELECTION_REQUIRED` error
  - [ ] Allow `select_project_for_session` through
- [ ] Update `get_last_handover` to:
  - [ ] Use session's project if not specified
  - [ ] Handle `__PENDING__` gracefully
- [ ] Add helper: `_get_projects_for_selection()`

### Testing (1 hour)

- [ ] Test: New session → Any tool → Error with project list
- [ ] Test: select_project → Tool works
- [ ] Test: Multiple projects → Correct list shown
- [ ] Test: Invalid project name → Clear error
- [ ] Test: Session remembers selected project

### Documentation (1 hour)

- [ ] Update TOOL_INSTRUMENTATION_PLAN.md
- [ ] Add PROJECT_SELECTION_IMPLEMENTATION.md to docs
- [ ] Update README with project selection flow
- [ ] Add examples to tool descriptions

### Future Enhancements (Later)

- [ ] Auto-select if only one project
- [ ] Remember last project per user
- [ ] Native UI integration in Claude Code
- [ ] Keyboard shortcuts for project switching

---

## Error Handling

**Scenario: User calls select_project with non-existent project**

```python
select_project_for_session('nonexistent')

→ ⚠️  Project 'nonexistent' doesn't exist.

   Available projects:
   - innkeeper
   - linkedin
   - default

   Or create new: create_project('nonexistent')
```

**Scenario: User tries to use tool without selecting project**

```python
lock_context(...)

→ ❌ PROJECT_SELECTION_REQUIRED
   [Shows project list]
```

**Scenario: Session expired, new session started**

```python
# After 120 min inactivity
lock_context(...)

→ ❌ Session inactive (401)
   [Client reinitializes]
   [New session created with project='__PENDING__']
   [Flow starts over]
```

---

## Success Criteria

1. **Every new session** prompts for project selection
2. **Clear error message** guides user to select project
3. **Project list** shows context locks + last used time
4. **Handover loads** automatically after selection
5. **Zero friction** for single-project users (future)

---

## Next Steps

**Immediate (This Session):**
1. Implement `select_project_for_session` tool
2. Update middleware with `__PENDING__` sentinel
3. Test end-to-end flow manually

**Follow-up (Next Session):**
1. Integrate with Claude Code client
2. Add auto-select for single project
3. Polish UX with better error messages

**Ready to implement?**
