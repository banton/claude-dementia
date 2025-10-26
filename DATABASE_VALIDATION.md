# Database Validation Design

## Problem Statement

After implementing multi-project isolation, we need to ensure that the initialization script (`wake_up()`) always confirms it's using the correct database for the current project, and can detect/report any isolation violations.

## Database "Rightness" Parameters

A database is considered "right" for the current project when:

### 1. Path Correctness ✅
**Definition**: Database path is calculated dynamically from current working directory

**Validation**:
```python
current_cwd = os.getcwd()
expected_hash = hashlib.md5(current_cwd.encode()).hexdigest()[:8]
actual_db_path = get_current_db_path()
expected_db_path = f"~/.claude-dementia/{expected_hash}.db"

assert actual_db_path == expected_db_path
```

**What This Catches**:
- Stale static database paths
- Database path not recalculated per call
- Fallback database being used unexpectedly

---

### 2. Hash Consistency ✅
**Definition**: Database filename hash matches MD5 of current directory path

**Validation**:
```python
current_cwd = os.getcwd()
calculated_hash = hashlib.md5(current_cwd.encode()).hexdigest()[:8]
db_filename = os.path.basename(actual_db_path)  # e.g., "832c1a38.db"
db_hash = db_filename.replace('.db', '')

assert db_hash == calculated_hash
```

**What This Catches**:
- Wrong database file being opened
- Database file from different project
- Hash calculation errors

---

### 3. Session Alignment ✅
**Definition**: Session's `project_fingerprint` matches current project's fingerprint

**Validation**:
```python
current_project_root = get_project_root()
current_project_name = get_project_name()
expected_fingerprint = hashlib.md5(
    f"{current_project_root}:{current_project_name}".encode()
).hexdigest()[:8]

session = get_current_session()
actual_fingerprint = session['project_fingerprint']

assert actual_fingerprint == expected_fingerprint
```

**What This Catches**:
- Session created for different project
- Session fingerprint stale or incorrect
- Multiple projects sharing same session

---

### 4. Path Mapping Accuracy ✅
**Definition**: Entry in `~/.claude-dementia/path_mapping.json` matches current directory

**Validation**:
```python
mapping_file = "~/.claude-dementia/path_mapping.json"
with open(mapping_file) as f:
    mappings = json.load(f)

expected_entry = {
    "path": current_cwd,
    "name": os.path.basename(current_cwd),
    "last_used": <timestamp>
}

assert mappings[db_hash] == expected_entry
```

**What This Catches**:
- Mapping file out of sync
- Hash collision (different path, same hash)
- Stale mapping entries

---

### 5. Context Isolation ✅
**Definition**: All contexts in database belong to current session only (no contamination)

**Validation**:
```python
# Query all contexts in database
all_contexts = conn.execute(
    "SELECT DISTINCT session_id FROM context_locks"
).fetchall()

current_session_id = get_current_session_id()

# Should only have contexts for current session
foreign_sessions = [s for s in all_contexts if s != current_session_id]

assert len(foreign_sessions) == 0, f"Found {len(foreign_sessions)} foreign sessions"
```

**What This Catches**:
- Cross-project contamination
- Old contexts from previous project
- Database accidentally shared between projects

---

### 6. Schema Integrity ✅
**Definition**: Database has all required tables and columns

**Validation**:
```python
required_tables = [
    'sessions',
    'context_locks',
    'audit_trail',
    'handovers',
    'file_model',
    'file_change_history'
]

for table in required_tables:
    cursor = conn.execute(
        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
    )
    assert cursor.fetchone() is not None

# Check critical columns
cursor = conn.execute("PRAGMA table_info(sessions)")
session_columns = [col[1] for col in cursor.fetchall()]
assert 'project_fingerprint' in session_columns
assert 'project_path' in session_columns
assert 'project_name' in session_columns
```

**What This Catches**:
- Missing tables (incomplete migration)
- Missing columns (old schema version)
- Corrupted database

---

### 7. No Orphaned Data ⚠️
**Definition**: All contexts reference valid session_id, no orphaned records

**Validation**:
```python
# Find contexts without valid session
orphaned = conn.execute("""
    SELECT cl.id, cl.label
    FROM context_locks cl
    LEFT JOIN sessions s ON cl.session_id = s.id
    WHERE s.id IS NULL
""").fetchall()

assert len(orphaned) == 0, f"Found {len(orphaned)} orphaned contexts"
```

**What This Catches**:
- Deleted sessions with lingering contexts
- Database corruption
- Manual database edits gone wrong

