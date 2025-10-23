# Full SQL Operations Design - Write Capabilities for Database Tools

## Executive Summary

Extend database tools to support full CRUD operations (CREATE, READ, UPDATE, DELETE) on any SQLite database in the workspace, with the dementia memory database as the core use case.

**Status**: Planning Phase
**Target**: v4.1 or v4.2
**Complexity**: Medium-High (safety critical)

## Current State (v4.0)

✅ **query_database()** - Read-only SELECT queries
- Supports any SQLite database via `db_path` parameter
- Parameterized queries (SQL injection protection)
- Multiple output formats (table, JSON, CSV, markdown)
- Automatic LIMIT for unbounded queries
- Workspace path validation

✅ **inspect_database()** - Preset inspection queries
- Overview, schema, contexts, tables modes
- Works with any SQLite database
- Dementia-specific modes for memory system

## Requirements

### 1. Write Operations
- **INSERT**: Add new records
- **UPDATE**: Modify existing records
- **DELETE**: Remove records
- **Transaction support**: Multi-statement transactions
- **Schema operations**: CREATE TABLE, ALTER TABLE (optional)

### 2. Safety Requirements
- **Dry-run mode**: Preview changes without executing
- **Confirmation**: Require explicit approval for destructive operations
- **Backup**: Optional database backup before execution
- **Transaction rollback**: Automatic rollback on error
- **Limits**: Max rows affected per operation
- **Validation**: Prevent dangerous operations (DROP DATABASE, etc.)

### 3. Auditability
- **Change logging**: Record all write operations
- **Affected rows**: Report count of modified records
- **Execution time**: Track performance
- **Rollback history**: Track what was undone

## Design Options

### Option A: Single Tool `execute_sql()`
```python
@mcp.tool()
async def execute_sql(
    sql: str,
    params: Optional[List[str]] = None,
    db_path: Optional[str] = None,
    dry_run: bool = True,
    confirm: bool = False,
    backup: bool = False
) -> str
```

**Pros**:
- Single tool for all operations
- Flexible, handles any SQL
- Consistent interface

**Cons**:
- Less explicit about operation type
- Harder to document all use cases
- Less granular safety controls

### Option B: Separate Tools Per Operation
```python
insert_record()    # INSERT operations
update_records()   # UPDATE operations
delete_records()   # DELETE operations
execute_transaction()  # Multi-statement transactions
```

**Pros**:
- Very explicit and safe
- Operation-specific validations
- Clear documentation per tool

**Cons**:
- More tools to maintain
- Less flexible for complex SQL
- Repetitive code

### Option C: Two-Tier Approach (RECOMMENDED)
```python
# Keep existing read-only tool
query_database()  # SELECT only (existing)

# Add new write-capable tool with enhanced safety
execute_sql()     # INSERT, UPDATE, DELETE, CREATE
execute_transaction()  # Multi-statement transactions
```

**Pros**:
- Clear separation: read vs write
- Write operations get special handling
- Maintains backward compatibility
- Flexible but safe

**Cons**:
- Two tools to learn
- Slight API inconsistency

## Recommended Design: Two-Tier Approach

### Tool 1: execute_sql() - Single Statement Execution

```python
@mcp.tool()
async def execute_sql(
    sql: str,
    params: Optional[List[str]] = None,
    db_path: Optional[str] = None,
    dry_run: bool = True,
    confirm: bool = False,
    backup: bool = False,
    max_affected: Optional[int] = None
) -> str:
    """
    Execute write operations (INSERT, UPDATE, DELETE) on SQLite databases.

    **SAFETY FEATURES:**
    - Dry-run by default: Set dry_run=False to execute
    - Confirmation required: Set confirm=True to proceed
    - Automatic transaction: Auto-rollback on error
    - Parameterized queries: Use ? placeholders
    - Row limits: Set max_affected to limit changes
    - Backup option: Create .backup file before execution

    **EXAMPLES:**

    1. Insert new context (dry-run first):
       execute_sql(
           "INSERT INTO context_locks (label, version, content) VALUES (?, ?, ?)",
           params=["test", "1.0", "Test content"],
           dry_run=True
       )

    2. Execute after confirming:
       execute_sql(
           "INSERT INTO context_locks (label, version, content) VALUES (?, ?, ?)",
           params=["test", "1.0", "Test content"],
           dry_run=False,
           confirm=True
       )

    3. Update with safety limit:
       execute_sql(
           "UPDATE context_locks SET priority = ? WHERE label LIKE ?",
           params=["important", "api_%"],
           max_affected=10,
           dry_run=False,
           confirm=True
       )

    4. Delete with backup:
       execute_sql(
           "DELETE FROM memory_entries WHERE timestamp < ?",
           params=["2024-01-01"],
           backup=True,
           dry_run=False,
           confirm=True
       )
    """
```

