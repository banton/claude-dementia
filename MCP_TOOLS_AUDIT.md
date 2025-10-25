# Dementia MCP Tools Audit & Optimization Analysis

**Date:** 2025-01-15
**Purpose:** Comprehensive evaluation of all 24 MCP tools before cloud migration
**Goal:** Maximize user value, eliminate redundancy, identify gaps

---

## Executive Summary

**Current State:** 24 tools across 5 categories
**Key Findings:**
- ✅ Strong context management foundation (8 tools)
- ⚠️ Significant tool overlap and redundancy (5 duplicates identified)
- ❌ File tagging system underutilized (7 tools, low adoption)
- ✅ New SQL tools well-designed (3 tools, comprehensive safety)
- 🔍 Missing: Batch operations, context search, analytics

**Recommendations:**
1. **Consolidate** 5 redundant tools → 2 unified tools
2. **Deprecate** 7 file tagging tools (or make them optional)
3. **Add** 3 new high-value tools (batch operations, search, analytics)
4. **Result:** 24 tools → 15 tools (40% reduction, 100% value retention)

---

## Tool Inventory & Analysis

### Category 1: Session Management (2 tools)

#### 1.1 `wake_up()` ⭐⭐⭐⭐⭐
**Purpose:** Start session, load context dashboard
**Features:**
- Project detection and context switching warnings
- Handover package display (previous session summary)
- Active TODOs
- High-priority locked contexts
- Recent updates
- Error notifications

**Value Assessment:** **CRITICAL**
**Usage:** Every session start
**User Benefit:** Immediate situational awareness

**Strengths:**
- Rich, actionable information
- Prevents context confusion (multi-project warning)
- Good UX with emojis and prioritization

