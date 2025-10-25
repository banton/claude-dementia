# Dementia Cloud Migration Analysis

**Date:** 2025-01-15
**Purpose:** Migrate local SQLite-based Dementia MCP to cloud-hosted PostgreSQL
**Goal:** Cross-device portability with project-level isolation

---

## 1. Current Architecture Summary

### Project Identification Mechanism
- **Primary:** Filesystem-based via `PROJECT_ROOT` (from `CLAUDE_PROJECT_DIR` env var or `cwd`)
- **Fingerprint:** MD5 hash of `{PROJECT_ROOT}:{PROJECT_NAME}` (first 8 chars)
- **Detection:** Project markers (`.git`, `package.json`, etc.) determine DB location
- **Session Binding:** Each session is tied to a specific project fingerprint

### Database Strategy
**Three-tier storage selection:**
1. Environment variable override (`CLAUDE_MEMORY_DB`)
2. Project-local storage (`.claude-memory.db` if project markers found)
3. User cache with path hashing (`~/.claude-dementia/{hash}.db`)

**Result:** Each project gets its own SQLite database file.

### Schema Structure (9 tables)
```sql
sessions            -- Project-aware sessions (fingerprint, path, name)
context_locks       -- Versioned immutable contexts (50KB limit)
context_archives    -- Soft-deleted contexts with recovery
memory_entries      -- Categorized memory updates
file_tags           -- Semantic file tagging (project scanning)
todos               -- Task tracking
project_variables   -- Key-value config
session_updates     -- Session activity log
memory (legacy)     -- Backward compatibility
fixes               -- Bug fix documentation
decisions           -- Decision tracking (not seen in init)
```

**Key constraint:** `UNIQUE(session_id, label, version)` in context_locks

### Tools Inventory (23 tools)

**Session Management:**
- `wake_up()` - Start session, load context
- `sleep()` - Create handover package
- `memory_update()` - Add categorized memories
- `memory_status()` - Show memory stats

**Context Operations (RLM-optimized):**
- `lock_context()` - Create versioned snapshot (with preview/key_concepts)
- `recall_context()` - Retrieve exact content
- `update_context()` - Create new version
- `unlock_context()` - Archive context
- `get_context_preview()` - Quick preview without full load
- `explore_context_tree()` - Browse organized contexts
- `list_topics()` - List all topics
- `check_contexts()` - Find relevant contexts for text
- `ask_memory()` - Natural language search with synthesis

**Project Scanning:**
- `project_update()` - Intelligent file tagging
- `project_status()` - Project insights
- `tag_path()` - Manual file tagging
- `search_by_tags()` - Tag-based search
- `file_insights()` - File/project analysis
- `get_tags()` / `search_tags()` - Tag queries

**Database Operations:**
- `query_database()` - Read-only SELECT queries
- `inspect_database()` - Preset inspections
- `execute_sql()` - Write operations (INSERT/UPDATE/DELETE)

**Initialization:**
- `sync_project_memory()` - Auto-extract project contexts

### File References
- **Storage:** Relative paths in `file_tags` table
- **Context:** Path resolution assumes same `PROJECT_ROOT`
- **Usage:** File tagging links files to semantic metadata

### Session Management
- **Lifespan:** Persistent across tool calls (SQLite connection)
- **Activity tracking:** `last_active` timestamp updated per tool call
- **Project switching:** Warns if switching between projects
- **Auto-recovery:** Finds/reuses active session for current project

---

## 2. Cloud Migration: Critical Changes Required

### Priority 1: Project Identification (BREAKING CHANGE)
**Current:** Filesystem path (`/Users/banton/Sites/my-project`)
**Cloud:** Explicit project selection mechanism needed

**Options:**
1. **User-provided project ID** (recommended for POC)
   - User specifies `project_id` parameter in tools
   - Simple, explicit, works immediately
   - Con: Requires manual tracking

2. **MCP session context** (future)
   - Project ID embedded in MCP connection metadata
   - Transparent to user once set
   - Con: Requires MCP protocol understanding

3. **Inferred from conversation** (complex)
   - LLM detects project from conversation
   - Most magical UX
   - Con: Error-prone, needs fallback

**Recommendation:** Start with #1 (explicit `project_id`), migrate to #2 post-POC.

### Priority 2: Database Access Pattern
**Current:**
```python
def get_db():
    return sqlite3.connect(DB_PATH)  # Thread-local connection pool
```

**Cloud:**
```python
import psycopg2
from psycopg2.pool import ThreadedConnectionPool

# Global connection pool
pool = ThreadedConnectionPool(
    minconn=2,
    maxconn=10,
    host=os.environ['POSTGRES_HOST'],
    database=os.environ['POSTGRES_DB'],
    user=os.environ['POSTGRES_USER'],
    password=os.environ['POSTGRES_PASSWORD']
)

def get_db():
    return pool.getconn()  # Must return to pool when done
```

