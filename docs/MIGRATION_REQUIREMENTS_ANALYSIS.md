# Dementia Migration Requirements Analysis

**Date**: 2025-11-09
**Current Version**: 4.2.0
**Analysis Scope**: Version migration requirements for users upgrading Dementia

---

## Executive Summary

### Current State
- ✅ PostgreSQL has automatic schema migrations (11 migrations)
- ✅ SQLite migration script exists (v4.0 → v4.1)
- ❌ No schema version tracking table
- ❌ No formal migration documentation
- ❌ No SQLite → PostgreSQL migration tool
- ❌ No rollback capability
- ⚠️ Migrations use column existence checks (fragile)

### Risk Assessment
| Risk | Severity | Impact |
|------|----------|--------|
| **No rollback** | 🔴 High | Broken migrations are permanent |
| **No version tracking** | 🟠 Medium | Can't detect partial/failed migrations |
| **SQLite users abandoned** | 🟠 Medium | Can't upgrade to PostgreSQL version |
| **No migration tests** | 🟡 Low | Migrations untested in isolation |
| **Silent failures** | 🟠 Medium | Errors caught but not logged |

---

## Migration Paths Identified

### Path 1: PostgreSQL User (Automatic ✅)
**Scenario**: User already on PostgreSQL, upgrading to newer code

```
Old PostgreSQL → New PostgreSQL
     ↓
PostgreSQLAdapter.__init__()
     ↓
ensure_schema_exists()
     ↓
_run_migrations()  ← Automatic!
     ↓
✅ Schema updated
```

**Migrations Applied**:
1. Add session_id to memory_entries
2. Add timestamp to memory_entries
3. Add category to memory_entries
4. Add summary to sessions
5. Add UNIQUE constraint to file_semantic_model
6. Add preview to context_locks (RLM optimization)
7. Add key_concepts to context_locks (RLM optimization)
8. Add project_name to mcp_sessions
9. Add session_summary to mcp_sessions
10. Add indices for project_name/last_active
11. Update default project_name '__PENDING__'

**Strengths**:
- Fully automatic (zero user action)
- Idempotent (safe to run multiple times)
- Uses `information_schema` column checks

