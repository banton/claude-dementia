# Function Refactoring Analysis
**Branch:** `claude/refactor-functions-01WQfcDL5fD8twQRvp6evAJj`
**Date:** 2025-11-17
**Goal:** Systematic function-level refactoring for improved maintainability

## Executive Summary

### Codebase Statistics
- **Total Files Analyzed:** 28 Python files
- **Total Functions:** 133+ functions
- **Primary File:** `claude_mcp_hybrid_sessions.py` (9,925 lines, 76 functions)
- **Critical Issues:** 15 functions >200 lines (largest: 766 lines)

### Refactoring Priorities
1. **P0 (Critical):** 15 functions >200 lines - immediate refactoring needed
2. **P1 (High):** 13 functions 100-200 lines - refactor during next iteration
3. **P2 (Medium):** 3 functions 50-100 lines - monitor and refactor if complexity increases
4. **P3 (Low):** 5 functions <50 lines - no action needed

---

## File: `claude_mcp_hybrid_sessions.py`

### P0: Critical Refactoring (>200 lines)

#### 1. `context_dashboard` - **766 lines** (Line 6503)
**Issues:**
- Single function handles entire dashboard generation
- Mixes data retrieval, formatting, and presentation logic
- Multiple database queries embedded
- Complex conditional logic for different view modes

**Refactoring Strategy:**
```python
# Split into:
- _fetch_dashboard_stats(conn, project) -> dict
- _format_context_summary(contexts: list) -> str
- _format_recent_activity(sessions: list) -> str
- _format_staleness_warnings(stale_contexts: list) -> str
- _format_priority_breakdown(stats: dict) -> str
- context_dashboard() -> str  # Orchestrator only
```

**Estimated Functions After:** 6 functions (~120 lines each)

---

#### 2. `ai_summarize_context` - **762 lines** (Line 7531)
**Issues:**
- Handles API calls, retry logic, error handling, and formatting
- Multiple LLM provider branches (OpenRouter, Ollama)
- Complex token management and chunking logic
- Embedded prompt templates

**Refactoring Strategy:**
```python
# Split into:
- _build_summarization_prompt(content: str, topic: str) -> str
- _call_llm_api(provider: str, prompt: str) -> dict
- _handle_llm_retry_logic(api_call: callable) -> dict
- _extract_summary_from_response(response: dict, provider: str) -> str
- _store_generated_summary(conn, topic: str, summary: str)
- ai_summarize_context() -> str  # Orchestrator
```

**Estimated Functions After:** 6 functions (~125 lines each)

---

#### 3. `query_database` - **504 lines** (Line 5046)
**Issues:**
- Combines query validation, execution, formatting, and pagination
- Multiple output formats (table, JSON, schema)
- Complex result processing logic
- Embedded SQL query templates for inspect_database

**Refactoring Strategy:**
```python
# Split into:
- _validate_sql_query(sql: str) -> tuple[bool, Optional[str]]
- _execute_safe_query(conn, sql: str, params: tuple) -> list
- _format_query_results(results: list, format: str) -> str
- _handle_query_pagination(conn, results: list, query_id: str) -> dict
- query_database() -> str  # Orchestrator
```

**Estimated Functions After:** 5 functions (~100 lines each)

---

#### 4. `apply_migrations` - **437 lines** (Line 8841)
**Issues:**
- Hardcoded migration SQL embedded in function
- No migration version tracking strategy
- Combines detection, application, and verification
- Long SQL strings make function unreadable

**Refactoring Strategy:**
```python
# Extract to:
migrations/
  - migration_v4_0.sql
  - migration_v4_1.sql
  - migration_v4_2.sql

# Refactor to:
- _load_migration_file(version: str) -> str
- _get_applied_migrations(conn) -> set
- _apply_single_migration(conn, version: str, sql: str) -> bool
- _verify_migration_success(conn, version: str) -> bool
- apply_migrations() -> str  # Orchestrator
```

**Estimated Functions After:** 5 functions + SQL files

---

#### 5. `search_contexts` - **402 lines** (Line 4529)
**Issues:**
- Combines full-text search, semantic search, and filtering
- Multiple search modes (basic, priority, tags)
- Complex scoring and ranking logic
- Result formatting mixed with search logic

