# Local vs Production Architecture - Why Production Doesn't Work

## Date: Nov 16, 2025
## Analysis: Understanding Session Management Architectural Mismatch

---

## Local Environment (Working ✅)

### Process Lifecycle
```
User runs: npx @anthropic-ai/claude-code
↓
Node.js process starts
↓
Runs: python3 claude_mcp_hybrid_sessions.py
↓
main() executes (line 9808-9830)
↓
_init_local_session() called ONCE at startup (line 171-222)
↓
Creates ONE session: _local_session_id = uuid.uuid4().hex
↓
Sets GLOBAL state: config._current_session_id = _local_session_id
↓
MCP server starts with stdio transport
↓
Process stays alive for HOURS/DAYS
↓
All tool calls use SAME global session ID
↓
Session persists because process never dies
```

### Key Code: claude_mcp_hybrid_sessions.py

**Lines 171-222** - `_init_local_session()`:
```python
def _init_local_session():
    """Initialize local MCP session with PostgreSQL persistence."""

    # CRITICAL: Only safe for stdio (single-threaded)
    transport = os.getenv('MCP_TRANSPORT', 'stdio')
    if transport == 'http':
        raise RuntimeError("🚫 Session-aware fork CANNOT run in HTTP mode")

    global _local_session_id, _session_store

    # Generate session ID ONCE at startup
    _local_session_id = uuid.uuid4().hex

    # Create session in database
    result = _session_store.create_session(
        session_id=_local_session_id,
        project_name='__PENDING__',
        client_info={'transport': 'stdio', 'type': 'local_mcp'}
    )

    # Set GLOBAL session context (stays constant)
    config._current_session_id = _local_session_id

    return _local_session_id
```

**Lines 9808-9830** - main() execution:
```python
if __name__ == "__main__":
    # Initialize PostgreSQL session BEFORE starting MCP
    session_id = _init_local_session()
    print(f"📦 Session ID: {session_id}")

    # Run the MCP server
    mcp.run()
```

### Why It Works

**Transport**: stdio (standard input/output)
- Single-threaded
- No HTTP connections
- No reconnections
- Process lifetime = Session lifetime

**Session Creation**: ONCE at process startup
- `_local_session_id` created at line 194
- `config._current_session_id` set at line 218
- NEVER changes during process lifetime

**Tool Execution**:
```python
get_current_session_id()  # Returns _local_session_id (from config)
↓
Same session ID every time
↓
All tools operate on SAME session
↓
Project selection persists (stored in session record)
```

---

## Production Environment (Broken ❌)

### Request Lifecycle
```
User opens Claude Desktop
↓
Claude Desktop makes HTTP request to /mcp
↓
server_hosted.py receives request
↓
NO session initialization at startup!
↓
FastMCP creates transport for THIS request
↓
Generates new session_id (from FastMCP)
↓
Middleware intercepts → Creates PostgreSQL record
↓
project_name='__PENDING__' (awaiting selection)
↓
Sets config._current_session_id = session_id
↓
Request completes
↓
Connection TIMES OUT (30-60 seconds later)
↓
Claude Desktop RECONNECTS (new HTTP request)
↓
FastMCP creates NEW transport (no session ID header)
↓
Generates DIFFERENT session_id
↓
Middleware intercepts → Creates NEW PostgreSQL record
↓
project_name='__PENDING__' again!
↓
Sets config._current_session_id = NEW session_id
↓
Tool calls blocked (THIS session hasn't selected project)
```

### Key Code: server_hosted.py

**Line 32** - Import MCP server:
```python
from claude_mcp_hybrid_sessions import mcp
```

**Line 409** - Get FastMCP app:
```python
app = mcp.streamable_http_app()
```

**Line 442-443** - Add session middleware:
```python
app.add_middleware(MCPSessionPersistenceMiddleware,
                   db_pool=adapter)
```

**NO CALL TO `_init_local_session()`** - This is the critical difference!

### Why It Doesn't Work

**Transport**: HTTP (streamable)
- Multi-threaded (concurrent requests)
- Stateless (each request independent)
- Connection timeouts
- Request lifetime = Session lifetime (SECONDS, not hours)

**Session Creation**: PER REQUEST
- Claude Desktop connects → New session_id
- Middleware creates PostgreSQL record → `project_name='__PENDING__'`
- Connection times out (30-60s) → Claude Desktop reconnects
- NEW session_id generated (different from first)
- NEW PostgreSQL record → `project_name='__PENDING__'` again
- `config._current_session_id` now points to NEW session

