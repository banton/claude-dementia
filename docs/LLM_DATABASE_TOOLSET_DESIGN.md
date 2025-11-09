# LLM Database Toolset Design v2.0
**Purpose:** Unified, self-contained database tools for LLM-driven work
**Philosophy:** One call does everything - no chaining required
**Date:** 2025-11-09

## Design Principles

1. **One Call, Complete Answer** - Each tool is self-contained and comprehensive
2. **Internal Interdependency** - Tools coordinate internally, not through chaining
3. **Auto-Repair by Default** - Tools fix what they can, report what they can't
4. **Rich, Actionable Output** - Every response includes next steps
5. **Safety with Convenience** - `auto_fix` parameter controls write operations
6. **PostgreSQL-Native** - Designed for PostgreSQL/Neon, no SQLite legacy

---

## Core Philosophy Shift

### ❌ Old Approach (12 Tools, 5+ Calls)
```
User: "Is my database healthy?"
LLM: inspect_project_data() → validate_project_data() → analyze_query_performance()
     → repair_project_data() → validate_project_data()
Result: 5 tool calls, complex state management, confusing UX
```

### ✅ New Approach (6 Tools, 1 Call)
```
User: "Is my database healthy?"
LLM: health_check_and_repair(auto_fix=False)
Result: 1 tool call, complete answer with recommendations
```

**Why:** LLM doesn't need step-by-step tools. It needs complete answers.

---

## The Complete Toolset (6 Tools)

### Core Tools (Do Everything)
1. **`health_check_and_repair()`** - Complete health check with optional auto-repair
2. **`apply_migrations()`** - Schema upgrades with safety checks
3. **`export_project()`** - Backup/export to portable format
4. **`import_project()`** - Restore/import from backup

### Utility Tools (Specific Needs)
5. **`inspect_schema()`** - Just schema info (rare use)
6. **`list_projects()`** - Multi-project management

---

## Tool 1: `health_check_and_repair()`

**Purpose:** One-stop health check, validation, and repair

**When LLM uses this:**
- User asks: "Is my database healthy?"
- User says: "Fix my database"
- User requests: "Check for problems"
- User wants: "Optimize performance"

### Signature

```python
async def health_check_and_repair(
    project: Optional[str] = None,
    auto_fix: bool = False,
    checks: List[str] = ["all"],
    dry_run: bool = False
) -> dict:
    """
    Complete database health check with optional auto-repair.

    Performs comprehensive validation in single call:
    1. Schema inspection (structure, indexes, constraints)
    2. Data validation (integrity, embeddings, orphans)
    3. Performance analysis (using pg_stat_user_tables)
    4. Issue detection (categorized by severity)
    5. [If auto_fix=True] Automatic repair
    6. Final verification

    Args:
        project: Project name (default: auto-detect)
        auto_fix: Automatically fix issues (default: False)
        checks: Which checks to run (default: ["all"])
                Options: "integrity", "embeddings", "performance", "schema"
        dry_run: Show what would be fixed without fixing (default: False)

    Returns:
        Complete health report with issues, fixes, recommendations
    """
```

### What It Does Internally