**Changes needed:**
- Replace `sqlite3` with `psycopg2`
- Add connection pool management
- Handle connection return (context managers)
- Replace `?` placeholders with `%s` (Postgres syntax)
- Update `AUTOINCREMENT` to `SERIAL`
- Replace `GLOB` with `~*` (regex)

### Priority 3: Schema Changes (Multi-Project Single Database)

**Current:** Separate DB per project → implicit isolation
**Cloud:** Shared database → explicit isolation via `project_id`

**Add to ALL tables:**
```sql
project_id UUID NOT NULL  -- Add to every table
CREATE INDEX idx_{table}_project ON {table}(project_id)
```

**New table:**
```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    owner_user_id TEXT,  -- Future: multi-user
    metadata JSONB
);
```

**Updated constraints:**
```sql
-- Before:
UNIQUE(session_id, label, version)

-- After:
UNIQUE(project_id, session_id, label, version)
```

**All queries need filtering:**
```sql
-- Before:
SELECT * FROM context_locks WHERE session_id = ?

-- After:
SELECT * FROM context_locks WHERE project_id = %s AND session_id = %s
```

### Priority 4: File Reference Handling

**Problem:** Local file paths (`./src/main.py`) meaningless in cloud

**Options:**

1. **Keep relative paths** (POC approach)
   - Store paths as-is
   - Note: Breaks cross-device file access
   - Works if "memory only" use case

2. **Git-based references** (better)
   ```json
   {
     "repo": "github.com/user/repo",
     "commit": "abc123",
     "path": "src/main.py"
   }
   ```
   - Portable across devices
   - Requires git integration

3. **Abstract file IDs** (future)
   - Cloud file storage with unique IDs
   - Most portable
   - Complex to implement

**Recommendation:** Option #1 for POC, document limitation.

### Priority 5: get_current_session_id() Rewrite

**Current logic:**
1. Hash `PROJECT_ROOT:PROJECT_NAME` → `project_fingerprint`
2. Find active session for this fingerprint
3. Create new session if none found

**Cloud logic:**
1. Get `project_id` from parameter/context
2. Find active session for this project_id
3. Create new session if none found

**Changes:**
```python
# Before:
project_fingerprint = hashlib.md5(f"{PROJECT_ROOT}:{PROJECT_NAME}".encode()).hexdigest()[:8]
cursor.execute("SELECT id FROM sessions WHERE project_fingerprint = ?", (project_fingerprint,))

# After:
cursor.execute("SELECT id FROM sessions WHERE project_id = %s ORDER BY last_active DESC LIMIT 1", (project_id,))
```

### Priority 6: Tools Requiring Modification

**Minimal changes (add `project_id` parameter):**
- `wake_up(project_id)` ← **Entry point, must have this**
- `lock_context(project_id, ...)`
- `recall_context(project_id, topic, ...)`
- All other context tools

**No changes needed (work as-is):**
- `query_database()` - Database agnostic
- `inspect_database()` - Database agnostic
- `execute_sql()` - Database agnostic

**Major rework:**
- `project_update()` - File scanning assumes local filesystem
- `file_insights()` - Reads local files
- All file tagging tools

**Recommendation:** Phase 1 = Context tools only, Phase 2 = File tools (or drop).

---

## 3. Session Strategy Assessment

### Option A: Session-Based (Current Architecture)
**How it works:**
- Each tool call updates `last_active` timestamp
- Session persists across tool invocations
- `wake_up()` loads context at start
- `sleep()` creates handover at end

**With SSE:**
- SSE connection maps to session naturally
- Connection open = session active
- Connection close = session ends (or timeout)

**Pros:**
- Matches current design (minimal changes)
- Natural fit for SSE long-lived connections
- State management already implemented

**Cons:**
- Requires connection state tracking
- Session cleanup on disconnect needed

### Option B: Stateless (REST-like)
**How it works:**
- Every tool call is independent
- `project_id` passed in every request
- No session concept, just project context

**Pros:**
- Simpler cloud deployment
- Easier horizontal scaling
- No session management

**Cons:**
- Doesn't match current design
- Loses "session start" context loading
- No handover between sessions

### Recommendation: **Hybrid Approach for POC**

**Start stateless, add session layer later:**

```python
# Phase 1 (Weekend POC):
# All tools take project_id explicitly
lock_context(project_id="abc-123", content="...", topic="...")

# Phase 2 (Post-POC):
# Session middleware infers project_id from SSE connection
# Tools work without project_id parameter
lock_context(content="...", topic="...")  # project_id from session context
```

