# switch_project() Dependency Map

Visual representation of all dependencies and data flows.

---

## 1. Global State Dependency Graph

```
┌─────────────────────────────────────────────────────────────┐
│                    GLOBAL STATE                              │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  _local_session_id: str                                      │
│      ↓                                                        │
│      ├── READ BY: switch_project()                           │
│      ├── READ BY: _get_project_for_context()                 │
│      ├── READ BY: _check_project_selection_required()        │
│      └── SET BY: _init_local_session()                       │
│                                                               │
│  _session_store: PostgreSQLSessionStore                      │
│      ↓                                                        │
│      ├── READ BY: switch_project()                           │
│      ├── USED BY: update_session_project()                   │
│      ├── USED BY: get_session()                              │
│      └── SET BY: _init_local_session()                       │
│                                                               │
│  _active_projects: dict[str, str]                            │
│      ↓                                                        │
│      ├── WRITE BY: switch_project() ← SIDE EFFECT            │
│      ├── READ BY: _get_project_for_context()                 │
│      └── CLEARED BY: Tests (to simulate stateless)           │
│                                                               │
│  config.database_url: str                                    │
│      ↓                                                        │
│      ├── READ BY: switch_project()                           │
│      ├── READ BY: PostgreSQLAdapter()                        │
│      └── SET BY: .env file / environment                     │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Database Schema Relationships

```
┌───────────────────────────────────────────────────────────────┐
│                    DATABASE STRUCTURE                          │
├───────────────────────────────────────────────────────────────┤
│                                                                 │
│  public.mcp_sessions                                           │
│  ┌─────────────────────────────────────────────────┐          │
│  │ session_id   │ project_name │ last_active │ ... │          │
│  ├─────────────────────────────────────────────────┤          │
│  │ '3b68d4a...' │ 'innkeeper'  │ 2025-11-17  │ ... │          │
│  │      ↑             ↑                                │          │
│  │      │             │                                │          │
│  │      │             └── UPDATED BY switch_project()  │          │
│  │      └── MATCHED BY _local_session_id              │          │
│  └─────────────────────────────────────────────────┘          │
│                          ↓                                      │
│                          ↓ project_name determines schema      │
│                          ↓                                      │
│  Schema: innkeeper (created by create_project)                 │
│  ┌───────────────────────────────────────────────┐            │
│  │ innkeeper.sessions                             │            │
│  │ innkeeper.context_locks   ← COUNTED BY switch_project     │
│  │ innkeeper.memory_entries                       │            │
│  │ innkeeper.file_tags                            │            │
│  └───────────────────────────────────────────────┘            │
│                                                                 │
│  Schema: linkedin                                              │
│  ┌───────────────────────────────────────────────┐            │
│  │ linkedin.sessions                              │            │
│  │ linkedin.context_locks    ← COUNTED BY switch_project     │
│  │ linkedin.memory_entries                        │            │
│  │ linkedin.file_tags                             │            │
│  └───────────────────────────────────────────────┘            │
│                                                                 │
└───────────────────────────────────────────────────────────────┘
```

---

## 3. Function Call Hierarchy

```
USER: switch_project("My-Project 2024!")
    ↓