```python
# Step 1: Inspect (no separate tool call)
schema = _inspect_postgresql_schema(project)  # Uses information_schema
data_stats = _gather_statistics(project)       # Table counts, sizes

# Step 2: Validate (no separate tool call)
issues = []

# Check: Missing embeddings
missing_embeddings = _query_contexts_without_embeddings(project)
if missing_embeddings:
    issues.append({
        "type": "missing_embeddings",
        "severity": "warning",
        "count": len(missing_embeddings),
        "impact": "Semantic search unavailable for these contexts",
        "auto_fixable": True,
        "fix_method": "generate_embeddings()"
    })

# Check: Performance (using pg_stat_user_tables)
slow_tables = _analyze_table_stats(project)  # High seq_scan on large tables
if slow_tables:
    for table in slow_tables:
        issues.append({
            "type": "missing_index",
            "severity": "warning",
            "table": table["name"],
            "seq_scans": table["seq_scan"],
            "size_mb": table["size_mb"],
            "impact": "20-80% query speedup available",
            "auto_fixable": True,
            "fix_method": f"CREATE INDEX {table['suggested_index']}"
        })

# Check: Referential integrity
orphans = _find_orphaned_records(project)  # Sessions without projects, etc.
if orphans:
    issues.append({
        "type": "orphaned_records",
        "severity": "error",
        "count": len(orphans),
        "impact": "Data corruption, wasted space",
        "auto_fixable": True,
        "fix_method": "DELETE orphaned records"
    })

# Check: Schema drift
drift = _compare_schema_to_migrations(schema)  # Expected vs actual
if drift:
    issues.append({
        "type": "schema_drift",
        "severity": "warning",
        "differences": drift,
        "impact": "Manual schema changes detected",
        "auto_fixable": False,
        "fix_method": "Review and document changes"
    })

# Step 3: Auto-fix if requested
fixes_applied = []
if auto_fix and not dry_run:
    for issue in issues:
        if not issue["auto_fixable"]:
            continue

        if issue["type"] == "missing_embeddings":
            result = await generate_embeddings(project=project)
            fixes_applied.append({
                "issue": "missing_embeddings",
                "action": "generated embeddings",
                "count": issue["count"]
            })

        elif issue["type"] == "missing_index":
            sql = issue["fix_method"]
            await execute_sql(sql, confirm=True, project=project)
            fixes_applied.append({
                "issue": "missing_index",
                "action": "created index",
                "table": issue["table"]
            })

        elif issue["type"] == "orphaned_records":
            deleted = _delete_orphans(orphans, project)
            fixes_applied.append({
                "issue": "orphaned_records",
                "action": "deleted orphans",
                "count": deleted
            })

# Step 4: Final validation
if auto_fix:
    final_issues = _validate_again(project)
else:
    final_issues = issues

# Step 5: Determine health status
if not final_issues:
    health = "healthy"
elif all(i["severity"] == "warning" for i in final_issues):
    health = "good_with_warnings"
else:
    health = "needs_attention"

# Return complete report
return {
    "health": health,
    "summary": f"{len(final_issues)} issues found" if final_issues else "All checks passed",
    "checks_performed": checks,
    "statistics": {
        "contexts": data_stats["contexts"]["total"],
        "sessions": data_stats["sessions"]["total"],
        "embeddings_coverage": f"{data_stats['embeddings']['coverage']}%",
        "database_size_mb": data_stats["size_mb"]
    },
    "issues_found": issues,  # Original issues (before fixes)
    "fixes_applied": fixes_applied,  # What was fixed (if auto_fix=True)
    "remaining_issues": final_issues,  # Still needs attention
    "recommendations": _generate_recommendations(final_issues, auto_fix)
}
```

### Example Output

**Without auto_fix:**
```json
{
  "health": "good_with_warnings",
  "summary": "3 issues found",
  "checks_performed": ["integrity", "embeddings", "performance", "schema"],
  "statistics": {
    "contexts": 42,
    "sessions": 5,
    "embeddings_coverage": "90%",
    "database_size_mb": 12.5
  },
  "issues_found": [
    {
      "type": "missing_embeddings",
      "severity": "warning",
      "count": 4,
      "impact": "Semantic search unavailable for 4 contexts",
      "auto_fixable": true,
      "fix_method": "generate_embeddings()"
    },
    {
      "type": "missing_index",
      "severity": "warning",
      "table": "context_locks",
      "seq_scans": 245,
      "size_mb": 8.3,
      "impact": "20-80% query speedup available",
      "auto_fixable": true,
      "fix_method": "CREATE INDEX idx_context_project_active ON context_locks(project_name, last_active)"
    },
    {
      "type": "orphaned_records",
      "severity": "error",
      "count": 3,
      "impact": "Data corruption, wasted space",
      "auto_fixable": true,
      "fix_method": "DELETE orphaned records"
    }
  ],
  "fixes_applied": [],
  "remaining_issues": [
    /* same as issues_found */
  ],
  "recommendations": [
    "Run health_check_and_repair(auto_fix=True) to automatically fix 3 issues",
    "Or manually run: generate_embeddings()",
    "Or manually execute: CREATE INDEX idx_context_project_active ON context_locks(project_name, last_active)"
  ]
}
```

