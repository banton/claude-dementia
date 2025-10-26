# Claude Dementia System Audit - User Experience Perspective

**Date:** 2025-01-26
**Status:** Post-PostgreSQL Migration, Pre-Project Integration

---

## Executive Summary

**Current State:**
- 37 MCP tools available
- Project management (CRUD) implemented but disconnected
- Multi-project isolation broken for Claude Desktop users
- Feature creep with developer/debug tools exposed to end users

**Critical Issues:**
1. **Project isolation doesn't work** - Tools don't know which project to use
2. **Too many tools** - Overwhelming, unclear which to use
3. **No project switching** - Can't tell system "work on project X now"
4. **Developer tools exposed** - SQL queries, diagnostics mixed with user tools

---

## Tool Inventory (37 Total)

### Core User Features (8 tools)
✅ **Session Management**
- `wake_up()` - Initialize session, load context
- `sleep()` - Create handover for next session
- `get_last_handover()` - Retrieve previous handover

✅ **Context Management (RLM)**
- `lock_context()` - Store context for perfect recall
- `recall_context()` - Retrieve locked context
- `unlock_context()` - Delete context
- `check_contexts()` - Find relevant contexts
- `explore_context_tree()` - Browse context hierarchy

### Project Management (4 tools) - NEW, DISCONNECTED
⚠️ **Project CRUD**
- `create_project(name)` - Create project schema
- `list_projects()` - List all projects
- `get_project_info(name)` - Get project details
- `delete_project(name)` - Delete project

**PROBLEM:** These tools exist but nothing uses them!

### Memory/Analytics (4 tools)
📊 **Memory Tracking**
- `memory_status()` - Show memory system status
- `memory_analytics()` - Detailed analytics
- `context_dashboard()` - Visual dashboard
- (missing: `memory_update()` - should exist)

### File Management (5 tools)
📁 **File Scanning**
- `scan_project_files()` - Scan and tag files
- `scan_and_analyze_directory()` - Recursive scan
- `query_files()` - Search tagged files
- `file_model_status()` - File model stats
- `get_file_clusters()` - Find related files

**Note:** Filesystem-dependent, won't work in Claude Desktop

### Advanced Context Tools (5 tools)
🔍 **Search & Batch**
- `search_contexts()` - Search by keywords
- `semantic_search_contexts()` - Semantic similarity search
- `batch_lock_contexts()` - Lock multiple at once
- `batch_recall_contexts()` - Recall multiple
- `ai_summarize_context()` - AI-powered summaries

### Workspace/Tagging (1 tool)
🏷️ **Workspace Management**
- `manage_workspace_table()` - Manage workspace tags

**Question:** What is this? How does user use it?

### Developer/Debug Tools (6 tools) ⚠️
🛠️ **Database Tools** (DANGEROUS)
- `query_database()` - Run SQL queries
- `execute_sql()` - Execute SQL commands
- `inspect_database()` - Inspect schema

🧪 **Embedding Diagnostics**
- `generate_embeddings()` - Generate embeddings
- `test_single_embedding()` - Test embedding
- `embedding_status()` - Embedding service status
- `diagnose_ollama()` - Diagnose Ollama (DISABLED)

**PROBLEM:** These are admin/developer tools, shouldn't be exposed to Claude!

### Cost/Analytics (2 tools)
💰 **Usage Tracking**
- `cost_comparison()` - Compare costs
- `usage_statistics()` - Usage stats

### Pagination (1 tool)
📄 **Query Pagination**
- `get_query_page()` - Get paginated results

### Sync (1 tool)
🔄 **Project Sync**
- `sync_project_memory()` - Sync memory across projects?

**Question:** What does this do? How does user use it?

---

## Critical User Journey Gaps

### Scenario 1: Claude Desktop User with Multiple Projects

**User Goal:** Track context separately for "innkeeper" and "linkedin" projects

**Current Experience:**
```
User: "Create a project called innkeeper"
Claude: ✅ Project created!

User: "Lock this API specification"
Claude: [calls lock_context(...)]
❌ FAILS: Context goes to wrong project (auto-detected schema)

User: "Switch to linkedin project"
Claude: ❌ No way to switch projects!
```

**WHY IT FAILS:**
- `lock_context()` has NO project parameter
- Uses auto-detected schema from `os.getcwd()`
- In Claude Desktop, `os.getcwd()` is fixed (wherever server started)
- No concept of "active project" for the session