**Why:**
- Stateless is simpler to implement in 2 days
- Can add session layer without breaking API
- SSE can be added as enhancement

---

## 4. Project Management Requirements

### Creating Projects
```python
@mcp.tool()
async def create_project(name: str, metadata: Optional[dict] = None) -> str:
    """
    Create a new project in the cloud.

    Returns: project_id (UUID)
    """
    project_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO projects (id, name, metadata)
        VALUES (%s, %s, %s)
    """, (project_id, name, json.dumps(metadata or {})))
    return f"✅ Project created: {project_id}"
```

### Selecting Projects (POC)
```python
# Option 1: User passes project_id to every tool
wake_up(project_id="abc-123")

# Option 2: Set once per session (better UX)
@mcp.tool()
async def switch_project(project_id: str):
    """Switch to a different project."""
    # Store in session state/SSE metadata
    set_current_project(project_id)
```

### Listing Projects
```python
@mcp.tool()
async def list_projects() -> str:
    """List all accessible projects."""
    cursor.execute("""
        SELECT id, name, created_at,
               (SELECT COUNT(*) FROM context_locks WHERE project_id = projects.id) as context_count
        FROM projects
        ORDER BY created_at DESC
    """)
    # Format output
```

### Future: Merging/Archiving
- **Merge:** Copy all contexts from project A → project B
- **Archive:** Soft-delete project (mark `archived = true`)
- **Restore:** Un-archive project
- **Export:** Download all project data as JSON

**Not needed for POC.**

---

## 5. Weekend POC Scope

### What's Achievable in 2 Days

**Day 1: Database & Core Tools**
- [x] Set up Postgres database (Supabase/Neon/Railway)
- [x] Migrate schema (add `project_id` everywhere)
- [x] Replace `get_db()` with Postgres connection
- [x] Update SQL syntax (`?` → `%s`, `AUTOINCREMENT` → `SERIAL`)
- [x] Test `lock_context()` and `recall_context()` with `project_id` parameter

**Day 2: Project Management & Testing**
- [x] Implement `create_project()`, `list_projects()`, `switch_project()`
- [x] Update all context tools to accept `project_id`
- [x] Manual testing with 2 projects
- [x] Document what works and what doesn't

**What to Skip:**
- ❌ SSE session management (use stateless for now)
- ❌ File tagging tools (defer to Phase 2)
- ❌ Multi-user support (single user POC)
- ❌ Backup/restore (use Postgres native backups)
- ❌ Migration tools (manual migration acceptable)

**Success Criteria:**
1. Can create a project in the cloud
2. Can lock/recall contexts for specific project
3. Can switch between projects
4. Memory persists after disconnecting

---

## 6. Open Questions for User Decision

### Q1: Database Hosting
**Options:**
- **Supabase** (recommended) - Free tier, managed Postgres, realtime features
- **Neon** - Serverless Postgres, generous free tier
- **Railway** - Simple deploy, pays per usage
- **Self-hosted** - Most control, more maintenance

**User decision needed:** Which hosting platform?

### Q2: Project Identification for POC
**Options:**
- **Explicit parameter:** Every tool takes `project_id="abc-123"`
- **Session state:** Call `switch_project("abc-123")` once, then it's implicit
- **Environment variable:** `CLAUDE_PROJECT_ID=abc-123` in MCP config

**User decision needed:** Which UX pattern for POC?

### Q3: File Tools Handling
**Options:**
- **Drop file tools** - Focus on context-only memory (simplest)
- **Keep local file tools** - Work only when connected from same machine (limited)
- **Defer to Phase 2** - Implement git-based references later

**User decision needed:** Include file tools in POC or defer?

### Q4: Session Management
**Options:**
- **Fully stateless** - No sessions, just project_id everywhere (weekend POC)
- **Simple session** - Track active project per MCP connection (extra work)
- **Defer sessions** - Add post-POC

**User decision needed:** Sessions in POC or defer?

### Q5: Migration Strategy
**Options:**
- **Fresh start** - New cloud DB, don't migrate existing local DBs
- **Manual migration** - One-time script to copy key contexts to cloud
- **Automated migration** - Tool to sync local → cloud (complex)

**User decision needed:** How to handle existing local data?

### Q6: Authentication (Future)
Not needed for POC, but consider:
- Single user only? (POC assumption)
- Multi-user planned? (changes project ownership model)

---

## 7. Recommended POC Architecture

### Minimal Cloud Migration (Weekend Scope)

