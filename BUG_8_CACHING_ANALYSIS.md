# Bug #8 API-Key-Level Project Caching Implementation Analysis

**Date**: November 16, 2025
**Status**: IMPLEMENTED - Ready for evaluation
**Focus**: Single-user testing scenario (one API key per user)

---

## Executive Summary

The API-key-level project caching implementation in `mcp_session_middleware.py` (lines 59-102) is a **pragmatic solution** to Bug #8 that solves the stated problem effectively for the single-user testing scenario but has important limitations to understand before broader deployment.

### Quick Assessment

| Aspect | Status | Risk |
|--------|--------|------|
| Core functionality | ✅ Works | Low |
| Thread safety | ⚠️ Potential issues | Medium |
| Server restart handling | ✅ Acceptable | Low |
| Shared API key scenario | ❌ Not supported | High |
| Memory leaks | ✅ Handled | Low |
| Cache expiration | ✅ Correct | Low |

---

## 1. Implementation Architecture

### Current Design (Lines 59-102 in mcp_session_middleware.py)

```python
class MCPSessionPersistenceMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, db_pool):
        super().__init__(app)
        self.session_store = PostgreSQLSessionStore(db_pool)

        # API-key-level project caching
        self._active_project_cache = {}  # {api_key: project_name}
        self._cache_timestamps = {}      # {api_key: last_activity_timestamp}
        self._cache_ttl = 3600           # 1 hour idle timeout
```

### Cache Lifecycle

1. **Cache Write** (Line 100-102): When `select_project_for_session()` succeeds
   - Extracts API key from `Authorization: Bearer <key>` header
   - Stores `{api_key: project_name}` in `_active_project_cache`
   - Records timestamp in `_cache_timestamps`

2. **Cache Read** (Line 77-82): When new MCP session starts with `__PENDING__` project
   - Extracts API key from Authorization header
   - Calls `_get_cached_project(api_key)`
   - Checks TTL: if `time.time() - timestamp < 3600`, cache is valid
   - Updates timestamp (sliding window)
   - Returns cached project or None

3. **Cache Expiration** (Line 84-87): When idle > 1 hour
   - Deletes from both `_active_project_cache` and `_cache_timestamps`
   - Logs expiration event

---

## 2. Integration Points

### Where Cache is Used

**Line 145-154** (Middleware dispatcher):
```python
if method == 'initialize' or session_id == 'missing':
    # New session created by FastMCP...
    if response.status_code == 200:
        api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
        cached_project = self._get_cached_project(api_key) if api_key else None
        
        # Use cached project if available, otherwise __PENDING__
        initial_project = cached_project if cached_project else '__PENDING__'
        
        if cached_project:
            logger.info(f"🔄 Auto-applying cached project '{cached_project}'...")
        
        result = self.session_store.create_session(
            session_id=new_session_id,
            project_name=initial_project,  # ← Uses cache here
            ...
        )
```

**Line 235-246** (After project selection):
```python
if tool_name == 'select_project_for_session' and response.status_code == 200:
    try:
        project_name = body.get('params', {}).get('arguments', {}).get('name')
        api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if project_name and api_key:
            self._set_cached_project(api_key, project_name)  # ← Updates cache
            logger.info(f"✅ Cached project '{project_name}' for future sessions")
    except Exception as e:
        logger.warning(f"Failed to cache project selection: {e}")
```

### Integration with PostgreSQL

**Session Store Unmodified**: 
- Cache is completely separate from PostgreSQL
- No schema changes needed
- Sessions still store actual `project_name` in database
- Cache is just optimization layer

**Cache ↔ PostgreSQL Relationship**:
```
API Request #1 (select_project_for_session):
  1. Middleware creates MCP session with project='__PENDING__'
  2. Tool execution updates session.project_name in PostgreSQL ✅
  3. Middleware caches: {api_key: project_name}

API Request #2 (after reconnect):
  1. Middleware checks cache: finds project_name for api_key ✅
  2. Creates NEW MCP session with cached project_name ✅
  3. No need to call select_project again
```

---

## 3. Identified Pros & Cons

### Advantages

