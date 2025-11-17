# Refactoring Review Guide
**Interactive Review Session**

## Overview

We'll refactor **15 critical functions** (200-766 lines each) into smaller, maintainable units.

**Key Questions to Discuss:**
1. Do the extraction strategies make sense?
2. Are the new function names clear?
3. Should we adjust the granularity?
4. Are there dependencies we need to consider?

---

## Refactoring Pattern Examples

### Example 1: `switch_project` (205 lines) - SMALLEST P0

**Current Structure (lines 1995-2106):**
```python
async def switch_project(name: str) -> str:
    # Line 2022: Sanitize project name
    safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())

    # Line 2026-2048: Update session store
    if not _session_store or not _local_session_id:
        return error_json
    updated = _session_store.update_session_project(...)

    # Line 2057-2076: Check if project exists + get stats
    conn = psycopg2.connect(config.database_url)
    cur.execute("SELECT schema_name FROM information_schema.schemata...")
    cur.execute(f'SELECT COUNT(*) FROM "{safe_name}".sessions')
    cur.execute(f'SELECT COUNT(*) FROM "{safe_name}".context_locks')

    # Line 2078-2100: Build response JSON
    return json.dumps({"success": True, "stats": {...}})
```

**Issues:**
- ❌ Mixes validation, database ops, and formatting
- ❌ Direct database connection management
- ❌ Duplicated error handling
- ❌ Hard to test individual parts

**Proposed Refactoring:**
```python
# 1. Validation helper (~15 lines)
def _sanitize_project_name(name: str) -> str:
    """Sanitize project name for use as schema name."""
    safe = re.sub(r'[^a-z0-9]', '_', name.lower())
    return re.sub(r'_+', '_', safe).strip('_')[:32]

# 2. Session update helper (~25 lines)
def _update_session_project(session_id: str, project: str) -> tuple[bool, Optional[str]]:
    """Update session's active project. Returns (success, error_msg)."""
    if not _session_store or not session_id:
        return False, "No active session"

    try:
        updated = _session_store.update_session_project(session_id, project)
        if not updated:
            return False, f"Session {session_id[:8]} not found"
        _active_projects[session_id] = project  # Cache update
        return True, None
    except Exception as e:
        return False, f"Failed to update session: {e}"

# 3. Project stats fetcher (~30 lines)
def _fetch_project_stats(conn, schema: str) -> Optional[dict]:
    """Fetch project statistics. Returns None if project doesn't exist."""
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Check existence
    cur.execute("""
        SELECT schema_name FROM information_schema.schemata
        WHERE schema_name = %s
    """, (schema,))

    if not cur.fetchone():
        return None

    # Get stats
    cur.execute(f'SELECT COUNT(*) as count FROM "{schema}".sessions')
    sessions = cur.fetchone()['count']

    cur.execute(f'SELECT COUNT(*) as count FROM "{schema}".context_locks')
    contexts = cur.fetchone()['count']

    return {"sessions": sessions, "contexts": contexts}

# 4. Response builder (~20 lines)
def _build_switch_response(name: str, schema: str, stats: Optional[dict]) -> dict:
    """Build switch_project response JSON."""
    if stats:
        return {
            "success": True,
            "message": f"✅ Switched to project '{name}'",
            "project": name,
            "schema": schema,
            "exists": True,
            "stats": stats,
            "note": "All memory operations will now use this project"
        }
    else:
        return {
            "success": True,
            "message": f"✅ Switched to project '{name}' (will be created on first use)",
            "project": name,
            "schema": schema,
            "exists": False,
            "note": "Project schema will be created automatically"
        }

# 5. Main orchestrator (~40 lines)
async def switch_project(name: str) -> str:
    """
    Switch to a different project for this conversation.

    Returns: JSON with switch status and project info
    """
    import json

    try:
        # Step 1: Validate and sanitize
        safe_name = _sanitize_project_name(name)

        # Step 2: Update session
        success, error = _update_session_project(_local_session_id, safe_name)
        if not success:
            return json.dumps({"success": False, "error": error})

        # Step 3: Fetch project stats
        conn = psycopg2.connect(config.database_url)
        try:
            stats = _fetch_project_stats(conn, safe_name)
        finally:
            conn.close()

        # Step 4: Build response
        response = _build_switch_response(name, safe_name, stats)
        return json.dumps(response)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
```

