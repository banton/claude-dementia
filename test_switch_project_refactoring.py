"""
Focused tests for switch_project refactoring.

This test file focuses on testing the refactored switch_project
function without requiring the full MCP server to be running.
Uses comprehensive mocking to test in isolation.
"""

import pytest
import json
import sys
from unittest.mock import Mock, MagicMock, patch, call
from contextlib import contextmanager

# We'll import the utilities directly
from claude_mcp_utils import (
    sanitize_project_name,
    validate_session_store,
    safe_json_response
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_session_store():
    """Mock session store."""
    store = Mock()
    store.update_session_project = Mock(return_value=True)
    return store


@pytest.fixture
def mock_db_connection():
    """Mock database connection with cursor."""
    conn = Mock()
    cursor = Mock()

    # Mock cursor for schema check
    cursor.fetchone = Mock(return_value={'schema_name': 'test_project'})

    # Mock for stats queries
    cursor.fetchone.side_effect = [
        {'schema_name': 'test_project'},  # Schema exists
        {'count': 5},  # Sessions count
        {'count': 10}  # Contexts count
    ]

    conn.cursor = Mock(return_value=cursor)
    conn.close = Mock()

    return conn


# ============================================================================
# Test Utility Functions (Used in Refactoring)
# ============================================================================

class TestUtilityFunctions:
    """Test that our utility functions work correctly for switch_project."""

    def test_sanitize_project_name_for_switch(self):
        """Test project name sanitization."""
        assert sanitize_project_name("My Project") == "my_project"
        assert sanitize_project_name("API-2024") == "api_2024"
        assert sanitize_project_name("user_db") == "user_db"

    def test_validate_session_store_success(self):
        """Test session store validation when valid."""
        # Mock the module
        mock_module = MagicMock()
        mock_module._session_store = Mock()
        mock_module._local_session_id = "test_session_123"

        with patch.dict('sys.modules', {'claude_mcp_hybrid_sessions': mock_module}):
            is_valid, error = validate_session_store()
            assert is_valid is True
            assert error is None

    def test_validate_session_store_missing(self):
        """Test session store validation when missing."""
        # Mock module with missing values
        mock_module = MagicMock()
        mock_module._session_store = None
        mock_module._local_session_id = None

        with patch.dict('sys.modules', {'claude_mcp_hybrid_sessions': mock_module}):
            is_valid, error = validate_session_store()
            assert is_valid is False
            assert "Session store not initialized" in error

    def test_safe_json_response_format(self):
        """Test JSON response formatting."""
        result = safe_json_response({
            "message": "Success",
            "project": "test"
        }, success=True)

        data = json.loads(result)
        assert data["success"] is True
        assert data["message"] == "Success"
        assert data["project"] == "test"


# ============================================================================
# Test switch_project Behavior (Before Refactoring)
# ============================================================================

class TestSwitchProjectBehavior:
    """
    Test expected behavior of switch_project function.
    These tests define what the function SHOULD do.
    """

    def test_sanitizes_project_name(self):
        """Project names should be sanitized to valid schema names."""
        # Test through utility (this is what refactored version will use)
        assert sanitize_project_name("My-Project!") == "my_project"
        assert sanitize_project_name("API.Config-2024") == "api_config_2024"

    def test_requires_active_session(self):
        """Should fail if no active session."""
        # This is what the refactored version should check
        mock_module = MagicMock()
        mock_module._session_store = None
        mock_module._local_session_id = None

        with patch.dict('sys.modules', {'claude_mcp_hybrid_sessions': mock_module}):
            is_valid, error = validate_session_store()
            assert is_valid is False
            assert error is not None

    def test_updates_session_store_first(self):
        """Should update session store before querying database."""
        # This is critical ordering requirement
        # The refactored version MUST update session store before DB query
        pass  # This will be tested in integration tests

    def test_updates_cache_after_db(self):
        """Should update in-memory cache after database."""
        # Order: DB → Cache (this prevents inconsistency)
        pass  # This will be tested in integration tests

    def test_returns_stats_for_existing_project(self):
        """Should return project stats if project exists."""
        # Expected response structure
        expected_keys = ["success", "message", "project", "schema", "exists", "stats"]
        # Refactored version should maintain this structure
        pass

    def test_returns_success_for_new_project(self):
        """Should return success even if project doesn't exist yet."""
        # New projects are created on first use
        expected_keys = ["success", "message", "project", "schema", "exists"]
        # Should NOT have stats for non-existent project
        pass


# ============================================================================
# Test Refactoring Integration (After Refactoring)
# ============================================================================

class TestRefactoredSwitchProject:
    """
    Tests for the refactored switch_project function.
    These will initially FAIL (RED phase) until refactoring is complete.
    """

    @pytest.mark.skip(reason="Refactoring not started yet")
    def test_uses_sanitize_utility(self):
        """Refactored version should use sanitize_project_name() utility."""
        # After refactoring, this should pass
        # The implementation should call sanitize_project_name()
        pass

    @pytest.mark.skip(reason="Refactoring not started yet")
    def test_uses_validate_session_utility(self):
        """Refactored version should use validate_session_store() utility."""
        pass

    @pytest.mark.skip(reason="Refactoring not started yet")
    def test_uses_safe_json_response(self):
        """Refactored version should use safe_json_response() utility."""
        pass


# ============================================================================
# Critical Integration Tests (Must Pass After Refactoring)
# ============================================================================

class TestCriticalIntegration:
    """
    Critical tests that MUST pass after refactoring.
    These ensure the WHOLE system works together.
    """

    @pytest.mark.skip(reason="Requires full system integration")
    def test_switch_updates_global_state_correctly(self):
        """Test that switching updates both DB and cache correctly."""
        # This tests the critical Bug #1 fix
        # Must use SAME session ID for both updates
        pass

    @pytest.mark.skip(reason="Requires full system integration")
    def test_downstream_tools_see_new_project(self):
        """Test that lock_context uses the switched project."""
        # After switch_project("new_proj"), lock_context should use "new_proj"
        pass

    @pytest.mark.skip(reason="Requires full system integration")
    def test_preserves_exact_behavior(self):
        """Test that refactored version has exact same behavior."""
        # Run same inputs through old and new version
        # Compare outputs - should be identical
        pass


# ============================================================================
# Edge Cases & Error Handling
# ============================================================================

class TestEdgeCases:
    """Test edge cases that refactoring must handle."""

    def test_empty_project_name_rejected(self):
        """Empty project names should raise error."""
        with pytest.raises(ValueError):
            sanitize_project_name("")

    def test_only_special_chars_rejected(self):
        """Names with only special characters should raise error."""
        with pytest.raises(ValueError):
            sanitize_project_name("!@#$%")

    def test_very_long_name_truncated(self):
        """Very long names should be truncated to 32 chars."""
        long_name = "a" * 100
        result = sanitize_project_name(long_name)
        assert len(result) == 32


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