**With auto_fix=True:**
```json
{
  "health": "healthy",
  "summary": "All checks passed",
  "checks_performed": ["integrity", "embeddings", "performance", "schema"],
  "statistics": {
    "contexts": 42,
    "sessions": 5,
    "embeddings_coverage": "100%",
    "database_size_mb": 12.5
  },
  "issues_found": [
    /* same 3 issues as above */
  ],
  "fixes_applied": [
    {
      "issue": "missing_embeddings",
      "action": "generated embeddings",
      "count": 4
    },
    {
      "issue": "missing_index",
      "action": "created index",
      "table": "context_locks"
    },
    {
      "issue": "orphaned_records",
      "action": "deleted orphans",
      "count": 3
    }
  ],
  "remaining_issues": [],
  "recommendations": [
    "Database is now healthy!",
    "Consider running health_check_and_repair() weekly to maintain health"
  ]
}
```

---

## Tool 2: `apply_migrations()`

**Purpose:** Safe schema upgrades with validation

**When LLM uses this:**
- User asks: "Upgrade my database"
- User says: "Apply pending migrations"
- User requests: "Update schema to latest version"

### Signature

```python
async def apply_migrations(
    project: Optional[str] = None,
    dry_run: bool = True,
    confirm: bool = False
) -> dict:
    """
    Apply pending schema migrations with safety checks.

    What it does:
    1. Checks current schema version
    2. Identifies pending migrations
    3. [If dry_run=True] Shows what would change
    4. [If dry_run=False and confirm=True] Applies migrations
    5. Validates schema after migration
    6. Updates migration history

    Args:
        project: Project name (default: auto-detect)
        dry_run: Preview changes without applying (default: True)
        confirm: Required for actual execution (default: False)

    Returns:
        Migration plan (dry_run=True) or execution results (dry_run=False)
    """
```

### Example Output

**Dry-run (default):**
```json
{
  "project": "claude_dementia",
  "dry_run": true,
  "current_schema_version": "4.1",
  "pending_migrations": [
    {
      "id": 12,
      "name": "add_embedding_version",
      "description": "Track embedding model version for each context",
      "sql": "ALTER TABLE context_locks ADD COLUMN embedding_version TEXT",
      "estimated_duration_ms": 50,
      "breaking_change": false,
      "affected_tables": ["context_locks"],
      "affected_rows_estimate": 42
    },
    {
      "id": 13,
      "name": "add_context_relationships",
      "description": "Track relationships between contexts",
      "sql": "CREATE TABLE context_relationships (...)",
      "estimated_duration_ms": 100,
      "breaking_change": false,
      "affected_tables": ["context_relationships (new)"],
      "affected_rows_estimate": 0
    }
  ],
  "execution_plan": [
    "1. Backup current schema state (estimated: 500ms)",
    "2. Apply migration 12: add_embedding_version (estimated: 50ms)",
    "3. Validate schema integrity (estimated: 100ms)",
    "4. Apply migration 13: add_context_relationships (estimated: 100ms)",
    "5. Validate schema integrity (estimated: 100ms)",
    "6. Update migration history table"
  ],
  "total_estimated_time_ms": 850,
  "safety_checks": {
    "data_backed_up": "not yet (dry-run)",
    "rollback_available": true,
    "breaking_changes": false
  },
  "recommendation": "Safe to apply. Run with dry_run=False and confirm=True to execute."
}
```

**Actual execution:**
```json
{
  "project": "claude_dementia",
  "dry_run": false,
  "previous_schema_version": "4.1",
  "new_schema_version": "4.3",
  "applied_migrations": [
    {
      "id": 12,
      "name": "add_embedding_version",
      "status": "success",
      "duration_ms": 48,
      "affected_rows": 42
    },
    {
      "id": 13,
      "name": "add_context_relationships",
      "status": "success",
      "duration_ms": 95,
      "affected_rows": 0
    }
  ],
  "total_duration_ms": 723,
  "validation": {
    "schema_valid": true,
    "data_intact": true,
    "indexes_intact": true,
    "constraints_valid": true
  },
  "backup_location": "/tmp/backup_before_migration_2025-11-09.sql"
}
```

---

## Tool 3: `export_project()`

**Purpose:** Complete project backup to portable format

**When LLM uses this:**
- User asks: "Backup my database"
- User says: "Export this project"
- User requests: "Create backup before migration"

### Signature