**Tool Execution**:
```python
# First connection (09:26:58)
session_id = "9b4475c5"  # Created by FastMCP
config._current_session_id = "9b4475c5"
list_projects() works ✅

# User selects project (09:27:19)
session_id = "b70fef70"  # DIFFERENT! (reconnected after 19s)
config._current_session_id = "b70fef70"
select_project_for_session('linkedin') ✅
# Updates session b70fef70: project_name='linkedin'

# User calls next tool (09:27:38)
session_id = "7ed13d2c"  # DIFFERENT AGAIN! (reconnected after 19s)
config._current_session_id = "7ed13d2c"
get_last_handover() ❌ BLOCKED
# Session 7ed13d2c has project_name='__PENDING__' (never selected!)
```

---

## Evidence from Production Logs

**Test session 08:26-08:27 UTC** (from BUG_8_SESSION_PERSISTENCE.md):

```
08:26:58: Session 9b4475c5 initialize
08:27:02: Session 9b4475c5 - list_projects() ✅

08:27:17: Session b70fef70 initialize ← NEW SESSION (19s later!)
08:27:19: Session b70fef70 - select_project_for_session('linkedin') ✅

08:27:35: Session 7ed13d2c initialize ← ANOTHER NEW SESSION
08:27:38: Session 7ed13d2c - get_last_handover() ❌ BLOCKED

08:27:45: Session 3f3430a3 initialize ← YET ANOTHER NEW SESSION
08:27:47: Session 3f3430a3 - explore_context_tree() ❌ BLOCKED
```

**Pattern**: New MCP session created every 15-20 seconds (connection timeout).

---

## Root Cause Analysis

### The Fundamental Mismatch

**Local Environment**:
- Process lifetime: HOURS/DAYS
- Session lifetime: HOURS/DAYS (same as process)
- Session ID: CONSTANT (set once at startup)
- Project selection: PERSISTS (stored in session record)
- MCP transport: stdio (no reconnections)

**Production Environment**:
- Process lifetime: INDEFINITE (server stays up)
- Session lifetime: SECONDS (per HTTP connection)
- Session ID: CHANGES (new session per reconnection)
- Project selection: LOST (new session = new __PENDING__ record)
- MCP transport: HTTP (reconnects every 30-60s)

### Why Normal MCP HTTP Behavior Breaks Us

**Claude Desktop HTTP Behavior** (CORRECT per MCP spec):
1. Opens SSE (Server-Sent Events) connection to /mcp
2. Sends `initialize` request → FastMCP returns session_id
3. Connection stays open for ~30-60 seconds
4. Connection times out or Claude Desktop closes it
5. Claude Desktop RECONNECTS (step 1 again)
6. NEW `initialize` request → NEW session_id
7. Repeat...

This is **EXPECTED HTTP behavior**. Not a bug in Claude Desktop or FastMCP.

**Our Problem**:
- We treat each MCP session as a "work session" requiring project selection
- MCP sessions are SHORT-LIVED (seconds)
- Work sessions should be LONG-LIVED (hours/days)
- We're using the wrong abstraction!

---

## Why Bug #8 Cache Doesn't Solve It

**Bug #8 Implementation** (mcp_session_middleware.py):
```python
# After select_project_for_session succeeds:
if tool_name == 'select_project_for_session' and response.status_code == 200:
    project_name = body.get('params', {}).get('arguments', {}).get('name')
    api_key = request.headers.get('Authorization', '').replace('Bearer ', '')

    self._set_cached_project(api_key, project_name)
    # Stores in memory: {api_key: project_name}

# On new session creation:
cached_project = self._get_cached_project(api_key)
if cached_project:
    # Auto-apply to new session
    initial_project = cached_project
```

**Why It's Not Working** (from production logs):
- `select_project_for_session` returned status 200 ✅
- But NO cache logging appeared (no `💾 Cached project` message)
- Suggests the conditional is not triggering
- Likely: Response structure different than expected

**Even If Cache Worked**:
- Cache scoped to API key
- Multiple UIs using SAME API key on DIFFERENT projects
- Desktop working on 'linkedin' at 09:30
- claude.ai working on 'innkeeper' at 09:45
- Desktop reconnects → Cache returns 'innkeeper' (WRONG!)
- User saves context to WRONG project (data corruption)

