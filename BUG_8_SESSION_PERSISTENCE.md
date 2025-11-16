# Bug #8: MCP Session Persistence - Claude Desktop Creates Multiple Sessions

## Date: Nov 16, 2025
## Status: **IMPLEMENTED - READY FOR DEPLOYMENT**

---

## Discovery

User reported that during systematic testing in a SINGLE Claude Desktop conversation, all tools after `select_project_for_session()` were being blocked with "Project selection required" errors.

Initial assumption: User was creating multiple separate conversations.

**User clarification (CRITICAL):**
> "These have all been in a single session for me, the user. I have not closed or restarted between calls, it is literally just doing the testing prompt in a single session you did."

---

## Production Log Analysis

Test session 08:26-08:27 UTC showed **4 DIFFERENT MCP session IDs** created:

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

**Each session shows:**
- `{"mcp_session_id": "missing", ...}` - initialize request
- `Created new transport with session ID: XXXXXXXX` - FastMCP creates new transport
- Middleware creates PostgreSQL session record with `project_name='__PENDING__'`

---

## Root Cause Analysis

### The Architectural Mismatch

**Local Testing (npx - WORKS):**
```
User runs: npx @anthropic-ai/claude-code
↓
One persistent Node.js process starts
↓
MCP server process stays alive for entire conversation
↓
get_current_session_id() creates ONE session ID at startup
↓
Project selection persists because process never dies
↓
All tools use same session ID throughout conversation
```

**Production (HTTP - BROKEN):**
```
User opens Claude Desktop conversation
↓
Claude Desktop makes HTTP request to /mcp
↓
FastMCP creates transport for THIS request
↓
Request completes, connection may close
↓
User calls another tool...
↓
Claude Desktop makes NEW HTTP request to /mcp
↓
FastMCP creates NEW transport (no session ID header)
↓
Middleware creates NEW PostgreSQL session (__PENDING__)
↓
Tool is blocked because THIS session hasn't selected a project
```

### Why Multiple Sessions Are Created

**Normal MCP HTTP Behavior:**
- HTTP is stateless
- Connections timeout (SSE streams have timeouts)
- Claude Desktop reconnects when connection closes
- Each reconnection = new `initialize` handshake
- Each initialize = new MCP session ID

**Evidence from logs:**
- 19 seconds between Session 1 and Session 2 (likely connection timeout)
- Each session has its own SSE stream (GET requests at different times)
- Claude Desktop is working correctly - this is expected HTTP behavior!

**The problem:** Our middleware treats each new MCP connection as a separate "session" needing project selection.

---

## Why This Doesn't Affect Local Testing

Local testing with `npx` doesn't have this problem because:

1. **Persistent process:** `npx` starts a long-running Node.js process
2. **In-process transport:** No HTTP involved - direct function calls
3. **Single session:** `get_current_session_id()` called once at startup
4. **Filesystem-based:** Session tied to project directory detection
5. **No expiration:** Process stays alive until user kills it

Production can't work this way because:
- Serverless/cloud platforms don't keep processes alive indefinitely
- HTTP requires stateless request/response model
- FastMCP HTTP transport creates new sessions per connection

---

## The Solution

### Current (BROKEN):
```
Project selection scope: PER MCP SESSION
Result: Each new MCP connection requires re-selecting project
```

### Fixed (TARGET):
```
Project selection scope: PER CLAUDE DESKTOP INSTANCE (API key)
Result: Project stays selected across MCP reconnections
```

### Implementation Approach

**Key Insight:** The only stable identifier across MCP reconnections is the **Bearer token** (API key).

**New Architecture:**
1. Add `active_project_cache` dict: `{api_key: project_name}`
2. When new MCP session starts:
   - Check `active_project_cache[api_key]`
   - If project found → Auto-set on new session
   - If not found → Require project selection
3. When `select_project_for_session()` called:
   - Update PostgreSQL session record
   - Update `active_project_cache[api_key]`
4. Add cache expiration (e.g., 1 hour idle timeout)

**Benefits:**
- Works like local testing (project persists across tool calls)
- Handles Claude Desktop reconnections automatically
- Still secure (project scoped to API key)
- Compatible with existing middleware

---

## Impact