**Benefits:**
- ✅ Each function <40 lines
- ✅ Single responsibility per function
- ✅ Easy to test individually
- ✅ Clear error propagation
- ✅ Reusable components

**Questions:**
1. Should `_fetch_project_stats` be async?
2. Should we extract connection management to a context manager?
3. Is the granularity right, or too fine?

---

### Example 2: `context_dashboard` (766 lines) - LARGEST P0

**Current Structure (lines 6503-7268):**
```python
async def context_dashboard(project: Optional[str] = None) -> str:
    # Line 6526-6555: Query priority statistics
    stats_query = "SELECT priority, COUNT(*), SUM(LENGTH(content))..."
    priority_stats = {...}

    # Line 6558-6571: Query most/least accessed
    most_accessed = conn.execute("SELECT label, access_count...")
    least_accessed = conn.execute("SELECT label, access_count...")

    # Line 6576-6582: Query stale contexts
    stale_contexts = conn.execute("SELECT label WHERE last_accessed < ?...")

    # Line 6585-6595: Query version statistics
    version_stats = conn.execute("SELECT label, COUNT(*) as version_count...")

    # Line 6598-6750: Build 150+ line formatted text output
    summary_text = f"""
    📊 Context Library Dashboard
    ━━━━━━━━━━━━━━━━━━━━━━━━━━
    Total Contexts: {total_contexts}
    ...
    (150 lines of string formatting)
    """

    # Line 6751-7268: Build 500+ line JSON structure
    return json.dumps({
        "overview": {...},
        "by_priority": {...},
        "access_patterns": {...},
        "staleness": {...},
        "versions": {...},
        "recommendations": [...],
        ...
    })
```

**Issues:**
- ❌ 766 lines - impossible to understand at a glance
- ❌ Mixes 5+ database queries
- ❌ Mixes text and JSON formatting
- ❌ Duplicate logic for formatting different stats
- ❌ Hard to test or modify individual sections

**Proposed Refactoring:**

