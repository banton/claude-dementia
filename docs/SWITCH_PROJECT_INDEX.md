# switch_project() Documentation Index

**Complete architecture documentation for refactoring**

Created: 2025-11-17
Function: `switch_project(name: str) -> str`
Location: `/home/user/claude-dementia/claude_mcp_hybrid_sessions.py:1995-2106`

---

## 📚 Documentation Suite

This documentation suite provides complete coverage of the `switch_project()` function for safe refactoring:

### 1. **Main Architecture Document**
**File:** `SWITCH_PROJECT_ARCHITECTURE.md`
**Purpose:** Comprehensive technical specification
**Use for:** Deep understanding, design decisions, implementation details

**Contents:**
- Complete dependency analysis
- Data flow diagrams
- Side effects documentation
- Integration points
- Critical connections
- Testing strategy
- Refactoring guidelines
- Performance considerations
- Security analysis
- Related functions
- Full function listing

**Read this when:**
- Starting refactoring work
- Need to understand function internals
- Writing tests
- Debugging issues
- Making architectural decisions

---

### 2. **Quick Reference Card**
**File:** `SWITCH_PROJECT_QUICK_REF.md`
**Purpose:** Fast lookup for critical information
**Use for:** Daily reference, quick checks, emergency fixes

**Contents:**
- Critical dependencies summary
- Data flow overview
- Side effects checklist
- Testing requirements
- Common failure modes
- Debug commands
- Refactoring safety rules
- Success criteria

**Read this when:**
- Need quick answer
- Debugging production issue
- Reviewing pull request
- Verifying test coverage
- Emergency troubleshooting

---

### 3. **Dependency Map**
**File:** `SWITCH_PROJECT_DEPENDENCY_MAP.md`
**Purpose:** Visual representation of all relationships
**Use for:** Understanding system integration, impact analysis

**Contents:**
- Global state dependency graph
- Database schema relationships
- Function call hierarchy
- Downstream consumer map
- Data transformation pipeline
- Critical path analysis
- Error propagation tree
- State consistency map
- Integration point matrix
- Refactoring impact analysis
- Testing dependency graph
- Session lifecycle integration

**Read this when:**
- Need to see big picture
- Planning refactoring scope
- Understanding data flows
- Identifying breaking changes
- Analyzing test coverage

---

## 🎯 Quick Navigation

### By Task

| Task | Primary Doc | Supporting Docs |
|------|-------------|-----------------|
| **Planning refactoring** | Dependency Map | Architecture, Quick Ref |
| **Writing code** | Architecture | Quick Ref |
| **Writing tests** | Architecture (Section 10) | Dependency Map (Section 11) |
| **Code review** | Quick Ref | Dependency Map |
| **Debugging** | Quick Ref | Architecture (Section 13) |
| **Understanding integration** | Dependency Map | Architecture (Section 5) |
| **Performance optimization** | Architecture (Section 14) | - |
| **Security review** | Architecture (Section 15) | - |

### By Question

| Question | Where to Find Answer |
|----------|---------------------|
| What globals does it use? | Architecture Section 2, Quick Ref |
| What does it write to database? | Dependency Map Section 2, Architecture Section 4.1 |
| What tools depend on this? | Dependency Map Section 4, Architecture Section 5.2 |
| How do I test it? | Architecture Section 10, Quick Ref |
| What can I safely change? | Quick Ref "Refactoring Safety" |
| What breaks if this fails? | Dependency Map Section 4, 6 |
| How do I debug issues? | Quick Ref "Debug Commands", Architecture Section 13 |
| What's the performance impact? | Architecture Section 14 |
| Are there security risks? | Architecture Section 15 |
| How does it fit in session flow? | Dependency Map Section 12 |

### By Audience

| Role | Start Here | Then Read |
|------|-----------|-----------|
| **Developer (refactoring)** | Architecture | Quick Ref (keep open) |
| **Reviewer (PR review)** | Quick Ref | Architecture Section 11 |
| **Tester (writing tests)** | Architecture Section 10 | Dependency Map Section 11 |
| **DevOps (debugging production)** | Quick Ref | Architecture Section 13 |
| **Architect (design review)** | Dependency Map | Architecture |
| **New team member (learning)** | Architecture | Dependency Map |

