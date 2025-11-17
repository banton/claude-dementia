# lock_context Test Case Names (Concise List)

## 28 Test Cases for lock_context Refactoring

### Priority Auto-Detection (5 tests)
1. `test_priority_auto_detect_always_check_with_always`
2. `test_priority_auto_detect_always_check_with_never`
3. `test_priority_auto_detect_always_check_with_must`
4. `test_priority_auto_detect_important_with_critical`
5. `test_priority_auto_detect_reference_no_keywords`

### Version Management (5 tests)
6. `test_version_first_lock_creates_1_0`
7. `test_version_increment_1_0_to_1_1`
8. `test_version_increment_1_1_to_1_2`
9. `test_version_multiple_increments_sequential`
10. `test_version_respects_session_isolation`

### Keyword Extraction - 6 Patterns (7 tests)
11. `test_keyword_extract_output_pattern`
12. `test_keyword_extract_test_pattern`
13. `test_keyword_extract_config_pattern`
14. `test_keyword_extract_api_pattern`
15. `test_keyword_extract_database_pattern`
16. `test_keyword_extract_security_pattern`
17. `test_keyword_extract_multiple_keywords`

### Duplicate Handling & Validation (3 tests)
18. `test_duplicate_version_raises_error`
19. `test_invalid_priority_parameter`
20. `test_content_hash_uniqueness`

### Session & Project Isolation (3 tests)
21. `test_session_creation_if_not_exists`
22. `test_project_parameter_override`
23. `test_audit_trail_creation`

### Content Processing (3 tests)
24. `test_preview_generation_length_limit`
25. `test_key_concepts_extraction`
26. `test_metadata_json_structure`

### Embedding Generation - Graceful Failure (2 tests)
27. `test_embedding_graceful_failure_no_service`
28. `test_embedding_uses_preview_text`

---

## Test Execution Phases

| Phase | Tests | Type | Dependencies |
|-------|-------|------|--------------|
| 1 | 1-19 | Unit | Mock DB |
| 2 | 20-26 | Integration | PostgreSQL |
| 3 | 27-28 | Service | Mock embedding |

## Coverage by Scenario

| Scenario | Test Count | Coverage |
|----------|-----------|----------|
| Priority auto-detection | 5 | Keyword matching, case-insensitivity |
| Version incrementing | 5 | Sequential increments, session isolation |
| Keyword extraction (6 patterns) | 7 | Each pattern + multiple keywords |
| Duplicate handling | 3 | Errors, validation, uniqueness |
| Session/Project isolation | 3 | Auto-creation, overrides, auditing |
| Content processing | 3 | Preview, concepts, metadata |
| Embedding (graceful failure) | 2 | Service unavailable, text selection |

---

**Total Test Cases: 28**
**Target Coverage: >90%**
**Estimated Runtime: ~5-10 minutes**