**Bugs Fixed:**
- ✅ Bug #1-6: Adapter initialization (already fixed)
- ✅ Bug #7: get_current_session_id() ignores middleware (fixed deployment 026b125d)
- ⏳ **Bug #8: Project selection doesn't persist across MCP sessions** ← THIS ISSUE

**Current State:**
- Bug #7 fix WORKS for single MCP session
- Session 2 (b70fef70) successfully selected 'linkedin' project
- But Sessions 3 and 4 started PENDING again because they're NEW sessions

**What Needs to Happen:**
1. Implement API-key-level project caching
2. Auto-apply cached project to new MCP sessions
3. Test in production with multiple tool calls
4. Verify project persists across the full conversation

---

## Technical Details

### Files Affected

**mcp_session_middleware.py:**
- Add `_active_project_cache: Dict[str, str]` (api_key → project_name)
- Add `_project_cache_timestamps: Dict[str, float]` (for expiration)
- Modify `__call__()` to check cache on new PENDING sessions
- Modify project selection handler to update cache

**claude_mcp_hybrid_sessions.py:**
- `select_project_for_session()` should update middleware cache
- May need to import middleware to access cache

### Cache Design

```python
class MCPSessionPersistenceMiddleware(BaseHTTPMiddleware):
    _active_project_cache: Dict[str, str] = {}  # {api_key: project_name}
    _cache_timestamps: Dict[str, float] = {}    # {api_key: last_activity}
    _cache_ttl: int = 3600  # 1 hour idle timeout

    def _get_cached_project(self, api_key: str) -> Optional[str]:
        """Get cached project for API key if not expired."""
        if api_key in self._active_project_cache:
            last_activity = self._cache_timestamps.get(api_key, 0)
            if time.time() - last_activity < self._cache_ttl:
                # Update timestamp
                self._cache_timestamps[api_key] = time.time()
                return self._active_project_cache[api_key]
            else:
                # Expired - remove from cache
                del self._active_project_cache[api_key]
                del self._cache_timestamps[api_key]
        return None

    def _set_cached_project(self, api_key: str, project_name: str):
        """Cache project selection for API key."""
        self._active_project_cache[api_key] = project_name
        self._cache_timestamps[api_key] = time.time()
```

---

## User Experience Comparison

### Before Fix (Current - BROKEN):

```
User: [Opens Claude Desktop]
User: "list_projects"
Claude: ✅ [Returns 24 projects]

User: "select_project_for_session('linkedin')"
Claude: ✅ "Selected linkedin project"

[Claude Desktop reconnects - new MCP session]

User: "get_last_handover"
Claude: ❌ "Project selection required for session: 7ed13d2c"

User: "Why do I need to select again??"
```

### After Fix (TARGET):

```
User: [Opens Claude Desktop]
User: "list_projects"
Claude: ✅ [Returns 24 projects]

User: "select_project_for_session('linkedin')"
Claude: ✅ "Selected linkedin project"
Claude: [Caches: api_key_abc → 'linkedin']

[Claude Desktop reconnects - new MCP session]
[Middleware checks cache, finds 'linkedin' for this API key]
[Auto-applies 'linkedin' to new session 7ed13d2c]

User: "get_last_handover"
Claude: ✅ [Returns handover data from linkedin project]

User: "Perfect! Just like local testing!"
```

---

## Next Steps

1. **Implement cache in mcp_session_middleware.py**
2. **Update select_project_for_session() to populate cache**
3. **Add cache lookup on new PENDING sessions**
4. **Test in production:**
   - Call list_projects
   - Call select_project_for_session('linkedin')
   - Wait 30 seconds (force reconnection)
   - Call get_last_handover
   - Verify: should work WITHOUT re-selecting project
5. **Deploy fix**
6. **Re-run systematic test**
7. **Celebrate when all 10 tools pass!**

---

## Related Issues

**list_projects() schema bug:**
```
⚠️ list_projects: Failed to query schema 'dementia': UndefinedTable: relation "dementia.sessions" does not exist
```

This is a SEPARATE bug - list_projects() is querying wrong schema. Needs fix.

---

**Investigation By**: Claude Code (Sonnet 4.5)
**Investigation Duration**: 08:26 - 09:00 UTC (34 minutes)
**Key Insight**: User's clarification that "it is exactly the same code" led to understanding the architectural difference
**Status**: Solution designed, implementation pending
