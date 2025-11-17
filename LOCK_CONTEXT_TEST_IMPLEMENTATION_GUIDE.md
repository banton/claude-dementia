# lock_context Test Implementation Guide

## Quick Reference for Test Development

### Function Signature
```python
async def lock_context(
    content: str,
    topic: str,
    tags: Optional[str] = None,
    priority: Optional[str] = None,
    project: Optional[str] = None
) -> str
```

### Test Template Structure

```python
import pytest
import json
from unittest.mock import Mock, patch

class TestLockContextRefactoring:
    """Test suite for lock_context function"""

    @pytest.fixture
    def test_db(self):
        """Provide test database connection"""
        # Setup PostgreSQL test schema
        # Yield connection
        # Cleanup
        pass

    def test_case_name(self, test_db):
        # Arrange: Set up test data
        context = {
            "content": "...",
            "topic": "...",
            "tags": "..."
        }

        # Act: Call function
        result = await lock_context(**context)

        # Assert: Verify behavior
        assert "✅" in result
        assert "v1.0" in result
```

---

## Test Implementation Checklist

### Unit Tests (No DB Required)

#### Priority Auto-Detection Tests (1-5)
- [ ] Test "always"/"never"/"must" → "always_check"
- [ ] Test "important"/"critical"/"required" → "important"
- [ ] Test no keywords → "reference"
- [ ] Verify case-insensitive matching
- [ ] Verify error on invalid priority

**Mock Setup:**
```python
@patch('claude_mcp_hybrid_sessions._get_db_for_project')
def test_priority(mock_db):
    # Mock cursor.fetchone() to return None (no existing version)
    mock_cursor = Mock()
    mock_cursor.fetchone.return_value = None
```

#### Keyword Extraction Tests (11-17)
- [ ] Test each of 6 patterns independently
- [ ] Test multiple patterns in one content
- [ ] Verify regex patterns match correctly

**Test Data:**
```python
TEST_KEYWORDS = {
    'output': ['output', 'directory', 'folder', 'path'],
    'test': ['test', 'testing', 'spec'],
    'config': ['config', 'settings', 'configuration'],
    'api': ['api', 'endpoint', 'rest', 'graphql'],
    'database': ['database', 'db', 'sql', 'table'],
    'security': ['auth', 'token', 'password', 'secret'],
}
```

### Integration Tests (Real DB)

#### Version Management Tests (6-10)
- [ ] Create test PostgreSQL schema
- [ ] Test 1.0 creation on first lock
- [ ] Test 1.0 → 1.1 increment
- [ ] Test sequential increments (1.1 → 1.2 → 1.3)
- [ ] Verify session isolation for versions

**Database Setup:**
```python
@pytest.fixture(scope="function")
def test_postgres_db():
    """Create isolated test schema"""
    db_url = os.getenv("TEST_DATABASE_URL")
    adapter = PostgreSQLAdapter(db_url)

    # Create dementia_test schema
    adapter.execute_update("""
        DROP SCHEMA IF EXISTS dementia_test CASCADE;
        CREATE SCHEMA dementia_test;
    """)

    # Create context_locks table in schema
    adapter.execute_update("""
        CREATE TABLE dementia_test.context_locks (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            label TEXT NOT NULL,
            version TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata JSONB,
            preview TEXT,
            key_concepts JSONB,
            embedding BYTEA,
            embedding_model TEXT,
            last_accessed TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            UNIQUE(session_id, label, version)
        )
    """)

    yield adapter

    # Cleanup
    adapter.execute_update("DROP SCHEMA IF EXISTS dementia_test CASCADE;")
```

#### Session/Project Tests (21-23)
- [ ] Test session auto-creation
- [ ] Test project parameter override
- [ ] Verify audit trail in memory_entries

**Session Setup:**
```python
def test_session_creation_if_not_exists(test_postgres_db):
    """Verify session is created if not exists"""
    # Clear sessions table
    test_postgres_db.execute_update(
        "DELETE FROM dementia_test.sessions;"
    )

    # Call lock_context
    result = lock_context(
        content="test",
        topic="test_topic",
        project="test_project"
    )

    # Verify session was created
    cursor = test_postgres_db.execute_query(
        "SELECT * FROM dementia_test.sessions;"
    )
    assert len(cursor) > 0
```

### Content Processing Tests (24-26)

#### Preview Generation (Test 24)
- [ ] Verify preview ≤ 500 chars
- [ ] Test with content > 10,000 chars
- [ ] Verify preview contains key terms

```python
def test_preview_generation_length_limit():
    """Verify preview capped at 500 chars"""
    large_content = "x" * 10000
    preview = generate_preview(large_content, max_length=500)
    assert len(preview) <= 500
    assert len(preview) > 0  # Not empty
```

#### Key Concepts Extraction (Test 25)
- [ ] Verify concepts extracted correctly
- [ ] Test with and without tags
- [ ] Verify JSON format

```python
def test_key_concepts_extraction():
    """Verify key concepts extracted"""
    content = "PostgreSQL database with JWT tokens"
    tags = ["database", "security"]
    concepts = extract_key_concepts(content, tags)

    assert isinstance(concepts, list)
    assert len(concepts) > 0
    assert any("database" in c.lower() for c in concepts)
```

#### Metadata Structure (Test 26)
- [ ] Verify all required fields present
- [ ] Verify JSON validity
- [ ] Verify timestamps valid