**Refactoring Strategy:**
```python
# Split into:
- _build_search_query(query: str, priority: str, tags: str) -> tuple[str, tuple]
- _execute_fulltext_search(conn, query: str, filters: dict) -> list
- _execute_semantic_search(conn, query: str, filters: dict) -> list
- _rank_and_merge_results(fulltext: list, semantic: list) -> list
- _format_search_results(results: list, format: str) -> str
- search_contexts() -> str  # Orchestrator
```

**Estimated Functions After:** 6 functions (~65 lines each)

---

#### 6. `health_check_and_repair` - **362 lines** (Line 8293)
**Issues:**
- Performs multiple health checks in single function
- Repair logic embedded with check logic
- No clear separation of concerns
- Hard to test individual health checks

**Refactoring Strategy:**
```python
# Split into:
- _check_table_existence(conn) -> dict
- _check_schema_integrity(conn) -> dict
- _check_index_health(conn) -> dict
- _repair_missing_indexes(conn, issues: list) -> dict
- _verify_repair_success(conn) -> bool
- health_check_and_repair() -> str  # Orchestrator
```

**Estimated Functions After:** 6 functions (~60 lines each)

---

#### 7. `import_project` - **354 lines** (Line 9571)
**Issues:**
- Handles file I/O, validation, and database operations
- Complex error handling for various import formats
- Data transformation logic embedded
- Transaction management mixed with business logic

**Refactoring Strategy:**
```python
# Split into:
- _validate_import_file(file_path: str) -> dict
- _parse_import_data(file_path: str) -> dict
- _validate_import_schema(data: dict) -> tuple[bool, Optional[str]]
- _import_contexts(conn, contexts: list) -> int
- _import_sessions(conn, sessions: list) -> int
- import_project() -> str  # Orchestrator
```

**Estimated Functions After:** 6 functions (~60 lines each)

---

#### 8. `sleep` - **308 lines** (Line 2990)
**Issues:**
- Creates handover package with multiple components
- Fetches data from multiple tables
- Formatting logic mixed with data retrieval
- Staleness checking embedded

**Refactoring Strategy:**
```python
# Split into:
- _fetch_session_summary(conn, session_id: str) -> dict
- _fetch_important_contexts(conn, session_id: str) -> list
- _fetch_recent_activity(conn, session_id: str) -> list
- _check_staleness_warnings(conn, session_id: str) -> list
- _format_handover_package(summary: dict, contexts: list, activity: list) -> str
- sleep() -> str  # Orchestrator
```

**Estimated Functions After:** 6 functions (~50 lines each)

---

#### 9. `manage_workspace_table` - **304 lines** (Line 5837)
**Issues:**
- Handles create, drop, inspect operations in single function
- Complex validation logic for schema definitions
- SQL generation embedded
- Different operations have different return formats

**Refactoring Strategy:**
```python
# Split into:
- _validate_workspace_table_name(table_name: str) -> tuple[bool, Optional[str]]
- _validate_table_schema(schema: str) -> tuple[bool, Optional[str]]
- _create_workspace_table(conn, table_name: str, schema: str) -> dict
- _drop_workspace_table(conn, table_name: str) -> dict
- _inspect_workspace_table(conn, table_name: str) -> dict
- _list_workspace_tables(conn) -> list
- manage_workspace_table() -> str  # Router
```

**Estimated Functions After:** 7 functions (~40 lines each)

---

#### 10. `export_project` - **293 lines** (Line 9278)
**Issues:**
- Fetches data from multiple tables
- Builds export package structure
- Handles file I/O and compression
- Formatting mixed with data retrieval

**Refactoring Strategy:**
```python
# Split into:
- _fetch_export_contexts(conn, project: str) -> list
- _fetch_export_sessions(conn, project: str) -> list
- _fetch_export_metadata(conn, project: str) -> dict
- _build_export_package(contexts: list, sessions: list, metadata: dict) -> dict
- _write_export_file(data: dict, file_path: str, compress: bool) -> str
- export_project() -> str  # Orchestrator
```

**Estimated Functions After:** 6 functions (~50 lines each)

---

#### 11. `execute_sql` - **287 lines** (Line 5550)
**Issues:**
- Combines validation, execution, and result formatting
- Complex safety checks for write operations
- Transaction management embedded
- Dry-run logic mixed with actual execution

