# CRUD Design Specification

## 1. update_context() Design

### Function Signature
```python
async def update_context(
    topic: str,
    content: str,
    version: str = "latest",
    tags: Optional[str] = None,
    priority: Optional[str] = None,
    reason: Optional[str] = None
) -> str
```

### Versioning Logic
1. **Find current version**:
   - If `version="latest"`: Find highest version (e.g., v1.2)
   - If `version="1.0"`: Use exact version

2. **Create new version**:
   - Parse current: "1.2" → (major=1, minor=2)
   - Increment minor: v1.2 → v1.3
   - If updating old version (not latest): Branch with warning

3. **Preserve history**:
   - Old version stays in database
   - Can recall any version with `recall_context(topic, version="1.2")`

### Update Process
```python
# 1. Verify topic exists
if not exists:
    return "❌ Topic not found. Use lock_context() to create."

# 2. Get current version
current = get_context(topic, version)

# 3. Calculate new version
new_version = increment_version(current.version)

# 4. Generate RLM data
preview = generate_preview(content)
key_concepts = extract_key_concepts(content, tags)

# 5. Insert new version (like lock_context)
INSERT INTO context_locks (
    session_id, label, version, content, preview, key_concepts,
    metadata, ...
)

# 6. Update metadata to track change
metadata = {
    "tags": tags or current.tags,
    "priority": priority or current.priority,
    "updated_from": current.version,
    "update_reason": reason,
    "updated_at": timestamp
}

# 7. Return confirmation
return "✅ Updated 'topic' v1.2 → v1.3 (reason: ...)"
```

### Safety Features
- ✅ Prevents updating if topic doesn't exist
- ✅ Warns if updating old version (not latest)
- ✅ Preserves all history
- ✅ Tracks update reason in metadata

### Edge Cases
- **Update v1.0 when v1.5 exists**: Creates v1.1 with warning
- **Content identical**: Still creates new version (explicit update)
- **No changes to tags/priority**: Inherits from previous version
- **Version collision**: UNIQUE constraint prevents (already handled)

---

## 2. unlock_context() Design

### Function Signature
```python
async def unlock_context(
    topic: str,
    version: str = "all",
    force: bool = False,
    archive: bool = True
) -> str
```

### Delete Logic
1. **Find contexts to delete**:
   - `version="all"`: Delete all versions of topic
   - `version="1.0"`: Delete specific version
   - `version="latest"`: Delete only latest version

2. **Safety checks**:
   - If priority="always_check": Require `force=True` and show warning
   - Show what will be deleted before confirmation
   - Count references (if context is linked by others)

3. **Archive before delete** (if `archive=True`):
   ```python
   # Create archive record
   INSERT INTO context_archives (
       original_id, label, version, content, deleted_at, delete_reason
   )

   # Then delete
   DELETE FROM context_locks WHERE ...
   ```

### Delete Process
```python
# 1. Find contexts to delete
contexts = find_contexts(topic, version)

if not contexts:
    return "❌ Context not found"

# 2. Check priority
has_critical = any(c.priority == "always_check" for c in contexts)
if has_critical and not force:
    return "⚠️ Contains critical context. Use force=True to confirm."

# 3. Archive first
if archive:
    for ctx in contexts:
        archive_context(ctx)

# 4. Delete
DELETE FROM context_locks WHERE topic=? AND version IN (...)

# 5. Return summary
return "✅ Deleted 3 version(s) of 'topic' (archived in .archives/)"
```

### Safety Features
- ✅ Requires `force=True` for always_check contexts
- ✅ Archives before delete (recoverable)
- ✅ Shows count of what will be deleted
- ✅ Prevents accidental bulk deletion

### Archive Schema
```sql
CREATE TABLE context_archives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    label TEXT NOT NULL,
    version TEXT NOT NULL,
    content TEXT NOT NULL,
    preview TEXT,
    key_concepts TEXT,
    metadata TEXT,
    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delete_reason TEXT
)
```

### Edge Cases
- **Delete non-existent**: Return error
- **Delete all when none exist**: Return error
- **Delete with archive=False**: Skip archive, delete directly
- **Recover from archive**: Manual SQL or future `unarchive_context()` tool

---

## 3. Integration with Existing Tools

### explore_context_tree()
- Shows only latest version by default
- Optional: Add "Show all versions" mode

### ask_memory()
- Searches only latest versions
- Prevents confusion from old versions

### recall_context()
- Already supports `version` parameter
- Works with history

### list_topics()
- Should show latest version only
- Mark as deprecated (use explore_context_tree)

---

## 4. Test Cases

### test_update_context()
1. ✅ Update latest version increments minor (v1.0 → v1.1)
2. ✅ Update with new tags/priority works
3. ✅ Old version still exists after update
4. ✅ Update generates new preview and key_concepts
5. ✅ Update non-existent topic returns error
6. ✅ Update specific old version creates branch
7. ✅ Metadata tracks update reason and parent version
8. ✅ Can recall both old and new versions

### test_unlock_context()
1. ✅ Delete all versions removes all
2. ✅ Delete specific version removes only that one
3. ✅ Delete latest keeps old versions
4. ✅ Delete always_check requires force=True
5. ✅ Archive is created before delete
6. ✅ Delete non-existent returns error
7. ✅ Can recover from archive (manual)
8. ✅ Deleted context not in search results

### test_crud_integration()
1. ✅ CREATE → UPDATE → DELETE workflow
2. ✅ Multiple updates create version history
3. ✅ Delete removes from all search tools
4. ✅ Update shows in explore_context_tree

---

## 5. Implementation Order

1. **Schema**: Add context_archives table
2. **Tests**: Write test_update_context.py (TDD - RED)
3. **Implement**: update_context() (GREEN)
4. **Tests**: Write test_unlock_context.py (TDD - RED)
5. **Implement**: unlock_context() (GREEN)
6. **Tests**: Write test_crud_workflow.py (integration)
7. **Refactor**: Clean up and optimize
8. **Docs**: Update tool descriptions
