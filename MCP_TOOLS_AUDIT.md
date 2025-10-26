# MCP Tools Audit Report
**Date:** 2025-10-26

## Project Parameter Support

### ✅ Fully Supported (13/27 user-facing tools)
- switch_project, list_projects, delete_project
- wake_up, lock_context, recall_context, unlock_context, check_contexts
- sync_project_memory
- scan_project_files, query_files, file_model_status
- usage_statistics

### ❌ Missing Project Parameter (14 tools)

**Critical - Context/RLM Tools (6):**
- sleep
- get_last_handover
- batch_lock_contexts
- batch_recall_contexts
- search_contexts
- explore_context_tree

**Critical - Memory/Analytics (2):**
- memory_analytics
- context_dashboard

**Critical - Embeddings (3):**
- generate_embeddings
- semantic_search_contexts
- test_single_embedding

**Medium Priority - Files (1):**
- scan_and_analyze_directory

**Low Priority - Admin/Debug (3):**
- inspect_database
- execute_sql
- manage_workspace_table

## Embedding Support

### Tools That Generate Embeddings

**Currently Auto-Embedding:**
- ✅ lock_context() - Auto-generates on context lock

**Should Auto-Embed But Don't:**
- ❌ batch_lock_contexts() - Should embed all contexts
- ❌ wake_up() - Could embed handover content
- ❌ sleep() - Could embed handover being created

**Embedding Utilities (Don't Need Auto-Embed):**
- generate_embeddings() - Manual embedding tool
- semantic_search_contexts() - Uses embeddings (doesn't generate)
- embedding_status() - Status check only
- test_single_embedding() - Test utility

### Tools That Should Use Embeddings for Search

**Currently Using:**
- ✅ semantic_search_contexts() - Primary semantic search
- ✅ check_contexts() - Hybrid semantic + keyword

**Should Use But Don't:**
- ❌ search_contexts() - Still keyword-only
- ❌ explore_context_tree() - Could benefit from semantic grouping
- ❌ ai_summarize_context() - Could use embeddings to find related contexts

## Recommendations

### Phase 1: Critical Project Support (High Priority)
Add `project: Optional[str] = None` parameter to:
1. sleep
2. get_last_handover
3. batch_lock_contexts
4. batch_recall_contexts
5. search_contexts
6. explore_context_tree
7. memory_analytics
8. context_dashboard
9. generate_embeddings
10. semantic_search_contexts
11. test_single_embedding

### Phase 2: Embedding Integration (High Priority)
1. batch_lock_contexts() - Auto-embed all contexts
2. search_contexts() - Add semantic search option
3. explore_context_tree() - Use embeddings for clustering

### Phase 3: Admin Tools (Low Priority)
Add project support to admin/debug tools if needed:
- inspect_database
- execute_sql
- manage_workspace_table

## Implementation Notes

**Project Parameter Pattern:**
```python
@mcp.tool()
async def tool_name(
    # ... other params ...
    project: Optional[str] = None
) -> str:
    # Get connection with project resolution
    conn = get_db(project)
    # ... rest of implementation
```

**Embedding Pattern:**
```python
# After inserting/updating context
try:
    if embedding_service and embedding_service.enabled:
        embedding = embedding_service.generate_embedding(preview_text)
        if embedding:
            conn.execute("UPDATE ... SET embedding = ?", (pickle.dumps(embedding),))
except Exception as e:
    print(f"⚠️  Could not generate embedding: {e}", file=sys.stderr)
```

**Fallback Priority:**
1. Explicit `project` parameter (if provided)
2. Active project from session (if set via switch_project)
3. Auto-detect from filesystem (Claude Code only)
4. Default to "default" project
