# Test Plan: lock_context Function Refactoring

## Overview
Comprehensive test plan for `lock_context()` function (claude_mcp_hybrid_sessions.py:3676-3926) covering priority detection, version management, keyword extraction, and project isolation.

---

## Test Suite: Priority Auto-Detection (5 tests)

### 1. test_priority_auto_detect_always_check_with_always
**Scenario:** Content contains "always" keyword
- Input: content="ALWAYS validate input on server"
- Expected: priority = "always_check"
- Validates: Case-insensitive keyword matching

### 2. test_priority_auto_detect_always_check_with_never
**Scenario:** Content contains "never" keyword
- Input: content="NEVER store passwords in plaintext"
- Expected: priority = "always_check"
- Validates: Multiple trigger keywords

### 3. test_priority_auto_detect_always_check_with_must
**Scenario:** Content contains "must" keyword
- Input: content="MUST use TLS for all connections"
- Expected: priority = "always_check"
- Validates: Priority detection consistency

### 4. test_priority_auto_detect_important_with_critical
**Scenario:** Content contains "critical" keyword
- Input: content="This is a critical architecture decision"
- Expected: priority = "important"
- Validates: Secondary priority level

### 5. test_priority_auto_detect_reference_no_keywords
**Scenario:** Content has no priority keywords
- Input: content="General documentation about the project structure"
- Expected: priority = "reference"
- Validates: Default priority fallback

---

## Test Suite: Version Management (5 tests)

### 6. test_version_first_lock_creates_1_0
**Scenario:** First context lock with a topic
- Setup: Empty database for topic "api_spec"
- Expected: version = "1.0"
- Validates: Initial version creation

### 7. test_version_increment_1_0_to_1_1
**Scenario:** Lock same topic a second time
- Setup: topic="api_spec" exists as v1.0
- Expected: version = "1.1"
- Validates: Correct increment

### 8. test_version_increment_1_1_to_1_2
**Scenario:** Lock same topic a third time
- Setup: topic="api_spec" exists as v1.1
- Expected: version = "1.2"
- Validates: Continuous increment

### 9. test_version_multiple_increments_sequential
**Scenario:** Lock same topic 5 times
- Setup: topic="config" starts fresh
- Expected: versions 1.0, 1.1, 1.2, 1.3, 1.4
- Validates: Sequential version management

### 10. test_version_respects_session_isolation
**Scenario:** Same topic in different sessions
- Setup: Lock "auth_rules" in session A, then in session B
- Expected: Each session has independent version (1.0)
- Validates: Session-scoped versioning

---

## Test Suite: Keyword Extraction (7 tests)

### 11. test_keyword_extract_output_pattern
**Scenario:** Content mentions output/directory/folder/path
- Input: content="Store all files in the output directory"
- Expected: keywords include "output"
- Validates: Pattern: r'\b(output|directory|folder|path)\b'

### 12. test_keyword_extract_test_pattern
**Scenario:** Content mentions test/testing/spec
- Input: content="Unit tests required before deployment. See test spec."
- Expected: keywords include "test"
- Validates: Pattern: r'\b(test|testing|spec)\b'

### 13. test_keyword_extract_config_pattern
**Scenario:** Content mentions config/settings/configuration
- Input: content="Application configuration stored in .env file"
- Expected: keywords include "config"
- Validates: Pattern: r'\b(config|settings|configuration)\b'

### 14. test_keyword_extract_api_pattern
**Scenario:** Content mentions api/endpoint/rest/graphql
- Input: content="REST API endpoints require authentication"
- Expected: keywords include "api"
- Validates: Pattern: r'\b(api|endpoint|rest|graphql)\b'

### 15. test_keyword_extract_database_pattern
**Scenario:** Content mentions database/db/sql/table
- Input: content="PostgreSQL database with normalized tables"
- Expected: keywords include "database"
- Validates: Pattern: r'\b(database|db|sql|table)\b'

### 16. test_keyword_extract_security_pattern
**Scenario:** Content mentions auth/token/password/secret
- Input: content="JWT tokens with secret key rotation"
- Expected: keywords include "security"
- Validates: Pattern: r'\b(auth|token|password|secret)\b'

### 17. test_keyword_extract_multiple_keywords
**Scenario:** Content matches multiple patterns
- Input: content="API authentication with database schema. ALWAYS validate tokens."
- Expected: keywords include "api", "security", "database", and priority="always_check"
- Validates: Multiple keyword extraction and priority interaction

