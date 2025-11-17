# DRY Refactoring Quick Start Guide

> **TL;DR:** Extract 10 repeated patterns to save ~1,500 lines and prevent bugs

## Priority Order

### 🔴 **Week 1: High Priority** (Do These First)

#### 1. Project Name Sanitization (2 hours)
**Current:** Duplicated 5 times across project management tools
```python
# BEFORE (repeated 5+ times):
import re
safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())
safe_name = re.sub(r'_+', '_', safe_name).strip('_')[:32]

# AFTER (extract to utility):
from src.utils.project_utils import sanitize_project_name
safe_name = sanitize_project_name(name)
```

**Files to create:**
- `src/utils/project_utils.py`
- `tests/test_project_utils.py`

**Tools to update:** 5 (switch_project, create_project, get_project_info, delete_project, select_project_for_session)

---

#### 2. JSON Response Builder (1 day)
**Current:** 145 `json.dumps()` calls with inconsistent structures
```python
# BEFORE (inconsistent):
return json.dumps({"success": True, "message": "Done"})
return json.dumps({"error": str(e)})
return json.dumps({"success": False, "error": "Invalid"})

# AFTER (standardized):
from src.utils.response_builder import ResponseBuilder
return ResponseBuilder.success("Done")
return ResponseBuilder.error(str(e))
return ResponseBuilder.error("Invalid")
```

**Files to create:**
- `src/utils/response_builder.py`
- `tests/test_response_builder.py`

**Tools to update:** ALL 47 tools (start with 10 as proof of concept)

---

#### 3. Database Connection Standardization (1 day)
**Current:** 3 different connection patterns, causing connection leaks
```python
# PATTERN A: ❌ BAD (4 occurrences)
conn = psycopg2.connect(config.database_url)
# ... work ...
conn.close()  # Often forgotten!

# PATTERN B: ❌ OK but verbose (5 occurrences)
adapter = _get_cached_adapter(schema_name)
conn = adapter.get_connection()
try:
    # ... work ...
finally:
    adapter.release_connection(conn)
    adapter.close()

# PATTERN C: ✅ BEST (15 occurrences - USE EVERYWHERE)
with _get_db_for_project(project) as conn:
    # ... work ...
    # Auto-closes!
```

**Action:** Migrate all Pattern A and B to Pattern C

**Tools to update:** ~25 tools using Pattern A/B

---

### 🟡 **Week 2: Medium Priority**

#### 4. Project Selection Decorator (4 hours)
**Current:** Repeated check in 13 tools
```python
# BEFORE (repeated 13 times):
@mcp.tool()
async def some_tool(project: Optional[str] = None) -> str:
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check
    # ... rest of logic ...

# AFTER (decorator handles it):
@mcp.tool()
@require_project_selection
async def some_tool(project: Optional[str] = None, **kwargs) -> str:
    resolved_project = kwargs['_resolved_project']
    # ... rest of logic ...
```

**Files to create:**
- `src/utils/decorators.py`
- `tests/test_decorators.py`

**Tools to update:** 13 memory/context tools

---

#### 5. Error Handling Decorator (1 day)
**Current:** Every tool has try-except boilerplate
```python
# BEFORE (repeated in all 47 tools):
@mcp.tool()
async def some_tool(param: str) -> str:
    import json  # ← Repeated!
    try:
        result = do_work(param)
        return json.dumps({"success": True, "result": result})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

# AFTER (decorator handles it):
@mcp.tool()
@tool_error_handler
async def some_tool(param: str) -> str:
    # No try-except needed!
    # No import json needed!
    result = do_work(param)
    return {"success": True, "result": result}
```

**Tools to update:** ALL 47 tools

---

#### 6. Transaction Context Manager (4 hours)
**Current:** 26 commits but only 4 rollbacks (missing error handling!)
```python
# BEFORE (error-prone):
try:
    conn.execute("INSERT ...")
    conn.execute("UPDATE ...")
    conn.commit()
except Exception as e:
    conn.rollback()  # ← Often forgotten!
    raise

# AFTER (automatic rollback):
with transaction(conn):
    conn.execute("INSERT ...")
    conn.execute("UPDATE ...")
    # Auto-commits on success, auto-rolls back on error!
```

**Files to create:**
- Add to `src/utils/db_helpers.py`

**Tools to update:** 26 tools with explicit commits

---

### 🟢 **Week 3: Low Priority** (Nice to Have)

#### 7. Logging Standardization (2 hours)
**Current:** 27 print statements, inconsistent format
```python
# BEFORE:
print(f"✅ Success", file=sys.stderr)
print(f"⚠️  Warning: {e}", file=sys.stderr)

# AFTER (use existing logger):
logger.info(f"✅ Success")
logger.warning(f"⚠️  Warning: {e}")
```

**Tools to update:** 27 print statements across codebase

---

#### 8. Import Cleanup (30 minutes)
**Current:** Duplicate imports in functions
```python
# BEFORE (in each function):
@mcp.tool()
async def tool_a() -> str:
    import json
    import re
    # ...

# AFTER (top-level only):
# Imports already at top (lines 15-28), just remove duplicates
```