┌────────────────────────────────────────────────────────────┐
│ switch_project(name="My-Project 2024!")                    │
│                                                             │
│ PHASE 1: SANITIZATION                                      │
│ ├─→ re.sub(r'[^a-z0-9]', '_', name.lower())               │
│ │   INPUT:  "My-Project 2024!"                            │
│ │   OUTPUT: "my_project_2024"                             │
│ └─→ safe_name = "my_project_2024"                         │
│                                                             │
│ PHASE 2: VALIDATION                                        │
│ ├─→ Check: _session_store is not None                     │
│ │   └─→ FAIL: return {"success": False, "error": ...}    │
│ └─→ Check: _local_session_id is not None                  │
│     └─→ FAIL: return {"success": False, "error": ...}    │
│                                                             │
│ PHASE 3: DATABASE UPDATE (CRITICAL)                        │
│ ├─→ _session_store.update_session_project(                │
│ │       _local_session_id,                                │
│ │       safe_name                                         │
│ │   )                                                      │
│ │   ↓                                                      │
│ │   PostgreSQLSessionStore.update_session_project()       │
│ │   ├─→ adapter.get_connection()                          │
│ │   ├─→ UPDATE mcp_sessions                              │
│ │   │   SET project_name = 'my_project_2024'             │
│ │   │   WHERE session_id = '3b68d4a...'                  │
│ │   ├─→ conn.commit()                                     │
│ │   └─→ adapter.release_connection()                     │
│ │   ↓                                                      │
│ │   RETURN: True/False (updated)                          │
│ │                                                          │
│ └─→ IF updated == False:                                  │
│     └─→ return {"success": False, "error": "not found"}  │
│                                                             │
│ PHASE 4: CACHE UPDATE (CRITICAL)                          │
│ └─→ _active_projects[_local_session_id] = safe_name      │
│     (In-memory cache for fast lookups)                    │
│                                                             │
│ PHASE 5: SCHEMA EXISTENCE CHECK                           │
│ ├─→ psycopg2.connect(config.database_url)                │
│ ├─→ SELECT schema_name FROM information_schema.schemata  │
│ │   WHERE schema_name = 'my_project_2024'                │
│ └─→ exists = (cur.fetchone() is not None)                │
│                                                             │
│ PHASE 6a: IF EXISTS - GET STATS                           │
│ ├─→ SELECT COUNT(*) FROM "my_project_2024".sessions      │
│ ├─→ SELECT COUNT(*) FROM "my_project_2024".context_locks │
│ ├─→ conn.close()                                          │
│ └─→ return {                                               │
│       "success": True,                                     │
│       "exists": True,                                      │
│       "stats": {"sessions": N, "contexts": M}             │
│     }                                                      │
│                                                             │
│ PHASE 6b: IF NOT EXISTS                                   │
│ ├─→ conn.close()                                          │
│ └─→ return {                                               │
│       "success": True,                                     │
│       "exists": False,                                     │
│       "note": "Will be created on first use"              │
│     }                                                      │
│                                                             │
└────────────────────────────────────────────────────────────┘
    ↓
RETURN: JSON string to MCP client
```

---

## 4. Downstream Consumer Map

```
switch_project() UPDATES:
├─→ mcp_sessions.project_name (DB)
├─→ _active_projects[session_id] (cache)
    ↓
    ↓ CONSUMED BY:
    ↓
    _get_project_for_context(project=None)
    ├─→ Priority 1: Explicit project parameter (if provided)
    ├─→ Priority 2: Session project ← READS FROM switch_project
    │   ├─→ Check: _active_projects[session_id]  (cache)
    │   └─→ Query: sessions.active_project       (DB fallback)
    ├─→ Priority 3: Auto-detect from filesystem
    └─→ Priority 4: Default project
        ↓
        ↓ USED BY ALL TOOLS:
        ↓
        ┌──────────────────────────────────────────────────┐
        │ MEMORY TOOLS                                     │
        ├──────────────────────────────────────────────────┤
        │ ✓ lock_context(project=None)                    │
        │ ✓ recall_context(project=None)                  │
        │ ✓ check_contexts(project=None)                  │
        │ ✓ semantic_search_contexts(project=None)        │
        │ ✓ batch_lock_contexts(project=None)             │
        │ ✓ batch_recall_contexts(project=None)           │
        │ ✓ get_context_history(project=None)             │
        │ ✓ list_contexts(project=None)                   │
        │ ✓ delete_context(project=None)                  │
        └──────────────────────────────────────────────────┘
        ┌──────────────────────────────────────────────────┐
        │ SESSION TOOLS                                    │
        ├──────────────────────────────────────────────────┤
        │ ✓ wake_up(project=None)                         │
        │ ✓ sleep(project=None)                           │
        │ ✓ get_last_handover(project=None)               │
        │ ✓ list_handovers(project=None)                  │
        └──────────────────────────────────────────────────┘
        ┌──────────────────────────────────────────────────┐
        │ FILE TOOLS                                       │
        ├──────────────────────────────────────────────────┤
        │ ✓ scan_codebase(project=None)                   │
        │ ✓ search_files(project=None)                    │
        │ ✓ get_file_context(project=None)                │
        └──────────────────────────────────────────────────┘

        IF switch_project BREAKS → ALL THESE TOOLS USE WRONG SCHEMA!