---

## Test Suite: Duplicate Handling & Constraints (3 tests)

### 18. test_duplicate_version_raises_error
**Scenario:** Attempt to lock identical content with same topic within same session
- Setup: Lock "api_auth" v1.0 in session
- Action: Attempt to lock identical content again (would create v1.1)
- Expected: Success (version increments, not duplicate)
- Validates: Version system prevents true duplicates

### 19. test_invalid_priority_parameter
**Scenario:** User provides invalid priority value
- Input: priority="urgent" (invalid)
- Expected: Error message listing valid priorities
- Validates: Priority validation

### 20. test_content_hash_uniqueness
**Scenario:** Different content generates different hashes
- Input: content1="First API spec", content2="Different API spec"
- Expected: Different content_hash values
- Validates: SHA256 hashing correctness

---

## Test Suite: Session & Project Isolation (3 tests)

### 21. test_session_creation_if_not_exists
**Scenario:** Lock context in new session
- Setup: No existing session
- Action: lock_context() without active session
- Expected: Session created automatically, context locked
- Validates: Auto-session initialization

### 22. test_project_parameter_override
**Scenario:** Lock context in specific project
- Input: project="innkeeper"
- Expected: Context stored in innkeeper project's schema
- Validates: Project-specific context isolation

### 23. test_audit_trail_creation
**Scenario:** Context lock creates audit entry
- Action: lock_context(topic="api_spec", priority="important")
- Expected: memory_entries row created with message: "Locked context 'api_spec' v1.0 [IMPORTANT]..."
- Validates: Audit logging

---

## Test Suite: Content Processing (3 tests)

### 24. test_preview_generation_length_limit
**Scenario:** Preview is capped at 500 characters
- Input: content="A" * 10000
- Expected: preview is ≤ 500 chars
- Validates: Preview truncation

### 25. test_key_concepts_extraction
**Scenario:** Key concepts extracted from content
- Input: content="PostgreSQL database configuration with JWT tokens", tags=["database","security"]
- Expected: key_concepts contains relevant technical terms
- Validates: Concept extraction logic

### 26. test_metadata_json_structure
**Scenario:** Metadata JSON contains all required fields
- Expected: metadata includes: tags[], priority, keywords[], created_at
- Validates: Metadata completeness

---

## Test Suite: Embedding Generation (2 tests)

### 27. test_embedding_graceful_failure_no_service
**Scenario:** Embedding service unavailable
- Setup: Mock embedding_service.enabled = False
- Expected: Context locked successfully with warning, no embedding
- Validates: Non-blocking embedding failure

### 28. test_embedding_uses_preview_text
**Scenario:** Embedding generated from preview (not full content)
- Setup: content > 1020 chars, preview ≤ 1020 chars
- Expected: Embedding uses preview text, not full content
- Validates: Optimized embedding text selection

---

## Test Execution Strategy

### Phase 1: Unit Tests (Tests 1-19)
- Mock database operations
- Focus on logic: priority detection, versioning, keyword extraction
- No external services required

### Phase 2: Integration Tests (Tests 20-26)
- Use test PostgreSQL database
- Full database operations
- Verify storage and retrieval

### Phase 3: Service Integration (Tests 27-28)
- Mock embedding service
- Verify error handling
- Graceful failure scenarios

---

## Success Criteria

- ✅ All 28 tests pass
- ✅ Code coverage: >90% of lock_context function
- ✅ No regressions in existing functionality
- ✅ Performance: lock_context completes in <2 seconds
- ✅ Error messages clear and actionable

---

## Test Data Fixtures

### Fixture: Basic Context
```python
{
    "content": "API endpoint /users MUST use JWT authentication",
    "topic": "api_auth_rules",
    "tags": "api,security,auth",
    "priority": None  # auto-detect should be "always_check"
}
```

### Fixture: Large Content
```python
{
    "content": "..." * 100,  # 10,000+ chars
    "topic": "documentation",
    "tags": "docs"
}
```

### Fixture: Multi-Pattern Content
```python
{
    "content": """
    API Configuration: Database schema with table definitions.
    Test scenarios required. Authentication tokens. Output directory settings.
    NEVER expose secrets. ALWAYS validate input.
    """,
    "topic": "rules_config"
}
```

---

## Version History
- **Created:** 2025-11-17
- **Target:** lock_context refactoring completion
- **Test Framework:** pytest
- **Database:** PostgreSQL (test instance)