**Files to update:** Remove 26 duplicate import statements

---

## File Structure After Refactoring

```
src/
├── utils/
│   ├── __init__.py
│   ├── project_utils.py         # NEW: sanitize_project_name()
│   ├── response_builder.py      # NEW: ResponseBuilder class
│   ├── db_helpers.py            # NEW: QueryHelper, transaction()
│   └── decorators.py            # NEW: @require_project_selection, @tool_error_handler
│
├── services/
│   └── ...
│
└── config.py

tests/
├── utils/
│   ├── test_project_utils.py
│   ├── test_response_builder.py
│   ├── test_db_helpers.py
│   └── test_decorators.py
│
└── ...
```

---

## Implementation Checklist

### Before Starting:
- [ ] Create branch: `refactor/dry-improvements`
- [ ] Run full test suite (record baseline)
- [ ] Set up test coverage monitoring

### Phase 1 (Week 1):
- [ ] Extract `sanitize_project_name()` utility
- [ ] Write tests for project utils
- [ ] Update 5 project management tools
- [ ] Extract `ResponseBuilder` class
- [ ] Write tests for response builder
- [ ] Update 10 tools as proof of concept
- [ ] Standardize connection management
- [ ] Audit all 47 tools for connection patterns
- [ ] Migrate Pattern A/B to Pattern C
- [ ] Run full test suite

### Phase 2 (Week 2):
- [ ] Create decorators module
- [ ] Implement `@require_project_selection`
- [ ] Update 13 memory tools
- [ ] Implement `@tool_error_handler`
- [ ] Update all 47 tools (gradual rollout)
- [ ] Roll out `ResponseBuilder` to remaining 37 tools
- [ ] Extract `transaction()` context manager
- [ ] Update 26 commit sites
- [ ] Run full test suite

### Phase 3 (Week 3):
- [ ] Replace print() with logger.*()
- [ ] Remove duplicate imports
- [ ] Update documentation
- [ ] Final test suite run
- [ ] Code review
- [ ] Merge to main

---

## Testing Strategy

### For Each Utility:
```python
# Example: test_project_utils.py
def test_sanitize_project_name_basic():
    assert sanitize_project_name("my-project") == "my_project"

def test_sanitize_project_name_special_chars():
    assert sanitize_project_name("My Project!@#") == "my_project"

def test_sanitize_project_name_max_length():
    long_name = "a" * 100
    assert len(sanitize_project_name(long_name)) == 32

def test_sanitize_project_name_collapse_underscores():
    assert sanitize_project_name("test___name") == "test_name"
```

### Regression Testing:
- Run existing test suite before and after each change
- Create snapshot tests for complex tools
- Verify MCP protocol compliance
- Check connection pool stats

---

## Expected Impact

### Code Metrics:
| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Total Lines | 9,925 | ~7,900 | -20% |
| Duplication | 15-20% | <5% | -75% |
| Connection Patterns | 3 | 1 | Standardized |
| Import Redundancy | 26 | 0 | Eliminated |

### Quality Improvements:
- ✅ Fewer connection leaks (more reliable)
- ✅ Consistent error messages (better UX)
- ✅ Easier to add new tools (copy pattern)
- ✅ Better testability (smaller functions)
- ✅ Clearer code intent (self-documenting decorators)

---

## Risk Mitigation

### High-Risk Changes:
1. **Connection Management** → Test thoroughly, monitor pool
2. **Error Handler Decorator** → Ensure response compatibility
3. **Transaction Manager** → Test rollback behavior

### Low-Risk Changes:
1. **Project Name Sanitization** → Pure function, easy to test
2. **Import Cleanup** → No runtime changes
3. **Logging** → No functional impact

---

## Common Pitfalls to Avoid

### ❌ Don't:
- Change error response schema without testing MCP clients
- Remove connection cleanup before adding new pattern
- Apply decorators to all tools at once (gradual rollout!)
- Skip tests ("I'll add them later")

### ✅ Do:
- Test each utility in isolation
- Migrate tools one at a time
- Keep old code until new code is verified
- Monitor connection pool usage
- Document breaking changes

---

## Quick Command Reference

```bash
# Create new utility module
touch src/utils/project_utils.py
touch tests/test_project_utils.py

# Run specific test
python3 -m pytest tests/test_project_utils.py -v

# Run all tests with coverage
python3 -m pytest --cov=src tests/

# Check for unused imports (after cleanup)
flake8 --select=F401 claude_mcp_hybrid_sessions.py

# Count duplicate patterns (before/after comparison)
grep -c "import json" claude_mcp_hybrid_sessions.py
grep -c "re.sub.*safe_name" claude_mcp_hybrid_sessions.py
```

---

## Need Help?

See full analysis: `DRY_ANALYSIS_REPORT.md`

**Questions?**
- Tool decorator examples → See existing `@breadcrumb` decorator
- Connection patterns → See `_get_db_for_project()` at line 599
- Response formats → Search for existing `json.dumps()` patterns