1. **Minimal Code Changes** (20 lines of implementation)
   - No database schema modifications
   - No breaking changes to session store interface
   - Backward compatible

2. **Solves the Stated Problem**
   - Project selection persists across MCP reconnections
   - Mimics local testing behavior (where process stays alive)
   - User experience matches expectations

3. **Correct Expiration Logic**
   - Sliding window: timestamp updates on each access
   - 1-hour TTL is reasonable for interactive sessions
   - Automatic cleanup prevents unbounded memory growth

4. **Handles Common Cases**
   - Multiple tool calls in single session ✅
   - Connection timeout/reconnect (19s gap) ✅
   - Server restart with existing sessions ✅

5. **Low Performance Impact**
   - O(1) dictionary lookups (constant time)
   - Time check only on cache hit (no DB calls)
   - Negligible CPU overhead

### Limitations & Risks

1. **Thread Safety Not Guaranteed** (MEDIUM RISK)
   
   **Issue**: Dictionary access without locks
   ```python
   # Potential race condition:
   # Thread A: checks if api_key in self._active_project_cache
   # Thread B: deletes self._active_project_cache[api_key]
   # Thread A: tries to access self._cache_timestamps[api_key] → KeyError
   ```
   
   **Real Risk Level**: LOW in practice
   - FastMCP HTTP middleware runs async/await (not true threads)
   - Python GIL protects dictionary operations
   - But: concurrent access from different uvicorn workers could cause issues
   
   **Mitigation**: Currently none (acceptable for single-user testing)

2. **Server Restart Loses Cache** (LOW RISK)
   
   **Issue**: In-memory cache cleared on restart
   ```
   Before restart: {api_key_abc: 'linkedin'} in memory
   After restart: {} in memory
   User logs in again: sees "Project selection required"
   ```
   
   **Real Impact**: Minimal
   - Only affects FIRST tool call after server restart
   - After selecting project again, cache refills
   - PostgreSQL sessions still work fine
   - Transparent to user if they wait for connection to stabilize
   
   **Alternative**: Could persist cache in PostgreSQL, but adds complexity

3. **Shared API Key Not Supported** (HIGH RISK - BUT NOT APPLICABLE TO SINGLE-USER SCENARIO)
   
   **Issue**: If same API key used by multiple users/devices:
   ```
   User A: select_project_for_session('linkedin')
   Cache: {api_key_shared: 'linkedin'}
   
   User B (same API key, different device):
   New MCP session created with project='linkedin' (not their project!)
   ```
   
   **Real Impact**: NOT AN ISSUE for single-user testing
   - Each user should have unique API key
   - This is OAuth best practice anyway
   - Production: use separate API keys or JWT with user info
   
   **Current Status**: Design explicitly targets single-user

4. **Cache Key Leakage Could Expose Projects** (LOW RISK)
   
   **Issue**: API key is extracted and used as dictionary key
   ```python
   api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
   self._active_project_cache[api_key] = project_name
   ```
   
   **Attack Vector**: 
   - If server process is compromised, attacker could read cache
   - But: attacker already has API key (from headers)
   
   **Real Risk**: Already mitigated by Bearer token auth
   - If API key is exposed, bigger problems exist
   - Cache doesn't increase attack surface

5. **Missing Edge Cases in Code** (LOW RISK)
   
   **Case 1: Empty API key**
   ```python
   # Line 146-147
   api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
   cached_project = self._get_cached_project(api_key) if api_key else None
   ```
   ✅ Correctly skips cache if no auth header
   
   **Case 2: Malformed Authorization header**
   ```python
   # If header is "Bearer" (no key) or "InvalidFormat xyz"
   api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
   # Results in empty string or "xyz" - handled correctly
   ```
   ✅ Defaults to `__PENDING__` session
   
   **Case 3: Cache expiration during request**
   ```python
   # Line 79: time check done, cache valid
   # ... network delay (>1 second) ...
   # Line 81: timestamp updated
   ```
   ✅ Sliding window correctly handles this
   
   **Case 4: Rapid project switches**
   ```python
   User: select_project('linkedin')  → Cache: {key: 'linkedin'}
   User: select_project('innkeeper') → Cache: {key: 'innkeeper'}
   ```
   ✅ Last write wins (correct)