```python
def test_metadata_json_structure(test_postgres_db):
    """Verify metadata JSON structure"""
    result = lock_context(
        content="test content",
        topic="metadata_test",
        tags="tag1,tag2",
        priority="important"
    )

    # Retrieve and parse metadata
    cursor = test_postgres_db.execute_query(
        "SELECT metadata FROM dementia_test.context_locks WHERE label = %s",
        ["metadata_test"]
    )

    metadata = json.loads(cursor[0]['metadata'])

    # Verify structure
    assert 'tags' in metadata
    assert 'priority' in metadata
    assert 'keywords' in metadata
    assert 'created_at' in metadata
    assert metadata['priority'] == "important"
    assert isinstance(metadata['tags'], list)
    assert isinstance(metadata['keywords'], list)
```

### Embedding Tests (27-28)

#### Graceful Failure (Test 27)
- [ ] Mock embedding service unavailable
- [ ] Verify context still locked
- [ ] Verify warning message logged

```python
@patch('src.services.embedding_service')
def test_embedding_graceful_failure_no_service(mock_service):
    """Verify embedding service failure doesn't block locking"""
    mock_service.enabled = False

    result = lock_context(
        content="test",
        topic="test_embedding"
    )

    # Should still succeed despite embedding service
    assert "✅" in result
    assert "[embedded]" not in result  # No embedding status
```

#### Preview Text Usage (Test 28)
- [ ] Verify embedding uses preview (≤1020 chars)
- [ ] Test with large content (>1020 chars)
- [ ] Verify truncation happens

```python
@patch('src.services.embedding_service.generate_embedding')
def test_embedding_uses_preview_text(mock_generate):
    """Verify embedding uses preview text"""
    large_content = "x" * 2000  # >1020 chars

    # Mock generate_embedding to capture input
    mock_generate.return_value = [0.1, 0.2, 0.3, ...]

    result = lock_context(
        content=large_content,
        topic="embedding_test"
    )

    # Verify generate_embedding was called with preview (≤1020)
    call_args = mock_generate.call_args
    embedding_text = call_args[0][0]
    assert len(embedding_text) <= 1020
```

---

## Running Tests

### Run all lock_context tests
```bash
pytest test_lock_context_*.py -v
```

### Run specific test category
```bash
# Priority detection tests
pytest -k "test_priority_auto_detect" -v

# Version management tests
pytest -k "test_version" -v

# Keyword extraction tests
pytest -k "test_keyword_extract" -v
```

### Run with coverage
```bash
pytest --cov=claude_mcp_hybrid_sessions --cov-report=html test_lock_context_*.py
```

### Run with logging
```bash
pytest -v -s --log-cli-level=DEBUG test_lock_context_*.py
```

---

## Common Test Assertions

```python
# Verify success response
assert "✅" in result

# Verify version number
assert "v1.0" in result or "v1.1" in result

# Verify priority indicator
assert "[ALWAYS CHECK]" in result  # for always_check
assert "[IMPORTANT]" in result      # for important
assert "[embedded]" in result       # if embedding succeeded

# Verify project label
assert "project 'innkeeper'" in result

# Verify content hash
assert "hash:" in result
```

---

## Debugging Tips

### Enable PostgreSQL Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# In tests
import psycopg2.extras
psycopg2.extras.register_uuid()
```

### Inspect Database State
```python
# Print all contexts in test schema
cursor = test_db.execute_query(
    "SELECT label, version, priority FROM dementia_test.context_locks ORDER BY label, version"
)
for row in cursor:
    print(f"{row['label']}: v{row['version']} ({row['priority']})")
```

### Test Data Inspection
```python
# Print metadata
metadata = json.loads(row['metadata'])
print(json.dumps(metadata, indent=2))

# Print keywords extracted
print(f"Keywords: {metadata['keywords']}")

# Print key concepts
concepts = json.loads(row['key_concepts'])
print(f"Concepts: {concepts}")
```

---

## Test Execution Timeline

| Phase | Tests | Time | Notes |
|-------|-------|------|-------|
| Setup | - | 1 min | Create schemas, fixtures |
| Unit | 1-19 | 2 min | Mock-based, fast |
| Integration | 20-26 | 4 min | Real DB operations |
| Services | 27-28 | 1 min | Mock embedding |
| Cleanup | - | 1 min | Drop schemas, reset |
| **Total** | **28** | **~9 min** | Full test suite |

---

## Expected Test Results

```
=============== test session starts ===============
collected 28 items

test_lock_context_priority.py::test_priority_auto_detect_always_check_with_always PASSED    [3%]
test_lock_context_priority.py::test_priority_auto_detect_always_check_with_never PASSED    [7%]
...
test_lock_context_embedding.py::test_embedding_uses_preview_text PASSED                    [100%]

=============== 28 passed in 9.23s ===============
```

---

## Document References

- **Main Function:** `/home/user/claude-dementia/claude_mcp_hybrid_sessions.py:3676-3926`
- **Test Plan:** `/home/user/claude-dementia/TEST_PLAN_LOCK_CONTEXT_REFACTORING.md`
- **Test Cases:** `/home/user/claude-dementia/LOCK_CONTEXT_TEST_CASES.md`
- **Helper Functions:** `generate_preview()`, `extract_key_concepts()` in `migrate_v4_1_rlm.py`