**WHAT'S NEEDED:**
1. Add `project` parameter to lock_context, recall_context, wake_up, etc.
2. OR: Add session-level "active project" that tools use by default
3. User must be able to switch projects conversationally

### Scenario 2: First-Time Claude Desktop User

**User Goal:** "I want Claude to remember important things"

**Current Experience:**
```
User: "Help me set up Dementia"
Claude: ❌ What should I do first?
       - Create a project? What's a project?
       - Just start using wake_up()? Which project?
       - What if I have multiple projects later?
```

**WHY IT FAILS:**
- No clear onboarding flow
- User doesn't understand "projects" yet
- Should default to "default" project for simple use case

**WHAT'S NEEDED:**
1. Default project behavior (implicit "default" project)
2. Clear onboarding: "I'll remember things for you. If you have multiple projects, tell me which one."
3. Progressive disclosure: start simple, add projects later

### Scenario 3: Claude Code User (has filesystem)

**User Goal:** Auto-detect project from working directory

**Current Experience:**
```
Working dir: /Users/banton/Sites/innkeeper/
User: "Lock this context"
Claude: [calls lock_context(...)]
✅ Works - uses schema "innkeeper" (auto-detected from git repo name)

BUT THEN:
User in Claude Desktop: "Recall that context"
❌ FAILS: Claude Desktop can't auto-detect directory
```

**WHY IT FAILS:**
- Auto-detection works in Claude Code
- But breaks in Claude Desktop
- Contexts are stored in "innkeeper" schema
- Claude Desktop has no way to access that schema

**WHAT'S NEEDED:**
- Consistent behavior across Claude Code and Claude Desktop
- Explicit project parameter > auto-detection
- Auto-detection only as fallback when project not specified

---

## Architecture Problems

### Problem 1: Project Isolation is Broken

**Current Implementation:**
```python
# postgres_adapter.py
def _get_schema_name(self):
    # Auto-detect from git repo or directory
    project_name = self._detect_project_name()  # Uses os.getcwd()
    return sanitize(project_name)
```

**Issue:**
- Claude Desktop: `os.getcwd()` returns fixed path (app directory?)
- Always uses same schema
- Projects exist but can't switch between them

**Solution Options:**

**Option A: Add project parameter everywhere**
```python
@mcp.tool()
async def lock_context(content: str, label: str, project: str = "default"):
    # Connect to specific project schema
    adapter = PostgreSQLAdapter(schema=project)
    ...
```

**Option B: Session-level active project**
```python
@mcp.tool()
async def switch_project(name: str):
    global _active_project
    _active_project = name
    return f"Switched to {name}"

@mcp.tool()
async def lock_context(content: str, label: str):
    # Uses _active_project automatically
    adapter = PostgreSQLAdapter(schema=_active_project)
    ...
```

**Option C: Hybrid (RECOMMENDED)**
```python
@mcp.tool()
async def lock_context(content: str, label: str, project: str = None):
    # 1. Explicit parameter wins
    # 2. Fall back to session active project
    # 3. Fall back to auto-detect (Claude Code)
    # 4. Fall back to "default"

    if not project:
        project = _get_active_project_for_session()

    adapter = PostgreSQLAdapter(schema=project)
    ...
```

### Problem 2: Too Many Tools (37 total)

**Current State:**
- User-facing tools (8)
- Developer tools (6) - shouldn't be exposed
- Advanced tools (10) - for power users
- Unclear tools (2) - manage_workspace_table, sync_project_memory

**Proposed Categorization:**

**Tier 1: Essential (10 tools)**
- Session: wake_up, sleep, get_last_handover
- Context: lock_context, recall_context, check_contexts, explore_context_tree
- Projects: create_project, list_projects, switch_project (NEW)

**Tier 2: Advanced (8 tools)**
- unlock_context, batch_lock_contexts, batch_recall_contexts
- search_contexts, semantic_search_contexts, ai_summarize_context
- memory_status, get_project_info

**Tier 3: Power User (6 tools)**
- File: scan_project_files, query_files, get_file_clusters
- Analytics: memory_analytics, context_dashboard, usage_statistics

**Tier 4: Admin Only (6 tools) - HIDE FROM CLAUDE**
- Database: query_database, execute_sql, inspect_database
- Debug: generate_embeddings, test_single_embedding, diagnose_ollama