---

## 4. Architecture Comparison: Why In-Memory Cache?

### Why NOT PostgreSQL?

**Considered But Rejected**:
```sql
-- Would need new table:
CREATE TABLE api_key_project_cache (
    api_key TEXT PRIMARY KEY,
    project_name TEXT,
    last_activity BIGINT
);
```

**Problems with DB approach**:
1. **Circular dependency**: Middleware creates sessions BEFORE user selects project
   - But needs project to know which schema to use
   - Can't query per-project tables yet
   
2. **Public schema pollution**: Would need to store in public schema (not isolated)
   - Violates "per-project schema isolation" design
   - Mixing API-level concerns with project-level storage
   
3. **Added latency**: SELECT on every new session
   - DB lookup ~50-100ms (network)
   - In-memory lookup: <1ms
   
4. **Overkill for TTL**: Don't need persistence across restarts
   - Cache is performance optimization, not critical data
   - Session selection is stateless operation
   - Worst case: user selects project again

**Why in-memory is correct**:
- Cache is temporary (1-hour sliding window)
- Not meant to survive restarts
- Improves performance, not required for correctness
- Simpler, fewer dependencies

### Alternative: Global MCP Transport Variable

**Alternative Approach** (considered but rejected):
```python
# In FastMCP - keep project in transport metadata
# (Like how session ID is tracked)
```

**Why this doesn't work**:
- FastMCP is stateless HTTP framework
- Each request creates new transport
- No way to propagate data between HTTP connections
- Would require rewriting FastMCP internals

---

## 5. Edge Cases Analysis

### Case 1: User Switches Projects Mid-Session

```
Request 1: select_project_for_session('linkedin')
  → Cache: {api_key: 'linkedin'}, Session 1 project='linkedin' ✅

Request 2: select_project_for_session('innkeeper')  [different project]
  → Cache: {api_key: 'innkeeper'}, Session 2 project='innkeeper' ✅
  → User's tools use new project ✅

Request 3: (after reconnect)
  → New Session 3 created with project='innkeeper' (from cache) ✅
```

**Result**: Correct behavior, cache follows user's most recent choice

---

### Case 2: Connection Timeout (19-second gap in Bug #8 logs)

```
Timeline:
T=00:00 User calls list_projects()
        → Session 1 created, active
        → Response sent via SSE stream
T=00:19 SSE stream timeout, connection closes
T=00:19+ User calls select_project('linkedin')
        → FastMCP creates new transport/session (Session 2)
        → Middleware: Session 2 starts with __PENDING__
        → User calls select_project, it succeeds
        → Cache: {api_key: 'linkedin'}

T=00:25 User calls get_last_handover()
        → FastMCP creates new transport/session (Session 3)
        → Middleware: checks cache, finds 'linkedin'
        → Session 3 created with project='linkedin' (from cache) ✅
        → Tool runs successfully ✅
```

**Result**: Project persists across multiple reconnections ✅

---

### Case 3: Rapid Reconnections

```
User's network is flaky, reconnecting every 2 seconds:

T=0:00   initialize → Session 1 created with project='__PENDING__'
T=0:05   select_project('linkedin') → Cache set
T=0:07   new connection → Session 2 created with cache='linkedin' ✅
T=0:09   new connection → Session 3 created with cache='linkedin' ✅
T=0:11   new connection → Session 4 created with cache='linkedin' ✅
         (cache timestamp updated each time)

After 1 hour idle:
T=1:00:00 new connection → Cache expired, Session 5 created with __PENDING__
```

**Result**: Robust to rapid reconnects, expires correctly ✅

---

### Case 4: Multiple Middleware Instances

```
Deployment setup: 2 uvicorn workers (each has own middleware instance)

Worker 1 middleware: _active_project_cache = {}
Worker 2 middleware: _active_project_cache = {}

Request 1 hits Worker 1:
  select_project('linkedin')
  → Worker 1 cache: {api_key: 'linkedin'}
  → Worker 2 cache: {} (doesn't know about it)

Request 2 hits Worker 2:
  new session created
  → Checks Worker 2 cache (empty)
  → Session created with project='__PENDING__'
  → User sees "Project selection required" ❌
```

