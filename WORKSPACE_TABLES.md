# Dynamic Workspace Tables

## Overview

Claude can now create temporary database tables dynamically for complex multi-step processing. This feature enables Claude to work with large datasets without filling the context window, by storing intermediate results in the database.

## The Problem This Solves

When Claude needs to:
- Process large datasets that exceed context window
- Perform multi-step analyses with intermediate results
- Build complex data transformation pipelines
- Cache results for pagination

Previously, Claude would have to keep all data in the conversation context, quickly exceeding the 200K token limit.

## The Solution

The `manage_workspace_table()` tool allows Claude to:
1. Create custom tables with any schema needed
2. Store unlimited data in the database
3. Query only what's needed at each step
4. Clean up when done

## Architecture

```
┌─────────────────────────────────────────────┐
│           Claude (LLM)                      │
│  - Decides what analysis to perform         │
│  - Creates table schema as needed           │
│  - Processes data in chunks                 │
│  - Queries only relevant data               │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│        Workspace Tables                     │
│  - workspace_analysis_results               │
│  - workspace_file_clusters_cache            │
│  - workspace_temp_processing                │
│  - (Any custom schema Claude needs)         │
└─────────────────────────────────────────────┘
```

## Tool: manage_workspace_table()

### Operations

#### 1. Create a Table

```python
manage_workspace_table(
    operation='create',
    table_name='analysis_results',
    schema='''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        complexity_score REAL,
        issue_count INTEGER,
        analyzed_at REAL
    ''',
    dry_run=False,
    confirm=True
)
```

**Returns:**
```json
{
  "success": true,
  "operation": "create",
  "table": "workspace_analysis_results",
  "sql": "CREATE TABLE workspace_analysis_results (...)",
  "usage": "Use query_database() with: SELECT * FROM workspace_analysis_results"
}
```

#### 2. List All Workspace Tables

```python
manage_workspace_table(operation='list')
```

**Returns:**
```json
{
  "operation": "list",
  "workspace_tables": [
    {
      "name": "workspace_analysis_results",
      "schema": "CREATE TABLE workspace_analysis_results (...)",
      "row_count": 156
    },
    {
      "name": "workspace_file_cache",
      "schema": "CREATE TABLE workspace_file_cache (...)",
      "row_count": 1243
    }
  ],
  "total_count": 2
}
```

#### 3. Inspect a Table

```python
manage_workspace_table(
    operation='inspect',
    table_name='analysis_results'
)
```

**Returns:**
```json
{
  "operation": "inspect",
  "table": "workspace_analysis_results",
  "schema": "CREATE TABLE workspace_analysis_results (...)",
  "row_count": 156,
  "sample_data": [
    {"id": 1, "file_path": "src/main.py", "complexity_score": 8.5, "issue_count": 3},
    {"id": 2, "file_path": "src/utils.py", "complexity_score": 4.2, "issue_count": 1},
    ...
  ]
}
```

#### 4. Drop a Table

```python
manage_workspace_table(
    operation='drop',
    table_name='analysis_results',
    dry_run=False,
    confirm=True
)
```

**Returns:**
```json
{
  "success": true,
  "operation": "drop",
  "table": "workspace_analysis_results",
  "sql": "DROP TABLE workspace_analysis_results"
}
```

## Complete Workflow Example

### Use Case: Analyze File Complexity Across Large Project

```python
# Step 1: Create workspace table
manage_workspace_table(
    operation='create',
    table_name='complexity_analysis',
    schema='''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        language TEXT,
        lines_of_code INTEGER,
        cyclomatic_complexity REAL,
        maintainability_index REAL,
        analyzed_at REAL
    ''',
    dry_run=False,
    confirm=True
)

# Step 2: Scan project and populate table
# (Claude would iterate through files, analyze each, and insert results)
for file in project_files:
    metrics = analyze_file(file)
    execute_sql(
        """INSERT INTO workspace_complexity_analysis
           (file_path, language, lines_of_code, cyclomatic_complexity,
            maintainability_index, analyzed_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        params=[
            file.path,
            file.language,
            metrics.loc,
            metrics.complexity,
            metrics.maintainability,
            time.time()
        ],
        dry_run=False,
        confirm=True
    )

# Step 3: Query top issues (pagination-friendly)
query_database("""
    SELECT file_path, cyclomatic_complexity, maintainability_index
    FROM workspace_complexity_analysis
    WHERE cyclomatic_complexity > 10
    ORDER BY cyclomatic_complexity DESC
    LIMIT 20
""")

# Step 4: Get statistics
query_database("""
    SELECT
        language,
        COUNT(*) as file_count,
        AVG(cyclomatic_complexity) as avg_complexity,
        AVG(maintainability_index) as avg_maintainability
    FROM workspace_complexity_analysis
    GROUP BY language
    ORDER BY avg_complexity DESC
""")

# Step 5: Store results for pagination (using existing infrastructure)
all_results = query_database("SELECT * FROM workspace_complexity_analysis")
query_id = store_query_results(conn, "complexity_analysis", {}, all_results)

# Return summary + query_id
return {
    "total_files": 1243,
    "high_complexity_files": 47,
    "avg_complexity": 6.8,
    "query_id": query_id,
    "note": "Use get_query_page() for details"
}

# Step 6: Clean up when done
manage_workspace_table(
    operation='drop',
    table_name='complexity_analysis',
    dry_run=False,
    confirm=True
)
```