---

### 8. Session Metadata Consistency ✅
**Definition**: Session record matches current runtime parameters

**Validation**:
```python
session = get_current_session()

assert session['project_path'] == get_project_root()
assert session['project_name'] == get_project_name()
assert session['project_fingerprint'] == calculate_fingerprint()

# Check last_active is recent (updated this session)
time_since_active = time.time() - session['last_active']
assert time_since_active < 60  # Should have been updated within last minute
```

**What This Catches**:
- Session metadata out of sync
- Project moved but session not updated
- Stale session data

---

## Validation Levels

### Level 1: Critical (MUST PASS) 🔴
Failures indicate serious isolation violations that could leak data:
- Hash Consistency
- Session Alignment
- Context Isolation

**Action on Failure**: Refuse to operate, alert user, require manual fix

### Level 2: Important (SHOULD PASS) 🟡
Failures indicate system inconsistencies but may be recoverable:
- Path Correctness
- Path Mapping Accuracy
- Session Metadata Consistency

**Action on Failure**: Warn user, auto-fix if possible, log issue

### Level 3: Informational (NICE TO HAVE) 🟢
Failures indicate potential issues but not critical:
- No Orphaned Data
- Schema Integrity (auto-fixable via migrations)

**Action on Failure**: Log warning, attempt auto-repair

---

## Implementation Plan

### Function: `validate_database_isolation()`

Returns validation report:
```python
{
    "valid": True/False,
    "level": "critical" | "important" | "informational",
    "checks": {
        "path_correctness": {
            "passed": True,
            "expected": "~/.claude-dementia/832c1a38.db",
            "actual": "~/.claude-dementia/832c1a38.db"
        },
        "hash_consistency": {
            "passed": True,
            "expected_hash": "832c1a38",
            "actual_hash": "832c1a38",
            "directory": "/Users/banton/Sites/linkedin"
        },
        "session_alignment": {
            "passed": True,
            "expected_fingerprint": "832c1a38",
            "actual_fingerprint": "832c1a38"
        },
        "context_isolation": {
            "passed": True,
            "current_session": "link_12345678",
            "foreign_sessions": []
        },
        "schema_integrity": {
            "passed": True,
            "missing_tables": [],
            "missing_columns": []
        }
    },
    "warnings": [],
    "errors": [],
    "recommendations": []
}
```

### Integration with wake_up()

Add validation section to wake_up() output:
```python
session_data = {
    # ... existing fields ...
    "database_validation": {
        "status": "valid" | "warning" | "error",
        "checks_passed": 5,
        "checks_total": 7,
        "issues": [...],
        "last_validated": timestamp
    }
}
```

---

## Testing Strategy

### Test 1: Normal Operation
**Setup**: Fresh project, clean database
**Expected**: All checks pass ✅

### Test 2: Wrong Database
**Setup**: Manually point to different project's database
**Expected**: Hash consistency fails, session alignment fails 🔴

### Test 3: Contaminated Database
**Setup**: Add contexts from different session to database
**Expected**: Context isolation fails 🔴

### Test 4: Moved Project
**Setup**: Project moved to different path after session creation
**Expected**: Session metadata updates automatically 🟡

### Test 5: Corrupted Database
**Setup**: Delete critical columns from database
**Expected**: Schema integrity fails 🟢

### Test 6: Path Mapping Mismatch
**Setup**: Manually edit path_mapping.json with wrong path
**Expected**: Path mapping accuracy fails 🟡

---

## Error Messages

### Critical Failure Example
```
🔴 DATABASE ISOLATION VIOLATION DETECTED

Your database contains contexts from a different project:
- Current project: linkedin (/Users/banton/Sites/linkedin)
- Foreign sessions found: innk_87654321 (innkeeper-claude)
- Contaminated contexts: 42

This is a critical security issue. Your contexts may have leaked between projects.

RECOMMENDED ACTIONS:
1. Switch to the correct project directory
2. Run: dementia:validate_database_isolation()
3. If issue persists: dementia:emergency_database_reset()

DO NOT PROCEED with locking new contexts until this is resolved.
```

### Warning Example
```
⚠️ DATABASE VALIDATION WARNING

Session metadata is out of sync with current project:
- Session project_path: /Users/banton/Sites/old-location
- Current project_path: /Users/banton/Sites/new-location

This usually happens when a project is moved or renamed.

AUTO-FIX AVAILABLE: Session metadata will be updated automatically.
```

---

## Configuration