**Refactoring Strategy:**
```python
# Split into:
- _validate_write_operation(sql: str) -> tuple[bool, Optional[str]]
- _check_sql_safety(sql: str, params: tuple) -> tuple[bool, Optional[str]]
- _execute_write_operation(conn, sql: str, params: tuple, dry_run: bool) -> dict
- _format_execution_result(result: dict, dry_run: bool) -> str
- execute_sql() -> str  # Orchestrator
```

**Estimated Functions After:** 5 functions (~55 lines each)

---

#### 12. `wake_up` - **273 lines** (Line 2717)
**Issues:**
- Initializes session and loads multiple contexts
- Performs git status check
- Scans project files
- Formats output with multiple sections

**Refactoring Strategy:**
```python
# Split into:
- _initialize_session(conn, project: str) -> str
- _load_session_contexts(conn, session_id: str) -> list
- _scan_project_state(project_root: str) -> dict
- _check_git_status(project_root: str) -> Optional[dict]
- _format_wake_up_output(session: dict, contexts: list, git: dict, scan: dict) -> str
- wake_up() -> str  # Orchestrator
```

**Estimated Functions After:** 6 functions (~45 lines each)

---

#### 13. `lock_context` - **253 lines** (Line 3554)
**Issues:**
- Handles versioning, hashing, and preview generation
- Generates embeddings if available
- Stores in database with transaction management
- Format output with multiple sections

**Refactoring Strategy:**
```python
# Split into:
- _generate_context_hash(content: str) -> str
- _generate_context_preview(content: str) -> str
- _extract_key_concepts(content: str) -> list
- _generate_context_embedding(content: str) -> Optional[list]
- _store_context_lock(conn, topic: str, content: str, metadata: dict) -> int
- lock_context() -> str  # Orchestrator
```

**Estimated Functions After:** 6 functions (~40 lines each)

---

#### 14. `unlock_context` - **216 lines** (Line 3967)
**Issues:**
- Handles archival, version checking, and cleanup
- Complex version selection logic
- Formatting mixed with business logic

**Refactoring Strategy:**
```python
# Split into:
- _find_context_versions(conn, topic: str) -> list
- _select_version_to_unlock(versions: list, version: Optional[int]) -> dict
- _archive_context(conn, context_id: int) -> bool
- _format_unlock_result(context: dict, archived: bool) -> str
- unlock_context() -> str  # Orchestrator
```

**Estimated Functions After:** 5 functions (~45 lines each)

---

#### 15. `switch_project` - **205 lines** (Line 1995)
**Issues:**
- Validates project, switches schema, and closes sessions
- Database adapter management embedded
- Complex state transition logic

**Refactoring Strategy:**
```python
# Split into:
- _validate_project_exists(project: str) -> tuple[bool, Optional[str]]
- _close_current_session(conn, session_id: str)
- _switch_database_schema(project: str) -> PostgreSQLAdapter
- _initialize_new_session(conn, project: str) -> str
- switch_project() -> str  # Orchestrator
```

**Estimated Functions After:** 5 functions (~40 lines each)

---

### P1: High Priority Refactoring (100-200 lines)

#### 16. `explore_context_tree` - **200 lines** (Line 6303)
- Split tree building and formatting logic
- Extract flat/tree view formatters

#### 17. `inspect_schema` - **186 lines** (Line 8655)
- Extract schema inspection queries
- Separate formatting logic

#### 18. `select_project_for_session` - **177 lines** (Line 2540)
- Split validation and session creation
- Extract project selection logic

#### 19. `check_contexts` - **162 lines** (Line 6141)
- Separate relevance checking from formatting
- Extract scoring logic

#### 20. `recall_context` - **160 lines** (Line 3807)
- Split retrieval and formatting
- Extract preview generation

#### 21. `get_query_page` - **144 lines** (Line 3410)
- Separate pagination logic
- Extract result formatting

#### 22. `semantic_search_contexts` - **139 lines** (Line 7392)
- Split embedding generation and search
- Extract result ranking

#### 23. `batch_recall_contexts` - **135 lines** (Line 4394)
- Extract batch processing logic
- Separate formatting

#### 24. `generate_embeddings` - **123 lines** (Line 7269)
- Split API calls by provider
- Extract retry logic

#### 25. `sync_project_memory` - **115 lines** (Line 4931)
- Separate file scanning and context creation
- Extract metadata extraction

#### 26. `get_last_handover` - **112 lines** (Line 3298)
- Split retrieval and formatting

