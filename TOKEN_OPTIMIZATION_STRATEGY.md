# Token Optimization Strategy: MCP as External Memory

## Core Principle

**The MCP server is Claude's external hard drive - it carries the burden of memory storage and retrieval, while the LLM operates at peak efficiency with only the relevant context it needs right now.**

## Mental Model

```
┌─────────────────────────────────────────────────────────────┐
│                    Claude (LLM)                              │
│  - Limited context window (200K tokens)                      │
│  - Needs ONLY relevant context for current task              │
│  - Should receive summaries, not full data                   │
└──────────────────┬──────────────────────────────────────────┘
                   │ Minimal, targeted queries
                   │ Summary responses only
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              MCP Server (External Memory)                    │
│  - Unlimited storage in SQLite                               │
│  - Process everything in Python                              │
│  - Store full details in database                            │
│  - Return only what's needed                                 │
│  - Acts like: grep, find, index, cache                       │
└─────────────────────────────────────────────────────────────┘
```

## Design Patterns

### Pattern 1: Summary-First

**Bad (Token-Heavy):**
```python
wake_up()
# Returns: 50KB of all contexts, full handover, all git history
```

**Good (Token-Light):**
```python
wake_up()
# Returns: {
#   contexts: {total: 42, by_priority: counts},
#   handover: {available: true, hours_ago: 2.5},
#   file_model: {total_files: 156, changes: {added: 3, modified: 5}}
# }
# Total: ~2KB
```

### Pattern 2: Database-First with Lazy Loading

**Process:**
1. MCP tool receives request
2. Process ALL data in Python (search, filter, analyze)
3. Store full results in database with query_id
4. Return ONLY:
   - Summary statistics (counts, totals)
   - First N results (preview)
   - query_id for pagination
5. Provide follow-up tools to get more if needed

**Example:**
```python
# User asks: "Find all files related to authentication"
query_files("authentication")

# MCP processes:
# - Searches 1000 files
# - Finds 50 matches
# - Stores all 50 in temp_query_results table
# - Returns:
{
  "query_id": "abc123",
  "total_matches": 50,
  "preview": [
    {"path": "auth.py", "purpose": "JWT authentication"},
    {"path": "login.js", "purpose": "Login form"},
    {"path": "oauth.py", "purpose": "OAuth provider"}
    # Only first 3-5 results
  ],
  "note": "Use get_query_page('abc123', offset=5, limit=10) for more"
}
# Total: ~500 bytes instead of 50KB
```

### Pattern 3: Context-Aware Retrieval

**Intelligence at the edges:**
- LLM asks: "What did I work on in the last session?"
- MCP knows: "This user cares about progress, not errors"
- MCP returns: Only progress entries, not everything

**Example:**
```python
@mcp.tool()
async def what_did_i_work_on(
    timeframe: str = "last_session",  # or "today", "this_week"
    categories: List[str] = ["progress", "decision"]  # not errors, todos
) -> str:
    """Smart retrieval - only what matters for understanding past work"""
    # Process in Python
    entries = fetch_memory_entries(timeframe, categories)

    # Summarize (don't return raw entries)
    summary = {
        "period": timeframe,
        "total_items": len(entries),
        "highlights": top_5_items(entries),
        "categories": categorize_and_count(entries),
        "query_id": store_full_results(entries)
    }

    return json.dumps(summary)  # ~1KB instead of 50KB
```

### Pattern 4: Progressive Disclosure

**Start minimal, drill down only if needed:**

```python
# Level 1: Overview (always fast)
wake_up()
# → "You have 42 contexts, 15 are important, 3 are stale"

# Level 2: Explore (if user asks)
explore_context_tree(flat=True)
# → List of context labels only

# Level 3: Details (if user needs specific context)
recall_context("api_spec")
# → Full content of that ONE context
```

## Implementation Guidelines

### For Every MCP Tool

**1. Token Budget Classification:**

```python
# Add to every tool's docstring:
"""
Token efficiency: [MINIMAL | SUMMARY | PREVIEW | FULL]
- MINIMAL: <500 tokens (counts, status, availability)
- SUMMARY: <2000 tokens (aggregated stats, top N items)
- PREVIEW: <5000 tokens (first page of results + pagination info)
- FULL: >5000 tokens (use sparingly, require explicit intent)

Expected response size: ~[size estimate]
"""
```

**2. Default to Summary:**

```python
@mcp.tool()
async def query_files(
    query: str,
    preview_only: bool = True,  # Default to summary
    limit: int = 5  # Default to small preview
) -> str:
```

**3. Provide Full Access When Needed:**

```python
# Summary version (default)
query_files("auth")
# → {total: 50, preview: [5 files], query_id}

# Full version (explicit)
query_files("auth", preview_only=False, limit=100)
# → {total: 50, results: [all 50 files]}

# Or paginate
get_query_page(query_id, offset=10, limit=10)
# → {results: [files 10-20], has_more: true}
```

### Database Schema for Pagination

