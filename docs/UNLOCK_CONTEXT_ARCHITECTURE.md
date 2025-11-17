# UNLOCK_CONTEXT_ARCHITECTURE.md

> **Architecture Documentation for the `unlock_context` Function**
> Complete technical reference for context deletion with archival, version control, and safety mechanisms.

---

## Table of Contents

1. [Function Overview](#function-overview)
2. [Data Flow Diagram](#data-flow-diagram)
3. [Database Operations](#database-operations)
4. [Dependencies](#dependencies)
5. [Side Effects](#side-effects)
6. [Critical Behavior](#critical-behavior)
7. [Integration Points](#integration-points)
8. [Error Handling](#error-handling)
9. [Security Considerations](#security-considerations)
10. [Examples](#examples)

---

## 1. Function Overview

### Purpose and Responsibility

The `unlock_context` function is responsible for **safely removing locked context entries** from the persistent memory system while providing:

- **Archival backup** before deletion (for recovery)
- **Critical context protection** (requires force=True)
- **Version-selective deletion** (all/latest/specific)
- **Audit trail creation** for deleted contexts

**File Location:** `/home/user/claude-dementia/claude_mcp_hybrid_sessions.py` (lines 4089-4265)

### Function Signature

```python
async def unlock_context(
    topic: str,
    version: str = "all",
    force: bool = False,
    archive: bool = True,
    project: Optional[str] = None
) -> str:
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `topic` | `str` | Required | The label/name of the context lock to delete |
| `version` | `str` | `"all"` | Version selector: `"all"`, `"latest"`, or specific version (e.g., `"1.2"`) |
| `force` | `bool` | `False` | Required to delete critical (always_check) contexts |
| `archive` | `bool` | `True` | Whether to archive contexts before deletion (for recovery) |
| `project` | `Optional[str]` | `None` | Target project name (uses current project if not specified) |

### Return Value

**Type:** `str` (JSON-formatted or human-readable string)

**Success Response:**
```
✅ Deleted {count} version(s) of '{topic}'
   💾 Archived for recovery (query context_archives table)
   ⚠️  Critical context deleted (force=True was used)
```

**Error Response:**
```
❌ Context '{topic}' (version: {version}) not found
⚠️  Cannot delete critical (always_check) context '{topic}' without force=True
❌ Failed to archive context: {error}
❌ Failed to delete context: {error}
```

### Key Features

1. **Archival System**: Backs up contexts to `context_archives` table before deletion
2. **Force Delete Protection**: Critical contexts require explicit `force=True` flag
3. **Version Control**: Granular control over which versions to delete
4. **Audit Trail**: Creates memory entries tracking deletion actions
5. **Session Isolation**: Only deletes contexts within the current session

---

## 2. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     unlock_context() Entry                       │
│  Parameters: topic, version, force, archive, project            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: Project Selection Check                                │
│  ┌───────────────────────────────────────────────┐              │
│  │ _check_project_selection_required(project)   │              │
│  └───────────┬───────────────────────────────────┘              │
│              ├─── If error: Return error message                │
│              └─── If OK: Continue                               │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: Update Session Activity                                │
│  ┌───────────────────────────────────────────────┐              │
│  │ update_session_activity()                    │              │
│  │  - Updates sessions.last_active = now()      │              │
│  └───────────────────────────────────────────────┘              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: Get Database Connection                                │
│  ┌───────────────────────────────────────────────┐              │
│  │ _get_db_for_project(project)                 │              │
│  │  - Returns context manager with DB conn       │              │
│  │  - Connection automatically closed on exit    │              │
│  └───────────┬───────────────────────────────────┘              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: Get Session ID for Project                             │
│  ┌───────────────────────────────────────────────┐              │
│  │ _get_session_id_for_project(conn, project)   │              │
│  │  - Returns session_id for filtering           │              │
│  └───────────────────────────────────────────────┘              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5: Find Contexts to Delete                                │
│  ┌───────────────────────────────────────────────┐              │
│  │ SELECT * FROM context_locks WHERE...         │              │
│  │  ├─ version="all":    label=? AND session=?  │              │
│  │  ├─ version="latest": label=? AND session=?  │              │
│  │  │                     ORDER BY version DESC  │              │
│  │  │                     LIMIT 1                │              │
│  │  └─ version="X.Y":    label=? AND version=?  │              │
│  │                       AND session=?           │              │
│  └───────────┬───────────────────────────────────┘              │
│              ├─── If no contexts: Return error                  │
│              └─── If found: Continue                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 6: Check for Critical Contexts                            │
│  ┌───────────────────────────────────────────────┐              │
│  │ FOR EACH context:                            │              │
│  │   metadata = json.loads(ctx['metadata'])     │              │
│  │   IF metadata.priority == 'always_check':    │              │
│  │     has_critical = True                      │              │
│  └───────────┬───────────────────────────────────┘              │
│              │                                                   │
│              ▼                                                   │
│  ┌───────────────────────────────────────────────┐              │
│  │ IF has_critical AND NOT force:               │              │
│  │   Return error (require force=True)          │              │
│  └───────────┬───────────────────────────────────┘              │
│              └─── If force=True: Continue                       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 7: Archive Contexts (if archive=True)                     │
│  ┌───────────────────────────────────────────────┐              │
│  │ FOR EACH context:                            │              │
│  │   INSERT INTO context_archives (              │              │
│  │     original_id, session_id, label, version, │              │
│  │     content, preview, key_concepts, metadata,│              │
│  │     deleted_at, delete_reason                │              │
│  │   ) VALUES (...)                             │              │
│  └───────────┬───────────────────────────────────┘              │
│              ├─── If error: Return archive error                │
│              └─── If success: Continue                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 8: Delete Contexts from context_locks                     │
│  ┌───────────────────────────────────────────────┐              │
│  │ DELETE FROM context_locks WHERE...           │              │
│  │  ├─ version="all":    label=? AND session=?  │              │
│  │  ├─ version="latest": id=?                   │              │
│  │  └─ version="X.Y":    label=? AND version=?  │              │
│  │                       AND session=?           │              │
│  └───────────┬───────────────────────────────────┘              │
│              ├─── If error: Return delete error                 │
│              └─── If success: Continue                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 9: Create Audit Trail Entry                               │
│  ┌───────────────────────────────────────────────┐              │
│  │ audit_message = "Deleted {version} of        │              │
│  │                  context '{topic}' [flags]"  │              │
│  │                                               │              │
│  │ INSERT INTO memory_entries (                 │              │
│  │   category='progress',                       │              │
│  │   content=audit_message,                     │              │
│  │   timestamp=now,                             │              │
│  │   session_id=session_id                      │              │
│  │ )                                            │              │
│  └───────────────────────────────────────────────┘              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 10: Commit Transaction                                    │
│  ┌───────────────────────────────────────────────┐              │
│  │ conn.commit()                                │              │
│  └───────────────────────────────────────────────┘              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 11: Build Success Response                                │
│  ┌───────────────────────────────────────────────┐              │
│  │ result = "✅ Deleted {version} of '{topic}'" │              │
│  │ IF archive: += "💾 Archived for recovery"    │              │
│  │ IF critical: += "⚠️ Critical context deleted"│              │
│  │ RETURN result                                │              │
│  └───────────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Database Operations

### Tables Involved

1. **`context_locks`** - Primary storage for locked contexts
2. **`context_archives`** - Backup storage for deleted contexts
3. **`memory_entries`** - Audit trail and session history
4. **`sessions`** - Session activity tracking (via `update_session_activity()`)

### Table Schema

#### context_locks
```sql
CREATE TABLE context_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    label TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0',
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    lock_source TEXT DEFAULT 'user',
    metadata TEXT,                    -- JSON with priority, importance, etc.
    preview TEXT,
    key_concepts TEXT,
    last_accessed TIMESTAMP,
    UNIQUE(session_id, label, version)
);
```

#### context_archives
```sql
CREATE TABLE context_archives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_id INTEGER NOT NULL,     -- FK to original context_locks.id
    session_id TEXT NOT NULL,
    label TEXT NOT NULL,
    version TEXT NOT NULL,
    content TEXT NOT NULL,
    preview TEXT,
    key_concepts TEXT,
    metadata TEXT,                    -- Preserved JSON metadata
    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delete_reason TEXT
);
```

#### memory_entries
```sql
CREATE TABLE memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    category TEXT NOT NULL,           -- 'progress' for audit trail
    content TEXT NOT NULL,
    timestamp REAL NOT NULL,
    -- ... other fields
);
```

### SQL Queries Executed

#### Query 1: Find Contexts to Delete (version="all")
```sql
SELECT * FROM context_locks
WHERE label = ? AND session_id = ?
```
**Purpose:** Retrieve all versions of a context for deletion
**Parameters:** `(topic, session_id)`
**Returns:** All matching context rows

---

#### Query 2: Find Contexts to Delete (version="latest")
```sql
SELECT * FROM context_locks
WHERE label = ? AND session_id = ?
ORDER BY version DESC
LIMIT 1
```
**Purpose:** Retrieve only the most recent version
**Parameters:** `(topic, session_id)`
**Returns:** Single row with highest version number

---

#### Query 3: Find Contexts to Delete (version=specific)
```sql
SELECT * FROM context_locks
WHERE label = ? AND version = ? AND session_id = ?
```
**Purpose:** Retrieve a specific version of a context
**Parameters:** `(topic, version, session_id)`
**Returns:** Single row matching exact version

---

#### Query 4: Archive Context
```sql
INSERT INTO context_archives
(original_id, session_id, label, version, content, preview,
 key_concepts, metadata, deleted_at, delete_reason)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```
**Purpose:** Backup context before deletion
**Parameters:** `(ctx['id'], ctx['session_id'], ctx['label'], ctx['version'], ctx['content'], ctx['preview'], ctx['key_concepts'], ctx['metadata'], time.time(), f"Deleted {version} version(s)")`
**Side Effect:** Creates archive row for recovery

---

#### Query 5: Delete Contexts (version="all")
```sql
DELETE FROM context_locks
WHERE label = ? AND session_id = ?
```
**Purpose:** Remove all versions of a context
**Parameters:** `(topic, session_id)`
**Side Effect:** Permanently removes rows from context_locks

---

#### Query 6: Delete Contexts (version="latest")
```sql
DELETE FROM context_locks
WHERE id = ?
```
**Purpose:** Remove only the latest version
**Parameters:** `(contexts[0]['id'],)`
**Side Effect:** Removes single row by primary key

---

#### Query 7: Delete Contexts (version=specific)
```sql
DELETE FROM context_locks
WHERE label = ? AND version = ? AND session_id = ?
```
**Purpose:** Remove specific version
**Parameters:** `(topic, version, session_id)`
**Side Effect:** Removes matching version row

---

#### Query 8: Create Audit Trail
```sql
INSERT INTO memory_entries (category, content, timestamp, session_id)
VALUES ('progress', ?, ?, ?)
```
**Purpose:** Record deletion action in audit trail
**Parameters:** `(audit_message, current_time, session_id)`
**Example audit_message:** `"Deleted 3 version(s) of context 'api_spec' [CRITICAL] (archived for recovery)"`

---

#### Query 9: Update Session Activity (via helper)
```sql
UPDATE sessions
SET last_active = ?
WHERE id = ?
```
**Purpose:** Mark session as recently active
**Parameters:** `(time.time(), session_id)`
**Location:** Called via `update_session_activity()` helper

---

### Transaction Boundaries

```
Transaction Start (implicit with context manager)
│
├─ [Read Operations - No transaction required]
│  ├─ SELECT contexts to delete
│  └─ Check critical contexts
│
├─ [Write Operations - Single transaction]
│  ├─ INSERT INTO context_archives (for each context)
│  ├─ DELETE FROM context_locks
│  └─ INSERT INTO memory_entries (audit trail)
│
└─ conn.commit() ← Transaction Commit Point
```

**Note:** If archive fails, the entire transaction is rolled back (no deletion occurs).

---

## 4. Dependencies

### Global Functions

1. **`_check_project_selection_required(project)`**
   - **Purpose:** Validates project parameter, triggers handover loading
   - **Returns:** Error string if project selection required, None otherwise
   - **Location:** Line 329
   - **Side Effects:** Auto-loads handover on first call

2. **`update_session_activity()`**
   - **Purpose:** Updates sessions.last_active timestamp
   - **Returns:** None
   - **Location:** Line 836
   - **Side Effects:** Database UPDATE to sessions table

3. **`_get_db_for_project(project)`**
   - **Purpose:** Returns database connection for target project
   - **Returns:** Context manager wrapping database connection
   - **Location:** Line 607
   - **Side Effects:** May create new database adapter (cached)

4. **`_get_session_id_for_project(conn, project)`**
   - **Purpose:** Gets most recent session ID for project
   - **Returns:** Session ID string
   - **Location:** Line 799
   - **Side Effects:** May create new session if none exists

### Global Variables

1. **`_session_store`** - MCPSessionStore instance for session management
2. **`_local_session_id`** - Current session ID for this MCP connection

### Standard Library Dependencies

```python
import time           # For timestamps (deleted_at, current_time)
import json           # For parsing metadata JSON
from typing import Optional  # For type hints
```

### External Dependencies

- **Database Driver:** `sqlite3` or `psycopg2` (via postgres_adapter)
- **MCP SDK:** For async function decoration

### Utility Functions (Could Be Used)

**Currently NOT used but could improve the function:**

- **`generate_embedding(text)`** - Could embed deleted context for semantic archive search
- **`generate_summary(text)`** - Could summarize deletion reason for audit trail
- **`hash_content(content)`** - Could verify archive integrity

---

## 5. Side Effects

### Database Side Effects

1. **context_locks Table**
   - **Effect:** Rows DELETED (1 to N rows depending on version parameter)
   - **Reversibility:** Irreversible unless archived
   - **Impact:** Context no longer available via `recall_context()`

2. **context_archives Table**
   - **Effect:** Rows INSERTED (equal to number deleted)
   - **Reversibility:** Permanent records (no automatic cleanup)
   - **Impact:** Growing archive table over time

3. **memory_entries Table**
   - **Effect:** 1 audit row INSERTED per unlock_context call
   - **Reversibility:** Permanent audit trail
   - **Impact:** Searchable history of deletions

4. **sessions Table** (via `update_session_activity()`)
   - **Effect:** last_active timestamp UPDATED
   - **Reversibility:** Overwrites previous timestamp
   - **Impact:** Affects session cleanup/expiry logic

### File System Side Effects

**None.** All operations are database-only.

### Network Side Effects

**None.** No external API calls.

### State Side Effects

1. **Session State**
   - **Effect:** Session marked as active (prevents cleanup)
   - **Duration:** Until session expires

2. **Cache State** (via `_get_db_for_project`)
   - **Effect:** May create cached database adapter
   - **Duration:** Process lifetime

---

## 6. Critical Behavior

### Force Delete Protection

**Problem:** Accidental deletion of critical contexts that contain important rules.

**Solution:**
```python
# 1. Check metadata for priority='always_check'
for ctx in contexts:
    metadata = json.loads(ctx['metadata']) if ctx['metadata'] else {}
    if metadata.get('priority') == 'always_check':
        has_critical = True
        break

# 2. Block deletion unless force=True
if has_critical and not force:
    return "⚠️  Cannot delete critical (always_check) context without force=True"
```

**Example Critical Context:**
```json
{
  "label": "security_rules",
  "metadata": {
    "priority": "always_check",
    "importance": "critical"
  },
  "content": "ALWAYS check authentication before database access"
}
```

**User Experience:**
```python
# Without force - BLOCKED
unlock_context("security_rules")
# Returns: ⚠️  Cannot delete critical (always_check) context...

# With force - ALLOWED
unlock_context("security_rules", force=True)
# Returns: ✅ Deleted 1 version(s) of 'security_rules'
#          ⚠️  Critical context deleted (force=True was used)
```

---

### Version Filtering Logic

**Three Modes:**

#### Mode 1: Delete All Versions (version="all")
```sql
SELECT * FROM context_locks
WHERE label = 'api_spec' AND session_id = 'proj_12345'
-- Returns: api_spec v1.0, v1.1, v1.2, v2.0

DELETE FROM context_locks
WHERE label = 'api_spec' AND session_id = 'proj_12345'
-- Deletes: All 4 versions
```

#### Mode 2: Delete Latest Version Only (version="latest")
```sql
SELECT * FROM context_locks
WHERE label = 'api_spec' AND session_id = 'proj_12345'
ORDER BY version DESC LIMIT 1
-- Returns: api_spec v2.0 (highest version)

DELETE FROM context_locks WHERE id = ?
-- Deletes: Only v2.0 (keeps v1.0, v1.1, v1.2)
```

#### Mode 3: Delete Specific Version (version="1.1")
```sql
SELECT * FROM context_locks
WHERE label = 'api_spec' AND version = '1.1' AND session_id = 'proj_12345'
-- Returns: api_spec v1.1 only

DELETE FROM context_locks
WHERE label = 'api_spec' AND version = '1.1' AND session_id = 'proj_12345'
-- Deletes: Only v1.1 (keeps v1.0, v1.2, v2.0)
```

**Version Comparison:**
- Uses string comparison (not semantic versioning)
- `"2.0"` > `"1.9"` (lexicographic order)
- `"1.10"` < `"1.9"` (lexicographic limitation)

**Recommendation:** Use semantic versioning format `"major.minor.patch"` with zero-padding for proper sorting.

---

### Archive vs No-Archive Behavior

#### With Archive (archive=True, default)

```python
unlock_context("api_spec", version="all", archive=True)
```

**Process:**
1. SELECT contexts to delete
2. **INSERT each into context_archives**
3. DELETE from context_locks
4. INSERT audit trail
5. COMMIT

**Result:**
- Contexts removed from active memory
- Full backup in context_archives table
- Recovery possible via manual SQL query

**Recovery Example:**
```sql
-- View archived contexts
SELECT * FROM context_archives WHERE label = 'api_spec';

-- Restore archived context (manual)
INSERT INTO context_locks (session_id, label, version, content, ...)
SELECT session_id, label, version, content, ...
FROM context_archives
WHERE id = 123;
```

---

#### Without Archive (archive=False)

```python
unlock_context("api_spec", version="all", archive=False)
```

**Process:**
1. SELECT contexts to delete
2. **Skip archive step**
3. DELETE from context_locks
4. INSERT audit trail
5. COMMIT

**Result:**
- Contexts permanently deleted
- No backup created
- Recovery impossible

**Use Cases:**
- Deleting sensitive data (compliance)
- Cleaning up test/temporary contexts
- Reducing archive table growth

---

### Critical Context Protection Workflow

```
User calls unlock_context("security_rules")
│
├─ Query: SELECT * FROM context_locks WHERE label='security_rules'
│  Returns: [{"metadata": "{\"priority\": \"always_check\"}"}]
│
├─ Parse metadata: json.loads(ctx['metadata'])
│  Result: {"priority": "always_check"}
│
├─ Check priority: metadata.get('priority') == 'always_check'
│  Result: True → has_critical = True
│
├─ Evaluate: has_critical AND NOT force
│  Result: True AND NOT False = True (BLOCKED)
│
└─ Return: ⚠️  Cannot delete critical context without force=True
```

**Override Path:**
```
User calls unlock_context("security_rules", force=True)
│
├─ has_critical = True (same as above)
│
├─ Evaluate: has_critical AND NOT force
│  Result: True AND NOT True = False (ALLOWED)
│
├─ Continue with archive + deletion
│
└─ Return: ✅ Deleted... ⚠️ Critical context deleted (force=True was used)
```

---

## 7. Integration Points

### How Users Call This Function

**Via MCP Tool:**
```python
# Claude Desktop / MCP Client
{
  "tool": "unlock_context",
  "arguments": {
    "topic": "old_api_spec",
    "version": "all",
    "force": false,
    "archive": true,
    "project": "my-project"
  }
}
```

**Async API:**
```python
result = await unlock_context(
    topic="deployment_process",
    version="latest",
    force=False,
    archive=True,
    project="innkeeper"
)
```

---

### Dependent Tools

#### 1. recall_context()
**Relationship:** Users should recall before unlocking

```python
# Best practice workflow
result = await recall_context("old_api_spec", preview_only=True)
# Review content...
if "outdated" in result:
    await unlock_context("old_api_spec", version="all")
```

**Impact:** After unlock_context, recall_context returns "not found"

---

#### 2. lock_context()
**Relationship:** Creates contexts that unlock_context deletes

```python
# Lock workflow
await lock_context(content="...", topic="api_spec", version="1.0")
# ... later ...
await unlock_context("api_spec", version="1.0")
```

**Impact:** Deletion breaks lock/unlock symmetry (unless archived)

---

#### 3. list_context_locks()
**Relationship:** Shows available contexts to unlock

```python
# Discovery workflow
locks = await list_context_locks()
# Returns: ["api_spec v1.0", "api_spec v1.1", "deployment v2.0"]

await unlock_context("api_spec", version="1.0")

locks = await list_context_locks()
# Returns: ["api_spec v1.1", "deployment v2.0"]
```

**Impact:** Deleted contexts removed from list

---

#### 4. update_context()
**Relationship:** Updates contexts that may later be unlocked

```python
# Update workflow
await update_context("api_spec", new_content="...", version="2.0")
# Creates new version 2.0

await unlock_context("api_spec", version="latest")
# Deletes version 2.0 (keeps older versions)
```

---

### What Happens After Context Deleted

1. **Immediate Effects:**
   - `recall_context(topic)` returns "not found"
   - `list_context_locks()` excludes deleted contexts
   - Active context engine stops suggesting deleted contexts

2. **Audit Trail:**
   - Deletion logged in memory_entries
   - Searchable via `search_memory(category='progress')`

3. **Archive (if enabled):**
   - Context preserved in context_archives
   - Recoverable via manual SQL or future tool

4. **Session Impact:**
   - Session remains active (last_active updated)
   - No effect on other session contexts

---

## 8. Error Handling

### Error Scenarios

#### Scenario 1: Context Not Found
```python
unlock_context("nonexistent_topic")
# Returns: ❌ Context 'nonexistent_topic' (version: all) not found
```

**Cause:** No matching context_locks rows
**Recovery:** Use `list_context_locks()` to find available contexts

---

#### Scenario 2: Critical Context Without Force
```python
unlock_context("security_rules")  # Has priority='always_check'
# Returns: ⚠️  Cannot delete critical (always_check) context 'security_rules' without force=True
```

**Cause:** Critical context protection triggered
**Recovery:** Add `force=True` parameter if intentional

---

#### Scenario 3: Archive Failure
```python
# Database constraint violation during archive
unlock_context("api_spec")
# Returns: ❌ Failed to archive context: UNIQUE constraint failed
```

**Cause:** Archive insertion error (duplicate, constraint, etc.)
**Recovery:** Check context_archives table for conflicts
**Transaction:** Entire operation rolled back (no deletion occurs)

---

#### Scenario 4: Delete Failure
```python
# Database error during deletion
unlock_context("api_spec")
# Returns: ❌ Failed to delete context: database is locked
```

**Cause:** Database lock, constraint violation, etc.
**Recovery:** Retry after resolving lock, check database integrity
**Transaction:** Rolled back if in transaction block

---

#### Scenario 5: Project Selection Required
```python
unlock_context("api_spec")  # When session has project='__PENDING__'
# Returns: {"error": "project_selection_required", "available_projects": [...]}
```

**Cause:** Multi-project environment requires explicit project selection
**Recovery:** Specify `project` parameter

---

### Error Return Format

**Success:**
```python
return "✅ Deleted 3 version(s) of 'api_spec'\n   💾 Archived for recovery..."
```

**Error:**
```python
return "❌ Context 'topic' (version: all) not found"
return "⚠️  Cannot delete critical context without force=True"
return "❌ Failed to archive context: {str(e)}"
return "❌ Failed to delete context: {str(e)}"
```

**Project Selection Error (JSON):**
```python
return json.dumps({
    "error": "project_selection_required",
    "available_projects": ["project1", "project2"]
})
```

---

## 9. Security Considerations

### SQL Injection Protection

**All queries use parameterized statements:**

```python
# ✅ SAFE - Parameterized query
conn.execute("""
    SELECT * FROM context_locks WHERE label = ? AND session_id = ?
""", (topic, session_id))

# ❌ UNSAFE - String interpolation (NOT USED)
# conn.execute(f"SELECT * FROM context_locks WHERE label = '{topic}'")
```

**Validation:** SQLite/PostgreSQL parameterization prevents injection attacks.

---

### Session Isolation

**Only deletes contexts within current session:**

```python
WHERE session_id = ?  # Always includes session_id filter
```

**Protection:** Users cannot delete other users' contexts
**Limitation:** Same user across different sessions = different session_id

---

### Critical Context Protection

**Two-factor deletion for critical contexts:**

```python
if metadata.get('priority') == 'always_check' and not force:
    return error  # Requires explicit force=True
```

**Protection:** Prevents accidental deletion of security rules, compliance policies
**Override:** Intentional `force=True` bypasses (logged in audit trail)

---

### Archive as Safety Net

**Default behavior creates backup:**

```python
archive: bool = True  # Default parameter
```

**Protection:** Accidental deletions are recoverable
**Limitation:** Manual recovery process (no automatic undo)

---

### Audit Trail

**Every deletion logged:**

```python
INSERT INTO memory_entries (category='progress', content=audit_message, ...)
```

**Protection:** Forensic analysis of who deleted what and when
**Content:** Includes critical flag, archive status, version details

---

## 10. Examples

### Example 1: Delete All Versions (Safe)

```python
# Check what exists
list_context_locks()
# Returns: ["api_spec v1.0", "api_spec v1.1", "api_spec v2.0"]

# Delete all versions
unlock_context("api_spec", version="all")
# Returns:
# ✅ Deleted 3 version(s) of 'api_spec'
#    💾 Archived for recovery (query context_archives table)

# Verify deletion
list_context_locks()
# Returns: [] (api_spec completely removed)
```

---

### Example 2: Delete Latest Version Only

```python
# Situation: api_spec has versions 1.0, 1.1, 2.0
unlock_context("api_spec", version="latest")
# Returns:
# ✅ Deleted 1 version(s) of 'api_spec'
#    💾 Archived for recovery

# Result: Versions 1.0 and 1.1 still exist, only 2.0 deleted
```

---

### Example 3: Delete Specific Version

```python
# Remove buggy v1.1, keep v1.0 and v2.0
unlock_context("api_spec", version="1.1")
# Returns:
# ✅ Deleted version 1.1 of 'api_spec'
#    💾 Archived for recovery
```

---

### Example 4: Force Delete Critical Context

```python
# Attempt 1: Blocked
unlock_context("security_rules")
# Returns:
# ⚠️  Cannot delete critical (always_check) context 'security_rules' without force=True
#    This context contains important rules. Use force=True if you're sure.

# Attempt 2: Forced
unlock_context("security_rules", force=True)
# Returns:
# ✅ Deleted 1 version(s) of 'security_rules'
#    💾 Archived for recovery (query context_archives table)
#    ⚠️  Critical context deleted (force=True was used)
```

---

### Example 5: Delete Without Archive (Permanent)

```python
# Permanent deletion (no recovery)
unlock_context("temp_test_context", archive=False)
# Returns:
# ✅ Deleted 1 version(s) of 'temp_test_context'
# (No archive message)
```

---

### Example 6: Multi-Project Deletion

```python
# Delete context in specific project
unlock_context("deployment_config", project="innkeeper")
# Returns:
# ✅ Deleted 1 version(s) of 'deployment_config'
#    💾 Archived for recovery

# Contexts in other projects unaffected
```

---

### Example 7: Recovery from Archive

```sql
-- View archived contexts (manual SQL)
SELECT id, label, version, deleted_at, delete_reason
FROM context_archives
WHERE label = 'api_spec'
ORDER BY deleted_at DESC;

-- Results:
-- id  | label    | version | deleted_at | delete_reason
-- 123 | api_spec | 2.0     | 1637012345 | Deleted latest version(s)
-- 124 | api_spec | 1.1     | 1637012345 | Deleted all version(s)
-- 125 | api_spec | 1.0     | 1637012345 | Deleted all version(s)

-- Restore specific version (manual)
INSERT INTO context_locks (session_id, label, version, content, content_hash,
                           locked_at, metadata, preview, key_concepts)
SELECT session_id, label, version, content,
       hex(randomblob(16)),  -- New hash
       CURRENT_TIMESTAMP,
       metadata, preview, key_concepts
FROM context_archives
WHERE id = 123;  -- Restore v2.0
```

---

## Conclusion

The `unlock_context` function provides a **robust, safe deletion mechanism** with multiple layers of protection:

1. **Archival backup** for recovery
2. **Critical context protection** requiring explicit force flag
3. **Version-selective deletion** for granular control
4. **Audit trail** for forensic analysis
5. **Session isolation** for security
6. **Transactional integrity** preventing partial failures

**Key Design Principles:**
- **Safety first:** Archive by default, force flag for critical contexts
- **Transparency:** Detailed return messages, comprehensive audit trail
- **Flexibility:** Three version modes (all/latest/specific)
- **Recoverability:** Archive table preserves deleted contexts

**Best Practices:**
1. Always review context with `recall_context()` before deletion
2. Use `version="latest"` to preserve history when updating
3. Keep `archive=True` unless compliance requires permanent deletion
4. Use `force=True` cautiously on critical contexts
5. Monitor archive table growth and implement cleanup policy

**Future Enhancements:**
- Automated unarchive_context() tool
- Archive retention policies (auto-cleanup after N days)
- Batch unlock operations
- Soft delete with expiration (mark as deleted, purge later)
- Archive search capabilities (semantic search in deleted contexts)

---

**Document Version:** 1.0
**Last Updated:** 2025-11-17
**Function Version:** claude_mcp_hybrid_sessions.py (lines 4089-4265)