**Tier 5: Unknown/Review (7 tools)**
- manage_workspace_table (what is this?)
- sync_project_memory (what is this?)
- file_model_status
- scan_and_analyze_directory
- delete_project
- cost_comparison
- get_query_page (should be internal)
- embedding_status

### Problem 3: Ollama Tools Exist But Ollama Disabled

**Tools That Won't Work:**
- `diagnose_ollama()` - Ollama is disabled in config
- `test_single_embedding()` - References Ollama
- `embedding_status()` - Shows Ollama status

**Solution:**
- Remove or disable these tools
- OR: Fix them to work with Voyage AI only
- OR: Keep for future local mode restoration

---

## User Experience Recommendations

### Recommendation 1: Fix Project Integration (CRITICAL)

**Actions:**
1. Add `project` parameter to ALL context tools:
   - lock_context, recall_context, unlock_context
   - check_contexts, search_contexts, semantic_search_contexts
   - wake_up, sleep
   - All batch operations

2. Add session-level active project tracking:
   - switch_project(name) tool
   - get_active_project() tool (or part of wake_up)

3. Fallback logic:
   ```
   project = explicit_parameter
          OR session_active_project
          OR auto_detect_from_filesystem  # Claude Code only
          OR "default"
   ```

4. Test user journeys:
   - Claude Desktop multi-project
   - Claude Code multi-project
   - Single project user (should just work with "default")

### Recommendation 2: Simplify Tool Surface

**Actions:**
1. Hide admin/debug tools from Claude:
   - Move to separate admin mode or remove from MCP
   - query_database, execute_sql, inspect_database
   - generate_embeddings, test_single_embedding

2. Document tool tiers clearly:
   - Essential tools (always visible)
   - Advanced tools (show when relevant)
   - Power user tools (Claude Code only?)

3. Remove or fix Ollama-dependent tools

### Recommendation 3: Clear Onboarding

**Actions:**
1. Default project behavior:
   - First-time user: automatically uses "default" project
   - No need to create project explicitly

2. wake_up() should explain projects:
   ```json
   {
     "message": "Currently using project: default",
     "note": "You have 3 projects. Use list_projects() to see them."
   }
   ```

3. Progressive disclosure:
   - Simple: "I remember things for you"
   - Advanced: "I can track multiple projects separately"

### Recommendation 4: Consistent Naming & Behavior

**Current Inconsistencies:**
- `lock_context()` vs `batch_lock_contexts()` (plural)
- `recall_context()` vs `batch_recall_contexts()`
- Some tools return JSON strings, others return dicts
- Schema naming: simplified but old schemas still exist

**Actions:**
1. Consistent naming convention
2. Consistent return types (always JSON strings?)
3. Clean up old schemas (migration tool?)

---

## Next Steps (Priority Order)

### Phase 1: Fix Critical (Week 1)
1. ✅ Add switch_project() tool
2. ✅ Add project parameter to core tools (lock, recall, wake_up)
3. ✅ Test multi-project workflow in Claude Desktop
4. ✅ Test multi-project workflow in Claude Code

### Phase 2: Simplify (Week 2)
1. ⬜ Hide admin tools from Claude
2. ⬜ Remove/fix Ollama tools
3. ⬜ Document tool tiers
4. ⬜ Review and remove unknown tools

### Phase 3: Polish (Week 3)
1. ⬜ Improve wake_up() onboarding
2. ⬜ Default project behavior
3. ⬜ Consistent return types
4. ⬜ Migration tool for old schemas

### Phase 4: Documentation (Ongoing)
1. ⬜ User guide for each tool
2. ⬜ Example workflows
3. ⬜ Troubleshooting guide
4. ⬜ Migration guide from old version

---

## Questions for User

1. **Project Parameter Strategy:**
   - Option A: Add `project` param to every tool
   - Option B: Session-level active project (switch_project)
   - Option C: Hybrid (both)
   - **Recommendation:** Option C (most flexible)

2. **Unknown Tools:**
   - What is `manage_workspace_table()`?
   - What is `sync_project_memory()`?
   - Should we keep or remove?

3. **Admin Tools:**
   - Hide from Claude (make CLI-only)?
   - Remove entirely?
   - Keep but add warnings?

4. **Default Project:**
   - Should new users get "default" project auto-created?
   - Or require explicit project creation?
   - **Recommendation:** Auto-create "default"

5. **Old Schemas:**
   - Clean up old test schemas (user_*, local_*, etc.)?
   - Provide migration tool?
   - Leave as-is?
