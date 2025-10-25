# New MCP Tools Design - Phase 2 Enhancement

**Date:** 2025-01-15
**Purpose:** Add missing high-value capabilities identified in audit
**Goal:** Transform from basic memory → powerful knowledge management

---

## Tool 1: batch_lock_contexts()

### Purpose
Lock multiple contexts in a single operation - critical for cloud performance (reduces round-trips)

### Signature
```python
@mcp.tool()
async def batch_lock_contexts(
    contexts: List[dict]  # JSON array of context objects
) -> str:
    """
    Lock multiple contexts in one operation.

    Each context dict should have:
    - content: str (required)
    - topic: str (required)
    - tags: str (optional, comma-separated)
    - priority: str (optional: always_check/important/reference)

    Returns JSON with results for each context.
    """
```

### Design
```python
# Parse JSON input
contexts_list = json.loads(contexts)

results = []
for ctx in contexts_list:
    try:
        result = await lock_context(
            content=ctx['content'],
            topic=ctx['topic'],
            tags=ctx.get('tags'),
            priority=ctx.get('priority')
        )
        results.append({
            "topic": ctx['topic'],
            "status": "success",
            "result": result
        })
    except Exception as e:
        results.append({
            "topic": ctx['topic'],
            "status": "error",
            "error": str(e)
        })

return json.dumps({
    "total": len(contexts_list),
    "successful": sum(1 for r in results if r['status'] == 'success'),
    "failed": sum(1 for r in results if r['status'] == 'error'),
    "results": results
}, indent=2)
```

### Example Usage
```python
batch_lock_contexts([
    {
        "topic": "api_v1",
        "content": "API v1.0 specification...",
        "priority": "important",
        "tags": "api,schema"
    },
    {
        "topic": "database_schema",
        "content": "CREATE TABLE users...",
        "priority": "always_check",
        "tags": "database,schema"
    }
])
```

---

## Tool 2: batch_recall_contexts()

### Purpose
Retrieve multiple contexts in one operation

### Signature
```python
@mcp.tool()
async def batch_recall_contexts(
    topics: List[str]  # JSON array of topic names
) -> str:
    """
    Recall multiple contexts in one operation.

    Returns JSON with content for each requested topic.
    """
```

### Design
```python
topics_list = json.loads(topics) if isinstance(topics, str) else topics

results = []
for topic in topics_list:
    try:
        content = await recall_context(topic)
        results.append({
            "topic": topic,
            "status": "success",
            "content": content
        })
    except Exception as e:
        results.append({
            "topic": topic,
            "status": "error",
            "error": str(e)
        })

return json.dumps({
    "total": len(topics_list),
    "found": sum(1 for r in results if r['status'] == 'success'),
    "not_found": sum(1 for r in results if r['status'] == 'error'),
    "results": results
}, indent=2)
```

---

## Tool 3: search_contexts()

### Purpose
Full-text search within locked contexts - find contexts by content, not just label

### Signature
```python
@mcp.tool()
async def search_contexts(
    query: str,
    priority: Optional[str] = None,  # Filter by priority
    tags: Optional[str] = None,      # Filter by tags (comma-separated)
    limit: int = 10
) -> str:
    """
    Search locked contexts by content.

    Returns matching contexts with relevance scores.
    """
```

### Design Options

**Option A: Simple SQLite LIKE (fast, basic)**
```sql
SELECT label, version, content, preview
FROM context_locks
WHERE content LIKE '%' || ? || '%'
  OR preview LIKE '%' || ? || '%'
  OR key_concepts LIKE '%' || ? || '%'
```

**Option B: SQLite FTS5 (better, requires index)**
```sql
CREATE VIRTUAL TABLE context_fts USING fts5(
    label, content, preview, key_concepts,
    content='context_locks',
    content_rowid='id'
);

SELECT * FROM context_fts
WHERE context_fts MATCH ?
ORDER BY rank;
```

**Recommendation:** Start with Option A (simple LIKE), add FTS5 later if needed