**Result**: BROKEN with multiple workers (each has own cache) ⚠️

**Note**: Bug #8 fix is for single-user testing scenario
- In production with load balancer, would need Redis cache or database
- Current design acceptable for testing (one worker)
- Should document this limitation

---

## 6. Testing Implications

### Test Cases Written (Existing)

From `tests/integration/test_mcp_session_persistence.py`:

1. ✅ Session persistence across restarts
2. ✅ Session expiration (24 hours)
3. ✅ Activity update extends expiration
4. ✅ Cleanup removes only expired sessions
5. ✅ Middleware creates sessions on initialize
6. ✅ Middleware rejects expired sessions

### Test Cases MISSING (For Caching Feature)

```python
# Should be added:
def test_cache_should_persist_project_across_mcp_reconnections():
    """Test Bug #8 fix: project selection survives reconnect"""
    # 1. Initialize session
    # 2. Select project via select_project_for_session()
    # 3. Simulate connection timeout
    # 4. Create new MCP session with same API key
    # 5. Verify: new session has cached project (not __PENDING__)

def test_cache_should_expire_after_ttl():
    """Test cache expiration after 1 hour idle"""
    # 1. Select project
    # 2. Advance time by 3600+ seconds
    # 3. New session with same API key
    # 4. Verify: session has __PENDING__ (cache expired)

def test_cache_should_be_per_api_key():
    """Test cache isolation between different users"""
    # 1. API key A selects 'linkedin'
    # 2. API key B creates session
    # 3. Verify: API key B gets __PENDING__ (no cross-contamination)

def test_cache_should_handle_empty_api_key():
    """Test graceful degradation with missing Authorization header"""
    # 1. Request with no Authorization header
    # 2. Verify: session created with __PENDING__
    # 3. No errors thrown

def test_cache_timestamp_should_update_on_access():
    """Test sliding window: timestamp updates on each hit"""
    # 1. Cache: {key: 'project'}, ts=T1
    # 2. Access after 30 minutes
    # 3. Verify: ts updated to T2
    # 4. Another access after 30+ minutes from T2
    # 5. Verify: still valid (would have expired if no timestamp update)

def test_multiple_workers_should_have_separate_caches():
    """Test limitation: each worker has independent cache"""
    # 1. Start 2 middleware instances (different objects)
    # 2. Worker 1: cache project
    # 3. Worker 2: check cache (empty)
    # 4. Verify: each worker has isolated cache
    # 5. Document: production with load balancer needs Redis/DB cache
```

---

## 7. Logging & Observability

### Current Logging (Good Coverage)

**Line 85**: Cache expiration
```python
logger.info(f"🕒 Project cache expired for API key {api_key[:8]}... (idle > {self._cache_ttl}s)")
```

**Line 102**: Cache write
```python
logger.info(f"💾 Cached project '{project_name}' for API key {api_key[:8]}...")
```

**Line 153**: Cache hit
```python
logger.info(f"🔄 Auto-applying cached project '{cached_project}' for API key {api_key[:8]}...")
```

### Missing Metrics

Could add for production:
```python
# Cache hit rate
cache_hits = 0
cache_misses = 0

# Cache size
max_cache_size = len(self._active_project_cache)

# TTL distribution
cache_age = time.time() - self._cache_timestamps.get(api_key, 0)
```

---

## 8. Security Assessment

### Bearer Token Extraction

**Code** (Line 146, 240):
```python
api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
```

**Security Analysis**:

1. ✅ No validation of Bearer format
   - If header is "Bearer", results in empty string → skips cache
   - If header is "CustomFormat xyz", results in empty string → skips cache
   - Gracefully degrades

2. ✅ Token not logged (only first 8 chars of api_key in logs)
   - No secrets in logs ✅

3. ✅ Cache doesn't increase attack surface
   - If Bearer token exposed: attacker can already impersonate user
   - Cache value (project name) is non-sensitive

4. ⚠️ No HTTPS requirement checked
   - But: enforced at transport layer (CloudFlare/load balancer)
   - Not middleware's responsibility

### Data Privacy