```sql
CREATE TABLE query_results_cache (
    query_id TEXT PRIMARY KEY,
    query_type TEXT NOT NULL,           -- 'query_files', 'search_contexts', etc
    query_params TEXT,                  -- JSON of search parameters
    total_results INTEGER,
    result_data TEXT,                   -- JSON array of all results
    created_at REAL,
    expires_at REAL,                    -- Auto-cleanup after 1 hour
    session_id TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_query_expires ON query_results_cache(expires_at);
```

### Helper Functions

```python
def store_query_results(query_type: str, params: dict, results: list,
                       ttl_seconds: int = 3600) -> str:
    """
    Store query results in database for pagination.

    Returns query_id for retrieving results later.
    """
    query_id = hashlib.md5(
        f"{query_type}:{json.dumps(params, sort_keys=True)}".encode()
    ).hexdigest()[:12]

    conn.execute("""
        INSERT OR REPLACE INTO query_results_cache
        (query_id, query_type, query_params, total_results, result_data,
         created_at, expires_at, session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        query_id,
        query_type,
        json.dumps(params),
        len(results),
        json.dumps(results),
        time.time(),
        time.time() + ttl_seconds,
        get_current_session_id()
    ))

    return query_id


def get_query_page(query_id: str, offset: int = 0, limit: int = 20) -> dict:
    """Retrieve paginated results from stored query."""
    cursor = conn.execute("""
        SELECT query_type, total_results, result_data
        FROM query_results_cache
        WHERE query_id = ? AND expires_at > ?
    """, (query_id, time.time()))

    row = cursor.fetchone()
    if not row:
        return {"error": "Query not found or expired"}

    all_results = json.loads(row['result_data'])
    page_results = all_results[offset:offset + limit]

    return {
        "query_id": query_id,
        "query_type": row['query_type'],
        "total_results": row['total_results'],
        "offset": offset,
        "limit": limit,
        "page_size": len(page_results),
        "has_more": offset + limit < row['total_results'],
        "results": page_results
    }


def cleanup_expired_queries():
    """Remove expired query results (call periodically)."""
    conn.execute("""
        DELETE FROM query_results_cache
        WHERE expires_at < ?
    """, (time.time(),))
```

## Optimization Priority List

### Phase 1: Critical (Immediate)
1. ✅ **wake_up()** - Reduced from 50KB+ to ~2KB
2. ✅ **get_last_handover()** - Separated from wake_up()
3. 🔄 **recall_context()** - Add `preview_only` parameter
4. 🔄 **batch_recall_contexts()** - Add `preview_only` parameter

### Phase 2: High Priority (Next)
5. **query_files()** - Add pagination, store full results
6. **get_file_clusters()** - Return summary + top N files per cluster
7. **scan_project_files()** - Return only summary, store details
8. Add **get_query_page()** universal pagination tool

### Phase 3: Medium Priority
9. **explore_context_tree()** - Add limit parameter
10. **search_contexts()** - Already good, add pagination
11. **sleep()** - Return summary only, store full handover

### Phase 4: Infrastructure
12. Implement query_results_cache table
13. Add automatic cleanup of expired queries
14. Add token usage monitoring/logging
15. Create token efficiency dashboard tool

## Token Efficiency Metrics

### Target Goals

| Tool Type | Token Budget | Response Time | Example |
|-----------|--------------|---------------|---------|
| Status/Health | < 500 tokens | < 50ms | memory_status, file_model_status |
| Summary | < 2000 tokens | < 200ms | wake_up, memory_analytics |
| Preview | < 5000 tokens | < 500ms | query_files (preview), search_contexts |
| Full Content | < 20000 tokens | < 2s | recall_context (full) |

### Monitoring

```python
@mcp.tool()
async def token_usage_report() -> str:
    """
    Show token usage statistics for all tools.

    Returns metrics on:
    - Average response size per tool
    - Tools exceeding token budgets
    - Most/least efficient tools
    - Recommendations for optimization
    """
    pass  # Implementation
```

## Best Practices for Users

### Efficient Workflow

```python
# ✅ GOOD: Start minimal, drill down as needed
wake_up()  # Overview only
# → See you have 5 important contexts

explore_context_tree(flat=True)  # List labels
# → See context names

recall_context("api_spec")  # Get ONE you need
# → Full content of that context

# ❌ BAD: Load everything upfront
batch_recall_contexts(["all", "my", "contexts"])  # Don't do this!
```

### Smart Querying

```python
# ✅ GOOD: Use search with preview
search_contexts("authentication", limit=5)
# → See top 5 matches
# → If not enough, expand search

# ❌ BAD: Get all results at once
search_contexts("*", limit=1000)  # Don't do this!
```

## Success Metrics

**Target achievements:**
- wake_up() completes without filling context window ✅
- Most common workflows stay under 20K tokens ⏳
- Full context window (200K) lasts entire session ⏳
- Users can work on large projects (1000+ files) efficiently ⏳

**Key insight:** The LLM should feel like it has infinite memory, but technically only holds what it needs right now.

---

**Version:** 1.0
**Status:** Living document - update as we implement optimizations
**Next Review:** After Phase 2 implementation
