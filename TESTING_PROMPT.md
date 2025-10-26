# Claude Dementia - Comprehensive Testing Prompt

**Purpose:** Test all 27 MCP tools with multi-project support and embedding features.

**Environment:** Claude Desktop
**Duration:** ~15-20 minutes
**Expected:** Systematic testing with clear success/failure reporting

---

## Testing Instructions for Claude

Please execute this comprehensive test suite for the Claude Dementia MCP server. Test each category systematically and report results in the format specified at the end.

---

## Phase 1: Project Management (6 tools)

### Test 1.1: Create Projects
```
Create two test projects:
1. Create a project named "test_alpha"
2. Create a project named "test_beta"

Expected: Both projects created successfully with schema names shown
```

### Test 1.2: List Projects
```
List all available projects

Expected: Should show at least test_alpha and test_beta with stats
```

### Test 1.3: Switch Projects
```
1. Switch to project "test_alpha"
2. Get the active project

Expected: Active project should be test_alpha
```

### Test 1.4: Get Project Info
```
Get detailed information for project "test_alpha"

Expected: Shows sessions, contexts, memories counts (all should be 0 for new project)
```

### Test 1.5: Project Isolation Test
```
1. Switch to "test_alpha"
2. Lock a context: content="Alpha project data", topic="alpha_context"
3. Switch to "test_beta"
4. Lock a context: content="Beta project data", topic="beta_context"
5. Recall "alpha_context" (should fail - wrong project)
6. Switch back to "test_alpha"
7. Recall "alpha_context" (should succeed)

Expected: Contexts are isolated per project
```

---

## Phase 2: Session Management (3 tools)

### Test 2.1: Wake Up
```
Wake up in project "test_alpha"

Expected: Shows session info, context counts, memory status
```

### Test 2.2: Create Handover (Sleep)
```
1. Lock a context with topic="important_work" and content="We completed the authentication module"
2. Sleep to create handover

Expected: Handover created with session summary
```

### Test 2.3: Get Last Handover
```
Get the last handover from project "test_alpha"

Expected: Returns handover with work completed, including the context we locked
```

---

## Phase 3: Context/RLM Tools (11 tools)

### Test 3.1: Lock Context (with auto-embedding)
```
Lock a context in test_alpha:
- topic: "database_config"
- content: "PostgreSQL connection pooling is configured with min 1 and max 10 connections. Uses psycopg2.pool.SimpleConnectionPool."
- priority: "important"

Expected: Context locked successfully with [embedded] indicator
```

### Test 3.2: Recall Context
```
Recall context "database_config" with preview mode

Expected: Returns preview with key_concepts and metadata
```

### Test 3.3: Batch Lock Contexts
```
Batch lock these contexts in test_alpha:
[
  {"topic": "api_v1", "content": "RESTful API with FastAPI. Endpoints: /users, /auth, /data. Uses JWT tokens.", "priority": "important"},
  {"topic": "auth_flow", "content": "OAuth 2.0 flow with refresh tokens. Token expiry: 1 hour. Refresh expiry: 30 days.", "tags": "security,auth"},
  {"topic": "deployment", "content": "Deploy using Docker containers on DigitalOcean App Platform. Auto-scaling enabled.", "priority": "reference"}
]

Expected: Summary shows 3 successful, 3 embedded
```

### Test 3.4: Batch Recall Contexts
```
Batch recall these contexts: ["api_v1", "auth_flow", "deployment"] with preview_only=true

Expected: Returns previews for all 3 contexts
```

### Test 3.5: Check Contexts (Semantic Search)
```
Check contexts with text: "How do we handle user authentication?"

Expected: Should find "auth_flow" and possibly "api_v1" using semantic search, with similarity scores
```

### Test 3.6: Search Contexts (Hybrid)
```
Search contexts with query: "database connections"

Expected: Should find "database_config" using semantic or keyword search, marked with search_mode
```

### Test 3.7: Semantic Search
```
Semantic search for query: "API endpoints and authentication"

Expected: Should find "api_v1" and "auth_flow" with similarity scores above 0.6
```

### Test 3.8: Explore Context Tree
```
Explore the context tree for project test_alpha

Expected: Shows hierarchical view of all locked contexts
```

### Test 3.9: Unlock Context
```
Unlock context "deployment"

Expected: Context deleted successfully
```

### Test 3.10: Memory Status
```
Get memory status for project test_alpha

Expected: Shows contexts count, embedding stats (X/Y with embeddings), session info
```