**Implementation steps**:
1. Parse and validate SQL statement
2. Check operation type (INSERT/UPDATE/DELETE)
3. If dry_run: Execute SELECT to show what would change
4. If not dry_run and not confirm: Return error asking for confirmation
5. If backup: Create .backup copy of database
6. Start transaction
7. Execute statement
8. Check affected rows vs max_affected
9. Commit or rollback
10. Return report with affected rows and execution time

### Tool 2: execute_transaction() - Multi-Statement Transactions

```python
@mcp.tool()
async def execute_transaction(
    statements: List[Dict[str, Any]],
    db_path: Optional[str] = None,
    dry_run: bool = True,
    confirm: bool = False,
    backup: bool = False
) -> str:
    """
    Execute multiple SQL statements in a single transaction.

    All statements succeed together or all fail (atomic).

    **EXAMPLES:**

    1. Multi-step data migration:
       execute_transaction([
           {
               "sql": "INSERT INTO new_contexts SELECT * FROM context_locks WHERE version = ?",
               "params": ["1.0"]
           },
           {
               "sql": "UPDATE context_locks SET migrated = ? WHERE version = ?",
               "params": [True, "1.0"]
           },
           {
               "sql": "DELETE FROM old_contexts WHERE version = ?",
               "params": ["1.0"]
           }
       ], dry_run=False, confirm=True)

    2. Bulk insert:
       execute_transaction([
           {"sql": "INSERT INTO tags VALUES (?, ?)", "params": ["file1.py", "reviewed"]},
           {"sql": "INSERT INTO tags VALUES (?, ?)", "params": ["file2.py", "reviewed"]},
           {"sql": "INSERT INTO tags VALUES (?, ?)", "params": ["file3.py", "reviewed"]}
       ], dry_run=False, confirm=True)
    """
```

### Tool 3: backup_database() - Manual Backup

```python
@mcp.tool()
async def backup_database(
    db_path: Optional[str] = None,
    backup_name: Optional[str] = None
) -> str:
    """
    Create a backup copy of a SQLite database.

    **EXAMPLES:**

    1. Backup dementia database:
       backup_database()

    2. Backup custom database:
       backup_database(db_path="./data/app.db", backup_name="pre-migration")
    """
```

### Tool 4: rollback_database() - Restore from Backup

```python
@mcp.tool()
async def rollback_database(
    backup_file: str,
    db_path: Optional[str] = None,
    confirm: bool = False
) -> str:
    """
    Restore database from a backup file.

    **WARNING**: This will replace the current database.

    **EXAMPLES:**

    1. Restore from backup:
       rollback_database(
           backup_file="./.dementia.db.backup.2024-01-15-14-30-00",
           confirm=True
       )
    """
```

## Safety Mechanisms

### 1. Dry-Run Mode
**Default**: Always on (`dry_run=True`)

When dry_run=True:
- For INSERT: Shows the data that would be inserted
- For UPDATE: Shows rows that would be affected (executes equivalent SELECT)
- For DELETE: Shows rows that would be deleted (executes equivalent SELECT)
- No changes made to database

Example output:
```
🔍 DRY RUN - No changes will be made

SQL: UPDATE context_locks SET priority = ? WHERE label LIKE ?
Params: ["important", "api_%"]

Would affect 3 rows:
┌────────┬──────────┬──────────┬──────────────┐
│ id     │ label    │ version  │ priority     │
├────────┼──────────┼──────────┼──────────────┤
│ 1      │ api_spec │ 1.0      │ reference    │
│ 2      │ api_spec │ 1.1      │ reference    │
│ 3      │ api_docs │ 1.0      │ reference    │
└────────┴──────────┴──────────┴──────────────┘

To execute: Set dry_run=False and confirm=True
```

### 2. Confirmation Requirement
**Default**: Must be explicitly enabled (`confirm=False`)

Prevents accidental execution:
```python
# This will fail with error message
execute_sql(
    "DELETE FROM memory_entries WHERE timestamp < ?",
    params=["2024-01-01"],
    dry_run=False
)
# Error: ❌ Confirmation required. Set confirm=True to proceed.

# This will execute
execute_sql(
    "DELETE FROM memory_entries WHERE timestamp < ?",
    params=["2024-01-01"],
    dry_run=False,
    confirm=True
)
```