### Implementation
```python
conn = get_db()
session_id = get_current_session_id()

# Build query
sql = """
    SELECT
        label, version, content, preview, key_concepts,
        locked_at, metadata, last_accessed, access_count
    FROM context_locks
    WHERE session_id = ?
      AND (
          content LIKE ?
          OR preview LIKE ?
          OR key_concepts LIKE ?
          OR label LIKE ?
      )
"""

params = [session_id, f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%']

# Add filters
if priority:
    sql += " AND json_extract(metadata, '$.priority') = ?"
    params.append(priority)

if tags:
    tag_conditions = []
    for tag in tags.split(','):
        tag = tag.strip()
        tag_conditions.append("json_extract(metadata, '$.tags') LIKE ?")
        params.append(f'%{tag}%')
    sql += f" AND ({' OR '.join(tag_conditions)})"

sql += " LIMIT ?"
params.append(limit)

cursor = conn.execute(sql, params)
results = cursor.fetchall()

# Calculate relevance scores
scored_results = []
for row in results:
    score = 0.0

    # Exact label match = highest score
    if query.lower() in row['label'].lower():
        score += 1.0

    # Content match
    if query.lower() in (row['content'] or '').lower():
        score += 0.5

    # Preview match
    if query.lower() in (row['preview'] or '').lower():
        score += 0.3

    # Key concepts match
    if query.lower() in (row['key_concepts'] or '').lower():
        score += 0.7

    scored_results.append({
        "label": row['label'],
        "version": row['version'],
        "score": score,
        "preview": row['preview'] or row['content'][:200],
        "last_accessed": row['last_accessed'],
        "access_count": row['access_count']
    })

# Sort by score
scored_results.sort(key=lambda x: x['score'], reverse=True)

return json.dumps({
    "query": query,
    "total_found": len(scored_results),
    "results": scored_results
}, indent=2)
```

---

## Tool 4: memory_analytics()

### Purpose
Show usage patterns, identify waste, recommend cleanup

### Signature
```python
@mcp.tool()
async def memory_analytics() -> str:
    """
    Analyze memory system usage and health.

    Returns insights about:
    - Most/least accessed contexts
    - Storage distribution
    - Stale contexts
    - Growth trends
    """
```