```python
async def export_project(
    project: Optional[str] = None,
    output_path: str,
    format: str = "json",
    compress: bool = True,
    include_embeddings: bool = False
) -> dict:
    """
    Export entire project to portable format.

    What it exports:
    - All contexts (with content, metadata, versions)
    - All sessions (with timestamps, activity)
    - All memories (with categories, relationships)
    - Schema metadata (version, structure)
    - [Optional] Embeddings (large, usually excluded)

    Args:
        project: Project name (default: auto-detect)
        output_path: Where to save (absolute path)
        format: "json" (structured), "sql" (PostgreSQL dump), "archive" (tar.gz)
        compress: Use gzip compression (default: True)
        include_embeddings: Include embedding vectors (default: False, large)

    Returns:
        Export summary with file path, size, contents
    """
```

### Example Output

```json
{
  "project": "claude_dementia",
  "format": "json",
  "compressed": true,
  "output_path": "/tmp/claude_dementia_2025-11-09.json.gz",
  "exported": {
    "contexts": {
      "count": 42,
      "versions": 78,
      "size_mb": 8.3
    },
    "sessions": {
      "count": 5,
      "active": 1,
      "size_kb": 120
    },
    "memories": {
      "count": 1203,
      "categories": ["context", "file", "decision"],
      "size_mb": 4.2
    },
    "embeddings": {
      "included": false,
      "reason": "Excluded by default (would add 15MB)"
    },
    "schema_version": "4.1"
  },
  "file_size_mb": 3.8,
  "compression_ratio": "3.2x",
  "duration_ms": 2456,
  "checksum": "sha256:abc123...",
  "import_compatible": true,
  "restore_command": "import_project(input_path='/tmp/claude_dementia_2025-11-09.json.gz')"
}
```

---

## Tool 4: `import_project()`

**Purpose:** Restore project from backup

**When LLM uses this:**
- User asks: "Restore my backup"
- User says: "Import from file X"
- User requests: "Recover deleted project"

### Signature

```python
async def import_project(
    input_path: str,
    project: Optional[str] = None,
    overwrite: bool = False,
    validate_only: bool = False
) -> dict:
    """
    Import project from exported file.

    What it does:
    1. Validates file format and schema compatibility
    2. Checks for conflicts (existing project)
    3. [If validate_only=False] Imports all data
    4. Validates imported data integrity
    5. Regenerates embeddings if needed

    Args:
        input_path: Path to backup file
        project: Target project name (default: use name from backup)
        overwrite: Overwrite existing project (default: False, requires confirmation)
        validate_only: Just check if import would work (default: False)

    Returns:
        Import summary with validation results, imported counts
    """
```

### Example Output

**Validation only:**
```json
{
  "input_path": "/tmp/claude_dementia_2025-11-09.json.gz",
  "validate_only": true,
  "file_valid": true,
  "format": "json",
  "compressed": true,
  "schema_version": "4.1",
  "compatible": true,
  "target_project": "claude_dementia",
  "conflicts": {
    "project_exists": true,
    "requires_overwrite": true
  },
  "import_plan": {
    "contexts": 42,
    "sessions": 5,
    "memories": 1203,
    "estimated_time_ms": 4500,
    "embeddings_missing": 42,
    "regeneration_needed": true
  },
  "recommendation": "Compatible. Run with overwrite=True to import."
}
```

**Actual import:**
```json
{
  "input_path": "/tmp/claude_dementia_2025-11-09.json.gz",
  "validate_only": false,
  "target_project": "claude_dementia",
  "imported": {
    "contexts": 42,
    "sessions": 5,
    "memories": 1203
  },
  "embeddings_regenerated": 42,
  "validation": {
    "schema_valid": true,
    "data_intact": true,
    "referential_integrity": true,
    "embeddings_complete": true
  },
  "duration_ms": 4567,
  "final_health": "healthy"
}
```

---

## Tool 5: `inspect_schema()`

**Purpose:** Just schema info (rare use - most use health_check instead)

**When LLM uses this:**
- User specifically asks: "Show me the schema structure"
- User wants: "What columns does table X have?"
- Debugging: "What indexes exist on table Y?"

### Signature

```python
async def inspect_schema(
    project: Optional[str] = None,
    table: Optional[str] = None
) -> dict:
    """
    PostgreSQL-aware schema inspection.

    Returns detailed schema information using information_schema.

    Args:
        project: Project name (default: auto-detect)
        table: Specific table (default: all tables)

    Returns:
        Complete schema structure with columns, indexes, constraints
    """
```