This is why user said: **"Having the inheritance models sounds like a surefire way to mix projects"**

---

## What User Actually Wants

From user's architecture explanation:

### Data Model
```
API Key (Bearer token)
↓
PostgreSQL Schema (dementia_abc123)
↓
Multiple Logical Projects (linkedin, innkeeper, etc.)
↓
project_name column separates data
```

### Tool Call Requirements
```
1. Each tool call requires a project
2. Each tool call updates the session, marking it for project
3. Different UI reads last update from same project
4. If 120 min idle, finalize handover and create new session
5. If no project specified, ask for one
```

### Multi-UI Scenario
```
Desktop:     Working on 'linkedin' at 09:30
claude.ai:   Working on 'innkeeper' at 09:45
Claude Code: Working on 'linkedin' at 10:00

All using SAME API key
All accessing SAME schema
But working on DIFFERENT projects SIMULTANEOUSLY
```

### Session Lifecycle
```
Tool call → Project specified → Update session project_name
↓
Another tool call on SAME project → Reuse session
↓
120 minutes idle → Finalize handover → Create new session
↓
Next tool call → Select project again
```

---

## The Critical Questions

1. **How do we identify "conversation continuity"?**
   - Claude Desktop connection ≠ conversation
   - MCP session ≠ conversation
   - What makes two tool calls part of the SAME conversation?

2. **How do we prevent project mixing?**
   - Can't use API-key-level cache (multiple UIs, different projects)
   - Can't use session inheritance (newest might be from different UI)
   - What's the stable identifier?

3. **Should tools require explicit project parameter?**
   - Current: Implicit (session has project_name)
   - Alternative: Explicit (every tool call specifies project)
   - User said "Each tool call requires a project" - does this mean explicitly?

4. **What is the relationship between MCP sessions and Dementia sessions?**
   - MCP session: Technical (HTTP connection)
   - Dementia session: Logical (work period on project)
   - Should we decouple them completely?

---

## Possible Solutions

### Option 1: Require Explicit Project Parameter
```python
# Every tool requires project parameter
get_last_handover(project="linkedin")
lock_context(content="...", topic="...", project="linkedin")
```

**Pros**:
- No ambiguity
- Works with multiple UIs
- No data mixing risk

**Cons**:
- MASSIVE breaking change
- Poor UX (repetitive)
- Every tool signature changes

### Option 2: Track "Active Project" per UI Session
```python
# Identify UI session by some stable ID
# Store: {ui_session_id: active_project}
# Each tool call updates active_project
```

**Question**: What is the stable UI session ID?
- Not MCP session (changes every 30-60s)
- Not API key (multiple UIs use same key)
- Client IP? (unreliable)
- Custom header? (client must send)

### Option 3: Last-Used Project Lookup (with safety)
```python
# Query: What project was MOST RECENTLY used?
SELECT project_name FROM mcp_sessions
WHERE api_key_hash = hash(api_key)
AND last_active > NOW() - INTERVAL '120 minutes'
ORDER BY last_active DESC LIMIT 1
```

**Problem**: User REJECTED this (inheritance causes mixing)

Example:
```
Desktop    'linkedin'  09:30:00
claude.ai  'innkeeper' 09:45:00  ← Most recent
Desktop reconnects     09:46:00 → Inherits 'innkeeper' ❌
```

### Option 4: Conversation ID from Client
```python
# Claude Desktop sends custom header:
X-Conversation-ID: <unique per conversation>

# Cache: {(api_key, conversation_id): active_project}
```

**Problem**: Requires client-side changes (not in our control)

---

## Next Steps

**STOP IMPLEMENTATION** - We need architectural clarity first.

**Questions for User**:
1. How should we identify which tool calls belong to the same "conversation"?
2. Should tools require explicit `project` parameter on every call?
3. What happens when multiple UIs work on different projects simultaneously?
4. Is there a stable identifier we can use besides API key and MCP session?

**Current State**:
- Deployment 95d4cf6b ACTIVE (Bug #8 cache implementation)
- Cache not working (no logging in production)
- Fundamental architecture question unresolved

**Can't fix Bug #8 without answering these questions.**

---

**Analysis By**: Claude Code (Sonnet 4.5)
**Analysis Duration**: 60 minutes
**Status**: BLOCKED - Awaiting architectural decision
**Critical Insight**: We're conflating MCP sessions (technical, short-lived) with work sessions (logical, long-lived)