### 3. Row Limits
Prevent bulk operations from affecting too many rows:

```python
execute_sql(
    "UPDATE context_locks SET priority = ?",
    params=["important"],
    max_affected=100,
    dry_run=False,
    confirm=True
)
# If >100 rows would be affected: Transaction rolls back with error
```

### 4. Dangerous Operation Detection
Block operations that could destroy data:

**Blocked operations**:
- DROP DATABASE
- DROP TABLE (without explicit override)
- TRUNCATE TABLE (without WHERE clause warning)
- UPDATE/DELETE without WHERE clause (requires explicit confirmation)

```python
# This will warn and require extra confirmation
execute_sql(
    "DELETE FROM context_locks",  # No WHERE clause!
    dry_run=False,
    confirm=True,
    allow_bulk_delete=True  # Extra flag required
)
```

### 5. Automatic Backups
Create timestamped backups before destructive operations:

```python
execute_sql(
    "DELETE FROM old_data WHERE created < ?",
    params=["2020-01-01"],
    backup=True,  # Creates .dementia.db.backup.2024-01-15-14-30-00
    dry_run=False,
    confirm=True
)
```

Backup naming: `{db_name}.backup.{timestamp}.db`

### 6. Transaction Rollback
All operations wrapped in transactions:

```python
BEGIN TRANSACTION;
  -- Execute SQL
  -- Check affected rows
  -- If error or limit exceeded: ROLLBACK
COMMIT;
```

On error: Automatic rollback with detailed error message.

### 7. Audit Logging
Log all write operations to a separate audit table:

```sql
CREATE TABLE IF NOT EXISTS sql_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    database_path TEXT NOT NULL,
    operation_type TEXT NOT NULL,  -- INSERT, UPDATE, DELETE
    sql_statement TEXT NOT NULL,
    affected_rows INTEGER,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    execution_time_ms REAL,
    backup_file TEXT
)
```

## Use Cases

### Use Case 1: Direct Memory Manipulation
**Scenario**: Fix corrupted context metadata

```python
# 1. Inspect the problem
query_database(
    "SELECT id, label, metadata FROM context_locks WHERE metadata IS NULL"
)

# 2. Dry-run the fix
execute_sql(
    "UPDATE context_locks SET metadata = ? WHERE metadata IS NULL",
    params=['{"priority": "reference"}'],
    dry_run=True
)

# 3. Execute with backup
execute_sql(
    "UPDATE context_locks SET metadata = ? WHERE metadata IS NULL",
    params=['{"priority": "reference"}'],
    backup=True,
    dry_run=False,
    confirm=True
)
```

### Use Case 2: Bulk Data Import
**Scenario**: Import tags from CSV

```python
execute_transaction([
    {"sql": "INSERT INTO file_tags (path, tag) VALUES (?, ?)", "params": ["src/main.py", "reviewed"]},
    {"sql": "INSERT INTO file_tags (path, tag) VALUES (?, ?)", "params": ["src/utils.py", "reviewed"]},
    {"sql": "INSERT INTO file_tags (path, tag) VALUES (?, ?)", "params": ["tests/test.py", "needs-work"]}
], dry_run=False, confirm=True)
```

### Use Case 3: Database Maintenance
**Scenario**: Clean up old archives

```python
# 1. Check what will be deleted
query_database(
    "SELECT COUNT(*) as count, MIN(deleted_at) as oldest FROM context_archives WHERE deleted_at < ?",
    params=[time.time() - (90 * 86400)]  # 90 days ago
)

# 2. Delete with backup
execute_sql(
    "DELETE FROM context_archives WHERE deleted_at < ?",
    params=[time.time() - (90 * 86400)],
    backup=True,
    dry_run=False,
    confirm=True
)
```

### Use Case 4: Schema Migration
**Scenario**: Add new column to existing table

```python
execute_sql(
    "ALTER TABLE context_locks ADD COLUMN last_used REAL",
    backup=True,
    dry_run=False,
    confirm=True
)
```

### Use Case 5: Custom App Database
**Scenario**: Managing a custom SQLite database for your app

```python
# Insert user
execute_sql(
    "INSERT INTO users (name, email, created_at) VALUES (?, ?, ?)",
    params=["Alice", "alice@example.com", time.time()],
    db_path="./data/app.db",
    dry_run=False,
    confirm=True
)

# Update user status
execute_sql(
    "UPDATE users SET status = ? WHERE email = ?",
    params=["active", "alice@example.com"],
    db_path="./data/app.db",
    dry_run=False,
    confirm=True
)
```

## Testing Strategy

### Test Suite: test_sql_write_operations.py