### Example Output

```json
{
  "project": "claude_dementia",
  "schema": "claude_dementia",
  "database_type": "postgresql",
  "database_version": "15.5",
  "schema_version": "4.1",
  "tables": [
    {
      "name": "context_locks",
      "rows": 42,
      "size_mb": 8.3,
      "columns": [
        {
          "name": "id",
          "type": "SERIAL",
          "nullable": false,
          "default": "nextval('context_locks_id_seq'::regclass)"
        },
        {
          "name": "label",
          "type": "TEXT",
          "nullable": false,
          "default": null
        },
        {
          "name": "preview",
          "type": "TEXT",
          "nullable": true,
          "default": null
        }
      ],
      "indexes": [
        {
          "name": "context_locks_pkey",
          "columns": ["id"],
          "unique": true,
          "type": "btree"
        },
        {
          "name": "idx_context_label_version",
          "columns": ["label", "version", "session_id"],
          "unique": true,
          "type": "btree"
        }
      ],
      "constraints": [
        {
          "type": "PRIMARY KEY",
          "columns": ["id"]
        },
        {
          "type": "UNIQUE",
          "columns": ["label", "version", "session_id"]
        }
      ]
    }
  ],
  "migrations_applied": ["add_session_id", "add_preview", "add_key_concepts"]
}
```

---

## Tool 6: `list_projects()`

**Purpose:** Multi-project management

**When LLM uses this:**
- User asks: "What projects exist?"
- User wants: "Show all my projects"
- User needs: "Which project am I using?"

### Signature

```python
async def list_projects() -> dict:
    """
    List all projects in database with statistics.

    Returns:
        All projects with activity, size, health status
    """
```

### Example Output

```json
{
  "total_projects": 3,
  "database_size_mb": 25.8,
  "projects": [
    {
      "name": "claude_dementia",
      "schema": "claude_dementia",
      "active": true,
      "health": "healthy",
      "statistics": {
        "contexts": 42,
        "sessions": 5,
        "memories": 1203,
        "size_mb": 12.5
      },
      "last_activity": "2025-11-09 14:32:10"
    },
    {
      "name": "test_project",
      "schema": "test_project",
      "active": false,
      "health": "good_with_warnings",
      "statistics": {
        "contexts": 5,
        "sessions": 1,
        "memories": 45,
        "size_mb": 0.8
      },
      "last_activity": "2025-11-08 09:15:00"
    },
    {
      "name": "innkeeper",
      "schema": "innkeeper",
      "active": false,
      "health": "needs_attention",
      "statistics": {
        "contexts": 128,
        "sessions": 12,
        "memories": 5678,
        "size_mb": 12.5
      },
      "last_activity": "2025-11-07 16:45:30",
      "warnings": ["5 contexts missing embeddings", "2 orphaned sessions"]
    }
  ]
}
```

---

## LLM Usage Examples

### Example 1: Simple Health Check

```
User: "Is my database healthy?"

LLM: Calling health_check_and_repair(auto_fix=False)...

Result: "Your database is in good shape with 2 minor warnings:
- 4 contexts are missing embeddings (semantic search unavailable)
- Index missing on context_locks table (queries 20-50ms slower)

Would you like me to fix these automatically?"

User: "Yes, fix them"

LLM: Calling health_check_and_repair(auto_fix=True)...

Result: "Fixed! Generated embeddings for 4 contexts and created missing index.
Database is now 100% healthy."
```

### Example 2: Migration

```
User: "Upgrade my database to latest version"

LLM: Calling apply_migrations(dry_run=True)...

Result: "Found 2 pending migrations:
1. add_embedding_version (50ms, safe)
2. add_context_relationships (100ms, safe)

Total time: ~850ms. Safe to apply. Should I proceed?"

User: "Yes"

LLM: Calling apply_migrations(dry_run=False, confirm=True)...

Result: "Migration complete! Upgraded from v4.1 to v4.3 in 723ms.
All validation checks passed. Backup saved to /tmp/backup_before_migration_2025-11-09.sql"
```

### Example 3: Backup Before Risky Operation