#### 27. `get_project_info` - **109 lines** (Line 2357)
- Separate stats calculation from formatting

#### 28. `batch_lock_contexts` - **101 lines** (Line 4293)
- Extract batch validation
- Separate individual lock operations

---

## File: `postgres_adapter.py`

### Class: `PostgreSQLAdapter`

**Methods Analyzed:** 12 methods in class

**Refactoring Needs:**
- Class is well-structured
- Methods are reasonably sized
- **Action:** No immediate refactoring needed

---

## File: `mcp_session_store.py`

### Class: `PostgreSQLSessionStore`

**Methods Analyzed:** 13 methods in class

**Refactoring Needs:**
- Session management logic well-encapsulated
- **Action:** Review for any >100 line methods

---

## File: `server_hosted.py`

**Functions Analyzed:** 6 functions

**Largest:** `execute_tool_endpoint` - 99 lines

**Refactoring Needs:**
- All functions <100 lines
- **Action:** No immediate refactoring needed

---

## File: `oauth_mock.py`

**Functions Analyzed:** 6 functions

**Largest:** `oauth_token` - 119 lines

**Refactoring Needs:**
- `oauth_token` could be split into validation + token generation
- **Action:** P1 priority (medium)

---

## File: `file_semantic_model.py`

**Functions Analyzed:** 13 functions

**Largest:** `detect_file_change` - 126 lines

**Refactoring Needs:**
- `detect_file_change` should split hash checking logic
- **Action:** P1 priority (medium)

---

## Refactoring Execution Plan

### Phase 1: Critical Functions (P0)
**Estimated Time:** 2-3 days

1. Start with smallest P0 functions first (200-250 lines)
2. Order:
   - `switch_project` (205 lines)
   - `unlock_context` (216 lines)
   - `lock_context` (253 lines)
   - `wake_up` (273 lines)
   - `execute_sql` (287 lines)
   - `export_project` (293 lines)
   - `manage_workspace_table` (304 lines)
   - `sleep` (308 lines)
   - `import_project` (354 lines)
   - `health_check_and_repair` (362 lines)
   - `search_contexts` (402 lines)
   - `apply_migrations` (437 lines)
   - `query_database` (504 lines)
   - `ai_summarize_context` (762 lines)
   - `context_dashboard` (766 lines)

### Phase 2: High Priority (P1)
**Estimated Time:** 1-2 days

- Refactor 100-200 line functions
- Focus on those with highest complexity

### Phase 3: Testing & Validation
**Estimated Time:** 1 day

- Ensure all refactored functions have tests
- Run integration tests
- Performance benchmarking

---

## Refactoring Principles

### 1. Single Responsibility
Each function should do ONE thing well

### 2. Function Size
Target: <50 lines per function
Maximum: <100 lines acceptable for orchestrators

### 3. Extraction Pattern
```python
# Before:
async def big_function(args):
    # 300 lines of mixed logic

# After:
async def big_function(args):
    # 30 lines - orchestration only
    data = await _fetch_data(args)
    validated = await _validate_data(data)
    result = await _process_data(validated)
    return _format_result(result)
```

### 4. Naming Convention
- Private helpers: `_verb_noun()` (e.g., `_fetch_contexts`, `_format_output`)
- Public API: `verb_noun()` (e.g., `lock_context`, `wake_up`)

### 5. Error Handling
- Extract to dedicated error handler functions
- Use decorators for common error patterns

---

## Success Metrics

### Code Quality
- [ ] No function >200 lines
- [ ] <5 functions >100 lines
- [ ] Average function size <50 lines
- [ ] Cyclomatic complexity <10 per function

### Maintainability
- [ ] Each function testable in isolation
- [ ] Clear separation of concerns
- [ ] Reduced code duplication
- [ ] Improved readability

### Performance
- [ ] No performance regression
- [ ] Faster test execution (better isolation)
- [ ] Easier debugging

---

## Next Steps

1. **Review this document** - Validate refactoring strategies
2. **Create test suite** - Ensure tests exist before refactoring
3. **Start Phase 1** - Begin with `switch_project` (smallest P0)
4. **Commit frequently** - One function refactoring per commit
5. **Update documentation** - Document new function structure

---

**Total Functions to Refactor:** 28 (15 P0, 13 P1)
**Estimated Total Time:** 4-6 days
**Expected Outcome:** ~100 well-sized, maintainable functions