## Safety Features

### 1. Namespace Isolation
All workspace tables are automatically prefixed with `workspace_`:
- Input: `table_name='analysis_results'`
- Created: `workspace_analysis_results`

This prevents conflicts with core memory tables.

### 2. Protected Core Tables
Cannot create workspace tables with these names:
- `sessions`
- `memory_entries`
- `context_locks`
- `context_archives`
- `file_tags`
- `todos`
- `project_variables`
- `query_results_cache`
- `file_semantic_model`

### 3. Dry-Run by Default
All write operations default to `dry_run=True`:
```python
manage_workspace_table(
    operation='create',
    table_name='test'
)
# Returns preview without creating
```

Must explicitly set `dry_run=False` and `confirm=True` to execute.

### 4. Schema Validation
SQL syntax is validated before execution. Invalid schemas return clear error messages.

### 5. Workspace-Only Operations
Operations only work on tables prefixed with `workspace_`. Attempting to modify core tables fails with error.

## Integration with Existing Tools

### After Creating a Workspace Table

**Read Data:**
```python
query_database("SELECT * FROM workspace_my_table")
```

**Write Data:**
```python
execute_sql(
    "INSERT INTO workspace_my_table (col1, col2) VALUES (?, ?)",
    params=["value1", "value2"],
    dry_run=False,
    confirm=True
)
```

**Update Data:**
```python
execute_sql(
    "UPDATE workspace_my_table SET col1 = ? WHERE id = ?",
    params=["new_value", 123],
    dry_run=False,
    confirm=True
)
```

**Store for Pagination:**
```python
# Get all results
all_results = query_database("SELECT * FROM workspace_my_table")

# Store with pagination
query_id = store_query_results(conn, "my_analysis", {}, all_results)

# Return preview + query_id
return {
    "total": len(all_results),
    "preview": all_results[:5],
    "query_id": query_id
}
```

## Best Practices

### 1. Descriptive Table Names
✅ Good:
- `file_complexity_analysis`
- `search_results_cache`
- `temp_processing_pipeline`

❌ Bad:
- `temp`
- `data`
- `results`

### 2. Clean Up When Done
```python
# At end of analysis
manage_workspace_table(
    operation='drop',
    table_name='analysis_results',
    dry_run=False,
    confirm=True
)
```

### 3. Use for Multi-Step Processing
Perfect for:
- Iterative data transformations
- Building up results across multiple queries
- Caching intermediate calculations
- Complex aggregations

Not needed for:
- Single-query operations (use query_database directly)
- Small datasets (<100 rows)
- One-time reads

### 4. Combine with Pagination
```python
# 1. Process data into workspace table
# 2. Query all results from workspace table
# 3. Store results using store_query_results()
# 4. Return summary + query_id
# 5. User can get_query_page() for more details
# 6. Drop workspace table when done
```

## Performance Considerations

### When to Use Workspace Tables

**✅ Use workspace tables when:**
- Dataset exceeds 1000 rows
- Multi-step processing required
- Need to cache intermediate results
- Complex queries that would fill context window
- Building data transformation pipelines

**❌ Don't use workspace tables when:**
- Simple single query sufficient
- Dataset <100 rows
- One-time read operation
- Results fit easily in context window

### Storage Optimization

**Indexes:**
Add indexes to frequently queried columns:
```python
schema='''
    id INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL,
    complexity REAL,
    INDEX idx_complexity ON workspace_my_table(complexity)
'''
```

**Cleanup:**
Drop tables as soon as analysis is complete to avoid database bloat.

## Token Efficiency

### Before Workspace Tables
```
Large dataset (10,000 items)
↓
Load all into context (50KB)
↓
Context window filled immediately
↓
Can't continue analysis ❌
```

### After Workspace Tables
```
Large dataset (10,000 items)
↓
Store in workspace table (0 tokens)
↓
Query top 20 results (2KB)
↓
Context window preserved ✅
↓
Can continue analysis, get more via pagination
```

## Limitations

1. **SQLite Only:** Currently only works with SQLite databases
2. **No Transactions:** Each operation is auto-committed
3. **No ALTER TABLE:** Cannot modify existing workspace table schemas (must drop and recreate)
4. **No Joins with Core Tables:** Workspace tables are isolated namespace
5. **Manual Cleanup:** Tables persist until explicitly dropped

## Future Enhancements

Potential future additions:
- Auto-cleanup on session end (mark tables with TTL)
- ALTER TABLE support for schema modifications
- Performance monitoring (query execution time)
- Size limits per workspace table
- Compression for large text fields

---

**Version:** 1.0
**Added:** Phase 1 Token Optimization
**Status:** Production Ready ✅