```
User: "I'm about to try something risky, backup first"

LLM: Calling export_project(output_path="/tmp/backup.json.gz")...

Result: "Backup created:
- File: /tmp/backup.json.gz
- Size: 3.8 MB (compressed from 12.2 MB)
- Contents: 42 contexts, 5 sessions, 1203 memories
- Restore command: import_project(input_path='/tmp/backup.json.gz')

Your data is safe. Go ahead with your risky operation!"
```

---

## Implementation Plan

### Phase 1: Core Health Tool (Week 1) - 6-8 hours

**Priority 1: `health_check_and_repair()`**
- Implement schema inspection (PostgreSQL information_schema)
- Implement validation checks:
  - Missing embeddings
  - Missing indexes (using pg_stat_user_tables)
  - Orphaned records
  - Schema drift
- Implement auto-repair logic
- Test with real Neon database

**Files to create/modify:**
- `claude_mcp_hybrid_sessions.py` - Add tool
- `postgres_adapter.py` - Add helper methods if needed
- `tests/integration/test_health_check.py` - Integration tests

### Phase 2: Migration Tool (Week 2) - 4-5 hours

**Priority 2: `apply_migrations()`**
- Create schema_migrations tracking table
- Implement dry-run preview
- Implement migration executor
- Add validation after migration
- Test with test migrations

**Files to create/modify:**
- `claude_mcp_hybrid_sessions.py` - Add tool
- `postgres_adapter.py` - Add migration tracking
- `tests/integration/test_migrations.py` - Migration tests

### Phase 3: Portability Tools (Week 3) - 5-6 hours

**Priority 3: `export_project()` and `import_project()`**
- Implement JSON export format
- Implement compression
- Implement import validation
- Test backup/restore cycle

**Files to create/modify:**
- `claude_mcp_hybrid_sessions.py` - Add tools
- `tests/integration/test_export_import.py` - Round-trip tests

### Phase 4: Utility Tools (Week 4) - 2-3 hours

**Priority 4: `inspect_schema()` and `list_projects()`**
- Implement PostgreSQL schema inspection
- Implement multi-project listing
- Test with multiple projects

**Files to create/modify:**
- `claude_mcp_hybrid_sessions.py` - Add tools
- `tests/unit/test_schema_inspection.py` - Unit tests

**Total Estimated Time: 17-22 hours across 4 weeks**

---

## Success Metrics

### Before
- ❌ 12 tools, complex workflows
- ❌ 5+ tool calls for simple health check
- ❌ LLM must manage state across calls
- ❌ Broken `inspect_database` (SQLite only)
- ❌ No auto-repair capability
- ❌ No migration safety checks

### After
- ✅ 6 tools, simple workflows
- ✅ 1 tool call for complete health check
- ✅ LLM gets complete answers
- ✅ PostgreSQL-native schema inspection
- ✅ Auto-repair with confirmation
- ✅ Safe migrations with dry-run

### User Experience
- ✅ User: "Is my database healthy?" → LLM: Complete answer in one call
- ✅ User: "Fix it" → LLM: Repairs and reports results
- ✅ User: "Upgrade database" → LLM: Shows plan, executes safely
- ✅ User: "Backup my data" → LLM: Creates portable backup

---

## Why This Design is Better

| Aspect | Old Design (12 tools) | New Design (6 tools) |
|--------|----------------------|---------------------|
| **Tool Calls** | 5+ calls for health check | 1 call for health check |
| **Token Usage** | High (multiple calls) | Low (single call) |
| **State Management** | LLM tracks state | Tool tracks state |
| **User Experience** | "Please wait..." × 5 | "Done! Here's what I found/fixed" |
| **Error Handling** | Complex (partial states) | Simple (atomic operations) |
| **Testing** | Test tool interactions | Test individual tools |
| **Maintenance** | 12 tools to maintain | 6 tools to maintain |
| **LLM Confusion** | Many overlapping tools | Clear tool purposes |

---

## Next Steps

1. **Review this design** - Does this match your vision?
2. **Start Phase 1** - Implement `health_check_and_repair()` first
3. **Test with real workflow** - "Is my database healthy?" → one call
4. **Iterate** - Refine based on actual LLM usage
5. **Add remaining tools** - Phase 2-4 as needed

**Key principle:** Each tool is complete and self-contained. No chaining required.