```python
# 1. Data fetchers (~30 lines each)

def _fetch_priority_stats(conn) -> dict:
    """Fetch context counts and sizes by priority."""
    query = """
        SELECT
            (metadata::json)->>'priority' as priority,
            COUNT(*) as count,
            SUM(LENGTH(content)) as total_size,
            AVG(LENGTH(content)) as avg_size
        FROM context_locks
        GROUP BY priority
    """
    cursor = conn.execute(query)

    stats = {}
    for row in cursor.fetchall():
        priority = row['priority'] or 'reference'
        stats[priority] = {
            'count': row['count'],
            'total_size': row['total_size'],
            'avg_size': int(row['avg_size'])
        }

    return stats

def _fetch_access_patterns(conn) -> dict:
    """Fetch most/least accessed contexts."""
    most = conn.execute("""
        SELECT label, access_count, last_accessed
        FROM context_locks
        ORDER BY access_count DESC
        LIMIT 5
    """).fetchall()

    least = conn.execute("""
        SELECT label, access_count, last_accessed
        FROM context_locks
        WHERE access_count > 0
        ORDER BY access_count ASC
        LIMIT 5
    """).fetchall()

    return {"most_accessed": most, "least_accessed": least}

def _fetch_stale_contexts(conn, days: int = 30) -> list:
    """Fetch contexts not accessed in N days."""
    import time
    cutoff = time.time() - (days * 24 * 3600)

    return conn.execute("""
        SELECT label, last_accessed, access_count
        FROM context_locks
        WHERE (last_accessed < ? OR last_accessed IS NULL)
        ORDER BY last_accessed ASC
        LIMIT 10
    """, (cutoff,)).fetchall()

def _fetch_version_stats(conn) -> list:
    """Fetch contexts with multiple versions."""
    return conn.execute("""
        SELECT
            label,
            COUNT(*) as version_count,
            MAX(version) as latest_version
        FROM context_locks
        GROUP BY label
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 5
    """).fetchall()

# 2. Formatters (~40 lines each)

def _format_priority_section(priority_stats: dict, total: int, total_size: int) -> str:
    """Format the priority breakdown section."""
    lines = [
        "📊 By Priority:",
        "━━━━━━━━━━━━━━"
    ]

    for priority in ['always_check', 'important', 'reference']:
        if priority in priority_stats:
            stats = priority_stats[priority]
            pct = (stats['count'] / total * 100) if total > 0 else 0
            lines.append(
                f"  {priority:15s}: {stats['count']:3d} contexts "
                f"({pct:5.1f}%) | {stats['total_size']:,} bytes"
            )

    return "\n".join(lines)

def _format_access_patterns_section(patterns: dict) -> str:
    """Format the access patterns section."""
    lines = ["", "🔥 Most Accessed:", "━━━━━━━━━━━━━━━"]

    for ctx in patterns['most_accessed']:
        lines.append(
            f"  {ctx['label']:30s} | {ctx['access_count']:3d} accesses"
        )

    lines.extend(["", "❄️  Least Accessed:", "━━━━━━━━━━━━━━━━"])

    for ctx in patterns['least_accessed']:
        lines.append(
            f"  {ctx['label']:30s} | {ctx['access_count']:3d} accesses"
        )

    return "\n".join(lines)

def _format_staleness_section(stale: list) -> str:
    """Format the staleness warnings section."""
    if not stale:
        return "\n✅ No stale contexts (all accessed within 30 days)"

    lines = ["", f"⚠️  Stale Contexts ({len(stale)}):", "━━━━━━━━━━━━━━━━━━━"]

    for ctx in stale:
        days = _days_since_access(ctx['last_accessed'])
        lines.append(
            f"  {ctx['label']:30s} | {days:3d} days old"
        )

    return "\n".join(lines)

# 3. JSON builder (~60 lines)

def _build_dashboard_json(
    priority_stats: dict,
    access_patterns: dict,
    stale: list,
    versions: list,
    total_contexts: int,
    total_size: int
) -> dict:
    """Build the complete dashboard JSON structure."""
    return {
        "overview": {
            "total_contexts": total_contexts,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2)
        },
        "by_priority": priority_stats,
        "access_patterns": {
            "most_accessed": [_serialize_context(c) for c in access_patterns['most_accessed']],
            "least_accessed": [_serialize_context(c) for c in access_patterns['least_accessed']]
        },
        "staleness": {
            "count": len(stale),
            "contexts": [_serialize_stale_context(c) for c in stale]
        },
        "versions": {
            "count": len(versions),
            "multi_version_contexts": [_serialize_version(v) for v in versions]
        },
        "recommendations": _generate_recommendations(
            total_contexts, stale, priority_stats
        )
    }

# 4. Main orchestrator (~50 lines)

async def context_dashboard(project: Optional[str] = None) -> str:
    """
    Get comprehensive overview of all contexts with statistics and insights.

    Returns: JSON with comprehensive context statistics
    """
    with _get_db_for_project(project) as conn:
        # Fetch all data
        priority_stats = _fetch_priority_stats(conn)
        access_patterns = _fetch_access_patterns(conn)
        stale = _fetch_stale_contexts(conn, days=30)
        versions = _fetch_version_stats(conn)

        # Calculate totals
        total_contexts = sum(s['count'] for s in priority_stats.values())
        total_size = sum(s['total_size'] for s in priority_stats.values())

    # Build output sections
    text_sections = [
        "📊 Context Library Dashboard",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Total Contexts: {total_contexts}",
        f"Total Storage: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)",
        "",
        _format_priority_section(priority_stats, total_contexts, total_size),
        _format_access_patterns_section(access_patterns),
        _format_staleness_section(stale)
    ]

    # Build JSON response
    dashboard_json = _build_dashboard_json(
        priority_stats, access_patterns, stale, versions,
        total_contexts, total_size
    )

    dashboard_json["summary_text"] = "\n".join(text_sections)

    return json.dumps(dashboard_json)
```

**Benefits:**
- ✅ 766 lines → 11 functions (~60 lines each)
- ✅ Each query isolated and testable
- ✅ Formatters reusable for other dashboards
- ✅ Easy to add new stats sections
- ✅ Clear data flow: fetch → process → format

**Questions:**
1. Should we extract queries to SQL files?
2. Is 11 functions the right granularity, or should we combine formatters?
3. Should `_build_dashboard_json` be split further?
4. Keep text formatting or JSON-only output?

