#!/usr/bin/env python3
"""
Common utility functions for Claude Dementia MCP Server.

This module provides DRY (Don't Repeat Yourself) utilities extracted from
claude_mcp_hybrid_sessions.py to eliminate code duplication and improve
maintainability.

Key utilities:
- sanitize_project_name(): PostgreSQL schema name sanitization
- validate_session_store(): Session availability validation
- safe_json_response(): Standardized JSON response formatting
- get_db_connection(): Database connection context manager

Author: Claude Dementia Team
Version: 1.0.0
"""

import re
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def sanitize_project_name(name: str, max_length: int = 32) -> str:
    """
    Sanitize project name for use as PostgreSQL schema name.

    This function implements the exact pattern used 5+ times across
    claude_mcp_hybrid_sessions.py (lines 2022-2023, 2219-2220, etc.)

    Rules:
    - Convert to lowercase
    - Replace non-alphanumeric characters with underscores
    - Collapse multiple underscores to single underscore
    - Strip leading/trailing underscores
    - Truncate to max_length (default 32 for PostgreSQL identifier limit)

    Args:
        name: Raw project name (e.g., "My-Project!", "test___db")
        max_length: Maximum length (default: 32 chars for PostgreSQL)

    Returns:
        Sanitized schema-safe name (e.g., "my_project", "test_db")

    Raises:
        ValueError: If name is empty or results in empty string after sanitization

    Examples:
        >>> sanitize_project_name("My-Project!")
        'my_project'
        >>> sanitize_project_name("test___name")
        'test_name'
        >>> sanitize_project_name("a" * 100)
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'  # 32 chars
        >>> sanitize_project_name("API.Config-2024")
        'api_config_2024'
    """
    if not name:
        raise ValueError("Project name cannot be empty")

    # Convert to lowercase and replace non-alphanumeric with underscore
    safe = re.sub(r'[^a-z0-9]', '_', name.lower())

    # Collapse multiple underscores to single
    safe = re.sub(r'_+', '_', safe)

    # Strip leading/trailing underscores and truncate
    safe = safe.strip('_')[:max_length]

    # Ensure we didn't end up with empty string
    if not safe:
        raise ValueError(
            f"Project name '{name}' cannot be sanitized to valid schema name "
            f"(contains only special characters)"
        )

    return safe


def validate_session_store() -> Tuple[bool, Optional[str]]:
    """
    Check if session store and local session ID are available.

    This utility centralizes the session validation pattern used throughout
    the codebase (e.g., lines 2026-2030, 369-373).

    Returns:
        Tuple of (is_valid, error_message):
        - (True, None) if session store is available
        - (False, error_message) if session store is not available

    Examples:
        >>> is_valid, error = validate_session_store()
        >>> if not is_valid:
        ...     return json.dumps({"error": error})

    Note:
        This function accesses global variables _session_store and
        _local_session_id from claude_mcp_hybrid_sessions.py
    """
    # Import here to avoid circular dependencies
    try:
        from claude_mcp_hybrid_sessions import _session_store, _local_session_id
    except ImportError:
        return False, "Session management module not available"

    if not _session_store:
        return False, "Session store not initialized"

    if not _local_session_id:
        return False, "No active session ID"

    return True, None


def safe_json_response(
    data: Dict[str, Any],
    success: bool = True,
    include_timestamp: bool = False
) -> str:
    """
    Create standardized JSON response with consistent formatting.

    This utility standardizes the json.dumps() pattern used 145+ times
    across the codebase, ensuring consistent error/success response format.

    Args:
        data: Dictionary to serialize to JSON
        success: Whether this is a success response (default: True)
        include_timestamp: Whether to add ISO timestamp (default: False)

    Returns:
        JSON string with standardized formatting (2-space indent)

    Examples:
        >>> safe_json_response({"message": "Done", "count": 5})
        '{\\n  "success": true,\\n  "message": "Done",\\n  "count": 5\\n}'

        >>> safe_json_response({"error": "Failed"}, success=False)
        '{\\n  "success": false,\\n  "error": "Failed"\\n}'

        >>> safe_json_response({"data": [1,2,3]}, include_timestamp=True)
        # Includes "timestamp": "2025-11-17T12:34:56.789Z"
    """
    response = {"success": success, **data}

    if include_timestamp:
        response["timestamp"] = datetime.utcnow().isoformat() + "Z"

    try:
        return json.dumps(response, indent=2, default=str)
    except (TypeError, ValueError) as e:
        # Fallback for non-serializable objects
        logger.error(f"JSON serialization error: {e}")
        return json.dumps({
            "success": False,
            "error": "JSON serialization failed",
            "details": str(e)
        }, indent=2)