### Test 3.11: Context Dashboard
```
Get context dashboard for test_alpha

Expected: Visual dashboard with context distribution by priority, recent activity
```

---

## Phase 4: Memory & Analytics (2 tools)

### Test 4.1: Memory Analytics
```
Get memory analytics for project test_alpha

Expected: Detailed analytics with context growth, usage patterns, access frequency
```

### Test 4.2: Sync Project Memory
```
Sync project memory between test_alpha and test_beta

Expected: Shows sync status or operation details
```

---

## Phase 5: Embedding Tools (3 tools)

### Test 5.1: Generate Embeddings
```
Generate embeddings for all contexts in test_alpha that don't have them

Expected: Shows how many embeddings were generated
```

### Test 5.2: Embedding Status
```
Check embedding status for test_alpha

Expected: Shows embedding service info, model, dimensions, contexts with/without embeddings
```

### Test 5.3: Test Single Embedding
```
Test single embedding with text: "Testing the embedding service"

Expected: Shows embedding generated successfully with dimensions and sample values
```

---

## Phase 6: Admin/Debug Tools (3 tools)

### Test 6.1: Inspect Database
```
Inspect database for project test_alpha with mode="overview"

Expected: Shows database statistics, table counts, context summary
```

### Test 6.2: Inspect Database Schema
```
Inspect database schema for project test_alpha with mode="schema"

Expected: Shows all tables and their column definitions
```

### Test 6.3: Query Database
```
Query database in test_alpha: "SELECT COUNT(*) as total FROM context_locks"

Expected: Returns count of contexts in test_alpha project
```

### Test 6.4: Execute SQL (Dry Run)
```
Execute SQL with dry_run=true in test_alpha:
"UPDATE context_locks SET priority = 'always_check' WHERE label = 'database_config'"

Expected: Shows preview of what would be changed without executing
```

### Test 6.5: Manage Workspace Table
```
Manage workspace table in test_alpha:
- operation: "create"
- table_name: "test_results"
- schema: "id INTEGER PRIMARY KEY, test_name TEXT, status TEXT, timestamp REAL"
- dry_run: false
- confirm: true

Expected: Workspace table created successfully
```

---

## Phase 7: File Tools (4 tools)

### Test 7.1: Scan Project Files
```
Scan project files for test_alpha (if in a directory with files)

Expected: Shows files scanned, semantic tags generated, or graceful message if no filesystem access
```

### Test 7.2: Query Files
```
Query files in test_alpha with pattern "*.py"

Expected: Returns matching files with tags, or message about file scanning
```

### Test 7.3: Get File Clusters
```
Get file clusters for test_alpha

Expected: Shows related file groups, or message about file model
```

### Test 7.4: File Model Status
```
Get file model status for test_alpha

Expected: Shows file scanning statistics or indicates feature requires filesystem
```

---

## Phase 8: Cross-Project Operations

### Test 8.1: Cross-Project Isolation Verification
```
1. Switch to test_alpha
2. Memory status (should show contexts from alpha)
3. Switch to test_beta
4. Memory status (should show only beta contexts, not alpha)
5. List projects (should show both with different stats)

Expected: Complete isolation between projects verified
```

### Test 8.2: Multi-Project Context Search
```
1. Switch to test_alpha
2. Search contexts for "database"
3. Switch to test_beta
4. Search contexts for "database"

Expected: Different results per project (or no results in beta)
```

---

## Phase 9: Embedding Coverage Test

### Test 9.1: Auto-Embedding Verification
```
1. Lock a new context in test_beta: topic="new_feature", content="Implement real-time notifications using WebSockets"
2. Check result for [embedded] indicator
3. Memory status to verify embedding count increased

Expected: Context auto-embedded, memory status reflects it
```

### Test 9.2: Semantic Search Effectiveness
```
1. In test_alpha, semantic search for: "connecting to database"
2. Should find "database_config" even though exact words differ

Expected: Semantic similarity finds relevant context (similarity > 0.6)
```

### Test 9.3: Hybrid Search Comparison
```
1. Search contexts with use_semantic=true for "authentication"
2. Search contexts with use_semantic=false for "authentication"
3. Compare results

Expected: Both return results, semantic may have different ranking
```

---

## Phase 10: Error Handling & Edge Cases

### Test 10.1: Invalid Project
```
1. Try to switch to project "nonexistent_project"

Expected: Clear error message indicating project doesn't exist
```

### Test 10.2: Recall Nonexistent Context
```
Recall context "does_not_exist" from test_alpha

Expected: Clear error message, not a crash
```