Add settings for validation behavior:
```python
VALIDATION_CONFIG = {
    "run_on_wake_up": True,              # Validate during wake_up()
    "fail_on_critical": True,            # Refuse to operate on critical failures
    "auto_fix_important": True,          # Try to fix important-level issues
    "log_informational": True,           # Log informational issues
    "detailed_output": False             # Include full validation report
}
```

---

## Future Enhancements

### 1. Validation Command
```python
dementia:validate_database_isolation(
    detailed=True,
    auto_fix=True
)
```

### 2. Continuous Monitoring
Track validation history:
```sql
CREATE TABLE validation_history (
    id INTEGER PRIMARY KEY,
    timestamp REAL,
    session_id TEXT,
    status TEXT,
    issues_found INTEGER,
    auto_fixed INTEGER
)
```

### 3. Health Dashboard
```python
dementia:database_health_dashboard()
# Shows:
# - Last validation: 2 minutes ago ✅
# - Issues detected: 0
# - Auto-fixes applied: 1 (session metadata updated)
# - Database size: 2.3 MB
# - Context count: 42
# - Foreign sessions: 0 ✅
```

---

## Summary

**Rightness Parameters** (8 total):
1. ✅ Path Correctness
2. ✅ Hash Consistency
3. ✅ Session Alignment
4. ✅ Path Mapping Accuracy
5. ✅ Context Isolation
6. ✅ Schema Integrity
7. ⚠️ No Orphaned Data
8. ✅ Session Metadata Consistency

**Validation Levels**:
- 🔴 Critical (3 checks) - Must pass or refuse operation
- 🟡 Important (3 checks) - Warn and auto-fix
- 🟢 Informational (2 checks) - Log and repair

**Integration Points**:
- Runs automatically during `wake_up()`
- Results included in session data (summary only)
- Internal function (not exposed as MCP tool)
- Auto-fix capabilities for non-critical issues (future enhancement)

---

## Implementation Status ✅

**Completed Features** (2024-10-26):

1. ✅ **Internal Validation Function** (`validate_database_isolation()`)
   - All 8 checks implemented
   - Comprehensive error detection
   - Detailed reporting with recommendations
   - Internal only (not exposed as MCP tool)

2. ✅ **Integration with wake_up()**
   - Automatic validation on session start
   - Summary included in wake_up() output
   - Non-blocking (informational only)
   - Shows errors/warnings if detected

3. ✅ **Testing**
   - Validated on claude-dementia project (project-local DB)
   - Validated on LinkedIn project (user cache DB)
   - Correctly detects contamination and schema issues

---

## Usage

### Automatic Validation

Database validation runs automatically during `wake_up()`:

```python
# In Claude Desktop:
dementia:wake_up()
```

**wake_up() Output - Healthy Database:**
```json
{
  "session": {
    "id": "link_12345678",
    "project_name": "linkedin",
    "database": "~/.claude-dementia/832c1a38.db"
  },
  "database_validation": {
    "status": "valid",
    "checks_passed": 8,
    "checks_total": 8,
    "errors": [],
    "warnings": []
  },
  ...
}
```

**wake_up() Output - Contaminated Database:**
```json
{
  "session": {
    "id": "link_12345678",
    "project_name": "linkedin",
    "database": "~/.claude-dementia/832c1a38.db"
  },
  "database_validation": {
    "status": "critical",
    "checks_passed": 5,
    "checks_total": 8,
    "errors": [
      "CONTEXT CONTAMINATION DETECTED: Found 1 foreign sessions in database!"
    ],
    "warnings": [],
    "recommendations": [
      "Your database contains contexts from other projects. This is a critical isolation violation.",
      "  - Session innk_87654321: 42 contexts"
    ]
  },
  ...
}
```

The validation summary shows immediately if there are any isolation issues. No need to call a separate tool.

---

## Test Results

### Test 1: claude-dementia Project (Project-Local DB)
**Database**: `.claude-memory.db` (project-local)
**Result**: 2/8 checks passed (expected for non-standard setup)
**Issues Found**:
- Hash consistency failed (uses project-local DB)
- Context contamination (2 foreign sessions from old versions)
- Missing tables (audit_trail, handovers, file_model)

**Analysis**: Correctly identifies non-standard database setup.

### Test 2: LinkedIn Project (User Cache DB)
**Database**: `~/.claude-dementia/832c1a38.db`
**Result**: 7/8 checks passed ✅
**Issues Found**:
- 1 minor warning (path mapping)

**Analysis**: Clean database, proper isolation working correctly.

---

*Last updated: 2024-10-26 (v3.4 - Database Validation Implementation Complete)*