---

## General Refactoring Principles

### 1. **Function Size Targets**
- **Helpers:** <30 lines (single task)
- **Processors:** 30-60 lines (transform data)
- **Orchestrators:** 40-80 lines (coordinate helpers)

### 2. **Naming Convention**
- **Private helpers:** `_verb_noun` (e.g., `_fetch_stats`, `_format_output`)
- **Public tools:** `verb_noun` (e.g., `lock_context`, `wake_up`)
- **Validators:** `_validate_thing` or `_check_thing`
- **Builders:** `_build_thing` or `_create_thing`

### 3. **Extraction Order**
1. Pure functions first (no I/O)
2. Database queries next
3. Formatters third
4. Main orchestrator last

### 4. **Testing Strategy**
- Each extracted function gets unit test
- Orchestrator gets integration test
- Mock database connections for query tests

---

## Discussion Questions

### **Strategy Questions**

1. **Granularity:** Are we splitting too much or too little?
   - Current plan: 15 functions → ~60-90 functions
   - Alternative: Fewer, larger helper functions?

2. **Performance:** Any concerns about function call overhead?
   - Likely negligible for I/O-bound operations
   - Can inline later if profiling shows issues

3. **Dependencies:** Are there shared helpers we should extract to a utils module?
   - `_sanitize_project_name`, `_format_json_response`, etc.
   - Create `claude_mcp_utils.py`?

4. **SQL Management:** Should we move SQL to external files?
   - Pro: Cleaner code, easier to review queries
   - Con: More files to navigate, harder to see query in context

### **Execution Questions**

5. **Order:** Should we refactor in size order (smallest first)?
   - Pro: Build confidence, establish patterns
   - Con: Hardest problems left for last

6. **Testing:** Should we write tests before refactoring?
   - Ideal: Yes, capture current behavior
   - Practical: May need to write tests during refactoring

7. **Migration:** Refactor all at once or incrementally?
   - Option A: Feature branch, refactor all 15, then merge
   - Option B: One function per PR, merge continuously

### **Architecture Questions**

8. **Module Structure:** Should we split into multiple files?
   ```
   claude_mcp/
     __init__.py
     tools.py          # MCP tool decorators
     database.py       # DB operations
     formatters.py     # Output formatting
     validators.py     # Input validation
     queries.py        # SQL queries
   ```

9. **Error Handling:** Should we extract to decorators?
   ```python
   @handle_errors(default_response={"success": False})
   @require_session
   @log_breadcrumb
   async def my_tool(...):
       ...
   ```

10. **Context Managers:** Should we standardize database access?
    ```python
    async with project_db(project) as conn:
        # All functions use this pattern
    ```

---

## Priority Review Areas

### 🔴 **Critical** - Must Discuss

1. **`query_database` (504 lines)** - Security implications
   - SQL injection prevention in refactored code
   - Safe query validation approach

2. **`apply_migrations` (437 lines)** - Schema evolution
   - Migration version tracking
   - Rollback strategy

3. **`execute_sql` (287 lines)** - Write operations
   - Transaction management
   - Dry-run vs actual execution

### 🟡 **Important** - Should Discuss

4. **`wake_up` / `sleep`** - Session lifecycle
   - Ensure session state consistency
   - Handover package format

5. **`lock_context` / `unlock_context`** - Core operations
   - Versioning logic preservation
   - Archive vs delete semantics

### 🟢 **Good to Have** - Can Discuss Later

6. Dashboard and analytics functions
7. Import/export functions
8. Search and semantic functions

---

## Next Steps

1. **Discuss examples above** - Are strategies sound?
2. **Choose execution approach** - All at once vs incremental?
3. **Decide on testing** - Write tests first or during?
4. **Pick first function** - Which one to start with?
5. **Set success criteria** - How do we know refactoring is done?

---

## Your Input Needed

**Please review and provide feedback on:**

✅ Do the extraction strategies make sense?
✅ Are function names clear and intuitive?
✅ Is the granularity appropriate?
✅ Any concerns about the approach?
✅ Which function should we start with?
✅ Any architectural changes needed first?

**Let's discuss!** 🚀