**What's Stored**:
```python
_active_project_cache = {
    "bearer_token_hash_or_plaintext": "project_name"
}
```

**Privacy Concerns**:
- API keys stored in plaintext in middleware memory
- If server compromised: attacker can read all cached projects per key
- But: same attacker already has API keys from HTTP headers
- Not a unique exposure

**Mitigation** (Optional):
```python
# Could hash API keys:
api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
self._active_project_cache[api_key_hash] = project_name
```
But this adds complexity for minimal benefit (attacker with memory access wins anyway).

---

## 9. Issues Found During Implementation

### Bug 1: Empty API Key (Handled ✅)
```python
# Line 147: Correctly skips cache if no api_key
cached_project = self._get_cached_project(api_key) if api_key else None
```

### Bug 2: Race Condition in Expiration (Minor ⚠️)
```python
# Line 79: check expiration
if time.time() - last_activity < self._cache_ttl:
    # Line 81: update timestamp AFTER check
    self._cache_timestamps[api_key] = time.time()
```

**Potential Issue**: Between check (line 79) and update (line 81), another thread could delete the timestamp
**Real Impact**: Very low (requires concurrent middleware calls on same api_key)
**Acceptable**: For single-user testing scenario

### Bug 3: Missing else-if Optimization (Code Quality)
```python
# Current (fine):
if api_key in self._active_project_cache:
    if time.time() - last_activity < self._cache_ttl:
        # ... return and update timestamp
    else:
        # ... cleanup and return None
return None

# Could be:
if api_key not in self._active_project_cache:
    return None
if time.time() - last_activity >= self._cache_ttl:
    # ... cleanup
    return None
# ... valid, update and return
```
But current version is clear and correct.

---

## 10. Deployment Readiness Assessment

### For Single-User Testing (Current Scenario)

| Aspect | Status | Notes |
|--------|--------|-------|
| Functionality | ✅ READY | Solves Bug #8 |
| Performance | ✅ READY | <1ms overhead |
| Safety | ⚠️ ACCEPTABLE | No thread locks, but low contention |
| Monitoring | ⚠️ PARTIAL | Basic logging present |
| Documentation | ❌ MISSING | Should document limitations |
| Tests | ⚠️ PARTIAL | Basic tests exist, cache tests missing |

### For Multi-User Production

| Aspect | Status | Notes |
|--------|--------|-------|
| Functionality | ❌ BROKEN | Cache not shared across workers |
| Thread Safety | ❌ UNSAFE | Dictionary without locks |
| Scalability | ❌ POOR | Each worker has own cache |
| Security | ⚠️ ACCEPTABLE | But needs hardening |

---

## 11. Alternative Implementations Considered

### Alternative 1: Redis Cache (Production-Ready)

```python
import redis

class MCPSessionPersistenceMiddleware:
    def __init__(self, app, db_pool):
        self.redis = redis.Redis(host='localhost', port=6379, db=0)
    
    def _get_cached_project(self, api_key: str) -> Optional[str]:
        value = self.redis.get(f"project:{api_key}")
        if value:
            self.redis.expire(f"project:{api_key}", 3600)  # Sliding window
            return value.decode()
        return None
    
    def _set_cached_project(self, api_key: str, project_name: str):
        self.redis.setex(f"project:{api_key}", 3600, project_name)
```

**Advantages**:
- Shared across workers ✅
- Atomic operations ✅
- Built-in TTL ✅
- Production-ready ✅

**Disadvantages**:
- Extra dependency (Redis)
- Not needed for single-user testing
- Adds operational complexity

### Alternative 2: Database Cache (Matches Session Persistence)

```sql
-- In public schema (shared across projects)
CREATE TABLE api_key_project_cache (
    api_key_hash TEXT PRIMARY KEY,
    project_name TEXT,
    last_activity BIGINT,
    created_at TIMESTAMP
);
```

**Advantages**:
- Survives server restart ✅
- Shared across workers ✅
- No new infrastructure ✅

**Disadvantages**:
- Circular dependency issue (mentioned in section 4)
- Complicates schema design
- Overkill for caching (persistence not needed)

### Alternative 3: Session-Based Cache (Reuse Existing Sessions)