---

## 🚨 Critical Warnings

### Before Refactoring

**MUST READ:**
1. Architecture Section 8: Critical Connections (DO NOT BREAK)
2. Quick Ref: "MUST NOT Change"
3. Dependency Map Section 10: Refactoring Impact Analysis

**MUST TEST:**
1. Run `test_project_isolation_fix.py`
2. Verify stateless operation (clear cache test)
3. Check downstream tools (lock_context, etc.)

**MUST PRESERVE:**
- Same session ID for DB + cache updates (`_local_session_id`)
- Update order: Database → Cache
- Function signature
- Return JSON format

### Known Issues

**Bug #1 (Nov 2025):** Using different session IDs for DB and cache updates
- **Fixed by:** Using `_local_session_id` as single source of truth
- **Documented in:** `docs/PROJECT_SELECTION_REFACTOR.md`
- **Test for:** `test_project_isolation_fix.py`

**Risk Level:** 🔴 **HIGH** - This function is critical path for ALL tools

---

## 📊 Key Metrics

### Function Complexity
- Lines of code: 112
- Cyclomatic complexity: 7
- Database operations: 4 queries
- Global state mutations: 2
- External dependencies: 6

### Impact Scope
- Directly affects: 50+ tools
- Database tables touched: 1 write, 3+ reads
- Global variables modified: 1
- Integration points: 3 major

### Test Coverage
- Unit tests: 0 (currently integrated)
- Integration tests: 1 (`test_project_isolation_fix.py`)
- Manual test cases: 7 documented

---

## 🔄 Refactoring Workflow

### Phase 1: Preparation
1. ✅ Read all three documentation files
2. ✅ Run existing tests to establish baseline
3. ✅ Set up local test environment
4. ✅ Create feature branch

### Phase 2: Analysis
1. Map all dependencies (use Dependency Map)
2. Identify extraction opportunities
3. Design new function structure
4. Plan test strategy

### Phase 3: Implementation
1. Write unit tests for helpers (TDD)
2. Extract helper functions
3. Refactor main function
4. Maintain same behavior

### Phase 4: Validation
1. Run all tests (unit + integration)
2. Manual testing (switch + tools)
3. Performance comparison
4. Code review

### Phase 5: Documentation
1. Update architecture docs
2. Update API documentation
3. Update changelog
4. Document breaking changes (if any)

---

## 🧪 Testing Checklist

### Unit Tests (if extracting helpers)

```python
# Test name sanitization
def test_sanitize_project_name():
    assert _sanitize_project_name("My-Project 2024!") == "my_project_2024"
    assert _sanitize_project_name("test__123") == "test_123"
    assert _sanitize_project_name("A" * 50) == "a" * 32

# Test schema existence check
def test_schema_exists():
    assert _schema_exists("public") == True
    assert _schema_exists("nonexistent_xyz") == False

# Test project stats
def test_get_project_stats(test_schema):
    stats = _get_project_stats(test_schema)
    assert "sessions" in stats
    assert "contexts" in stats
```

### Integration Tests

```python
# Test basic switch
async def test_switch_project_basic():
    result = await switch_project("test_proj")
    data = json.loads(result)
    assert data["success"] == True

# Test persistence (CRITICAL!)
async def test_switch_project_persistence():
    await switch_project("proj_a")
    _active_projects.clear()
    project = _get_project_for_context()
    assert project == "proj_a"

# Test downstream integration
async def test_switch_affects_tools():
    await switch_project("proj_b")
    result = await lock_context("test", "topic")
    assert "proj_b" in result
```

### Manual Tests

1. Switch to existing project → verify stats displayed
2. Switch to non-existent project → verify "will be created" message
3. Clear cache + use tool → verify reads from DB
4. Error cases: no session, invalid session, DB down
5. Performance: time before/after refactoring

---

