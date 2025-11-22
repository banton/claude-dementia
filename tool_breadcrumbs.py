"""
Tool Execution Breadcrumb Trail System

Provides structured logging for tracking MCP tool execution flow.
Each breadcrumb is a uniquely marked log entry that can be grepped/filtered.

Usage:
    from tool_breadcrumbs import breadcrumb, log_breadcrumb

    @breadcrumb
    async def my_tool(arguments: dict):
        log_breadcrumb("VALIDATE", "Checking arguments", tool="my_tool")
        # ... validation logic ...

        log_breadcrumb("DB_QUERY", "Fetching data", tool="my_tool", query="SELECT...")
        # ... database logic ...

        log_breadcrumb("SUCCESS", "Returning result", tool="my_tool", rows=10)
        return result
"""

import functools
import time
import json
from typing import Any, Callable, Dict
from datetime import datetime

# Import structlog if available, fallback to logging
try:
    from src.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class BreadcrumbMarkers:
    """Consistent markers for easy grepping."""
    ENTRY = "🔵 CRUMB-ENTRY"
    EXIT = "🟢 CRUMB-EXIT"
    ERROR = "🔴 CRUMB-ERROR"
    VALIDATE = "🟡 CRUMB-VALIDATE"
    DB_QUERY = "🟣 CRUMB-DB"
    DB_UPDATE = "🟣 CRUMB-UPDATE"
    CACHE_HIT = "💚 CRUMB-CACHE-HIT"
    CACHE_MISS = "💔 CRUMB-CACHE-MISS"
    PROJECT_CHECK = "🔷 CRUMB-PROJECT"
    SESSION_CHECK = "🔶 CRUMB-SESSION"
    SUCCESS = "✅ CRUMB-SUCCESS"
    WARNING = "⚠️ CRUMB-WARN"
    DEPRECATED = "⛔ CRUMB-DEPRECATED"


# Global session store reference
_session_store = None

def set_session_store(store):
    """Set the session store instance for breadcrumb persistence."""
    global _session_store
    _session_store = store

def log_breadcrumb(
    marker: str,
    message: str,
    tool: str = None,
    **extra
):
    """
    Log a breadcrumb with structured data.

    Args:
        marker: Breadcrumb marker (use BreadcrumbMarkers constants)
        message: Human-readable message
        tool: Tool name (optional if used within @breadcrumb decorator)
        **extra: Additional structured data to log

    Example:
        log_breadcrumb("DB_QUERY", "Fetching contexts",
                       tool="search_contexts", query="SELECT...", limit=10)
    """
    # Build structured log entry
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "tool": tool,
        "message": message,
        **extra
    }

    # Use marker prefix for easy grepping
    if not marker.startswith("CRUMB-"):
        marker = f"CRUMB-{marker}"

    # Log with marker for easy filtering
    logger.info(f"{marker} | {tool or 'unknown'} | {message} | {json.dumps(extra)}")

    # Persist to session store if available
    if _session_store:
        try:
            # Try to get session ID from config (set by claude_mcp_hybrid_sessions)
            # This avoids circular imports
            import sys
            main_module = sys.modules.get('__main__')
            
            # Check if we can get the session ID
            session_id = None
            
            # Try config first (if available in sys.modules)
            if 'claude_mcp_hybrid_sessions' in sys.modules:
                try:
                    from claude_mcp_hybrid_sessions import config
                    session_id = getattr(config, '_current_session_id', None)
                except:
                    pass
            
            # If not found, try to get from main module if it has get_current_session_id
            if not session_id and hasattr(main_module, 'get_current_session_id'):
                try:
                    session_id = main_module.get_current_session_id()
                except:
                    pass

            if session_id:
                _session_store.store_breadcrumb(
                    session_id=session_id,
                    marker=marker,
                    tool=tool,
                    message=message,
                    metadata=extra
                )
        except Exception as e:
            # Don't let persistence failure break the tool
            logger.warning(f"Failed to persist breadcrumb: {e}")