```

---

## 5. Data Transformation Pipeline

```
INPUT DATA:
name = "My-Project 2024!"

    ↓ [TRANSFORMATION 1: Sanitization]

safe_name = "my_project_2024"

    ↓ [TRANSFORMATION 2: Database Persistence]

mcp_sessions.project_name = "my_project_2024"
(WHERE session_id = _local_session_id)

    ↓ [TRANSFORMATION 3: Cache Update]

_active_projects["3b68d4a..."] = "my_project_2024"

    ↓ [TRANSFORMATION 4: Schema Validation]

SELECT schema_name FROM information_schema.schemata
WHERE schema_name = "my_project_2024"
    → exists = True/False

    ↓ [TRANSFORMATION 5a: Stats Collection (if exists)]

sessions_count = SELECT COUNT(*) FROM "my_project_2024".sessions
contexts_count = SELECT COUNT(*) FROM "my_project_2024".context_locks

    ↓ [TRANSFORMATION 5b: Skip Stats (if not exists)]

stats = None

    ↓ [TRANSFORMATION 6: JSON Response]

OUTPUT DATA:
{
  "success": true,
  "message": "✅ Switched to project 'My-Project 2024!'",
  "project": "My-Project 2024!",       ← Original name
  "schema": "my_project_2024",         ← Sanitized name
  "exists": true,
  "stats": {
    "sessions": 5,
    "contexts": 42
  },
  "note": "All memory operations will now use this project"
}
```

---

## 6. Critical Path Analysis

### What MUST happen for system to work:

```
┌────────────────────────────────────────────────────────────┐
│ CRITICAL PATH: Session → Project Mapping                   │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Session Created (_init_local_session)                     │
│  ├─ _local_session_id = uuid.uuid4().hex                  │
│  └─ INSERT INTO mcp_sessions (session_id, project_name)   │
│      VALUES ('3b68d4a...', '__PENDING__')                  │
│          ↓                                                  │
│          ↓                                                  │
│  User Calls switch_project("innkeeper")                    │
│  ├─ UPDATE mcp_sessions                                    │
│  │   SET project_name = 'innkeeper'                        │
│  │   WHERE session_id = '3b68d4a...' ← MUST MATCH!        │
│  └─ _active_projects['3b68d4a...'] = 'innkeeper' ← SAME!  │
│          ↓                                                  │
│          ↓                                                  │
│  User Calls lock_context("content", "topic")               │
│  └─ project = _get_project_for_context()                  │
│      ├─ session_id = _get_local_session_id()              │
│      │   → '3b68d4a...'                                    │
│      ├─ Check: _active_projects['3b68d4a...']             │
│      │   → 'innkeeper' ✓                                   │
│      └─ Use schema: "innkeeper"                            │
│          ↓                                                  │
│          ↓                                                  │
│  INSERT INTO "innkeeper".context_locks (...)               │
│  ✓ SUCCESS - Correct schema used!                         │
│                                                             │
└────────────────────────────────────────────────────────────┘

IF ANY OF THESE FAIL:
├─ Different session IDs used → BUG #1 (Nov 2025)
├─ Cache not updated → Tools use wrong schema
├─ DB not updated → Stateless mode breaks
└─ Session ID not available → All tools fail
```

---

## 7. Error Propagation Tree

```
switch_project("test")
    ↓
    ├─→ [CHECK] _session_store exists?
    │   └─→ NO → ERROR: "No active session"
    │            STOPS HERE ✋
    │
    ├─→ [CHECK] _local_session_id exists?
    │   └─→ NO → ERROR: "No active session"
    │            STOPS HERE ✋
    │
    ├─→ [EXECUTE] update_session_project()
    │   ├─→ [CHECK] Session exists in DB?
    │   │   └─→ NO → ERROR: "Session not found"
    │   │            STOPS HERE ✋
    │   │
    │   └─→ [EXECUTE] UPDATE SQL
    │       └─→ EXCEPTION → ERROR: "Failed to update"
    │                        STOPS HERE ✋
    │
    ├─→ [UPDATE] _active_projects cache
    │   (No errors possible - dict assignment)
    │
    ├─→ [CONNECT] psycopg2.connect()
    │   └─→ EXCEPTION → ERROR: Connection failed
    │                    STOPS HERE ✋
    │
    ├─→ [QUERY] Schema exists?
    │   └─→ EXCEPTION → ERROR: Query failed
    │                    STOPS HERE ✋
    │
    └─→ [IF EXISTS] Query stats
        └─→ EXCEPTION → ERROR: Stats query failed
                         STOPS HERE ✋