## 📈 Success Metrics

### Before Merging PR

- [ ] All tests pass (existing + new)
- [ ] Code coverage maintained or improved
- [ ] Performance maintained or improved
- [ ] No breaking changes to API
- [ ] Documentation updated
- [ ] Code review approved
- [ ] Manual testing completed

### Post-Deployment Monitoring

- [ ] No increase in error rates
- [ ] No regression in response times
- [ ] No new bug reports
- [ ] Session switching works in production
- [ ] Downstream tools work correctly

---

## 🔗 Related Documentation

### Project-Level Docs
- `README.md` - Overall project documentation
- `CLAUDE.md` - Development guide
- `docs/PROJECT_SELECTION_REFACTOR.md` - Bug #1 fix documentation
- `TOOL_INTEROP_MAP.md` - Tool interaction patterns

### Code Files
- `claude_mcp_hybrid_sessions.py` - Main MCP server
- `mcp_session_store.py` - Session persistence
- `postgres_adapter.py` - Database layer
- `src/config.py` - Configuration

### Test Files
- `test_project_isolation_fix.py` - Integration test
- `tests/` - Test suite directory

---

## 🛠️ Maintenance Guide

### When to Update These Docs

**Update immediately if:**
- Function signature changes
- New dependencies added
- Database schema changes
- Critical bug discovered
- Major refactoring completed

**Review quarterly for:**
- Outdated examples
- New best practices
- Performance improvements
- Security updates

### How to Update

1. **Architecture Doc:** Add new sections, update existing
2. **Quick Ref:** Keep concise, remove obsolete info
3. **Dependency Map:** Update diagrams, check all arrows
4. **This Index:** Add new sections, update metrics

---

## 📞 Help & Support

### Questions About Documentation

- **Missing info?** Add to backlog, update docs
- **Confusing section?** Rewrite for clarity
- **Outdated info?** Verify and update
- **Found bug?** Document in Known Issues

### Questions About Code

- **How does X work?** → Architecture Doc
- **What breaks if Y?** → Dependency Map
- **Quick check on Z?** → Quick Ref
- **Need test case?** → Architecture Section 10

---

## 📅 Version History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-11-17 | 1.0 | Initial documentation suite created | Claude |

---

## 🎓 Learning Path

**For someone new to this function:**

1. **Day 1: Overview**
   - Read this index (10 min)
   - Skim Quick Ref (15 min)
   - Read function docstring (5 min)

2. **Day 2: Deep Dive**
   - Read Architecture Doc sections 1-5 (60 min)
   - Study Dependency Map sections 1-4 (45 min)
   - Run test_project_isolation_fix.py (15 min)

3. **Day 3: Hands-On**
   - Read Architecture sections 6-11 (60 min)
   - Try manual testing (30 min)
   - Review related functions (30 min)

4. **Day 4: Refactoring Prep**
   - Study Architecture section 11 (refactoring) (45 min)
   - Review Dependency Map section 10 (impact) (30 min)
   - Plan approach (45 min)

**Total time investment:** ~6 hours for complete mastery

---

## 🎯 TL;DR (Too Long; Didn't Read)

**What is it?**
`switch_project()` changes which PostgreSQL schema is used for all memory operations.

**Why is it critical?**
ALL 50+ tools depend on this working correctly. If it breaks, everything breaks.

**What MUST work?**
1. Update database: `mcp_sessions.project_name`
2. Update cache: `_active_projects[session_id]`
3. Use SAME session ID for both
4. Update database BEFORE cache

**How to refactor safely?**
1. Read Quick Ref "MUST NOT Change" section
2. Extract helpers with tests
3. Maintain exact behavior
4. Test thoroughly (especially stateless mode)

**What breaks if this fails?**
- All lock_context calls
- All recall_context calls
- All memory tools
- All session tools
- Project isolation

**Risk level?**
🔴 **HIGHEST** - Test everything, twice!

---

**END OF INDEX**

Start with the Quick Ref for immediate needs, dive into Architecture for details, use Dependency Map for big picture!