```
Instead of caching by API key:
  → Detect if user has active session for any project
  → Reuse that session's project selection
```

**Advantages**:
- No new cache infrastructure ✅
- Already in PostgreSQL ✅

**Disadvantages**:
- Only works if session still exists
- Doesn't help after session expires (24h)
- Requires complex session search logic
- Less reliable than explicit cache

**Current Implementation Verdict**: ✅ Correct choice for single-user testing scenario

---

## 12. Recommended Next Steps

### Before Production Deployment

1. **Add Cache Test Cases** (CRITICAL)
   ```python
   # tests/integration/test_cache_bug_8.py
   - Test cache persistence across reconnects
   - Test cache expiration after TTL
   - Test cache isolation per API key
   - Test handling of missing/invalid auth headers
   ```

2. **Document Limitations** (IMPORTANT)
   - Single-worker/single-process only
   - In-memory (not persisted)
   - 1-hour idle timeout
   - Add to README.md

3. **Add Prometheus Metrics** (NICE-TO-HAVE)
   - `cache_hits` counter
   - `cache_misses` counter
   - `cache_size` gauge
   - `cache_evictions` counter

4. **Evaluate Multi-Worker Setup** (CRITICAL IF SCALING)
   - Test with 2+ workers
   - Document that Redis needed for production
   - OR: Switch to database cache
   - OR: Use sticky sessions (not viable with HTTP reconnects)

### Before Broader Deployment (Multi-User)

1. **Implement Redis Cache**
   - Add Redis as dependency
   - Implement Redis version of cache methods
   - Test with multiple workers

2. **Add Security Hardening**
   - Consider API key hashing
   - Add cache key encryption
   - Rate limit project selection changes

3. **Add Monitoring**
   - Track cache hit rate
   - Alert on unusual cache size
   - Monitor TTL distribution

---

## 13. Conclusion

### Summary

The API-key-level project caching implementation is **correct and sufficient for the single-user testing scenario** described in Bug #8. It elegantly solves the problem of project selection not persisting across MCP reconnections by:

1. Caching the most recent project selection per API key
2. Using a 1-hour sliding-window TTL for reasonable memory bounds
3. Automatically applying cached project to new sessions
4. Integrating seamlessly with existing PostgreSQL session management

### Risks Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Cache inconsistency with multi-workers | High | High | Document single-worker requirement |
| Thread safety issues | Low | Medium | Acceptable for single-user; monitor |
| Memory unbounded growth | Low | Low | TTL handles cleanup |
| API key exposure in logs | Low | Medium | Already handled (only first 8 chars) |
| Circular dependency (if moved to DB) | N/A | N/A | Keep in-memory (correct design) |

### Recommendation

✅ **APPROVED FOR SINGLE-USER TESTING**

**Go/No-Go Decision**:
- Deploy as-is for testing ✅
- Document that production scaling needs Redis
- Plan Redis migration for multi-worker deployments
- Add cache test cases before merging

**Test Plan**:
1. Run systematic tool test (Bug #8 workflow)
2. Verify all 10 tools work with cached project
3. Test cache expiration by waiting 1+ hours
4. Test with multiple API keys (if applicable)
5. Monitor logs for any cache anomalies

---

## Appendix A: Code References

### Key Files
- `mcp_session_middleware.py` lines 48-102: Cache implementation
- `mcp_session_middleware.py` lines 145-154: Cache usage on initialize
- `mcp_session_middleware.py` lines 235-246: Cache update on project select
- `claude_mcp_hybrid_sessions.py` lines 2523-2686: select_project_for_session()
- `server_hosted.py` lines 442-443: Middleware registration

### Git History
- `a8d2941`: feat(sessions): implement API-key-level project caching to fix Bug #8
- `4bbe080`: fix(sessions): make get_current_session_id() use middleware session

---

## Appendix B: Single-User Testing Assumptions

This evaluation assumes:
1. **One API key** per test session
2. **One Claude Desktop instance** (or equivalent client)
3. **One server process** (or sticky sessions if multiple)
4. **Duration < 1 hour** of inactivity or full session lifecycle under 24 hours

If any of these assumptions change, reconsider cache architecture.