ALL ERRORS RETURN:
{"success": False, "error": "..."}
```

---

## 8. State Consistency Map

```
┌─────────────────────────────────────────────────────────┐
│ STATE CONSISTENCY: Database ⇄ Cache                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  DATABASE (persistent)                                  │
│  ┌──────────────────────────────────────┐              │
│  │ mcp_sessions                          │              │
│  │ ┌──────────────┬──────────────────┐  │              │
│  │ │ session_id   │ project_name     │  │              │
│  │ ├──────────────┼──────────────────┤  │              │
│  │ │ '3b68d4a...' │ 'innkeeper'     ├──┼─────┐        │
│  │ └──────────────┴──────────────────┘  │     │        │
│  └──────────────────────────────────────┘     │        │
│                                                │        │
│                                                │        │
│  CACHE (in-memory, volatile)                  │        │
│  ┌──────────────────────────────────────┐     │        │
│  │ _active_projects: dict               │     │        │
│  │ ┌──────────────┬──────────────────┐  │     │        │
│  │ │ session_id   │ project_name     │  │     │        │
│  │ ├──────────────┼──────────────────┤  │     │        │
│  │ │ '3b68d4a...' │ 'innkeeper'     ├──┼─────┘        │
│  │ └──────────────┴──────────────────┘  │    MUST      │
│  └──────────────────────────────────────┘    MATCH!    │
│                                                          │
│  switch_project() ENSURES CONSISTENCY:                  │
│  1. Update database FIRST                               │
│  2. Update cache SECOND (same session_id!)              │
│  3. If database update fails → don't update cache       │
│                                                          │
│  _get_project_for_context() HANDLES CACHE MISS:        │
│  1. Check cache first (fast)                           │
│  2. If miss → query database (slow)                    │
│  3. Populate cache from database                       │
│  4. Return project name                                │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 9. Integration Point Matrix

| Component | Relationship | Direction | Critical? | Notes |
|-----------|--------------|-----------|-----------|-------|
| `_local_session_id` | Identity | Read | ✅ Yes | SINGLE SOURCE OF TRUTH |
| `_session_store` | Service | Read | ✅ Yes | Database operations |
| `_active_projects` | Cache | Write | ✅ Yes | Performance optimization |
| `config.database_url` | Config | Read | ✅ Yes | Connection string |
| `mcp_sessions` table | Storage | Write | ✅ Yes | Persistent state |
| `information_schema` | Metadata | Read | ⚠️ Optional | Validation only |
| `{schema}.sessions` | Stats | Read | ⚠️ Optional | User feedback |
| `{schema}.context_locks` | Stats | Read | ⚠️ Optional | User feedback |
| `_get_project_for_context()` | Consumer | - | ✅ Yes | All tools depend on this |
| `lock_context()` | Consumer | - | ✅ Yes | Example downstream tool |
| Tests | Validation | - | ✅ Yes | Regression prevention |

**Legend:**
- ✅ Yes: MUST work or system breaks
- ⚠️ Optional: Can fail without breaking system
- Read: switch_project reads from this
- Write: switch_project writes to this

---

## 10. Refactoring Impact Analysis

### HIGH RISK: Breaking these breaks the system

```
🔴 CRITICAL - DO NOT CHANGE:
├─ Function signature: async def switch_project(name: str) -> str
├─ Database update: _session_store.update_session_project(_local_session_id, safe_name)
├─ Cache update: _active_projects[_local_session_id] = safe_name
├─ Session ID source: Must use _local_session_id
├─ Update order: Database → Cache
└─ Return type: JSON string

IF CHANGED → ALL 50+ TOOLS BREAK
```