### Implementation
```python
conn = get_db()
session_id = get_current_session_id()

analytics = {
    "overview": {},
    "most_accessed": [],
    "least_accessed": [],
    "largest_contexts": [],
    "stale_contexts": [],
    "by_priority": {},
    "by_tags": {},
    "recommendations": []
}

# Overview
cursor = conn.execute("""
    SELECT
        COUNT(*) as total,
        SUM(LENGTH(content)) as total_bytes,
        AVG(LENGTH(content)) as avg_bytes,
        MIN(locked_at) as oldest,
        MAX(locked_at) as newest
    FROM context_locks
    WHERE session_id = ?
""", (session_id,))
overview = cursor.fetchone()

analytics["overview"] = {
    "total_contexts": overview['total'],
    "total_size_mb": round(overview['total_bytes'] / (1024*1024), 2),
    "average_size_kb": round(overview['avg_bytes'] / 1024, 2),
    "oldest_context_age_days": round((time.time() - overview['oldest']) / 86400, 1) if overview['oldest'] else 0,
    "newest_context_age_days": round((time.time() - overview['newest']) / 86400, 1) if overview['newest'] else 0
}

# Most accessed (top 10)
cursor = conn.execute("""
    SELECT label, version, access_count, last_accessed, LENGTH(content) as size
    FROM context_locks
    WHERE session_id = ? AND access_count > 0
    ORDER BY access_count DESC
    LIMIT 10
""", (session_id,))
analytics["most_accessed"] = [dict(row) for row in cursor.fetchall()]

# Least accessed (never accessed)
cursor = conn.execute("""
    SELECT label, version, locked_at, LENGTH(content) as size
    FROM context_locks
    WHERE session_id = ? AND (access_count IS NULL OR access_count = 0)
    ORDER BY locked_at DESC
    LIMIT 10
""", (session_id,))
analytics["least_accessed"] = [dict(row) for row in cursor.fetchall()]

# Largest contexts (top 10 storage hogs)
cursor = conn.execute("""
    SELECT label, version, LENGTH(content) as size, access_count
    FROM context_locks
    WHERE session_id = ?
    ORDER BY LENGTH(content) DESC
    LIMIT 10
""", (session_id,))
analytics["largest_contexts"] = [dict(row) for row in cursor.fetchall()]

# Stale contexts (not accessed in 30+ days)
thirty_days_ago = time.time() - (30 * 86400)
cursor = conn.execute("""
    SELECT label, version, last_accessed, LENGTH(content) as size
    FROM context_locks
    WHERE session_id = ?
      AND (last_accessed IS NULL OR last_accessed < ?)
    ORDER BY last_accessed ASC
""", (session_id, thirty_days_ago))
analytics["stale_contexts"] = [dict(row) for row in cursor.fetchall()]

# By priority
cursor = conn.execute("""
    SELECT
        json_extract(metadata, '$.priority') as priority,
        COUNT(*) as count,
        SUM(LENGTH(content)) as total_bytes
    FROM context_locks
    WHERE session_id = ?
    GROUP BY json_extract(metadata, '$.priority')
""", (session_id,))
analytics["by_priority"] = {row['priority'] or 'reference': {
    "count": row['count'],
    "size_mb": round(row['total_bytes'] / (1024*1024), 2)
} for row in cursor.fetchall()}

# Recommendations
if len(analytics["stale_contexts"]) > 0:
    analytics["recommendations"].append(f"Consider unlocking {len(analytics['stale_contexts'])} stale contexts (not accessed in 30+ days)")

if len(analytics["least_accessed"]) > 5:
    analytics["recommendations"].append(f"{len(analytics['least_accessed'])} contexts have never been accessed - verify they're still needed")

total_mb = analytics["overview"]["total_size_mb"]
if total_mb > 40:  # 80% of 50MB limit
    analytics["recommendations"].append(f"Memory usage at {total_mb}MB (near 50MB limit) - consider cleanup")

return json.dumps(analytics, indent=2)
```

---

## Tool 5: Enhanced explore_context_tree()

### Current Implementation
Shows hierarchical context organization (though contexts don't actually have hierarchy)

### Enhancement: Add flat mode
```python
@mcp.tool()
async def explore_context_tree(flat: bool = False) -> str:
    """
    Explore locked contexts.

    Args:
        flat: If True, return simple list (replaces removed list_topics())
              If False, return grouped by priority (default)
    """

    if flat:
        # Simple flat list (replacement for list_topics)
        cursor = conn.execute("""
            SELECT label, version, locked_at
            FROM context_locks
            WHERE session_id = ?
            ORDER BY label
        """, (session_id,))

        results = []
        for row in cursor.fetchall():
            results.append(f"{row['label']} v{row['version']}")

        return "\n".join(results)
    else:
        # Existing grouped view
        # ... current implementation ...
```

---

## Implementation Priority

### Phase 2A - Core Enhancements (Now)
1. ✅ `batch_lock_contexts()` - 30 min
2. ✅ `batch_recall_contexts()` - 20 min
3. ✅ `search_contexts()` - 45 min
4. ✅ `memory_analytics()` - 60 min
5. ✅ Enhance `explore_context_tree()` - 15 min

**Total:** ~3 hours

### Phase 2B - Advanced Features (Later)
- FTS5 indexing for faster search
- Export/import contexts
- Auto-cleanup tool

---

## Expected Tool Count After Phase 2A

**Before:** 12 tools
**After:** 16 tools

**New tools (4):**
- batch_lock_contexts
- batch_recall_contexts
- search_contexts
- memory_analytics

**Enhanced (1):**
- explore_context_tree (now with flat mode)

---

## Testing Plan

For each new tool:
1. Unit test with sample data
2. Integration test with real database
3. Performance test with large datasets
4. Edge case testing (empty results, errors, etc.)

---

**Ready to implement!**