```
┌─────────────────────────────────────────────────┐
│  Claude Desktop / MCP Client                    │
│  - Explicitly passes project_id to all tools    │
└──────────────────┬──────────────────────────────┘
                   │ MCP Protocol
┌──────────────────▼──────────────────────────────┐
│  Dementia MCP Server (Python)                   │
│  ┌────────────────────────────────────────────┐ │
│  │ Tools (modified):                          │ │
│  │ - create_project()     NEW                 │ │
│  │ - list_projects()      NEW                 │ │
│  │ - lock_context(project_id, ...)            │ │
│  │ - recall_context(project_id, ...)          │ │
│  │ - update_context(project_id, ...)          │ │
│  │ - All context tools accept project_id      │ │
│  └────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────┐ │
│  │ Connection Pool                            │ │
│  │ - psycopg2.pool.ThreadedConnectionPool     │ │
│  └────────────────────────────────────────────┘ │
└──────────────────┬──────────────────────────────┘
                   │ PostgreSQL Protocol
┌──────────────────▼──────────────────────────────┐
│  PostgreSQL (Supabase/Neon/Railway)             │
│  ┌────────────────────────────────────────────┐ │
│  │ projects                                   │ │
│  │ - id (UUID)                                │ │
│  │ - name                                     │ │
│  │ - created_at                               │ │
│  └────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────┐ │
│  │ context_locks (+ project_id FK)            │ │
│  │ memory_entries (+ project_id FK)           │ │
│  │ sessions (+ project_id FK)                 │ │
│  │ ... all tables with project_id ...         │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### Key Simplifications for POC:
1. **No SSE** - Stateless tool calls only
2. **No file tools** - Context memory only
3. **No sessions** - Direct project_id passing
4. **No multi-user** - Single owner
5. **No migration** - Fresh start

### What You Get:
✅ Cross-device project memory
✅ Multiple isolated projects
✅ All context tools working
✅ Portable across machines
✅ Foundation for full migration

---

## 8. Implementation Checklist (Weekend POC)

### Setup (30 minutes)
- [ ] Create Postgres database (Supabase free tier recommended)
- [ ] Note down connection credentials
- [ ] Add to environment variables

### Schema Migration (2 hours)
- [ ] Add `projects` table
- [ ] Add `project_id UUID` to all tables
- [ ] Update `UNIQUE` constraints
- [ ] Create indexes on `project_id`
- [ ] Replace SQLite types with Postgres types
- [ ] Test schema with sample inserts

### Code Changes (4 hours)
- [ ] Replace `sqlite3` with `psycopg2`
- [ ] Create connection pool in `get_db()`
- [ ] Update all `?` to `%s` in SQL queries
- [ ] Add `project_id` parameter to context tools
- [ ] Update `get_current_session_id()` logic
- [ ] Implement `create_project()`, `list_projects()`

### Testing (2 hours)
- [ ] Create 2 test projects
- [ ] Lock contexts in both projects
- [ ] Recall contexts from each project
- [ ] Verify isolation (contexts don't leak between projects)
- [ ] Test from different machine (if possible)

### Documentation (1 hour)
- [ ] Update README with cloud setup instructions
- [ ] Document project_id parameter for each tool
- [ ] Note limitations (no files, no sessions yet)
- [ ] Write migration guide for future enhancements

**Total:** ~9-10 hours → Realistic for a focused weekend.

---

## 9. Risk Assessment

### High Risk (Must Address)
- **Connection pool exhaustion** - Postgres has connection limits (mitigate: pool size tuning)
- **Query injection** - Parameterized queries required (already done)
- **Project ID confusion** - User passes wrong project_id (mitigate: list_projects helper)

### Medium Risk (Can Defer)
- **No authentication** - Anyone with credentials can access any project (POC acceptable)
- **No backups** - Rely on Postgres hosting backups (acceptable for POC)
- **Large contexts** - 50KB limit may not work well with Postgres TEXT (test in POC)

### Low Risk (Monitor)
- **Performance** - Cloud DB slower than local SQLite (likely acceptable latency)
- **Cost** - Free tiers should handle POC volume (monitor usage)

---

## Conclusion

**Current Architecture:** Filesystem-based project isolation, SQLite per-project, local-first.

**Target Architecture:** Cloud-hosted multi-project database, explicit project selection, cross-device portability.

**Recommended Approach:**
1. **Weekend POC:** Stateless, explicit project_id, context tools only
2. **Phase 2:** Add session management, SSE integration
3. **Phase 3:** File tools with git-based references, multi-user

**Critical Path for POC:**
- Postgres setup → Schema migration → Connection pool → Add project_id to tools → Test

**Go/No-Go Decision Points:**
- Schema migration successful? → Continue
- First lock/recall working? → Continue
- Cross-project isolation verified? → Ship POC