**Weaknesses**:
- No version tracking (can't tell what version user is on)
- Errors silently caught (`except: pass`)
- No rollback if migration fails mid-way
- No migration status logged to database

**User Experience**: ✅ Seamless (zero intervention needed)

---

### Path 2: SQLite User (Manual + Broken ❌)
**Scenario**: User on old SQLite version wants PostgreSQL

```
SQLite v4.0 → SQLite v4.1 → PostgreSQL v4.2?
     ↓              ↓             ↓
  migrate_v4_1   Unknown      No tool!
```

**Current Tools**:
- `migrate_v4_1_rlm.py` - SQLite v4.0 → v4.1 (adds RLM features)
- ❌ No SQLite → PostgreSQL migration tool

**Upgrade Path (Current)**:
1. Run `migrate_v4_1_rlm.py .claude-memory.db` (SQLite)
2. ❌ STUCK - No way to move data to PostgreSQL
3. Manual export/import required

**Weaknesses**:
- No automated SQLite → PostgreSQL migration
- Users lose all data unless they manually export
- Migration script only handles v4.0 → v4.1, not current v4.2

**User Experience**: ❌ Broken (manual export required, data loss risk)

---

### Path 3: New User (Clean Install ✅)
**Scenario**: First-time user installing Dementia v4.2

```
No Database → PostgreSQL v4.2
     ↓
PostgreSQLAdapter.__init__()
     ↓
ensure_schema_exists()
     ↓
CREATE TABLE IF NOT EXISTS...
     ↓
✅ Full schema created
```

**Migrations Run**: None (schema created from scratch with all columns)

**User Experience**: ✅ Perfect (zero issues)

---

## Detailed Migration Analysis

### PostgreSQL Migration Strategy

**Location**: `postgres_adapter.py:623-800` (_run_migrations method)

**How it Works**:
```python
def _run_migrations(self, cur):
    """Apply schema migrations to existing tables."""

    # For each migration:
    # 1. Check if column/constraint exists via information_schema
    # 2. If missing, ALTER TABLE to add it
    # 3. Catch exceptions silently (table might not exist yet)
```

**Example Migration**:
```python
# Migration 8: Add project_name to mcp_sessions if missing
try:
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
        AND table_name = 'mcp_sessions'
        AND column_name = 'project_name'
    """)
    if not cur.fetchone():
        print("⚠️  Migrating mcp_sessions: adding project_name column", file=sys.stderr)
        cur.execute("ALTER TABLE mcp_sessions ADD COLUMN project_name TEXT DEFAULT '__PENDING__'")
        print("✅ Added project_name column to mcp_sessions", file=sys.stderr)
except Exception as e:
    print(f"❌ Migration 8 failed: {e}", file=sys.stderr)
```

**Strengths**:
- ✅ Idempotent (checks before altering)
- ✅ Works across schema versions
- ✅ Zero user intervention
- ✅ Prints status to stderr

**Weaknesses**:
- ❌ No rollback on failure
- ❌ No transaction wrapping (migrations 1-11 not atomic)
- ❌ Some migrations use `except: pass` (silent failures)
- ❌ No schema_migrations tracking table
- ❌ Can't detect "partially migrated" state

---

### SQLite Migration Strategy

**Location**: `migrate_v4_1_rlm.py` (standalone script)

**How it Works**:
```python
def migrate_database(db_path: str):
    """Apply v4.1 RLM schema changes."""

    # 1. Check if already migrated (preview column exists)
    if check_migration_status(conn):
        return "Already migrated"

    # 2. BEGIN TRANSACTION (rollback on error)

    # 3. ALTER TABLE add columns:
    #    - preview TEXT
    #    - key_concepts TEXT
    #    - related_contexts TEXT
    #    - last_accessed TIMESTAMP
    #    - access_count INTEGER

    # 4. CREATE new tables:
    #    - context_relationships
    #    - context_access_log
    #    - tool_usage_log

    # 5. Generate previews for existing contexts

    # 6. COMMIT or ROLLBACK
```

**Strengths**:
- ✅ Transaction wrapped (atomic)
- ✅ Rollback on failure
- ✅ Generates RLM previews for existing data
- ✅ Verification step
- ✅ Detailed error reporting

**Weaknesses**:
- ❌ Only handles v4.0 → v4.1 (outdated)
- ❌ No PostgreSQL equivalent
- ❌ No migration to PostgreSQL
- ❌ Abandoned (SQLite deprecated)

---

## Missing Migration Scenarios

### Scenario 1: SQLite → PostgreSQL
**User Story**: "I've been using SQLite Dementia v4.0 and want to upgrade to PostgreSQL v4.2"

**Current Solution**: ❌ None

**Required Tool**: `migrate_sqlite_to_postgres.py`

**Steps Needed**:
1. Read SQLite database schema and data
2. Map SQLite types to PostgreSQL types
3. Create PostgreSQL schema (target project)
4. Transform data:
   - Convert timestamps (SQLite TEXT → PostgreSQL TIMESTAMP)
   - Convert JSON (TEXT → JSONB)
   - Handle schema differences
5. INSERT data into PostgreSQL
6. Verify row counts match
7. Optional: backup/archive SQLite file

**Data to Migrate**:
```
Tables:
  - sessions (session history)
  - context_locks (locked contexts with versions)
  - audit_trail (history of changes)
  - memory_entries (compressed memory)
  - file_semantic_model (file analysis)
  - file_change_history (change tracking)
  - todos, decisions, file_tags
  - mcp_sessions (if exists)
```

**Estimated Complexity**: 2-3 hours to implement

---

### Scenario 2: Partial Migration Recovery
**User Story**: "PostgreSQL migration failed halfway, now database is broken"

**Current Solution**: ❌ None (migrations don't rollback)

**Problem**:
```
Migration 1-5 succeed ✅
Migration 6 fails ❌
Migrations 7-11 skipped
Result: Database in inconsistent state
```

**Required Solution**:
1. Wrap all migrations in single transaction
2. Or: Create `schema_migrations` tracking table
3. Or: Provide repair script

**Current Workaround**: Drop schema and recreate (loses data!)

---

### Scenario 3: Downgrade
**User Story**: "New version broke, need to roll back to v4.1"

**Current Solution**: ❌ Impossible

**Problem**:
- Migrations only go forward (ALTER TABLE ADD COLUMN)
- No ALTER TABLE DROP COLUMN migrations
- No version tracking

**Required Solution**:
- Schema version table
- Downgrade migrations (DROP COLUMN, remove constraints)
- Database backup recommendations

---

## Gap Analysis

### Critical Gaps

#### 1. No Schema Version Tracking ❌
**Problem**: Can't determine database schema version

**Impact**:
- Can't detect failed/partial migrations
- Can't skip already-applied migrations reliably
- Can't warn users about version mismatches

**Solution**: Add `schema_migrations` table
```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);
```

**Implementation**: 2 hours

---

#### 2. No SQLite → PostgreSQL Migration Tool ❌
**Problem**: SQLite users cannot upgrade to PostgreSQL

**Impact**:
- SQLite users stuck on old version
- Users lose data if they switch
- Creates split user base

**Solution**: Create `migrate_sqlite_to_postgres.py`

**Implementation**: 3 hours

---

#### 3. No Migration Testing ⚠️
**Problem**: Migrations untested in isolation

**Impact**:
- Bugs discovered in production
- No confidence in migration success
- Can't test rollback scenarios

**Solution**: Create migration test suite
- Test each migration independently
- Test migration idempotency
- Test migration failures

**Implementation**: 2 hours

---

#### 4. Silent Migration Failures ⚠️
**Problem**: Some migrations use `except: pass`

**Impact**:
- Errors hidden from users
- Database inconsistencies
- Hard to debug

**Example**:
```python
except Exception as e:
    pass  # ❌ Error silently ignored!
```

**Solution**: Log all migration errors
```python
except Exception as e:
    print(f"❌ Migration failed: {e}", file=sys.stderr)
    # Continue, but log error
```

**Implementation**: 30 minutes

---

### Medium Priority Gaps

#### 5. No Transaction Wrapping ⚠️
**Problem**: PostgreSQL migrations not atomic

**Current**:
```python
# Migration 1 runs
# Migration 2 runs
# Migration 3 FAILS
# Migrations 1-2 already committed!
```

**Solution**: Wrap all migrations in transaction
```python
try:
    conn.execute("BEGIN TRANSACTION")
    _run_all_migrations(cur)
    conn.commit()
except:
    conn.rollback()
    raise
```

**Trade-off**: SQLite allows ALTER TABLE in transactions, PostgreSQL does too

**Implementation**: 1 hour

---

#### 6. No Migration Documentation 📄
**Problem**: Users don't know how to upgrade

**Missing Docs**:
- UPGRADING.md guide
- CHANGELOG with migration notes
- Rollback procedures
- Troubleshooting guide

**Solution**: Write comprehensive migration docs

**Implementation**: 2 hours

---

## Recommendations

### Priority 1: Essential (Do Now) 🔴

#### 1. Add Schema Version Table
```python
# postgres_adapter.py - Add to ensure_schema_exists()

cur.execute("""
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        success BOOLEAN DEFAULT TRUE,
        error_message TEXT
    )
""")

# Update _run_migrations() to check version table
cur.execute("SELECT MAX(version) FROM schema_migrations WHERE success = TRUE")
current_version = cur.fetchone()[0] or 0

if current_version < 11:  # Run migrations > current_version
    # Apply migrations 1-11
    ...
```

**Benefit**:
- Track migration status
- Skip already-applied migrations
- Detect partial failures
- Enable safe rollback

**Effort**: 2 hours
**Impact**: High (prevents data corruption)

---

#### 2. Fix Silent Migration Failures
```python
# postgres_adapter.py - Replace all `except: pass` with:

except Exception as e:
    error_msg = f"❌ Migration {migration_number} failed: {e}"
    print(error_msg, file=sys.stderr)

    # Log to schema_migrations table
    cur.execute("""
        INSERT INTO schema_migrations (version, name, success, error_message)
        VALUES (?, ?, FALSE, ?)
    """, (migration_number, migration_name, str(e)))

    # Continue with next migration (or re-raise if critical)
```

**Benefit**:
- Visibility into migration issues
- Easier debugging
- Audit trail

**Effort**: 1 hour
**Impact**: High (prevents silent data loss)

---

#### 3. Document Current Migration Process
Create `docs/UPGRADING.md`:

```markdown
# Upgrading Dementia

## PostgreSQL Users (Automatic)
Upgrading is automatic! Just pull the latest code:

```bash
git pull origin main
python3 claude_mcp_hybrid.py
# Migrations run automatically on first connection
```

## SQLite Users (Manual)
SQLite is deprecated. To migrate to PostgreSQL:

### Option 1: Fresh Start (No Data Migration)
1. Set DATABASE_URL environment variable
2. Run new version (auto-creates PostgreSQL schema)
3. Locked contexts lost (re-lock important ones)

### Option 2: Manual Export/Import
[Coming Soon: migrate_sqlite_to_postgres.py]

## Troubleshooting
...
```

**Effort**: 1 hour
**Impact**: High (reduces support burden)

---

### Priority 2: Important (Do Next Week) 🟠

#### 4. Create SQLite → PostgreSQL Migration Tool
```python
# migrate_sqlite_to_postgres.py

def migrate_sqlite_to_postgres(
    sqlite_path: str,
    postgres_url: str,
    target_project: str
):
    """
    Migrate SQLite database to PostgreSQL.

    Steps:
    1. Connect to both databases
    2. Verify PostgreSQL schema exists
    3. For each table:
       - Read all SQLite rows
       - Transform data types
       - INSERT into PostgreSQL
    4. Verify row counts
    5. Optional: archive SQLite file
    """
    ...
```

**Benefit**:
- Enables SQLite users to upgrade
- Preserves user data
- Unifies user base on PostgreSQL

**Effort**: 3-4 hours
**Impact**: High (unblocks SQLite users)

---

#### 5. Add Transaction Wrapping to Migrations
```python
def _run_migrations(self, cur):
    """Apply schema migrations (atomic)."""

    # START TRANSACTION
    cur.execute("BEGIN TRANSACTION")

    try:
        # Run all migrations
        for migration_number in range(1, 12):
            self._run_migration_N(cur, migration_number)

        # COMMIT if all succeed
        cur.connection.commit()

    except Exception as e:
        # ROLLBACK if any fail
        cur.connection.rollback()
        raise RuntimeError(f"Migration failed: {e}")
```

**Benefit**:
- Atomic migrations (all-or-nothing)
- Prevents partial migration state
- Safe rollback

**Effort**: 1-2 hours
**Impact**: Medium (improves reliability)

---

#### 6. Create Migration Test Suite
```python
# tests/integration/test_migrations.py

def test_migration_1_adds_session_id_column():
    """Test migration 1: session_id column"""
    # Create database with old schema
    # Run migration 1
    # Verify column exists
    # Verify idempotent (run twice)

def test_migration_rollback():
    """Test migration rollback on error"""
    # Mock migration to fail
    # Verify rollback
    # Verify database unchanged
```

**Benefit**:
- Confidence in migrations
- Catch bugs before production
- Test idempotency

**Effort**: 2-3 hours
**Impact**: Medium (prevents future bugs)

---

### Priority 3: Nice-to-Have (Future) 🟢

#### 7. Rollback/Downgrade Support
- Add downgrade migrations (DROP COLUMN)
- Create rollback CLI tool
- Document rollback procedures

**Effort**: 4-6 hours
**Impact**: Low (rarely needed)

---

#### 8. Migration Performance Optimization
- Batch data migrations
- Add progress indicators
- Parallel migrations (where safe)

**Effort**: 2-3 hours
**Impact**: Low (migrations are fast currently)

---

## Action Plan

### Week 1: Critical Fixes (Priority 1)
- [x] **Day 1**: Add schema_migrations table (2 hours)
- [x] **Day 2**: Fix silent failures + logging (1 hour)
- [x] **Day 3**: Write UPGRADING.md documentation (1 hour)
- [ ] **Day 4**: Test migrations on clean database
- [ ] **Day 5**: Test migrations on production clone

### Week 2: SQLite Migration (Priority 2)
- [ ] **Day 1-2**: Build migrate_sqlite_to_postgres.py (4 hours)
- [ ] **Day 3**: Test with real SQLite databases
- [ ] **Day 4**: Add transaction wrapping (2 hours)
- [ ] **Day 5**: Create migration test suite (3 hours)

### Future: Enhancements (Priority 3)
- [ ] Downgrade/rollback support
- [ ] Performance optimization
- [ ] Migration audit dashboard

---

## Success Metrics

### Before Improvements
- ❌ 0 migration tracking
- ❌ Silent failure rate unknown
- ❌ SQLite users: 0% upgrade path
- ❌ 0 migration tests
- ❌ 0 migration documentation

### After Priority 1 (Week 1)
- ✅ 100% migration tracking (schema_migrations)
- ✅ 0% silent failures (all logged)
- ⚠️ SQLite users: Still no upgrade path
- ✅ Migration documentation exists

### After Priority 2 (Week 2)
- ✅ SQLite users: 100% upgrade path
- ✅ 100% atomic migrations (transaction wrapped)
- ✅ 90%+ test coverage for migrations

---

## Conclusion

**Current State**: PostgreSQL users have automatic migrations, but no safety net. SQLite users are abandoned.

**Critical Issues**:
1. No version tracking (can't detect failures)
2. Silent migration failures (data corruption risk)
3. No SQLite → PostgreSQL migration (user abandonment)

**Recommendation**: Implement Priority 1 (Week 1) immediately. This adds schema version tracking and error visibility, preventing data corruption for all PostgreSQL users.

Priority 2 (Week 2) unblocks SQLite users and adds transaction safety.

**Total Effort**: 10-12 hours over 2 weeks
**Impact**: Eliminates all migration risks, unifies user base on PostgreSQL

**Status**: ⚠️ NEEDS IMMEDIATE ATTENTION (Priority 1 items critical)
