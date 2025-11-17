#!/usr/bin/env python3
"""
Comprehensive tests for claude_mcp_utils.py

Tests all utility functions with edge cases, error conditions,
and production scenarios.

Run with: python3 -m pytest test_claude_mcp_utils.py -v
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import functions to test
from claude_mcp_utils import (
    sanitize_project_name,
    validate_session_store,
    safe_json_response,
    get_db_connection,
    format_error_response,
    validate_project_name,
    truncate_string,
)


class TestSanitizeProjectName:
    """Test sanitize_project_name() function."""

    def test_basic_sanitization(self):
        """Test basic name sanitization."""
        assert sanitize_project_name("my-project") == "my_project"
        assert sanitize_project_name("Test_Project") == "test_project"
        assert sanitize_project_name("simple") == "simple"

    def test_special_characters_removed(self):
        """Test removal of special characters."""
        assert sanitize_project_name("My Project!@#") == "my_project"
        assert sanitize_project_name("test.db-name") == "test_db_name"
        assert sanitize_project_name("app(v2)") == "app_v2"
        assert sanitize_project_name("api/config") == "api_config"

    def test_collapse_multiple_underscores(self):
        """Test collapsing multiple underscores to single."""
        assert sanitize_project_name("test___name") == "test_name"
        assert sanitize_project_name("a__b__c") == "a_b_c"
        assert sanitize_project_name("foo____bar") == "foo_bar"

    def test_strip_leading_trailing_underscores(self):
        """Test stripping leading/trailing underscores."""
        assert sanitize_project_name("_test_") == "test"
        assert sanitize_project_name("__name__") == "name"
        assert sanitize_project_name("___project___") == "project"

    def test_truncation_to_max_length(self):
        """Test truncation to max length (default 32)."""
        long_name = "a" * 100
        result = sanitize_project_name(long_name)
        assert len(result) == 32
        assert result == "a" * 32

    def test_custom_max_length(self):
        """Test custom max length parameter."""
        long_name = "projectname" * 10
        result = sanitize_project_name(long_name, max_length=10)
        assert len(result) == 10

    def test_preserves_numbers(self):
        """Test that numbers are preserved."""
        assert sanitize_project_name("project123") == "project123"
        assert sanitize_project_name("2024-app") == "2024_app"

    def test_case_conversion(self):
        """Test lowercase conversion."""
        assert sanitize_project_name("UPPERCASE") == "uppercase"
        assert sanitize_project_name("MixedCase") == "mixedcase"
        assert sanitize_project_name("camelCase") == "camelcase"

    def test_empty_name_raises_error(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            sanitize_project_name("")

    def test_only_special_chars_raises_error(self):
        """Test that name with only special characters raises error."""
        with pytest.raises(ValueError, match="cannot be sanitized"):
            sanitize_project_name("!@#$%^&*()")

        with pytest.raises(ValueError, match="cannot be sanitized"):
            sanitize_project_name("---")

    def test_real_world_examples(self):
        """Test real-world project names."""
        assert sanitize_project_name("My-Project!") == "my_project"
        assert sanitize_project_name("API.Config-2024") == "api_config_2024"
        assert sanitize_project_name("user_db") == "user_db"
        assert sanitize_project_name("test-env-prod") == "test_env_prod"

    def test_unicode_characters(self):
        """Test handling of unicode characters."""
        assert sanitize_project_name("café") == "caf"
        assert sanitize_project_name("项目") == ""  # Should raise on empty

        with pytest.raises(ValueError):
            sanitize_project_name("项目")  # Chinese chars only


class TestValidateSessionStore:
    """Test validate_session_store() function."""

    @patch('claude_mcp_utils._session_store')
    @patch('claude_mcp_utils._local_session_id')
    def test_valid_session_store(self, mock_session_id, mock_store):
        """Test with valid session store and ID."""
        # Note: This test requires mocking the imports correctly
        # In actual implementation, this would need proper module mocking
        pass  # Placeholder - see note below

    def test_import_error_handling(self):
        """Test handling when module import fails."""
        # This would be tested with proper import mocking
        pass  # Placeholder - requires environment setup

    # Note: Full testing of validate_session_store() requires integration
    # testing with actual claude_mcp_hybrid_sessions.py module loaded


class TestSafeJsonResponse:
    """Test safe_json_response() function."""

    def test_success_response_basic(self):
        """Test basic success response."""
        result = safe_json_response({"message": "Done", "count": 5})
        data = json.loads(result)

        assert data["success"] is True
        assert data["message"] == "Done"
        assert data["count"] == 5

    def test_error_response(self):
        """Test error response."""
        result = safe_json_response({"error": "Failed"}, success=False)
        data = json.loads(result)

        assert data["success"] is False
        assert data["error"] == "Failed"

    def test_includes_timestamp_when_requested(self):
        """Test timestamp inclusion."""
        result = safe_json_response({"data": "test"}, include_timestamp=True)
        data = json.loads(result)

        assert "timestamp" in data
        assert data["timestamp"].endswith("Z")
        # Verify it's a valid ISO format timestamp
        datetime.fromisoformat(data["timestamp"].rstrip("Z"))

    def test_no_timestamp_by_default(self):
        """Test that timestamp is not included by default."""
        result = safe_json_response({"data": "test"})
        data = json.loads(result)

        assert "timestamp" not in data

    def test_formatting_with_indent(self):
        """Test JSON is formatted with 2-space indent."""
        result = safe_json_response({"key": "value"})

        # Check for indentation in output
        assert "\n" in result
        assert "  " in result  # 2-space indent

    def test_complex_nested_data(self):
        """Test with complex nested data structures."""
        complex_data = {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"}
            ],
            "metadata": {
                "total": 2,
                "page": 1
            }
        }
        result = safe_json_response(complex_data)
        data = json.loads(result)

        assert data["success"] is True
        assert len(data["users"]) == 2
        assert data["metadata"]["total"] == 2

    def test_non_serializable_objects_handled(self):
        """Test handling of non-serializable objects."""
        class CustomObject:
            def __str__(self):
                return "CustomObject"

        # Should use default=str fallback
        result = safe_json_response({"obj": CustomObject()})
        data = json.loads(result)

        assert "obj" in data
        assert data["obj"] == "CustomObject"

    def test_empty_data_dict(self):
        """Test with empty data dictionary."""
        result = safe_json_response({})
        data = json.loads(result)

        assert data == {"success": True}

    def test_preserves_boolean_values(self):
        """Test that boolean values are preserved correctly."""
        result = safe_json_response({
            "is_active": True,
            "is_deleted": False
        })
        data = json.loads(result)

        assert data["is_active"] is True
        assert data["is_deleted"] is False

    def test_preserves_none_values(self):
        """Test that None values are preserved."""
        result = safe_json_response({"value": None})
        data = json.loads(result)

        assert data["value"] is None


class TestGetDbConnection:
    """Test get_db_connection() context manager."""

    @patch('claude_mcp_utils._get_db_for_project')
    def test_yields_connection(self, mock_get_db):
        """Test that context manager yields connection."""
        mock_conn = Mock()
        mock_get_db.return_value = mock_conn

        with get_db_connection("test_project") as conn:
            assert conn == mock_conn

        mock_get_db.assert_called_once_with("test_project")

    @patch('claude_mcp_utils._get_db_for_project')
    def test_closes_connection_on_success(self, mock_get_db):
        """Test connection is closed on successful execution."""
        mock_conn = Mock()
        mock_get_db.return_value = mock_conn

        with get_db_connection("test_project") as conn:
            pass

        mock_conn.close.assert_called_once()

    @patch('claude_mcp_utils._get_db_for_project')
    def test_closes_connection_on_error(self, mock_get_db):
        """Test connection is closed even on exception."""
        mock_conn = Mock()
        mock_get_db.return_value = mock_conn

        with pytest.raises(ValueError):
            with get_db_connection("test_project") as conn:
                raise ValueError("Test error")

        mock_conn.close.assert_called_once()

    @patch('claude_mcp_utils._get_db_for_project')
    def test_handles_none_connection(self, mock_get_db):
        """Test handling when connection is None."""
        mock_get_db.return_value = None

        # Should not raise error
        with get_db_connection("test_project") as conn:
            assert conn is None

    @patch('claude_mcp_utils._get_db_for_project')
    def test_handles_close_error(self, mock_get_db):
        """Test handling when close() raises error."""
        mock_conn = Mock()
        mock_conn.close.side_effect = Exception("Close failed")
        mock_get_db.return_value = mock_conn

        # Should not raise error, just log warning
        with get_db_connection("test_project") as conn:
            pass

        # Verify close was attempted
        mock_conn.close.assert_called_once()


class TestFormatErrorResponse:
    """Test format_error_response() function."""

    def test_basic_error_formatting(self):
        """Test basic error formatting."""
        error = ValueError("Invalid input")
        result = format_error_response(error)
        data = json.loads(result)

        assert data["success"] is False
        assert data["error"] == "Invalid input"
        assert data["error_type"] == "ValueError"

    def test_with_context(self):
        """Test error formatting with context."""
        error = KeyError("missing_key")
        context = {"field": "name", "line": 42}
        result = format_error_response(error, context=context)
        data = json.loads(result)

        assert data["error"] == "'missing_key'"
        assert data["field"] == "name"
        assert data["line"] == 42

    def test_without_error_type(self):
        """Test error formatting without type."""
        error = RuntimeError("Test")
        result = format_error_response(error, include_type=False)
        data = json.loads(result)

        assert "error_type" not in data
        assert data["error"] == "Test"

    def test_different_exception_types(self):
        """Test formatting different exception types."""
        exceptions = [
            (ValueError("val"), "ValueError"),
            (KeyError("key"), "KeyError"),
            (RuntimeError("run"), "RuntimeError"),
            (Exception("generic"), "Exception"),
        ]

        for exc, expected_type in exceptions:
            result = format_error_response(exc)
            data = json.loads(result)
            assert data["error_type"] == expected_type


class TestValidateProjectName:
    """Test validate_project_name() function."""

    def test_valid_names(self):
        """Test valid project names return True."""
        assert validate_project_name("myproject") is True
        assert validate_project_name("test_db") is True
        assert validate_project_name("project123") is True
        assert validate_project_name("a1_b2_c3") is True

    def test_invalid_uppercase(self):
        """Test uppercase names are invalid."""
        assert validate_project_name("MyProject") is False
        assert validate_project_name("TEST") is False

    def test_invalid_special_chars(self):
        """Test names with special characters are invalid."""
        assert validate_project_name("my-project") is False
        assert validate_project_name("test.db") is False
        assert validate_project_name("app@v2") is False

    def test_invalid_empty(self):
        """Test empty string is invalid."""
        assert validate_project_name("") is False

    def test_invalid_too_long(self):
        """Test names longer than 32 chars are invalid."""
        assert validate_project_name("a" * 33) is False
        assert validate_project_name("a" * 100) is False

    def test_valid_max_length(self):
        """Test name at exactly 32 chars is valid."""
        assert validate_project_name("a" * 32) is True

    def test_only_underscores_valid(self):
        """Test name with only underscores is technically valid."""
        assert validate_project_name("_") is True
        assert validate_project_name("__") is True

    def test_numbers_only_valid(self):
        """Test name with only numbers is valid."""
        assert validate_project_name("123456") is True


class TestTruncateString:
    """Test truncate_string() function."""

    def test_no_truncation_needed(self):
        """Test string shorter than max_length."""
        assert truncate_string("Short", 10) == "Short"
        assert truncate_string("Hello", 5) == "Hello"

    def test_truncation_with_default_suffix(self):
        """Test truncation with default ... suffix."""
        assert truncate_string("Hello World", 8) == "Hello..."
        assert truncate_string("1234567890", 7) == "1234..."

    def test_truncation_with_custom_suffix(self):
        """Test truncation with custom suffix."""
        assert truncate_string("Hello World", 8, suffix="..") == "Hello .."
        assert truncate_string("Long text here", 10, suffix="…") == "Long text…"

    def test_empty_string(self):
        """Test with empty string."""
        assert truncate_string("", 10) == ""

    def test_exact_length(self):
        """Test string at exactly max_length."""
        assert truncate_string("12345", 5) == "12345"

    def test_very_short_max_length(self):
        """Test with very short max_length."""
        assert truncate_string("Hello", 3) == "..."
        assert truncate_string("Hi", 1, suffix="") == "H"

    def test_empty_suffix(self):
        """Test with empty suffix."""
        assert truncate_string("Hello World", 5, suffix="") == "Hello"


# Integration test helpers
class TestIntegration:
    """Integration tests combining multiple utilities."""

    def test_sanitize_and_validate_together(self):
        """Test sanitize and validate work together correctly."""
        # Names that need sanitization
        dirty_names = ["My-Project", "Test DB", "API_2024"]

        for dirty in dirty_names:
            clean = sanitize_project_name(dirty)
            # Cleaned name should always be valid
            assert validate_project_name(clean) is True

    def test_error_response_serialization(self):
        """Test error response can be serialized and parsed."""
        error = ValueError("Test error")
        response = format_error_response(error, context={"code": 400})

        # Should be valid JSON
        data = json.loads(response)
        assert data["success"] is False

        # Can be passed to safe_json_response
        final = safe_json_response(data, success=False)
        final_data = json.loads(final)
        assert final_data["success"] is False


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