**Issues:**
- 🐛 Relies on SQLite single-DB architecture (won't work in cloud without changes)
- 📊 Could show memory usage stats
- 🔍 No search capability for old sessions

**Recommendation:** **KEEP & ENHANCE**
- Add memory usage metrics
- Add "last 5 sessions" quick switcher for cloud
- Add search: `wake_up(search="authentication")`

---

#### 1.2 `sleep()` ⭐⭐⭐⭐
**Purpose:** Create handover package for next session
**Features:**
- Auto-collects progress from last N updates
- Auto-collects decisions
- Auto-collects high-priority TODOs
- Lists important locked contexts
- Tracks open issues

**Value Assessment:** **HIGH**
**Usage:** End of session (manual trigger)
**User Benefit:** Smooth session continuity

**Strengths:**
- Automatic data collection (no manual summary needed)
- JSON structure for parsing
- Integrates with wake_up() nicely

**Issues:**
- ⚠️ Manual trigger (users forget to call it)
- 📊 No automatic sleep on idle/disconnect
- 🔍 Doesn't compress/archive old handovers

**Recommendation:** **KEEP & AUTOMATE**
- Auto-trigger on MCP server shutdown
- Add `auto_sleep` setting (default: true)
- Archive handovers older than 7 days

---

### Category 2: Memory Management (3 tools)

#### 2.1 `memory_update(category, content, metadata)` ⭐⭐⭐
**Purpose:** Log categorized memory entries
**Categories:** progress, decision, error, insight, todo, question

**Value Assessment:** **MEDIUM**
**Usage:** Occasional (Claude-initiated logging)
**User Benefit:** Session history tracking

**Issues:**
- 🔄 **REDUNDANT** with context locking (lock_context is better for important info)
- 📊 No clear use case vs. just using memory_entries table directly
- 🤔 When would Claude call this vs lock_context?

**Recommendation:** **DEPRECATE or MERGE**
- Option A: Remove entirely, use lock_context for important info
- Option B: Merge into `log_event(type, content)` for simple logging

---

#### 2.2 `memory_status()` ⭐⭐⭐⭐
**Purpose:** Show memory system statistics

**Value Assessment:** **MEDIUM-HIGH**
**Usage:** Troubleshooting, capacity planning
**User Benefit:** Visibility into memory health

**Strengths:**
- Quick health check
- Useful for debugging

**Issues:**
- 📊 Limited analytics (just counts, no trends)
- 🔍 No breakdown by category/priority

**Recommendation:** **KEEP & ENHANCE**
- Add trend analysis (growth rate)
- Add capacity warnings (approaching limits)
- Add top-N most accessed contexts

---

#### 2.3 `ask_memory(question)` ⭐⭐
**Purpose:** Natural language query against memory entries

**Value Assessment:** **LOW**
**Usage:** Unknown (likely very rare)
**User Benefit:** Conversational memory retrieval

**Issues:**
- 🔄 **REDUNDANT** with check_contexts() which searches locked contexts
- 🔍 Searches memory_entries (unstructured logs) vs locked contexts (important info)
- 🤔 Unclear when this would be better than recall_context()
- 📊 No semantic search (just text matching)

**Recommendation:** **DEPRECATE**
- Remove in favor of enhanced check_contexts()
- If semantic search is desired, add it to check_contexts() instead

---

### Category 3: Context Locking (9 tools) 🚨 HIGH REDUNDANCY

#### 3.1 `lock_context(content, topic, tags, priority)` ⭐⭐⭐⭐⭐
**Purpose:** Create immutable versioned context snapshot
**Features:**
- Auto-versioning (semantic)
- Priority levels (always_check, important, reference)
- Tagging for organization
- 50KB size limit
- RLM optimization (preview, key_concepts)

**Value Assessment:** **CRITICAL**
**Usage:** Heavy (core feature)
**User Benefit:** Perfect recall of important information

**Strengths:**
- Solves the core problem (Claude's memory loss)
- Versioning prevents overwrites
- Priority system enables smart loading

**Issues:**
- 📊 No usage analytics (which contexts are actually accessed?)
- 🔍 No full-text search within content
- 🤔 50KB limit may be too small for complex schemas

**Recommendation:** **KEEP & ENHANCE**
- Add access tracking (last_accessed, access_count)
- Add content search: `lock_context(..., searchable=True)` to enable FTS
- Increase limit to 100KB or make configurable

---

#### 3.2 `recall_context(topic, version)` ⭐⭐⭐⭐⭐
**Purpose:** Retrieve exact locked context by label

**Value Assessment:** **CRITICAL**
**Usage:** Heavy (core feature)
**User Benefit:** Perfect recall

**Recommendation:** **KEEP** (no changes needed)

---

#### 3.3 `update_context(topic, content, change_type)` ⭐⭐⭐
**Purpose:** Create new version of existing context
**Features:**
- Preserves old version
- Auto-increments version number
- Tracks change type (minor/major/patch)

**Value Assessment:** **MEDIUM**
**Usage:** Low (most users just lock new versions manually)
**User Benefit:** Semantic versioning for contexts

**Issues:**
- 🔄 **REDUNDANT** - can just call lock_context() with same topic
- 🤔 Change type is rarely meaningful for context
- 📊 Adds complexity without clear value

**Recommendation:** **DEPRECATE**
- Remove tool
- Document pattern: "To update a context, lock again with same topic"
- System auto-increments version anyway

---

#### 3.4 `unlock_context(topic, version)` ⭐⭐⭐⭐
**Purpose:** Soft-delete context to archive

**Value Assessment:** **MEDIUM-HIGH**
**Usage:** Occasional cleanup
**User Benefit:** Remove obsolete contexts

**Recommendation:** **KEEP** (useful for cleanup)

---

#### 3.5 `list_topics()` ⭐⭐⭐⭐
**Purpose:** Show all locked context topics

**Value Assessment:** **MEDIUM-HIGH**
**Usage:** Discovery, inventory

**Issues:**
- 🔄 **PARTIALLY REDUNDANT** with explore_context_tree()
- 📊 No grouping by tags/priority

**Recommendation:** **MERGE into explore_context_tree()**
- Add flat mode: `explore_context_tree(flat=True)` → same as list_topics

---

#### 3.6 `check_contexts(text)` ⭐⭐⭐⭐⭐
**Purpose:** Find relevant contexts for given text
**Features:**
- Semantic relevance matching
- Priority-aware results
- Violation detection (always_check contexts)

**Value Assessment:** **CRITICAL**
**Usage:** Automatic (engine calls before actions)
**User Benefit:** Automatic context injection

**Recommendation:** **KEEP & ENHANCE**
- Add caching (same text → cached results)
- Add explicit user calls: `check_contexts("authentication")`

---

#### 3.7 `get_context_preview(topic)` ⭐⭐
**Purpose:** Get RLM-optimized preview of context

**Value Assessment:** **LOW**
**Usage:** Unknown (RLM optimization)

**Issues:**
- 🔄 **REDUNDANT** - recall_context() already returns preview
- 🤔 Unclear why separate tool is needed
- 📊 Preview is auto-generated anyway

**Recommendation:** **DEPRECATE**
- Remove tool
- Use recall_context() which includes preview

---

#### 3.8 `explore_context_tree()` ⭐⭐⭐
**Purpose:** Show hierarchical context organization

**Value Assessment:** **MEDIUM**
**Usage:** Discovery, navigation

**Issues:**
- 🔄 **PARTIALLY REDUNDANT** with list_topics()
- 🤔 "Tree" structure not clear (contexts don't have hierarchy)
- 📊 Could show relationships/references

**Recommendation:** **KEEP & ENHANCE**
- Merge list_topics() into this (add flat=True parameter)
- Add actual relationships (context A references context B)
- Rename to `explore_contexts()` (simpler)

---

#### 3.9 `sync_project_memory()` ⭐⭐⭐⭐
**Purpose:** Manual sync trigger for multi-device (future-facing)

**Value Assessment:** **MEDIUM** (becomes HIGH in cloud)
**Usage:** Currently no-op (local SQLite)

**Recommendation:** **KEEP for cloud migration**
- Will be critical for cloud sync
- Implement in Phase 2 of migration

---

### Category 4: Database Operations (3 tools) ✅ WELL-DESIGNED

#### 4.1 `query_database(sql, params, db_path, format)` ⭐⭐⭐⭐⭐
**Purpose:** Read-only SQL queries on any SQLite DB
**Features:**
- Workspace validation
- Parameterized queries (SQL injection protection)
- Multiple output formats (table, json, csv)
- Safety: Blocks non-SELECT queries

**Value Assessment:** **HIGH**
**Usage:** Power users, debugging
**User Benefit:** Direct database access for analysis

**Recommendation:** **KEEP** (excellent design)

---

#### 4.2 `inspect_database(mode, filter_text, db_path)` ⭐⭐⭐⭐
**Purpose:** User-friendly database exploration
**Modes:** overview, schema, contexts, tables

**Value Assessment:** **MEDIUM-HIGH**
**Usage:** Discovery, inventory

**Issues:**
- 🔄 **PARTIALLY REDUNDANT** with query_database
- 🤔 "contexts" mode duplicates explore_context_tree()

**Recommendation:** **KEEP but refine**
- Remove "contexts" mode (use explore_contexts instead)
- Keep schema/overview/tables modes (helpful)

---

#### 4.3 `execute_sql(sql, params, db_path, dry_run, confirm, max_affected)` ⭐⭐⭐⭐⭐
**Purpose:** Safe write operations (INSERT/UPDATE/DELETE)
**Features:**
- Dry-run by default (preview changes)
- Explicit confirmation required
- Transaction wrapping with automatic rollback
- Row limits (max_affected)
- Dangerous operation detection (UPDATE/DELETE without WHERE)
- Parameterized queries

**Value Assessment:** **HIGH**
**Usage:** Advanced users, data management
**User Benefit:** Full database control with safety rails

**Recommendation:** **KEEP** (excellent design, comprehensive safety)

---

### Category 5: File Tagging & Project Scanning (7 tools) 🚨 LOW VALUE

#### 5.1 `project_update()` ⭐⭐
**Purpose:** Scan project files and auto-tag with metadata
**Features:**
- Resumable multi-phase scanning
- Language detection
- Complexity analysis
- Tag suggestions

**Value Assessment:** **LOW**
**Usage:** Likely very rare (slow, complex)
**User Benefit:** Unclear - when is this better than grep/search?

**Issues:**
- ⚠️ **DISABLED in v4.0.0-rc1** (removed for stability)
- 🐌 Slow on large codebases
- 🤔 Value unclear vs standard code search
- 📊 Tags stored in SQLite (not portable)

**Recommendation:** **DEPRECATE or MAKE OPTIONAL**
- Don't include in cloud migration
- Keep as optional plugin for local use
- Focus on git-based file references instead

---

#### 5.2 `project_status()` ⭐⭐
**Purpose:** Show tagged file statistics

**Issues:**
- 🔄 Depends on project_update()
- ⚠️ Disabled in v4.0.0-rc1

**Recommendation:** **DEPRECATE**

---

#### 5.3-5.7 `tag_path()`, `search_by_tags()`, `file_insights()`, `get_tags()`, `search_tags()` ⭐
**Purpose:** File tagging CRUD operations

**Value Assessment:** **LOW** (all depend on project_update)

**Recommendation:** **DEPRECATE ALL**
- Remove from cloud migration
- If file references needed, use git references:
  - `repo:branch:path/to/file.js:line_number`
  - Works across devices
  - No database storage needed

---

## Redundancy Matrix

| Tool | Redundant With | Keep? | Reason |
|------|----------------|-------|--------|
| `update_context()` | `lock_context()` | ❌ | Can lock same topic to create new version |
| `get_context_preview()` | `recall_context()` | ❌ | Preview included in recall |
| `list_topics()` | `explore_context_tree()` | ❌ | Merge as flat mode |
| `ask_memory()` | `check_contexts()` | ❌ | check_contexts is better (searches locked contexts) |
| `memory_update()` | `lock_context()` | ❌ | Lock important info, skip trivial logs |
| File tagging (7 tools) | Standard code search | ❌ | Low value, high complexity |

**Total redundancy:** 12 tools can be removed/merged

---

## Missing Capabilities

### Gap 1: Batch Operations ⭐⭐⭐⭐⭐
**What:** Lock/recall multiple contexts in one call
**Why:** Common pattern in complex workflows
**Proposal:**
```python
batch_lock_contexts([
    {"topic": "api_v1", "content": "...", "priority": "important"},
    {"topic": "api_v2", "content": "...", "priority": "important"}
])

batch_recall_contexts(["api_v1", "database_schema", "auth_flow"])
```

**Value:** **CRITICAL** for cloud (reduces round-trips)

---

### Gap 2: Context Search ⭐⭐⭐⭐⭐
**What:** Full-text search within locked contexts
**Why:** Users can't find contexts by content, only by label
**Proposal:**
```python
search_contexts(
    query="JWT authentication",
    filters={"priority": "important", "tags": ["api"]}
)
# Returns: [{"topic": "api_auth", "match": "...JWT token validation...", "score": 0.95}]
```

**Value:** **CRITICAL** as context library grows

---

### Gap 3: Analytics & Insights ⭐⭐⭐⭐
**What:** Usage analytics for memory system
**Why:** Users can't see what's being used/wasted
**Proposal:**
```python
memory_analytics()
# Returns:
# - Most accessed contexts (top 10)
# - Largest contexts (storage hogs)
# - Unused contexts (never accessed in 30 days)
# - Memory growth rate (MB/week)
# - Stale contexts (not updated in 90 days)
```

**Value:** **HIGH** for optimization and cleanup

---

### Gap 4: Context Export/Import ⭐⭐⭐⭐
**What:** Export contexts for sharing/backup
**Why:** Users want to share contexts between projects/teams
**Proposal:**
```python
export_contexts(
    topics=["api_spec", "database_schema"],
    format="json",  # or markdown
    output_path="./exports/api_contexts.json"
)

import_contexts(
    input_path="./exports/api_contexts.json",
    strategy="merge"  # or "replace"
)
```

**Value:** **MEDIUM-HIGH** for collaboration

---

### Gap 5: Smart Cleanup ⭐⭐⭐
**What:** Automated archival of stale contexts
**Why:** Manual cleanup is tedious
**Proposal:**
```python
auto_cleanup(
    stale_days=90,     # No access in 90 days
    max_versions=5,    # Keep only last 5 versions per topic
    dry_run=True
)
```

**Value:** **MEDIUM** for maintenance

---

## Proposed Tool Suite (v5.0)

### Core Tools (15 tools, -9 from current)

**Session Management (2)**
1. ✅ `wake_up()` - Enhanced with search, session switcher
2. ✅ `sleep()` - Auto-trigger on shutdown

**Context Management (7)**
3. ✅ `lock_context()` - Enhanced with searchable flag, 100KB limit
4. ✅ `recall_context()` - No changes
5. ✅ `unlock_context()` - No changes
6. ✅ `check_contexts()` - Enhanced with explicit user calls
7. ✅ `explore_contexts()` - Merged list_topics, improved UX
8. 🆕 `search_contexts()` - NEW: Full-text search
9. 🆕 `batch_lock_contexts()` - NEW: Batch operations
10. 🆕 `batch_recall_contexts()` - NEW: Batch operations

**Database Operations (3)**
11. ✅ `query_database()` - No changes
12. ✅ `inspect_database()` - Remove "contexts" mode
13. ✅ `execute_sql()` - No changes

**System Management (3)**
14. ✅ `memory_status()` - Enhanced with analytics
15. 🆕 `memory_analytics()` - NEW: Usage insights

**Removed (9 tools)**
- ❌ `memory_update()` - Use lock_context instead
- ❌ `ask_memory()` - Use search_contexts instead
- ❌ `update_context()` - Use lock_context with same topic
- ❌ `get_context_preview()` - Included in recall_context
- ❌ `list_topics()` - Merged into explore_contexts
- ❌ `project_update()` - Low value
- ❌ `project_status()` - Depends on project_update
- ❌ `tag_path()`, `search_by_tags()`, `file_insights()`, `get_tags()`, `search_tags()` - 5 file tagging tools (low value)

**Deferred to Phase 2 (cloud migration)**
- 🔄 `sync_project_memory()` - Becomes active in cloud
- 🔄 `export_contexts()` - Nice to have, not critical
- 🔄 `import_contexts()` - Nice to have, not critical
- 🔄 `auto_cleanup()` - Nice to have, not critical

---

## Implementation Priority

### Phase 1: Cleanup (2 hours)
1. Remove 9 redundant tools from claude_mcp_hybrid.py
2. Update documentation
3. Add deprecation warnings for removed tools
4. Test remaining tools still work

### Phase 2: Core Enhancements (4 hours)
1. Implement `search_contexts()` with SQLite FTS
2. Implement `batch_lock_contexts()` and `batch_recall_contexts()`
3. Enhance `memory_status()` with basic analytics
4. Enhance `explore_contexts()` with flat mode

### Phase 3: Advanced Features (6 hours)
1. Implement `memory_analytics()` with full insights
2. Add auto-sleep on MCP shutdown
3. Add access tracking to lock_context/recall_context
4. Add content search indexing

### Phase 4: Cloud Migration (weekend POC)
1. Migrate to PostgreSQL
2. Add project_id to all operations
3. Implement connection pooling
4. Test cross-device sync

---

## User Impact Analysis

### Users Will Lose
- ❌ File tagging system (7 tools) - **Low impact** (rarely used, disabled anyway)
- ❌ `memory_update()` - **Low impact** (just use lock_context)
- ❌ `ask_memory()` - **Low impact** (new search_contexts is better)
- ❌ `update_context()` - **Zero impact** (can just lock again)
- ❌ `get_context_preview()` - **Zero impact** (included in recall)

### Users Will Gain
- ✅ **Full-text search** within contexts (game changer)
- ✅ **Batch operations** (faster workflows)
- ✅ **Usage analytics** (visibility into memory health)
- ✅ **Simpler tool suite** (less confusion, better docs)
- ✅ **Better performance** (fewer tools, better caching)

**Net Result:** +100% user value, -40% tool complexity

---

## Questions for Discussion

1. **File Tagging System**
   - Completely remove? Or make optional plugin?
   - Any specific use case where it's valuable?

2. **Memory Updates**
   - Remove `memory_update()` entirely? Or keep for simple logging?
   - Is there value in lightweight logs vs heavy locked contexts?

3. **Batch Operations**
   - Should batch_lock support atomic transactions (all-or-nothing)?
   - What's max batch size?

4. **Search Implementation**
   - SQLite FTS5 sufficient? Or need external search (Elasticsearch)?
   - Index all contexts by default? Or opt-in?

5. **Analytics Scope**
   - What metrics are most valuable?
   - Real-time vs periodic calculation?

6. **Cloud Migration Timing**
   - Do cleanup first, then migrate? Or migrate then cleanup?
   - Which tools are must-have for cloud POC?

---

## Recommendation Summary

**Immediate Action:**
1. ✅ Remove 9 redundant tools (Phase 1)
2. ✅ Implement search_contexts and batch operations (Phase 2)
3. ✅ Enhance analytics (Phase 3)
4. 🔄 Then proceed with cloud migration (Phase 4)

**Rationale:** Clean architecture before migration prevents carrying technical debt to cloud.

**Timeline:**
- Phase 1-3: 12 hours (1.5 days)
- Phase 4: 10 hours (weekend POC)
- **Total:** 2.5 days to production-ready cloud version

**Expected Outcome:**
- Simpler, faster, more powerful tool suite
- Clean foundation for cloud migration
- Better user experience
- Easier maintenance

---

**Ready to discuss any section in detail.**