@contextmanager
def get_db_connection(project: Optional[str] = None):
    """
    Context manager for database connections with automatic cleanup.

    This utility wraps the existing _get_db_for_project() pattern to ensure
    connections are always properly closed, even on exceptions.

    Args:
        project: Project name (optional, uses default if None)

    Yields:
        Database connection (AutoClosingPostgreSQLConnection)

    Raises:
        Exception: Re-raises any database errors after cleanup

    Examples:
        >>> with get_db_connection("my_project") as conn:
        ...     cursor = conn.execute("SELECT * FROM table")
        ...     results = cursor.fetchall()
        # Connection automatically closed here

    Note:
        This is a wrapper around the existing _get_db_for_project()
        function from claude_mcp_hybrid_sessions.py. It provides a
        cleaner interface and ensures proper error handling.
    """
    # Import here to avoid circular dependencies
    from claude_mcp_hybrid_sessions import _get_db_for_project

    conn = None
    try:
        # Get connection using existing helper
        conn = _get_db_for_project(project)
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        # Ensure connection is closed
        if conn is not None:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"Error closing database connection: {e}")


def format_error_response(
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
    include_type: bool = True
) -> str:
    """
    Format exception as standardized JSON error response.

    This utility provides consistent error formatting across all MCP tools.

    Args:
        error: Exception object to format
        context: Optional context dictionary to include
        include_type: Whether to include exception type (default: True)

    Returns:
        JSON error response string

    Examples:
        >>> try:
        ...     raise ValueError("Invalid input")
        ... except Exception as e:
        ...     return format_error_response(e, {"field": "name"})
        '{\\n  "success": false,\\n  "error": "Invalid input",\\n  ...}'
    """
    response_data = {"error": str(error)}

    if include_type:
        response_data["error_type"] = type(error).__name__

    if context:
        response_data.update(context)

    return safe_json_response(response_data, success=False)


def validate_project_name(name: str) -> bool:
    """
    Check if project name is valid without sanitizing.

    This is useful for validation before sanitization or for checking
    if sanitization would change the name.

    Args:
        name: Project name to validate

    Returns:
        True if valid (lowercase alphanumeric + underscores, <= 32 chars)
        False otherwise

    Examples:
        >>> validate_project_name("myproject")
        True
        >>> validate_project_name("My-Project")
        False
        >>> validate_project_name("a" * 100)
        False
    """
    if not name:
        return False

    if len(name) > 32:
        return False

    # Must match pattern: lowercase alphanumeric and underscores only
    return bool(re.match(r'^[a-z0-9_]+$', name))


def truncate_string(
    text: str,
    max_length: int,
    suffix: str = "..."
) -> str:
    """
    Truncate string to maximum length with optional suffix.

    Args:
        text: String to truncate
        max_length: Maximum length (including suffix)
        suffix: Suffix to add if truncated (default: "...")

    Returns:
        Truncated string with suffix if needed

    Examples:
        >>> truncate_string("Hello World", 8)
        'Hello...'
        >>> truncate_string("Short", 10)
        'Short'
    """
    if len(text) <= max_length:
        return text

    suffix_len = len(suffix)
    return text[:max_length - suffix_len] + suffix


# Module metadata
__all__ = [
    'sanitize_project_name',
    'validate_session_store',
    'safe_json_response',
    'get_db_connection',
    'format_error_response',
    'validate_project_name',
    'truncate_string',
]

__version__ = '1.0.0'