### MEDIUM RISK: Breaking these causes errors

```
🟡 IMPORTANT - CHANGE WITH CARE:
├─ Name sanitization: Schema creation will fail
├─ Error handling: Tools won't know what failed
├─ Connection management: Resource leaks
└─ Validation logic: Invalid states possible

IF CHANGED → SOME OPERATIONS FAIL
```

### LOW RISK: Breaking these affects UX only

```
🟢 SAFE - CAN CHANGE:
├─ Error messages
├─ Console output (stderr)
├─ Stats collection
├─ Schema existence check
└─ Comment wording

IF CHANGED → NO FUNCTIONAL IMPACT
```

---

## 11. Testing Dependency Graph

```
test_project_isolation_fix.py
    ↓
    TESTS:
    ├─→ switch_project("test_project_a")
    │   ├─→ VERIFY: Returns success
    │   ├─→ VERIFY: Database updated
    │   └─→ VERIFY: Cache updated
    │
    ├─→ _active_projects.clear()
    │   (Simulate stateless HTTP request)
    │
    ├─→ _get_project_for_context()
    │   └─→ VERIFY: Returns "test_project_a" (from DB)
    │
    ├─→ lock_context("content", "topic")
    │   └─→ VERIFY: Uses "test_project_a" schema
    │
    ├─→ switch_project("test_project_b")
    │   └─→ VERIFY: Can switch to different project
    │
    └─→ recall_context("topic", project="test_project_a")
        └─→ VERIFY: Contexts are isolated by project

    IF ANY FAIL → switch_project IS BROKEN
```

---

## 12. Session Lifecycle Integration

```
┌───────────────────────────────────────────────────────────┐
│ SESSION LIFECYCLE: Creation → Project Selection → Usage  │
├───────────────────────────────────────────────────────────┤
│                                                            │
│  [1] SERVER START                                         │
│      ├─ _init_local_session()                            │
│      │  ├─ _local_session_id = uuid.uuid4().hex          │
│      │  └─ INSERT mcp_sessions (project='__PENDING__')   │
│      └─ _session_store = PostgreSQLSessionStore(...)     │
│          ↓                                                 │
│          ↓                                                 │
│  [2] FIRST TOOL CALL (any tool)                          │
│      ├─ _check_project_selection_required()              │
│      │  ├─ session = _session_store.get_session(...)     │
│      │  ├─ IF session.project_name == '__PENDING__':     │
│      │  │   └─ RETURN ERROR: "PROJECT_SELECTION_REQUIRED"│
│      │  └─ Tool execution BLOCKED ✋                      │
│      └─ User sees: "Please select a project first"       │
│          ↓                                                 │
│          ↓                                                 │
│  [3] USER SELECTS PROJECT                                │
│      switch_project("innkeeper") ← WE ARE HERE            │
│      ├─ UPDATE mcp_sessions SET project_name='innkeeper' │
│      └─ _active_projects[session_id] = 'innkeeper'       │
│          ↓                                                 │
│          ↓                                                 │
│  [4] SUBSEQUENT TOOL CALLS                               │
│      lock_context("content", "topic")                     │
│      ├─ project = _get_project_for_context()             │
│      │  ├─ Check: _active_projects[session_id]           │
│      │  │   → 'innkeeper' ✓                              │
│      │  └─ Use schema: "innkeeper"                        │
│      ├─ INSERT INTO "innkeeper".context_locks (...)       │
│      └─ SUCCESS ✓                                         │
│          ↓                                                 │
│          ↓                                                 │
│  [5] SESSION END                                          │
│      └─ Session expires after 24h inactivity              │
│          (Cleanup by mcp_session_cleanup.py)              │
│                                                            │
└───────────────────────────────────────────────────────────┘

switch_project() is the GATEWAY between Phase 2 and Phase 4!
```

---

**END OF DEPENDENCY MAP**

Use this map when refactoring to ensure all connections are preserved!