**Test Coverage**:
1. ✅ INSERT operations
   - Single row insert
   - Bulk insert via transaction
   - Insert with all column types
   - Insert with NULL values

2. ✅ UPDATE operations
   - Update single row
   - Update multiple rows
   - Update with complex WHERE clause
   - Update without WHERE (should warn)

3. ✅ DELETE operations
   - Delete single row
   - Delete multiple rows
   - Delete with complex WHERE clause
   - Delete without WHERE (should require extra confirmation)

4. ✅ Safety mechanisms
   - Dry-run shows correct preview
   - Confirmation requirement enforced
   - Max affected rows limit enforced
   - Backup created correctly
   - Transaction rollback on error
   - Dangerous operations blocked

5. ✅ Transaction support
   - Multiple statements succeed together
   - Rollback on error (atomic)
   - Nested transaction handling

6. ✅ Audit logging
   - All operations logged
   - Success and failure tracked
   - Execution time recorded

7. ✅ Custom databases
   - Works with any SQLite database in workspace
   - Path validation enforced

## Implementation Plan

### Phase 1: Core Write Operations (Week 1)
1. ✅ Create test suite (TDD approach)
2. Implement `execute_sql()` with basic safety
   - Dry-run mode
   - Confirmation requirement
   - Transaction wrapping
3. Implement parameterized queries
4. Test with dementia database

### Phase 2: Enhanced Safety (Week 2)
1. Add max_affected rows limit
2. Implement backup functionality
3. Add dangerous operation detection
4. Implement audit logging
5. Test all safety mechanisms

### Phase 3: Transaction Support (Week 2)
1. Implement `execute_transaction()`
2. Test multi-statement transactions
3. Test rollback behavior
4. Test with complex scenarios

### Phase 4: Utility Tools (Week 3)
1. Implement `backup_database()`
2. Implement `rollback_database()`
3. Add backup management utilities
4. Test backup/restore workflow

### Phase 5: Documentation & Polish (Week 3)
1. Comprehensive docstrings
2. Usage examples in docs
3. Error message improvements
4. User testing and feedback

## Migration Path

### For Existing Users
- ✅ No breaking changes - existing tools unchanged
- New tools are opt-in
- Clear documentation on when to use each tool
- Safety defaults protect against accidents

### Deprecation Plan
- None - all tools remain available
- `query_database()` stays read-only forever
- Write operations are explicit and separate

## Open Questions

1. **Should we support CREATE TABLE / ALTER TABLE?**
   - Pro: Useful for schema migrations
   - Con: Very dangerous, could break system
   - Decision: Start without, add later if needed with extra safety

2. **Should audit log be in same database or separate?**
   - Same DB: Easier to manage, but takes space
   - Separate: Cleaner separation, but more complexity
   - Decision: Same DB, with cleanup utilities

3. **Maximum backup retention?**
   - Keep last N backups per database
   - Auto-delete old backups
   - Decision: Keep last 10, with manual override

4. **Should we support ATTACH DATABASE?**
   - Useful for cross-database operations
   - Security risk (could attach external DBs)
   - Decision: Block for now, reconsider later

## Security Considerations

1. **Path Traversal**: Already handled (workspace validation)
2. **SQL Injection**: Handled via parameterized queries
3. **Data Loss**: Multiple safety layers (dry-run, confirmation, backups)
4. **Audit Trail**: All operations logged
5. **Access Control**: Tool-level (MCP server must be trusted)

## Performance Considerations

1. **Backup overhead**: ~100ms-1s for typical dementia DB
2. **Transaction overhead**: Minimal (SQLite is fast)
3. **Audit logging**: <10ms per operation
4. **Dry-run queries**: Same cost as normal SELECT

## Success Metrics

1. ✅ Zero data loss incidents
2. ✅ 100% test coverage for write operations
3. ✅ All safety mechanisms tested
4. ✅ User feedback positive on safety vs usability balance
5. ✅ No security vulnerabilities found in review

## References

- SQLite documentation: https://www.sqlite.org/lang.html
- SQLite transactions: https://www.sqlite.org/lang_transaction.html
- Python sqlite3 module: https://docs.python.org/3/library/sqlite3.html

## Conclusion

This design provides a comprehensive, safe, and flexible system for full SQL operations on SQLite databases. The two-tier approach (read-only + write-with-safety) maintains backward compatibility while enabling powerful new capabilities. Multiple safety layers protect against accidents while still allowing experienced users to perform complex operations when needed.

**Recommendation**: Proceed with implementation following the phased plan above, starting with comprehensive tests (TDD).