### Test 10.3: Empty Search
```
Search contexts with empty query: ""

Expected: Returns all contexts or clear validation error
```

### Test 10.4: Batch Operations with Errors
```
Batch lock contexts with one invalid:
[
  {"topic": "valid1", "content": "Valid content"},
  {"topic": "invalid", "missing": "content field"},
  {"topic": "valid2", "content": "More valid content"}
]

Expected: Shows 2 successful, 1 failed with clear error message
```

---

## Phase 11: Cleanup

### Test 11.1: Delete Test Project
```
1. Delete project "test_beta" with confirm=false (should ask for confirmation)
2. Delete project "test_beta" with confirm=true (should succeed)
3. List projects (should no longer show test_beta)

Expected: Safe deletion with confirmation requirement
```

---

## Reporting Format

After completing all tests, please provide a summary in this format:

```markdown
# Claude Dementia Test Results

**Test Date:** [Date]
**Environment:** Claude Desktop
**Total Tests:** 50+

## Summary by Category

| Category | Tests | Passed | Failed | Skipped |
|----------|-------|--------|--------|---------|
| Project Management | 5 | X | X | X |
| Session Management | 3 | X | X | X |
| Context/RLM | 11 | X | X | X |
| Memory & Analytics | 2 | X | X | X |
| Embeddings | 3 | X | X | X |
| Admin/Debug | 5 | X | X | X |
| File Tools | 4 | X | X | X |
| Cross-Project | 2 | X | X | X |
| Embedding Coverage | 3 | X | X | X |
| Error Handling | 4 | X | X | X |
| Cleanup | 1 | X | X | X |

## Overall Score
**Passed:** X/50 (XX%)
**Failed:** X/50 (XX%)
**Skipped:** X/50 (XX%)

## Failed Tests Detail

### Test X.Y: [Test Name]
**Error:** [Detailed error message]
**Expected:** [What should have happened]
**Actual:** [What actually happened]
**Severity:** Critical/High/Medium/Low

[Repeat for each failed test]

## Bugs Discovered

### Bug #1: [Bug Title]
**Affected Tools:** [Tool names]
**Steps to Reproduce:**
1. [Step 1]
2. [Step 2]

**Expected Behavior:** [Description]
**Actual Behavior:** [Description]
**Error Message:** [If any]
**Severity:** Critical/High/Medium/Low
**Suggested Fix:** [If obvious]

[Repeat for each bug]

## Feature Observations

### Multi-Project Support
- ✅/❌ Projects create successfully
- ✅/❌ Context isolation works correctly
- ✅/❌ Project switching is smooth
- ✅/❌ Cross-project operations isolated

### Embedding System
- ✅/❌ Auto-embedding works on lock_context
- ✅/❌ Auto-embedding works on batch_lock_contexts
- ✅/❌ Semantic search finds relevant contexts
- ✅/❌ Graceful fallback when embeddings unavailable
- ✅/❌ Embedding stats accurate in memory_status

### Admin Tools
- ✅/❌ Database inspection works per project
- ✅/❌ SQL execution safe (dry-run works)
- ✅/❌ Workspace tables work per project

## Performance Notes
- Context locking speed: [Fast/Medium/Slow]
- Semantic search speed: [Fast/Medium/Slow]
- Batch operations efficiency: [Good/Acceptable/Poor]
- Cross-project switching: [Instant/Fast/Slow]

## Recommendations
1. [Any suggestions for improvements]
2. [Any features that need documentation]
3. [Any UX improvements needed]

## Conclusion
[Overall assessment of system stability, feature completeness, and readiness]
```

---

## Notes for Tester

**Important:**
- Test in a clean environment if possible
- Some file-related tests may not work in Claude Desktop (no filesystem access)
- If a test consistently fails, note it and continue
- Embedding tests require Voyage AI service to be available
- Admin tools are powerful - be careful with execute_sql
- Always use dry_run=true first for destructive operations

**Success Criteria:**
- ✅ All project isolation tests pass
- ✅ Auto-embedding works (shows [embedded] indicator)
- ✅ Semantic search finds relevant contexts
- ✅ No crashes or unhandled exceptions
- ✅ All 27 tools execute without errors

**What to Look For:**
- Clear error messages (not cryptic stack traces)
- Graceful degradation when features unavailable
- Consistent behavior across projects
- Embedding status accurately reflected
- Project parameter respected in all tools

---

Good luck testing! Please be thorough and report all issues, even minor UX problems.