def breadcrumb(func: Callable) -> Callable:
    """
    Decorator to automatically log entry/exit breadcrumbs for MCP tools.

    Usage:
        @breadcrumb
        async def my_tool(arguments: dict):
            # Tool implementation
            return result

    Logs:
        - Entry with timestamp and arguments
        - Exit with duration and result size
        - Errors with exception details
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        tool_name = func.__name__
        start_time = time.time()

        # Log entry
        log_breadcrumb(
            BreadcrumbMarkers.ENTRY,
            f"Starting {tool_name}",
            tool=tool_name,
            args_count=len(args),
            kwargs_keys=list(kwargs.keys())
        )

        try:
            # Execute tool
            result = await func(*args, **kwargs)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Determine result size
            result_size = 0
            if isinstance(result, (list, tuple)):
                result_size = len(result)
            elif isinstance(result, str):
                result_size = len(result)
            elif isinstance(result, dict):
                result_size = len(str(result))

            # Log successful exit
            log_breadcrumb(
                BreadcrumbMarkers.EXIT,
                f"Completed {tool_name}",
                tool=tool_name,
                duration_ms=round(duration_ms, 2),
                result_size=result_size,
                status="success"
            )

            return result

        except Exception as e:
            # Calculate duration even for errors
            duration_ms = (time.time() - start_time) * 1000

            # Log error exit
            log_breadcrumb(
                BreadcrumbMarkers.ERROR,
                f"Error in {tool_name}: {str(e)}",
                tool=tool_name,
                duration_ms=round(duration_ms, 2),
                error_type=type(e).__name__,
                error_message=str(e),
                status="error"
            )

            # Re-raise exception
            raise

    return wrapper


def log_tool_stage(
    stage: str,
    tool: str,
    message: str,
    **extra
):
    """
    Log a specific stage within a tool's execution.

    Common stages:
        - VALIDATE: Input validation
        - PROJECT_CHECK: Project resolution
        - SESSION_CHECK: Session validation
        - DB_QUERY: Database read
        - DB_UPDATE: Database write
        - CACHE_HIT/CACHE_MISS: Cache operations
        - SUCCESS: Final success
        - WARNING: Non-fatal issues

    Example:
        log_tool_stage("VALIDATE", "search_contexts",
                       "Checking query length", query_len=150)
        log_tool_stage("DB_QUERY", "search_contexts",
                       "Running semantic search", threshold=0.7, limit=10)
    """
    # Map stage names to markers
    stage_markers = {
        "VALIDATE": BreadcrumbMarkers.VALIDATE,
        "PROJECT_CHECK": BreadcrumbMarkers.PROJECT_CHECK,
        "SESSION_CHECK": BreadcrumbMarkers.SESSION_CHECK,
        "DB_QUERY": BreadcrumbMarkers.DB_QUERY,
        "DB_UPDATE": BreadcrumbMarkers.DB_UPDATE,
        "CACHE_HIT": BreadcrumbMarkers.CACHE_HIT,
        "CACHE_MISS": BreadcrumbMarkers.CACHE_MISS,
        "SUCCESS": BreadcrumbMarkers.SUCCESS,
        "WARNING": BreadcrumbMarkers.WARNING,
        "ERROR": BreadcrumbMarkers.ERROR,
    }

    marker = stage_markers.get(stage, f"CRUMB-{stage}")
    log_breadcrumb(marker, message, tool=tool, stage=stage, **extra)


# Convenience functions for common patterns
def log_validation(tool: str, message: str, **extra):
    """Log validation step."""
    log_tool_stage("VALIDATE", tool, message, **extra)


def log_db_query(tool: str, query: str, **extra):
    """Log database query."""
    log_tool_stage("DB_QUERY", tool, f"Executing query",
                   query_preview=query[:100], **extra)


def log_db_update(tool: str, operation: str, **extra):
    """Log database update."""
    log_tool_stage("DB_UPDATE", tool, f"Executing {operation}", **extra)


def log_project_check(tool: str, project: str, **extra):
    """Log project resolution."""
    log_tool_stage("PROJECT_CHECK", tool, f"Resolving project: {project}",
                   project=project, **extra)


def log_session_check(tool: str, session_id: str, **extra):
    """Log session validation."""
    log_tool_stage("SESSION_CHECK", tool, f"Checking session",
                   session_id=session_id[:8], **extra)


# Example usage in a tool
async def example_instrumented_tool(arguments: dict):
    """
    Example of how to use breadcrumbs in a tool.
    """
    tool_name = "example_tool"

    # Entry logged automatically if using @breadcrumb decorator
    log_breadcrumb(BreadcrumbMarkers.ENTRY, "Starting", tool=tool_name)

    # Validation stage
    log_validation(tool_name, "Validating arguments",
                   arg_count=len(arguments))

    # Project check
    project = arguments.get("project", "default")
    log_project_check(tool_name, project, source="arguments")

    # Database query
    log_db_query(tool_name, "SELECT * FROM contexts WHERE project = %s",
                 params=[project], limit=10)

    # Success
    log_breadcrumb(BreadcrumbMarkers.SUCCESS, "Query completed",
                   tool=tool_name, rows=5)

    # Exit logged automatically if using @breadcrumb decorator
    log_breadcrumb(BreadcrumbMarkers.EXIT, "Completed", tool=tool_name)

    return {"status": "success", "rows": 5}
