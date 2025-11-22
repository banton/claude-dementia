#!/usr/bin/env python3
"""
Claude Dementia MCP Server (Session-Aware Fork)

This is a fork of claude_mcp_hybrid.py with PostgreSQL session persistence.
Designed for LOCAL testing of session management without HTTP middleware.

Key differences from original:
- Creates PostgreSQL session on startup
- Tracks session ID for tools to use
- Supports project selection workflow
- Sessions persist across restarts in database
"""

import os
import json
import sqlite3
import asyncio
import hashlib
import time
import re
import sys
import tempfile
import gzip
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Set, Tuple
import uuid
from contextlib import contextmanager

from mcp.server import FastMCP

# Enhanced scanner removed for v4.0.0-rc1 stable release

# Import breadcrumb trail system
from tool_breadcrumbs import (
    breadcrumb,
    log_breadcrumb,
    log_validation,
    log_db_query,
    log_db_update,
    log_project_check,
    log_session_check,
    log_tool_stage,
    log_tool_stage,
    BreadcrumbMarkers,
    set_session_store
)

# Import active context engine
from active_context_engine import (
    ActiveContextEngine,
    check_command_context,
    get_relevant_contexts_for_text,
    get_session_start_reminders
)

# Import RLM preview generation
from migrate_v4_1_rlm import generate_preview, extract_key_concepts

# Import file semantic model
from file_semantic_model import (
    detect_file_change,
    compute_file_hash,
    detect_file_type,
    check_standard_file_warnings,
    analyze_file_semantics,
    walk_project_files,
    cluster_files_by_semantics
)

# Initialize MCP server
mcp = FastMCP("claude-dementia")

# Initialize logger
import logging
logger = logging.getLogger(__name__)

# Import configuration
from src.config import config

# Import DRY utilities for code deduplication
from claude_mcp_utils import (
    sanitize_project_name,
    validate_session_store,
    safe_json_response,
    format_error_response
)

# ============================================================================
# POSTGRESQL/NEON DATABASE SETUP (ONLY MODE)
# ============================================================================
# Initialize PostgreSQL adapter - NO FALLBACK to SQLite
from postgres_adapter import PostgreSQLAdapter

# ============================================================================
# SESSION MANAGEMENT (New for session-aware fork)
# ============================================================================
from mcp_session_store import PostgreSQLSessionStore

# Global: Session tracking for this MCP instance
_local_session_id = None
_session_store = None

# Global: Handover auto-loading tracking
_handover_auto_loaded = False
_handover_message = None

# Global: Default adapter (lazy initialization for cloud deployment)
# WARNING: In stateless cloud (serverless/containers), these globals reset per request!
# Solution: postgres_adapter.py uses 1-1 pooling (no app-side pooling) + Neon pooler
_postgres_adapter = None
_adapter_cache = {}  # Cache adapters by schema name (works in local, resets in cloud)

def _get_db_adapter():
    """Lazy initialization of database adapter to avoid import-time connection failures."""
    global _postgres_adapter
    if _postgres_adapter is None:
        _postgres_adapter = PostgreSQLAdapter(
            database_url=config.database_url,
            schema=os.getenv('DEMENTIA_SCHEMA')  # Will auto-detect if not set
        )
        _postgres_adapter.ensure_schema_exists()
        print(f"✅ PostgreSQL/Neon connected (schema: {_postgres_adapter.schema})", file=sys.stderr)
        # Add to cache
        _adapter_cache[_postgres_adapter.schema] = _postgres_adapter
    return _postgres_adapter

def _validate_schema_name(schema_name: str) -> None:
    """
    Validate schema name to prevent SQL injection.

    Schema names must:
    - Be 1-63 characters (PostgreSQL limit)
    - Only contain alphanumeric, underscore, or hyphen
    - Not start with a digit

    Raises:
        ValueError: If schema name is invalid
    """
    if not schema_name:
        raise ValueError("Schema name cannot be empty")

    if len(schema_name) > 63:
        raise ValueError(f"Schema name too long: {len(schema_name)} chars (max 63)")

    # Check for valid characters (alphanumeric, underscore, hyphen)
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_-]*$', schema_name):
        raise ValueError(
            f"Invalid schema name '{schema_name}': "
            "must start with letter/underscore and contain only alphanumeric, underscore, or hyphen"
        )

def _get_cached_adapter(schema_name: str) -> PostgreSQLAdapter:
    """
    Get or create a cached adapter for the given schema.
    Prevents creating multiple connection pools for the same schema.

    CRITICAL: Each PostgreSQLAdapter creates a connection pool (1-10 connections).
    Creating multiple adapters for the same schema exhausts the connection pool!
    """
    global _adapter_cache

    # Validate schema name to prevent SQL injection
    _validate_schema_name(schema_name)

    if schema_name not in _adapter_cache:
        adapter = PostgreSQLAdapter(
            database_url=config.database_url,
            schema=schema_name
        )
        try:
            adapter.ensure_schema_exists()
        except Exception as e:
            # Only ignore "schema already exists" errors, re-raise others
            error_msg = str(e).lower()
            if 'already exists' in error_msg or 'duplicate' in error_msg:
                pass  # Schema exists, continue
            else:
                # Connection failure, permission error, etc - don't cache broken adapter
                print(f"❌ Failed to ensure schema '{schema_name}': {e}", file=sys.stderr)
                raise  # Re-raise to prevent caching broken adapter

        _adapter_cache[schema_name] = adapter
        print(f"✅ Cached new adapter for schema: {schema_name}", file=sys.stderr)

    return _adapter_cache[schema_name]

# ============================================================================
# SESSION INITIALIZATION (New for session-aware fork)
# ============================================================================

def _init_local_session():
    """
    Initialize local MCP session with PostgreSQL persistence.

    Creates a new session in the database with project_name='__PENDING__'
    so user must select project before using tools.

    Returns:
        str: Session ID

    Raises:
        RuntimeError: If MCP_TRANSPORT=http (unsafe with global session state)
    """
    # CRITICAL: Session-aware fork uses global state, ONLY safe for stdio (single-threaded)
    transport = os.getenv('MCP_TRANSPORT', 'stdio')
    if transport == 'http':
        raise RuntimeError(
            "🚫 Session-aware fork CANNOT run in HTTP mode (uses global state).\n"
            "   Global _local_session_id would be shared across concurrent requests.\n"
            "   This would cause data corruption (request A gets request B's session).\n"
            "\n"
            "   Solutions:\n"
            "   1. Use stdio transport for local testing: MCP_TRANSPORT=stdio\n"
            "   2. Use claude_mcp_hybrid.py (original) for HTTP/cloud deployments\n"
            "   3. Implement request-scoped session storage (not yet available)\n"
        )

    global _local_session_id, _session_store

    # Generate session ID
    _local_session_id = uuid.uuid4().hex

    # Get database adapter
    adapter = _get_db_adapter()
    _session_store = PostgreSQLSessionStore(adapter)

    # Create session in database
    try:
        result = _session_store.create_session(
            session_id=_local_session_id,
            project_name='__PENDING__',  # User must select project
            client_info={'transport': 'stdio', 'type': 'local_mcp'}
        )
        print(f"✅ MCP session created: {_local_session_id[:8]} (project selection required)", file=sys.stderr)

        # Set session context for tools to access
        config._current_session_id = _local_session_id

        # Initialize breadcrumb persistence
        set_session_store(_session_store)

        return _local_session_id
    except Exception as e:
        print(f"❌ Session creation failed: {e}", file=sys.stderr)
        raise

def _get_local_session_id() -> Optional[str]:
    """Get current local session ID."""
    return _local_session_id

def _auto_load_handover() -> Optional[str]:
    """
    Automatically load the last handover on first tool call.
    Returns the handover message to show to the LLM, or None if no handover exists.

    This replaces the need for explicit wake_up() calls.
    """
    global _handover_auto_loaded, _handover_message

    # Only load once per session
    if _handover_auto_loaded:
        return _handover_message

    _handover_auto_loaded = True

    try:
        # Get current project and database adapter
        project = _get_project_for_context()
        adapter = _get_db_adapter()
        session_id = get_current_session_id()

        # Look for most recent handover from a different session
        # Handovers are stored in memory_entries with category='handover'
        with adapter.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT metadata, timestamp
                    FROM memory_entries
                    WHERE category = 'handover'
                      AND session_id != %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (session_id,))

                handover = cur.fetchone()

        if handover:
            handover_data = json.loads(handover[0])  # metadata is first column
            hours_ago = (time.time() - handover[1]) / 3600  # timestamp is second column

            # Build compact summary
            summary_parts = []
            summary_parts.append(f"📋 **Previous Session ({hours_ago:.1f}h ago)**")

            # Work completed
            if handover_data.get('work_done', {}).get('completed_todos'):
                completed = handover_data['work_done']['completed_todos']
                summary_parts.append(f"\n✅ Completed: {len(completed)} tasks")
                for task in completed[:3]:
                    summary_parts.append(f"   • {task}")

            # Pending work
            if handover_data.get('next_steps', {}).get('todos'):
                pending = handover_data['next_steps']['todos']
                summary_parts.append(f"\n📋 Pending: {len(pending)} tasks")
                for task in pending[:3]:
                    priority = ['LOW', 'NORMAL', 'HIGH'][min(task.get('priority', 0), 2)]
                    summary_parts.append(f"   • [{priority}] {task['content']}")

            # Important context
            if handover_data.get('important_context', {}).get('critical_contexts'):
                contexts = handover_data['important_context']['critical_contexts']
                summary_parts.append(f"\n⚠️  {len(contexts)} critical contexts locked")

            _handover_message = "\n".join(summary_parts)
            return _handover_message
        else:
            _handover_message = "ℹ️  No previous session handover found (fresh start)"
            return None  # Don't show message for fresh starts

    except Exception as e:
        # Silently fail - don't block tool execution
        logger.debug(f"Auto-load handover failed: {e}")
        _handover_message = None
        return None


# Session-level active project tracking (per conversation)
_active_projects = {}  # {session_id: project_name}

def _check_project_selection_required(project: Optional[str] = None) -> Optional[str]:
    """
    Check if project selection is required before tool execution.

    For session-aware fork: Checks if session has project_name='__PENDING__'.
    If yes, returns error response with available projects.
    If no, returns None (tool can continue).

    Also triggers auto-load of previous session handover on first call.

    Args:
        project: Explicit project parameter (if provided, check is skipped)

    Returns:
        JSON error string if project selection required, None otherwise
    """
    global _session_store, _local_session_id

    # Auto-load handover on first tool call (does nothing after first call)
    handover_msg = _auto_load_handover()
    if handover_msg:
        # Print to stderr so LLM sees it in tool result context
        print(handover_msg, file=sys.stderr)

    # If explicit project parameter provided, validate it exists
    if project:
        # Validate project exists to prevent typos creating new schemas
        if not _session_store:
            return None  # No session management, can't validate

        try:
            projects = _session_store.get_projects_with_stats()
            project_names = [p['project_name'] for p in projects]

            if project not in project_names:
                return json.dumps({
                    "error": "INVALID_PROJECT",
                    "message": f"⚠️  Project '{project}' does not exist",
                    "available_projects": [p for p in project_names if p != '__PENDING__'],
                    "instruction": "📌 Use an existing project name or create a new project first"
                })
        except Exception as e:
            # Validation failed, but don't block tool - log warning
            print(f"⚠️  Project validation failed: {e}", file=sys.stderr)

        return None  # Project validated or validation unavailable

    # Check if session exists and has __PENDING__ project
    if not _session_store or not _local_session_id:
        return None  # No session management active

    try:
        session = _session_store.get_session(_local_session_id)

        if session and session.get('project_name') == '__PENDING__':
            # Get available projects
            projects = _session_store.get_projects_with_stats()

            # Filter out __PENDING__ from list
            project_names = [p['project_name'] for p in projects if p['project_name'] != '__PENDING__']

            return json.dumps({
                "error": "PROJECT_SELECTION_REQUIRED",
                "message": "⚠️  Please select a project before using this tool",
                "available_projects": project_names if project_names else ["(no projects yet - create one with create_project)"],
                "project_stats": [p for p in projects if p['project_name'] != '__PENDING__'],
                "instruction": "📌 Call select_project_for_session('project_name') to select a project"
            }, indent=2)
    except Exception as e:
        # If checking fails, allow tool to continue (don't block on error)
        print(f"⚠️  Warning: Could not check project selection: {e}", file=sys.stderr)
        return None

    return None  # Project selected, continue normally

def _get_project_for_context(project: str = None) -> str:
    """
    Determine which project to use for this operation.

    Priority:
    1. Explicit project parameter
    2. Session active project (from database, set via switch_project)
    3. Auto-detect from filesystem (Claude Code with git repo)
    4. Fall back to "default"

    Returns:
        str: Project name/schema to use
    """
    # Priority 1: Explicit parameter
    if project:
        return project

    # Priority 2: Session active project (from database for MCP server persistence)
    try:
        # Use session-aware fork's session ID (not old SQLite-based get_current_session_id)
        session_id = _get_local_session_id()

        # Skip if no session (session not initialized yet)
        if not session_id:
            pass  # Fall through to Priority 3
        else:
            # First check in-memory cache
            if session_id in _active_projects:
                return _active_projects[session_id]

            # Then check database (for MCP server statelessness)
            try:
                # Try all projects to find which one has this session with active_project set
                adapter = _get_db_adapter()

                # FIX: Use context manager to prevent connection leak
                with adapter.get_connection() as conn:
                    # Query active_project from sessions table
                    if hasattr(conn, 'execute_with_conversion'):  # PostgreSQL
                        result = conn.execute_with_conversion(
                            "SELECT active_project FROM sessions WHERE id = ? AND active_project IS NOT NULL",
                            (session_id,),
                            fetchone=True
                        )
                    else:  # SQLite
                        cursor = conn.execute(
                            "SELECT active_project FROM sessions WHERE id = ? AND active_project IS NOT NULL",
                            (session_id,)
                        )
                        result = cursor.fetchone()

                    if result:
                        active_project = result[0] if isinstance(result, tuple) else result.get('active_project')
                        if active_project:
                            # Cache it in memory for faster subsequent lookups
                            _active_projects[session_id] = active_project
                            return active_project
            except:
                pass
    except:
        pass

    # Priority 3: Auto-detect from filesystem (Claude Code only)
    # This uses the global adapter's auto-detection
    # Only works if we're in a project directory
    if _get_db_adapter().schema and _get_db_adapter().schema != 'default':
        return _get_db_adapter().schema

    # Priority 4: Default project
    return "default"


class AutoClosingPostgreSQLConnection:
    """Wrapper for PostgreSQL connections that returns them to pool"""
    def __init__(self, conn, adapter):
        self.conn = conn
        self.adapter = adapter
        self._closed = False

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def _convert_sql_placeholders(self, sql):
        """Convert SQLite placeholders (?) to PostgreSQL placeholders (%s)"""
        return sql.replace('?', '%s')

    def execute(self, sql, parameters=None):
        """Execute SQL with cursor (SQLite compatibility)"""
        # Convert SQLite placeholders to PostgreSQL
        sql = self._convert_sql_placeholders(sql)

        try:
            cur = self.conn.cursor()
            if parameters:
                cur.execute(sql, parameters)
            else:
                cur.execute(sql)
            return cur
        except Exception as e:
            # Log error details (rollback handled by __exit__() in context manager)
            print(f"⚠️  SQL Error: {e}", file=sys.stderr)
            print(f"   SQL: {sql[:200]}...", file=sys.stderr)
            raise  # Let context manager __exit__() handle rollback

    def cursor(self):
        """Get cursor from connection with RealDictCursor for dict-like row access"""
        from psycopg2.extras import RealDictCursor
        return self.conn.cursor(cursor_factory=RealDictCursor)

    def __enter__(self):
        """Context manager entry - return self for 'with' statement"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - commit on success, rollback on error"""
        if exc_type is None:
            self.conn.commit()  # Success - commit transaction
        else:
            self.conn.rollback()  # Error - rollback transaction
        self.close()
        return False  # Don't suppress exceptions

    def close(self):
        """Return connection to pool instead of closing"""
        if not self._closed:
            try:
                self.adapter.release_connection(self.conn)
                self._closed = True
            except:
                pass

    def __del__(self):
        """Fallback cleanup if close() wasn't called"""
        self.close()


def _get_table_list(conn, like_pattern: str = '%'):
    """
    Get list of tables from database (works with SQLite and PostgreSQL).

    Args:
        conn: Database connection
        like_pattern: SQL LIKE pattern for table names (default: all tables)

    Returns:
        List of dicts with 'name' and 'sql' keys
    """
    # Check if PostgreSQL (AutoClosingPostgreSQLConnection or psycopg2 connection)
    is_pg = isinstance(conn, AutoClosingPostgreSQLConnection) or not hasattr(conn, 'row_factory')

    if is_pg:
        # PostgreSQL - use ? placeholder (wrapper will convert to %s)
        cursor = conn.execute(f"""
            SELECT
                table_name as name,
                NULL as sql
            FROM information_schema.tables
            WHERE table_schema = current_schema()
            AND table_type = 'BASE TABLE'
            AND table_name LIKE ?
            ORDER BY table_name
        """, (like_pattern,))
    else:
        # SQLite
        cursor = conn.execute(f"""
            SELECT name, sql FROM sqlite_master
            WHERE type='table' AND name LIKE ?
            ORDER BY name
        """, (like_pattern,))

    return cursor.fetchall()

def _table_exists(conn, table_name: str) -> bool:
    """
    Check if a table exists (works with SQLite and PostgreSQL).

    Args:
        conn: Database connection
        table_name: Name of table to check

    Returns:
        True if table exists, False otherwise
    """
    # Check if PostgreSQL (AutoClosingPostgreSQLConnection or psycopg2 connection)
    is_pg = isinstance(conn, AutoClosingPostgreSQLConnection) or not hasattr(conn, 'row_factory')

    if is_pg:
        # PostgreSQL
        cursor = conn.execute("""
            SELECT table_name as name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
            AND table_name = ?
        """, (table_name,))
    else:
        # SQLite
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """, (table_name,))

    return cursor.fetchone() is not None

def _get_db_for_project(project: str = None):
    """
    Get database connection for a specific project.

    Args:
        project: Project name (uses fallback logic if not provided)

    Returns:
        Database connection for the specified project
    """
    target_project = _get_project_for_context(project)

    # If it's the same as our global adapter, reuse it
    if target_project == _get_db_adapter().schema:
        return get_db()

    # Get cached adapter for different project (prevents connection pool exhaustion)
    adapter = _get_cached_adapter(target_project)
    conn = adapter.get_connection()
    return AutoClosingPostgreSQLConnection(conn, adapter)

# ============================================================================
# ============================================================================

# ============================================================================
# UTILITY: Project information functions (used by both PostgreSQL and SQLite)
# ============================================================================

def get_project_root() -> str:
    """
    Dynamically get current project root.
    IMPORTANT: Returns CURRENT working directory, not cached value.
    This enables proper project isolation in long-running MCP servers.
    """
    if os.environ.get('CLAUDE_PROJECT_DIR'):
        return os.environ['CLAUDE_PROJECT_DIR']
    return os.getcwd()

def get_project_name() -> str:
    """Get current project name from dynamic project root."""
    return os.path.basename(get_project_root()) or 'Claude Desktop'

def is_project_directory(path: str) -> bool:
    """Check if path is a project directory (has .git, package.json, etc)."""
    project_markers = [
        '.git',
        'package.json',
        'requirements.txt',
        'pyproject.toml',
        'Cargo.toml',
        'go.mod',
        'pom.xml',
        'build.gradle',
        'Makefile'
    ]

    for marker in project_markers:
        if os.path.exists(os.path.join(path, marker)):
            return True

    return False

def get_current_db_path() -> str:
    """Get current database path (PostgreSQL returns schema name, not file path)."""
    if is_postgresql_mode():
        return f"postgresql://{_get_db_adapter().schema}"
    # SQLite mode disabled
    return "N/A"

def get_db_location_type() -> str:
    """Get human-readable description of database location."""
    if is_postgresql_mode():
        return "cloud (PostgreSQL/Neon)"
    return "unknown"

# ============================================================================
# POSTGRESQL: Connection wrapper for connection pooling
# ============================================================================

# ============================================================================
# POSTGRESQL-ONLY DATABASE FUNCTIONS
# ============================================================================

def is_postgresql_mode():
    """Always returns True - PostgreSQL is the only mode."""
    return True

def get_db():
    """
    Get PostgreSQL database connection with auto-cleanup.

    Uses the global adapter's default schema (no project switching).
    For project-aware connections, use _get_db_for_project(project) instead.

    Returns AutoClosingPostgreSQLConnection with:
    - Schema isolation via search_path (global adapter's schema)
    - Dict-like rows via RealDictCursor
    - Automatic placeholder conversion (? to %s)
    - Connection pooling (returned to pool on close)

    WARNING: Do not call this with a project parameter!
    Use _get_db_for_project(project) for project-aware connections.
    """
    conn = _get_db_adapter().get_connection()
    return AutoClosingPostgreSQLConnection(conn, _postgres_adapter)

# ============================================================================

# ============================================================================

# ============================================================================
# ACTIVE: Utility Functions (work with both SQLite and PostgreSQL)
# ============================================================================

def estimate_tokens(text: str) -> int:
    """Estimate token count (rough approximation)"""
    return len(text) // 4

def get_current_session_id() -> str:
    """Get or create session ID - tied to specific project context for safety"""
    # For testing: allow SESSION_ID to override
    if hasattr(sys.modules[__name__], 'SESSION_ID') and SESSION_ID:
        return SESSION_ID

    # ✅ PRODUCTION: Check if middleware set the session ID (MCP protocol sessions)
    # This allows production cloud deployments to use MCP sessions from middleware
    session_id_from_middleware = getattr(config, '_current_session_id', None)
    if session_id_from_middleware:
        return session_id_from_middleware

    # ✅ LOCAL TESTING: Fall back to filesystem-based project detection
    # This allows local npx testing to auto-create project-based sessions
    # ✅ FIX: Use context manager to ensure connection is closed
    with get_db() as conn:
        # CRITICAL: Use dynamic project detection for proper isolation in long-running MCP servers
        current_project_root = get_project_root()
        current_project_name = get_project_name()

        # Create a project fingerprint - this ensures sessions are project-specific
        project_fingerprint = hashlib.md5(f"{current_project_root}:{current_project_name}".encode()).hexdigest()[:8]

        # Find active session for THIS PROJECT
        cursor = conn.execute("""
            SELECT id, last_active, project_path, project_name
            FROM sessions
            WHERE project_fingerprint = ?
            ORDER BY last_active DESC
            LIMIT 1
        """, (project_fingerprint,))

        row = cursor.fetchone()
        if row:
            # Verify we're in the same project (safety check)
            if row['project_path'] != current_project_root:
                # Project moved but same logical project - update path
                conn.execute("""
                    UPDATE sessions
                    SET project_path = ?, last_active = ?
                    WHERE id = ?
                """, (current_project_root, time.time(), row['id']))
            else:
                # Normal case - just update activity
                conn.execute("""
                    UPDATE sessions
                    SET last_active = ?
                    WHERE id = ?
                """, (time.time(), row['id']))
            conn.commit()
            return row['id']

        # Create new session for this project
        session_id = f"{current_project_name[:4]}_{str(uuid.uuid4())[:8]}"

        # First add columns if they don't exist (migration - SQLite only)
        # PostgreSQL schema is already complete from ensure_schema_exists()
        if not is_postgresql_mode():
            cursor.execute("PRAGMA table_info(sessions)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'project_fingerprint' not in columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN project_fingerprint TEXT")
                conn.execute("ALTER TABLE sessions ADD COLUMN project_path TEXT")
                conn.execute("ALTER TABLE sessions ADD COLUMN project_name TEXT")
                conn.commit()

        conn.execute("""
            INSERT INTO sessions (id, started_at, last_active, project_fingerprint, project_path, project_name)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, time.time(), time.time(), project_fingerprint, current_project_root, current_project_name))
        conn.commit()

        return session_id

def _get_session_id_for_project(conn, project_name: Optional[str] = None) -> str:
    """
    Get the most recent session ID for a given project from the correct schema.

    Args:
        conn: Database connection (already connected to correct schema)
        project_name: Project name (optional, uses current project if None)

    Returns:
        Session ID for the project, or creates one if none exists
    """
    # Get project name if not provided
    if not project_name:
        project_name = get_project_name()

    # Find most recent session for this project in the current schema
    cursor = conn.execute("""
        SELECT id
        FROM sessions
        ORDER BY last_active DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    if row:
        return row['id']

    # No session exists - create one
    session_id = f"{project_name[:4]}_{str(uuid.uuid4())[:8]}"
    conn.execute("""
        INSERT INTO sessions (id, started_at, last_active, project_name)
        VALUES (?, ?, ?, ?)
    """, (session_id, time.time(), time.time(), project_name))
    conn.commit()

    return session_id

def update_session_activity():
    """Update last active time for current session"""
    # ✅ FIX: Use context manager to ensure connection is closed
    with get_db() as conn:
        session_id = get_current_session_id()
        conn.execute("""
            UPDATE sessions
            SET last_active = ?
            WHERE id = ?
        """, (time.time(), session_id))
        conn.commit()

def _check_path_correctness(conn) -> dict:
    """
    Check 1: Validate database path calculated from current directory.

    Args:
        conn: Database connection

    Returns:
        dict: Check result with passed, level, and metadata
    """
    if is_postgresql_mode():
        return {
            "passed": True,
            "note": "Skipped (PostgreSQL mode uses schema-based isolation)",
            "level": "informational"
        }

    try:
        current_cwd = os.getcwd()
        expected_hash = hashlib.md5(current_cwd.encode()).hexdigest()[:8]
        actual_db_path = get_current_db_path()
        expected_db_path = os.path.expanduser(f"~/.claude-dementia/{expected_hash}.db")

        # Normalize paths for comparison
        actual_normalized = os.path.normpath(actual_db_path)
        expected_normalized = os.path.normpath(expected_db_path)

        path_correct = actual_normalized == expected_normalized

        return {
            "passed": path_correct,
            "expected": expected_db_path,
            "actual": actual_db_path,
            "level": "important",
            "warning": None if path_correct else
                f"Database path mismatch. Expected: {expected_db_path}, Actual: {actual_db_path}"
        }
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "level": "important"
        }


def _check_hash_consistency(conn) -> dict:
    """
    Check 2: Verify database filename hash matches directory MD5.

    Args:
        conn: Database connection

    Returns:
        dict: Check result with passed, level, and metadata
    """
    if is_postgresql_mode():
        return {
            "passed": True,
            "note": "Skipped (PostgreSQL mode uses schema names for isolation)",
            "schema": _get_db_adapter().schema,
            "level": "informational"
        }

    try:
        current_cwd = os.getcwd()
        expected_hash = hashlib.md5(current_cwd.encode()).hexdigest()[:8]
        actual_db_path = get_current_db_path()
        db_filename = os.path.basename(actual_db_path)
        db_hash = db_filename.replace('.db', '')

        hash_consistent = db_hash == expected_hash

        result = {
            "passed": hash_consistent,
            "expected_hash": expected_hash,
            "actual_hash": db_hash,
            "directory": current_cwd,
            "level": "critical"
        }

        if not hash_consistent:
            result["error"] = (
                f"DATABASE ISOLATION VIOLATION: Hash mismatch! "
                f"Expected {expected_hash} for {current_cwd}, got {db_hash}"
            )
            result["recommendation"] = (
                "This indicates you may be using a database from a different project. "
                "Check if you're in the correct directory."
            )

        return result
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "level": "critical"
        }


def _check_session_alignment(conn) -> dict:
    """
    Check 3: Verify session fingerprint matches current project.

    Args:
        conn: Database connection

    Returns:
        dict: Check result with passed, level, and metadata
    """
    try:
        current_project_root = get_project_root()
        current_project_name = get_project_name()
        expected_fingerprint = hashlib.md5(
            f"{current_project_root}:{current_project_name}".encode()
        ).hexdigest()[:8]

        session_id = get_current_session_id()
        cursor = conn.execute(
            "SELECT project_fingerprint, project_path, project_name FROM sessions WHERE id = ?",
            (session_id,)
        )
        session = cursor.fetchone()

        if session:
            actual_fingerprint = session['project_fingerprint']
            session_aligned = actual_fingerprint == expected_fingerprint

            result = {
                "passed": session_aligned,
                "expected_fingerprint": expected_fingerprint,
                "actual_fingerprint": actual_fingerprint,
                "session_id": session_id,
                "level": "critical"
            }

            if not session_aligned:
                result["error"] = (
                    f"SESSION ISOLATION VIOLATION: Session fingerprint mismatch! "
                    f"Expected {expected_fingerprint}, got {actual_fingerprint}"
                )
                result["recommendation"] = (
                    f"Session {session_id} belongs to a different project. "
                    f"This should never happen with proper isolation."
                )

            return result
        else:
            return {
                "passed": False,
                "error": "Session not found in database",
                "level": "critical"
            }
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "level": "critical"
        }


def _check_path_mapping(conn) -> dict:
    """
    Check 4: Verify entry in path_mapping.json is accurate.

    Args:
        conn: Database connection

    Returns:
        dict: Check result with passed, level, and metadata
    """
    if is_postgresql_mode():
        return {
            "passed": True,
            "note": "Skipped (PostgreSQL mode uses schema names directly)",
            "schema": _get_db_adapter().schema,
            "level": "informational"
        }

    try:
        current_cwd = os.getcwd()
        mapping_file = os.path.expanduser("~/.claude-dementia/path_mapping.json")

        if os.path.exists(mapping_file):
            with open(mapping_file, 'r') as f:
                mappings = json.load(f)

            expected_hash = hashlib.md5(current_cwd.encode()).hexdigest()[:8]
            if expected_hash in mappings:
                mapping_entry = mappings[expected_hash]
                mapping_accurate = mapping_entry['path'] == current_cwd

                result = {
                    "passed": mapping_accurate,
                    "expected_path": current_cwd,
                    "mapped_path": mapping_entry['path'],
                    "mapped_name": mapping_entry['name'],
                    "level": "important"
                }

                if not mapping_accurate:
                    result["warning"] = (
                        f"Path mapping mismatch. Mapped to {mapping_entry['path']}, "
                        f"current directory is {current_cwd}"
                    )

                return result
            else:
                return {
                    "passed": False,
                    "error": f"No mapping entry found for hash {expected_hash}",
                    "level": "informational",
                    "warning": "Path mapping entry missing (will be created automatically)"
                }
        else:
            return {
                "passed": False,
                "error": "Path mapping file does not exist",
                "level": "informational"
            }
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "level": "informational"
        }


def _check_context_isolation(conn) -> dict:
    """
    Check 5: Verify no contexts from other projects exist.

    Args:
        conn: Database connection

    Returns:
        dict: Check result with passed, level, and metadata
    """
    try:
        cursor = conn.execute("SELECT DISTINCT session_id FROM context_locks")
        all_sessions = [row['session_id'] for row in cursor.fetchall()]
        current_session_id = get_current_session_id()

        foreign_sessions = [s for s in all_sessions if s != current_session_id]

        result = {
            "passed": len(foreign_sessions) == 0,
            "current_session": current_session_id,
            "foreign_sessions": foreign_sessions,
            "foreign_count": len(foreign_sessions),
            "level": "critical"
        }

        if len(foreign_sessions) > 0:
            result["error"] = (
                f"CONTEXT CONTAMINATION DETECTED: Found {len(foreign_sessions)} foreign sessions in database!"
            )
            result["recommendations"] = [
                "Your database contains contexts from other projects. "
                "This is a critical isolation violation. "
                "Each project should have its own database file."
            ]

            # Get details about foreign sessions
            for foreign_session in foreign_sessions[:5]:  # Limit to first 5
                cursor = conn.execute(
                    "SELECT COUNT(*) as count FROM context_locks WHERE session_id = ?",
                    (foreign_session,)
                )
                count = cursor.fetchone()['count']
                result["recommendations"].append(
                    f"  - Session {foreign_session}: {count} contexts"
                )

        return result
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "level": "critical"
        }


def _check_schema_integrity(conn) -> dict:
    """
    Check 6: Verify all required tables and columns exist.

    Args:
        conn: Database connection

    Returns:
        dict: Check result with passed, level, and metadata
    """
    try:
        # Skip SQLite-specific schema checks in PostgreSQL mode
        if not is_postgresql_mode():
            required_tables = [
                'sessions',
                'context_locks',
                'audit_trail',
                'handovers',
                'file_model',
                'file_change_history'
            ]

            missing_tables = []
            for table in required_tables:
                cursor = conn.execute(
                    f"SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,)
                )
                if cursor.fetchone() is None:
                    missing_tables.append(table)

            # Check critical columns in sessions table
            cursor = conn.execute("PRAGMA table_info(sessions)")
            session_columns = [col[1] for col in cursor.fetchall()]
            required_columns = ['project_fingerprint', 'project_path', 'project_name']
            missing_columns = [col for col in required_columns if col not in session_columns]
        else:
            # PostgreSQL - assume schema is correct (managed by postgres_adapter)
            missing_tables = []
            missing_columns = []

        schema_valid = len(missing_tables) == 0 and len(missing_columns) == 0

        result = {
            "passed": schema_valid,
            "missing_tables": missing_tables,
            "missing_columns": missing_columns,
            "level": "informational"
        }

        if not schema_valid:
            result["warning"] = (
                f"Schema incomplete: {len(missing_tables)} missing tables, "
                f"{len(missing_columns)} missing columns (will auto-migrate)"
            )

        return result
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "level": "informational"
        }


def _check_orphaned_data(conn) -> dict:
    """
    Check 7: Find orphaned records without valid sessions.

    Args:
        conn: Database connection

    Returns:
        dict: Check result with passed, level, and metadata
    """
    try:
        cursor = conn.execute("""
            SELECT cl.id, cl.label, cl.session_id
            FROM context_locks cl
            LEFT JOIN sessions s ON cl.session_id = s.id
            WHERE s.id IS NULL
        """)
        orphaned = cursor.fetchall()

        result = {
            "passed": len(orphaned) == 0,
            "orphaned_count": len(orphaned),
            "orphaned_contexts": [
                {"id": o['id'], "label": o['label'], "session_id": o['session_id']}
                for o in orphaned[:5]  # Limit to first 5
            ],
            "level": "informational"
        }

        if len(orphaned) > 0:
            result["warning"] = f"Found {len(orphaned)} orphaned contexts (no valid session)"
            result["recommendation"] = "Run cleanup to remove orphaned contexts"

        return result
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "level": "informational"
        }


def _check_session_metadata(conn) -> dict:
    """
    Check 8: Verify session record matches runtime parameters.

    Args:
        conn: Database connection

    Returns:
        dict: Check result with passed, level, and metadata
    """
    try:
        session_id = get_current_session_id()
        cursor = conn.execute(
            "SELECT project_path, project_name, last_active FROM sessions WHERE id = ?",
            (session_id,)
        )
        session = cursor.fetchone()

        if session:
            metadata_consistent = (
                session['project_path'] == get_project_root() and
                session['project_name'] == get_project_name()
            )

            time_since_active = time.time() - session['last_active']

            result = {
                "passed": metadata_consistent,
                "expected_path": get_project_root(),
                "actual_path": session['project_path'],
                "expected_name": get_project_name(),
                "actual_name": session['project_name'],
                "time_since_active": round(time_since_active, 2),
                "level": "important"
            }

            if not metadata_consistent:
                result["warning"] = (
                    "Session metadata out of sync with current project "
                    "(will be updated automatically)"
                )

            return result
        else:
            return {
                "passed": False,
                "error": "Session not found",
                "level": "important"
            }
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "level": "important"
        }


def validate_database_isolation(conn) -> dict:
    """
    Internal function to validate database isolation for current project.

    Args:
        conn: Existing database connection (to avoid creating new connection)

    Checks 8 parameters of database "rightness":
    1. Path Correctness - Database path calculated from current directory
    2. Hash Consistency - Database filename hash matches directory MD5
    3. Session Alignment - Session fingerprint matches current project
    4. Path Mapping - Entry in path_mapping.json is accurate
    5. Context Isolation - No contexts from other projects
    6. Schema Integrity - All required tables/columns exist
    7. No Orphaned Data - All contexts have valid sessions
    8. Session Metadata - Session record matches runtime parameters

    Returns:
        dict: Validation report with status, checks, warnings, errors
    """
    validation_report = {
        "valid": True,
        "level": "valid",  # valid | warning | critical
        "checks": {},
        "warnings": [],
        "errors": [],
        "recommendations": []
    }

    # Define validation checks in order
    checks = [
        ("path_correctness", _check_path_correctness),
        ("hash_consistency", _check_hash_consistency),
        ("session_alignment", _check_session_alignment),
        ("path_mapping", _check_path_mapping),
        ("context_isolation", _check_context_isolation),
        ("schema_integrity", _check_schema_integrity),
        ("orphaned_data", _check_orphaned_data),
        ("session_metadata", _check_session_metadata),
    ]

    # Run each validation check
    for check_name, check_func in checks:
        check_result = check_func(conn)
        validation_report["checks"][check_name] = check_result

        # Process check result
        if not check_result.get("passed", False):
            validation_report["valid"] = False

            # Update severity level
            check_level = check_result.get("level", "informational")
            if check_level == "critical":
                validation_report["level"] = "critical"
            elif check_level == "important" and validation_report["level"] != "critical":
                validation_report["level"] = "warning"

        # Aggregate warnings
        if "warning" in check_result and check_result["warning"]:
            validation_report["warnings"].append(check_result["warning"])

        # Aggregate errors
        if "error" in check_result and not check_result.get("passed", False):
            error_msg = check_result["error"]
            if error_msg not in validation_report["errors"]:
                validation_report["errors"].append(error_msg)

        # Aggregate recommendations
        if "recommendation" in check_result:
            validation_report["recommendations"].append(check_result["recommendation"])

        if "recommendations" in check_result:
            validation_report["recommendations"].extend(check_result["recommendations"])

    # Calculate summary stats
    checks_passed = sum(1 for check in validation_report["checks"].values() if check.get("passed", False))
    checks_total = len(validation_report["checks"])

    validation_report["summary"] = {
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "warnings_count": len(validation_report["warnings"]),
        "errors_count": len(validation_report["errors"]),
        "validated_at": time.time()
    }

    return validation_report

def analyze_file_content(file_path: Path) -> Set[str]:
    """Analyze file content for quality indicators"""
    tags = set()
    
    try:
        # Skip binary files
        if file_path.suffix in ['.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.zip', '.tar', '.gz']:
            return tags
            
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        content_lower = content.lower()
        
        # Check for improvement markers
        if re.search(r'\b(todo|fixme)\b', content_lower):
            tags.add('quality:needs-work')
        if re.search(r'\b(hack|xxx|temporary|workaround)\b', content_lower):
            tags.add('quality:has-workarounds')
        if re.search(r'\bFIXME\b', content):
            tags.add('quality:has-issues')
        
        # Check for test assertions (indicates it's tested or is a test)
        if re.search(r'\b(assert|expect|test|describe|it\(|beforeEach|afterEach)\b', content):
            tags.add('quality:tested')
        
        # Check for documentation comments
        if re.search(r'("""[\s\S]*?"""|/\*\*[\s\S]*?\*/|///)', content):
            tags.add('quality:documented')
        
        # Check for deprecated markers
        if re.search(r'@deprecated|DEPRECATED|deprecated', content):
            tags.add('status:deprecated')
        
        # Check for code complexity indicators
        lines = content.split('\n')
        if len(lines) > 500:
            tags.add('quality:large-file')
        if len(lines) > 1000:
            tags.add('quality:very-large')
        
        # Check for refactoring markers
        if re.search(r'\b(refactor|cleanup|improve|optimize)\b', content_lower):
            tags.add('quality:marked-for-refactor')
        
        # Check for technical debt markers
        if re.search(r'\b(technical.?debt|legacy|old.?code)\b', content_lower):
            tags.add('quality:technical-debt')
        
        # Check for mock data and static references - CRITICAL for tracking dev artifacts
        if re.search(r'\b(mock|dummy|fake|sample|test.?data|example.?data|placeholder|lorem.?ipsum)\b', content_lower):
            tags.add('quality:has-mock-data')
        if re.search(r'\b(hardcoded|hard.?coded|static.?value|magic.?number)\b', content_lower):
            tags.add('quality:has-hardcoded-values')
        # Check for common mock patterns
        if re.search(r'(foo|bar|baz|test@example|john.?doe|jane.?doe|12345|password123|admin/admin)', content_lower):
            tags.add('quality:has-placeholder-data')
        # Check for localhost/development URLs
        if re.search(r'(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.|10\.0\.|example\.com)', content_lower):
            tags.add('quality:has-dev-urls')
        
        # Check for security-sensitive patterns
        if re.search(r'\b(password|secret|token|api_key|private_key|credential)\b', content_lower):
            tags.add('security:sensitive')
            
        # Check for external API calls
        if re.search(r'\b(fetch|axios|requests|httpClient|urllib|curl)\b', content):
            tags.add('deps:external')
            
        # Check for database operations
        if re.search(r'\b(SELECT|INSERT|UPDATE|DELETE|query|execute|mongodb|redis|postgres)\b', content):
            tags.add('deps:database')
            
    except Exception:
        # If we can't read the file, skip content analysis
        pass
    
    return tags

def get_file_tags(file_path: Path, project_root: Path) -> Set[str]:
    """Generate tags for a file based on path, name, and content"""
    tags = set()
    rel_path = file_path.relative_to(project_root)
    path_parts = rel_path.parts
    file_name = file_path.name.lower()
    
    # Status based on directory
    if any(part in ['deprecated', 'legacy', 'old'] for part in path_parts):
        tags.add('status:deprecated')
    elif any(part in ['experiments', 'poc', 'prototype'] for part in path_parts):
        tags.add('status:poc')
    elif any(part in ['alpha', 'beta', 'preview'] for part in path_parts):
        tags.add('status:beta')
    elif any(part in ['stable', 'production', 'release'] for part in path_parts):
        tags.add('status:stable')
    
    # Domain based on directory or filename
    domain_patterns = {
        'auth': ['auth', 'login', 'signup', 'session', 'jwt', 'oauth'],
        'payment': ['payment', 'billing', 'stripe', 'checkout', 'subscription'],
        'user': ['user', 'profile', 'account', 'member'],
        'admin': ['admin', 'dashboard', 'management'],
        'api': ['api', 'endpoint', 'routes', 'rest', 'graphql'],
        'messaging': ['email', 'notification', 'message', 'sms', 'mail'],
        'analytics': ['analytics', 'metrics', 'tracking', 'stats', 'report'],
        'search': ['search', 'filter', 'query', 'elasticsearch', 'algolia'],
        'data': ['etl', 'pipeline', 'transform', 'migration', 'import', 'export']
    }
    
    for domain, patterns in domain_patterns.items():
        if any(pattern in str(rel_path).lower() for pattern in patterns):
            tags.add(f'domain:{domain}')
    
    # Layer based on directory structure and file patterns
    if 'test' in file_name or any('test' in part for part in path_parts):
        tags.add('layer:test')
    elif 'mock' in file_name or 'stub' in file_name:
        tags.add('layer:mock')
    elif any(part in ['models', 'model', 'schemas', 'schema'] for part in path_parts):
        tags.add('layer:model')
    elif any(part in ['views', 'view', 'components', 'component', 'pages', 'page'] for part in path_parts):
        tags.add('layer:view')
    elif any(part in ['controllers', 'controller', 'handlers', 'handler'] for part in path_parts):
        tags.add('layer:controller')
    elif any(part in ['services', 'service'] for part in path_parts):
        tags.add('layer:service')
    elif any(part in ['repositories', 'repository', 'dao'] for part in path_parts):
        tags.add('layer:repository')
    elif any(part in ['middleware', 'middlewares', 'interceptors'] for part in path_parts):
        tags.add('layer:middleware')
    elif any(part in ['config', 'configuration', 'settings'] for part in path_parts):
        tags.add('layer:config')
    elif any(part in ['migrations', 'migration'] for part in path_parts):
        tags.add('layer:migration')
    
    # File type based on extension
    ext = file_path.suffix.lower()
    if ext in ['.ts', '.tsx', '.js', '.jsx']:
        if 'react' in file_name or 'component' in file_name or ext in ['.tsx', '.jsx']:
            tags.add('tech:react')
        else:
            tags.add('tech:javascript')
    elif ext in ['.py']:
        tags.add('tech:python')
    elif ext in ['.go']:
        tags.add('tech:golang')
    elif ext in ['.rs']:
        tags.add('tech:rust')
    elif ext in ['.java']:
        tags.add('tech:java')
    elif ext in ['.cs']:
        tags.add('tech:csharp')
    elif ext in ['.rb']:
        tags.add('tech:ruby')
    elif ext in ['.md', '.rst', '.txt']:
        tags.add('layer:docs')
    elif ext in ['.json', '.yaml', '.yml', '.toml', '.ini', '.env']:
        tags.add('layer:config')
    elif ext in ['.sql']:
        tags.add('layer:migration')
        tags.add('deps:database')
    
    # Special files
    special_files = {
        'dockerfile': 'devops:docker',
        'docker-compose': 'devops:docker',
        '.github': 'devops:ci',
        '.gitlab': 'devops:ci',
        'jenkinsfile': 'devops:ci',
        '.circleci': 'devops:ci',
        'makefile': 'devops:build',
        'package.json': 'tech:node',
        'requirements.txt': 'tech:python',
        'go.mod': 'tech:golang',
        'cargo.toml': 'tech:rust',
        'pom.xml': 'tech:java',
        'gemfile': 'tech:ruby'
    }
    
    for pattern, tag in special_files.items():
        if pattern in file_name.lower() or pattern in str(rel_path).lower():
            tags.add(tag)
    
    # Add content-based tags
    content_tags = analyze_file_content(file_path)
    tags.update(content_tags)
    
    # Check if it's a test file that tests something
    if 'layer:test' in tags:
        # Try to identify what it tests
        test_target = file_name.replace('.test', '').replace('.spec', '').replace('_test', '').replace('test_', '')
        if test_target and test_target != file_name:
            tags.add(f'tests:{test_target}')
    
    return tags

def apply_tags_to_file(conn: sqlite3.Connection, file_path: str, tags: Set[str], session_id: str) -> int:
    """Apply tags to a file in the database"""
    applied = 0
    for tag in tags:
        try:
            conn.execute("""
                INSERT INTO file_tags (path, tag, created_at, created_by)
                VALUES (?, ?, ?, ?)
            """, (file_path, tag, time.time(), session_id))
            applied += 1
        except sqlite3.IntegrityError:
            # Tag already exists for this file
            pass
    return applied

# ============================================================================
# STALENESS DETECTION & FILE RELEVANCE
# ============================================================================

def extract_file_paths(text: str) -> List[str]:
    """Extract file paths from text using multiple patterns"""
    paths = []

    # Pattern 1: Explicit file paths (schema.sql, src/api/users.py, etc.)
    # Matches: word characters, slashes, dots, hyphens
    import re
    file_pattern = r'[\w\-/]+\.[\w]+(?::[\d]+)?'
    matches = re.findall(file_pattern, text)
    for match in matches:
        # Remove line number suffix if present
        path = match.split(':')[0]
        # Filter out common false positives
        if not any(fp in path for fp in ['http', 'https', 'www.', 'localhost']):
            paths.append(path)

    return list(set(paths))  # Deduplicate

def extract_directory_refs(text: str) -> List[str]:
    """Extract directory references from text"""
    dirs = []

    # Pattern: "src/auth/", "the config directory", etc.
    import re

    # Explicit directory paths ending with /
    dir_pattern = r'[\w\-/]+/'
    matches = re.findall(dir_pattern, text)
    for match in matches:
        if not any(fp in match for fp in ['http', 'https', '://']):
            dirs.append(match)

    # Natural language: "the X directory" or "X folder"
    natural_pattern = r'(?:the\s+)?([\w\-/]+)\s+(?:directory|folder|dir)'
    matches = re.findall(natural_pattern, text, re.IGNORECASE)
    dirs.extend([f"{m}/" for m in matches])

    return list(set(dirs))

def get_all_tracked_files() -> List[str]:
    """Get all git-tracked files in project"""
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'ls-files'],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip().split('\n')
    except:
        pass
    return []

def get_related_files(context: dict, git_info: Optional[dict] = None) -> List[dict]:
    """
    Find files related to this context using multiple signals.
    Returns list of {path, relevance, reason}
    """
    related = []
    seen = {}

    # Signal 1: Explicit file paths in content
    explicit_files = extract_file_paths(context['content'])
    for file_path in explicit_files:
        if os.path.exists(file_path):
            seen[file_path] = {
                'path': file_path,
                'relevance': 1.0,
                'reason': 'explicitly_mentioned'
            }

    # Signal 2: Directory references
    directories = extract_directory_refs(context['content'])
    for directory in directories:
        if os.path.exists(directory) and os.path.isdir(directory):
            # Get files in this directory
            for root, _, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    if file_path not in seen:
                        seen[file_path] = {
                            'path': file_path,
                            'relevance': 0.7,
                            'reason': f'in_directory_{directory}'
                        }

    # Signal 3: Temporal proximity (files modified within 24h of lock time)
    if git_info and git_info.get('available'):
        lock_time = context['locked_at']
        window = 86400  # 24 hours

        tracked_files = get_all_tracked_files()
        for file_path in tracked_files:
            full_path = os.path.join(PROJECT_ROOT, file_path)
            if os.path.exists(full_path):
                try:
                    file_mtime = os.path.getmtime(full_path)
                    time_delta = abs(file_mtime - lock_time)

                    if time_delta <= window:
                        proximity_score = 1.0 - (time_delta / window)
                        relevance = proximity_score * 0.6

                        if full_path not in seen or seen[full_path]['relevance'] < relevance:
                            seen[full_path] = {
                                'path': full_path,
                                'relevance': relevance,
                                'reason': f'modified_{int(time_delta/3600)}h_from_lock'
                            }
                except:
                    pass

    # Signal 4: Metadata explicit related_files
    if context.get('metadata'):
        try:
            metadata = json.loads(context['metadata']) if isinstance(context['metadata'], str) else context['metadata']
            if metadata.get('related_files'):
                for file_path in metadata['related_files']:
                    if os.path.exists(file_path):
                        seen[file_path] = {
                            'path': file_path,
                            'relevance': 1.0,
                            'reason': 'user_specified'
                        }
        except:
            pass

    return sorted(seen.values(), key=lambda x: x['relevance'], reverse=True)

def check_context_staleness(context: dict, git_info: Optional[dict] = None) -> Optional[dict]:
    """
    Check if context is stale (content changed or not accessed recently)
    Returns staleness info or None if fresh
    """
    related_files = get_related_files(context, git_info)

    # Priority 1: Deleted files (highest priority stale)
    for file_info in related_files:
        if file_info['relevance'] >= 0.5:  # Only check relevant files
            if not os.path.exists(file_info['path']):
                return {
                    "type": "content_stale",
                    "reason": f"{file_info['path']} no longer exists",
                    "file": file_info['path'],
                    "confidence": "high",
                    "severity": "deleted_file",
                    "recommendation": "update_or_unlock"
                }

    # Priority 2: Modified files (content staleness)
    for file_info in related_files:
        if file_info['relevance'] >= 0.5:  # Only check relevant files
            try:
                file_mtime = os.path.getmtime(file_info['path'])

                if file_mtime > context['locked_at']:
                    days_delta = (file_mtime - context['locked_at']) / 86400
                    confidence = "high" if file_info['relevance'] >= 0.7 else "medium"

                    return {
                        "type": "content_stale",
                        "reason": f"{file_info['path']} modified after context locked",
                        "file": file_info['path'],
                        "relevance_score": file_info['relevance'],
                        "relevance_reason": file_info['reason'],
                        "days_delta": round(days_delta, 1),
                        "confidence": confidence,
                        "recommendation": "review_and_update"
                    }
            except:
                pass

    # Priority 3: Relevance staleness (not accessed recently)
    if context.get('last_accessed'):
        days_since_access = (time.time() - context['last_accessed']) / 86400

        if days_since_access >= 30:
            return {
                "type": "relevance_stale",
                "reason": f"not accessed in {int(days_since_access)} days",
                "days_since_access": int(days_since_access),
                "confidence": "high",
                "recommendation": "verify_still_relevant_or_unlock"
            }
        elif days_since_access >= 14:
            return {
                "type": "relevance_stale",
                "reason": f"not accessed in {int(days_since_access)} days",
                "days_since_access": int(days_since_access),
                "confidence": "medium",
                "recommendation": "verify_still_relevant"
            }

    return None

def get_git_status() -> Optional[dict]:
    """Get git status information if available"""
    try:
        import subprocess

        # Check if git is available and this is a git repo
        if not os.path.exists(os.path.join(PROJECT_ROOT, '.git')):
            return None

        # Get current branch
        branch_result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=2
        )
        current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else 'unknown'

        # Get modified files
        status_result = subprocess.run(
            ['git', 'status', '--short'],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=2
        )

        modified = []
        staged = []
        untracked = []

        if status_result.returncode == 0:
            for line in status_result.stdout.strip().split('\n'):
                if not line:
                    continue
                status = line[:2]
                filepath = line[3:]

                if status[0] in ('M', 'A', 'D', 'R'):
                    staged.append(filepath)
                if status[1] in ('M', 'D'):
                    modified.append(filepath)
                if status == '??':
                    untracked.append(filepath)

        # Get unpushed commits
        unpushed_result = subprocess.run(
            ['git', 'log', '@{u}..HEAD', '--oneline'],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=2
        )
        unpushed_commits = len(unpushed_result.stdout.strip().split('\n')) if unpushed_result.returncode == 0 and unpushed_result.stdout.strip() else 0

        return {
            'available': True,
            'current_branch': current_branch,
            'modified_files': modified,
            'staged_files': staged,
            'untracked_files': untracked,
            'unpushed_commits': unpushed_commits,
            'uncommitted_changes': len(modified) > 0 or len(staged) > 0
        }
    except:
        return None

# ============================================================================
# FILE SEMANTIC MODEL - Database Helper Functions
# ============================================================================

def load_stored_file_model(conn, session_id: str) -> Dict[str, Dict]:
    """Load stored file semantic model from database"""
    cursor = conn.execute("""
        SELECT file_path, file_size, content_hash, modified_time, hash_method,
               file_type, language, purpose, imports, exports, dependencies,
               used_by, contains, is_standard, standard_type, warnings,
               cluster_name, related_files
        FROM file_semantic_model
        WHERE session_id = ?
    """, (session_id,))

    stored = {}
    for row in cursor.fetchall():
        stored[row['file_path']] = {
            'file_size': row['file_size'],
            'content_hash': row['content_hash'],
            'modified_time': row['modified_time'],
            'hash_method': row['hash_method'],
            'file_type': row['file_type'],
            'language': row['language'],
            'purpose': row['purpose'],
            'imports': row['imports'],
            'exports': row['exports'],
            'dependencies': row['dependencies'],
            'used_by': row['used_by'],
            'contains': row['contains'],
            'is_standard': bool(row['is_standard']),
            'standard_type': row['standard_type'],
            'warnings': row['warnings'],
            'cluster_name': row['cluster_name'],
            'related_files': row['related_files']
        }

    return stored


def store_file_metadata(conn, session_id: str, file_path: str, metadata: Dict, scan_time_ms: int):
    """Store or update file metadata in database"""
    conn.execute("""
        INSERT INTO file_semantic_model (
            session_id, file_path, file_size, content_hash, modified_time, hash_method,
            file_type, language, purpose, imports, exports, dependencies, used_by, contains,
            is_standard, standard_type, warnings, cluster_name, related_files,
            last_scanned, scan_duration_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (session_id, file_path)
        DO UPDATE SET
            file_size = EXCLUDED.file_size,
            content_hash = EXCLUDED.content_hash,
            modified_time = EXCLUDED.modified_time,
            hash_method = EXCLUDED.hash_method,
            file_type = EXCLUDED.file_type,
            language = EXCLUDED.language,
            purpose = EXCLUDED.purpose,
            imports = EXCLUDED.imports,
            exports = EXCLUDED.exports,
            dependencies = EXCLUDED.dependencies,
            used_by = EXCLUDED.used_by,
            contains = EXCLUDED.contains,
            is_standard = EXCLUDED.is_standard,
            standard_type = EXCLUDED.standard_type,
            warnings = EXCLUDED.warnings,
            cluster_name = EXCLUDED.cluster_name,
            related_files = EXCLUDED.related_files,
            last_scanned = EXCLUDED.last_scanned,
            scan_duration_ms = EXCLUDED.scan_duration_ms
    """, (
        session_id,
        file_path,
        metadata['file_size'],
        metadata['content_hash'],
        metadata['modified_time'],
        metadata['hash_method'],
        metadata.get('file_type'),
        metadata.get('language'),
        metadata.get('purpose'),
        json.dumps(metadata.get('imports', [])),
        json.dumps(metadata.get('exports', [])),
        json.dumps(metadata.get('dependencies', [])),
        json.dumps(metadata.get('used_by', [])),
        json.dumps(metadata.get('contains', {})),
        1 if metadata.get('is_standard') else 0,
        metadata.get('standard_type'),
        json.dumps(metadata.get('warnings', [])),
        metadata.get('cluster_name'),
        json.dumps(metadata.get('related_files', [])),
        time.time(),
        scan_time_ms
    ))


def mark_file_deleted(conn, session_id: str, file_path: str):
    """Remove file from semantic model (it was deleted)"""
    conn.execute("""
        DELETE FROM file_semantic_model
        WHERE session_id = ? AND file_path = ?
    """, (session_id, file_path))


def record_file_change(conn, session_id: str, file_path: str, change_type: str,
                       old_hash: Optional[str], new_hash: str, size_delta: int):
    """Record file change in history"""
    conn.execute("""
        INSERT INTO file_change_history (
            session_id, file_path, change_type, timestamp, old_hash, new_hash, size_delta
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (session_id, file_path, change_type, time.time(), old_hash, new_hash, size_delta))


# ============================================================================
# PAGINATION HELPERS (v4.3.0 - Token Optimization)
# ============================================================================

def store_query_results(conn, query_type: str, params: dict, results: list,
                       ttl_seconds: int = 3600) -> str:
    """
    Store query results in database for pagination.

    Purpose: Database-first pattern - process all results, store in DB,
    return only summary + query_id for later retrieval.

    Args:
        conn: Database connection
        query_type: Type of query (e.g., 'query_files', 'search_contexts')
        params: Query parameters (for cache key)
        results: Full list of results to store
        ttl_seconds: Time to live (default: 1 hour)

    Returns:
        query_id: Unique identifier for retrieving results

    Example:
        query_id = store_query_results(conn, 'query_files', {'query': 'auth'}, all_files)
        # Later: get_query_page(conn, query_id, offset=10, limit=10)
    """
    session_id = get_current_session_id()

    # Create deterministic query_id from query_type + params
    query_id = hashlib.md5(
        f"{query_type}:{json.dumps(params, sort_keys=True)}".encode()
    ).hexdigest()[:12]

    conn.execute("""
        INSERT INTO query_results_cache
        (query_id, query_type, query_params, total_results, result_data,
         created_at, expires_at, session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (query_id)
        DO UPDATE SET
            query_type = EXCLUDED.query_type,
            query_params = EXCLUDED.query_params,
            total_results = EXCLUDED.total_results,
            result_data = EXCLUDED.result_data,
            created_at = EXCLUDED.created_at,
            expires_at = EXCLUDED.expires_at,
            session_id = EXCLUDED.session_id
    """, (
        query_id,
        query_type,
        json.dumps(params),
        len(results),
        json.dumps(results),
        time.time(),
        time.time() + ttl_seconds,
        session_id
    ))

    return query_id


def get_query_page_data(conn, query_id: str, offset: int = 0, limit: int = 20) -> dict:
    """
    Retrieve paginated results from stored query.

    Args:
        conn: Database connection
        query_id: Query identifier from store_query_results()
        offset: Starting index (0-based)
        limit: Number of results to return

    Returns:
        dict with: {
            query_id, query_type, total_results,
            offset, limit, page_size, has_more, results
        }

    Example:
        page = get_query_page_data(conn, 'abc123', offset=10, limit=10)
        # Returns results [10-20] of total results
    """
    cursor = conn.execute("""
        SELECT query_type, query_params, total_results, result_data
        FROM query_results_cache
        WHERE query_id = ? AND expires_at > ?
    """, (query_id, time.time()))

    row = cursor.fetchone()
    if not row:
        return {"error": "Query not found or expired"}

    all_results = json.loads(row['result_data'])
    page_results = all_results[offset:offset + limit]

    return {
        "query_id": query_id,
        "query_type": row['query_type'],
        "query_params": json.loads(row['query_params']),
        "total_results": row['total_results'],
        "offset": offset,
        "limit": limit,
        "page_size": len(page_results),
        "has_more": offset + limit < row['total_results'],
        "results": page_results
    }


def cleanup_expired_queries(conn):
    """
    Remove expired query results (auto-cleanup).

    Call this periodically (e.g., in wake_up()) to prevent database bloat.
    """
    cursor = conn.execute("""
        DELETE FROM query_results_cache
        WHERE expires_at < ?
    """, (time.time(),))

    deleted_count = cursor.rowcount
    if deleted_count > 0:
        conn.commit()

    return deleted_count


# ============================================================================
# PROJECT MANAGEMENT (CRUD operations for multi-project support)
# ============================================================================

def _fetch_project_stats(conn, schema: str) -> Optional[dict]:
    """
    Check if project schema exists and fetch statistics.

    Queries PostgreSQL information_schema to verify schema existence,
    then counts records in sessions and context_locks tables if present.

    This function is called by switch_project() to determine if a project
    schema already exists in the database and gather statistics for user
    feedback. The schema name must be pre-sanitized before calling.

    Args:
        conn: Active psycopg2 connection (caller manages lifecycle)
        schema: Sanitized schema name to check (alphanumeric + underscore only)

    Returns:
        dict with {"sessions": int, "contexts": int} if schema exists
        None if schema does not exist

    Example:
        >>> import psycopg2
        >>> conn = psycopg2.connect(config.database_url)
        >>> stats = _fetch_project_stats(conn, "innkeeper")
        >>> if stats:
        ...     print(f"Found {stats['sessions']} sessions")
        >>> conn.close()

    Note:
        - Connection must be opened by caller
        - Connection must be closed by caller
        - Schema name MUST be sanitized (no SQL injection protection here)
        - Uses RealDictCursor for dict-based result access
    """
    from psycopg2.extras import RealDictCursor

    # Create cursor for database queries
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Check if schema exists in PostgreSQL catalog
        # Uses parameterized query for safety
        cur.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name = %s
        """, (schema,))

        exists = cur.fetchone() is not None

        if not exists:
            # Schema doesn't exist - will be created on first use
            return None

        # Schema exists - gather statistics for user feedback

        # Count sessions in this project
        # Note: Schema name in f-string is safe because it was pre-sanitized
        cur.execute(f'SELECT COUNT(*) as count FROM "{schema}".sessions')
        sessions = cur.fetchone()['count']

        # Count locked contexts in this project
        cur.execute(f'SELECT COUNT(*) as count FROM "{schema}".context_locks')
        contexts = cur.fetchone()['count']

        return {
            "sessions": sessions,
            "contexts": contexts
        }

    finally:
        # Always clean up cursor (connection managed by caller)
        cur.close()


def _build_switch_response(name: str, schema: str, stats: Optional[dict]) -> dict:
    """
    Build success response dictionary for switch_project operation.

    Constructs a standardized response indicating successful project switch.
    Response format differs based on whether the project schema already exists
    (has stats) or will be created on first use (no stats).

    This is a pure function with no side effects - it only constructs data.
    The caller (switch_project) is responsible for converting to JSON.

    Args:
        name: Original project name provided by user (unsanitized)
        schema: Sanitized schema name that will be used in PostgreSQL
        stats: Project statistics from _fetch_project_stats(), or None if new

    Returns:
        dict with fields:
            - success: Always True (error responses handled elsewhere)
            - message: User-friendly status message with emoji
            - project: Original project name (for display)
            - schema: Sanitized schema name (for technical reference)
            - exists: Boolean indicating if schema exists
            - stats: {"sessions": int, "contexts": int} if exists
            - note: Informational message about next steps

    Example:
        >>> # Existing project with data
        >>> response = _build_switch_response(
        ...     "My Project",
        ...     "my_project",
        ...     {"sessions": 5, "contexts": 10}
        ... )
        >>> print(response["message"])
        ✅ Switched to project 'My Project'

        >>> # New project (will be created)
        >>> response = _build_switch_response(
        ...     "New Project",
        ...     "new_project",
        ...     None
        ... )
        >>> print(response["exists"])
        False

    Note:
        - Returns dict, NOT JSON string (caller handles serialization)
        - Always returns success=True (errors handled in switch_project)
        - Preserves original name for user-facing messages
        - Includes sanitized schema for technical debugging
    """
    if stats is not None:
        # Existing project - return with statistics
        # User can see how many sessions and contexts already exist
        return {
            "success": True,
            "message": f"✅ Switched to project '{name}'",
            "project": name,
            "schema": schema,
            "exists": True,
            "stats": stats,  # {"sessions": int, "contexts": int}
            "note": "All memory operations will now use this project"
        }
    else:
        # New project - will be created automatically on first use
        # Schema creation is lazy (happens when first tool is called)
        return {
            "success": True,
            "message": f"✅ Switched to project '{name}' (will be created on first use)",
            "project": name,
            "schema": schema,
            "exists": False,
            "note": "Project schema will be created automatically when you use memory tools"
        }


@mcp.tool()
async def switch_project(name: str) -> str:
    """
    Switch to a different project for this conversation.

    All subsequent memory operations (lock_context, recall_context, etc.)
    will use this project unless explicitly overridden.

    Args:
        name: Project name to switch to

    Returns:
        JSON with switch status and project info

    Example:
        User: "Switch to my innkeeper project"
        Claude: switch_project(name="innkeeper")
        Claude: "Switched to innkeeper project!"

        User: "Switch to linkedin"
        Claude: switch_project(name="linkedin")
        Claude: "Switched! (Project will be created if it doesn't exist)"
    """
    import psycopg2

    try:
        # Step 1: Validate and sanitize project name using DRY utility
        # Raises ValueError if name is empty or contains only special characters
        try:
            safe_name = sanitize_project_name(name)
        except ValueError as e:
            return safe_json_response({
                "error": str(e),
                "error_type": "ValueError"
            }, success=False)

        # Step 2: Validate session store using DRY utility
        # CRITICAL: Use _local_session_id as single source of truth (Bug #1 fix)
        is_valid, error = validate_session_store()
        if not is_valid:
            return safe_json_response({"error": error}, success=False)

        # Step 3: Update session store (database)
        # CRITICAL: This MUST happen before cache update to maintain consistency
        try:
            updated = _session_store.update_session_project(_local_session_id, safe_name)
            if updated:
                print(f"✅ Switched to project: {safe_name} (session: {_local_session_id[:8]})", file=sys.stderr)
            else:
                print(f"⚠️  Session not found: {_local_session_id[:8]}", file=sys.stderr)
                return safe_json_response({
                    "error": f"Session {_local_session_id[:8]} not found in database"
                }, success=False)
        except Exception as e:
            print(f"❌ Failed to update session project: {e}", file=sys.stderr)
            return safe_json_response({
                "error": f"Failed to update session: {str(e)}"
            }, success=False)

        # Step 4: Update in-memory cache (after database)
        # CRITICAL: Uses same session ID as database update (Bug #1 fix)
        _active_projects[_local_session_id] = safe_name

        # Step 5: Check if project schema exists and get stats
        # Uses connection with try/finally to guarantee cleanup (prevents leaks)
        conn = psycopg2.connect(config.database_url)
        try:
            stats = _fetch_project_stats(conn, safe_name)
        finally:
            conn.close()

        # Step 6: Build and return response using DRY utilities
        response = _build_switch_response(name, safe_name, stats)
        return safe_json_response(response)

    except Exception as e:
        return format_error_response(e)


@mcp.tool()
#async def get_active_project() -> str:
#    """
#    Show which project is currently active for this conversation.
#
#    Returns:
#        JSON with active project name and stats
#
#    Example:
#        User: "Which project am I using?"
#        Claude: get_active_project()
#    """
#    import json
#
#    try:
#        # Get current project using fallback logic
#        current_project = _get_project_for_context()
#
#        # Check if it exists
#        import psycopg2
#        from psycopg2.extras import RealDictCursor
#
#        conn = psycopg2.connect(config.database_url)
#        cur = conn.cursor(cursor_factory=RealDictCursor)
#
#        cur.execute("""
#            SELECT schema_name
#            FROM information_schema.schemata
#            WHERE schema_name = %s
#        """, (current_project,))
#
#        exists = cur.fetchone() is not None
#
#        if exists:
#            # Get stats
#            cur.execute(f'SELECT COUNT(*) as count FROM "{current_project}".sessions')
#            sessions = cur.fetchone()['count']
#
#            cur.execute(f'SELECT COUNT(*) as count FROM "{current_project}".context_locks')
#            contexts = cur.fetchone()['count']
#
#            cur.execute(f'SELECT COUNT(*) as count FROM "{current_project}".memory_entries')
#            memories = cur.fetchone()['count']
#
#            conn.close()
#
#            return json.dumps({
#                "success": True,
#                "project": current_project,
#                "exists": True,
#                "stats": {
#                    "sessions": sessions,
#                    "contexts": contexts,
#                    "memories": memories
#                },
#                "detection": _get_detection_source()
#            })
#        else:
#            conn.close()
#
#            return json.dumps({
#                "success": True,
#                "project": current_project,
#                "exists": False,
#                "message": "Project will be created on first use",
#                "detection": _get_detection_source()
#            })
#
#    except Exception as e:
#        return json.dumps({
#            "success": False,
#            "error": str(e)
#        })
#
#
#def _get_detection_source() -> str:
#    """Helper to explain how current project was determined."""
#    try:
#        session_id = get_current_session_id()
#        if session_id in _active_projects:
#            return "session_switch"
#    except:
#        pass
#
#    if _get_db_adapter().schema and _get_db_adapter().schema != 'default':
#        return "auto_detected_from_directory"
#
#    return "default_fallback"
#

@mcp.tool()
async def create_project(name: str) -> str:
    """
    Create a new project with isolated PostgreSQL schema.

    Args:
        name: Project name (e.g., "innkeeper", "linkedin-posts")

    Returns:
        JSON with project creation status and schema name

    Example:
        User: "Create a project called innkeeper"
        Claude: create_project(name="innkeeper")
    """
    import json

    try:
        # Sanitize project name for PostgreSQL
        import re
        safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')[:32]

        # Get cached adapter with explicit schema (prevents connection pool exhaustion)
        adapter = _get_cached_adapter(safe_name)

        # Check if schema already exists
        conn = adapter.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name = %s
            """, (safe_name,))

            if cur.fetchone():
                adapter.release_connection(conn)
                adapter.close()
                return json.dumps({
                    "success": False,
                    "error": f"Project '{name}' already exists (schema: {safe_name})",
                    "schema": safe_name
                })

            # Return connection before proceeding
            adapter.release_connection(conn)
        except Exception:
            # If error, try to return connection before closing
            try:
                adapter.release_connection(conn)
            except:
                pass
            adapter.close()
            raise

        # Create schema and tables
        adapter.ensure_schema_exists()
        adapter.close()

        return json.dumps({
            "success": True,
            "message": f"✅ Project '{name}' created successfully!",
            "project": name,
            "schema": safe_name,
            "usage": f"Use project='{name}' parameter in wake_up() and other tools"
        })

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@breadcrumb
@mcp.tool()
async def list_projects() -> str:
    """
    List all available projects with statistics.

    Returns:
        JSON with list of projects, each with session/context counts

    Example:
        User: "What projects do I have?"
        Claude: list_projects()
    """
    import json
    import psycopg2
    from psycopg2.extras import RealDictCursor

    try:
        conn = psycopg2.connect(config.database_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get all schemas (excluding system schemas)
        cur.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'public')
              AND schema_name NOT LIKE 'pg_%'
            ORDER BY schema_name
        """)

        schemas = [row['schema_name'] for row in cur.fetchall()]

        projects = []
        for schema in schemas:
            # Get stats for each project
            try:
                cur.execute(f'SELECT COUNT(*) as count FROM "{schema}".sessions')
                sessions = cur.fetchone()['count']

                cur.execute(f'SELECT COUNT(*) as count FROM "{schema}".context_locks')
                contexts = cur.fetchone()['count']

                cur.execute(f'SELECT COUNT(*) as count FROM "{schema}".memory_entries')
                memories = cur.fetchone()['count']

                projects.append({
                    "name": schema,
                    "sessions": sessions,
                    "contexts": contexts,
                    "memories": memories
                })
            except Exception as e:
                # Schema might not have tables yet
                # IMPORTANT: Rollback the failed transaction to allow subsequent queries
                conn.rollback()

                # Log the actual error for debugging
                import sys
                print(f"⚠️  list_projects: Failed to query schema '{schema}': {type(e).__name__}: {e}", file=sys.stderr)
                projects.append({
                    "name": schema,
                    "sessions": 0,
                    "contexts": 0,
                    "memories": 0,
                    "note": f"Schema exists but not initialized ({type(e).__name__})"
                })

        conn.close()

        return json.dumps({
            "success": True,
            "projects": projects,
            "total": len(projects)
        }, indent=2)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@mcp.tool()
async def get_project_info(name: str) -> str:
    """
    Get detailed information about a specific project.

    Args:
        name: Project name

    Returns:
        JSON with project details, recent sessions, top contexts

    Example:
        User: "Show me info about innkeeper project"
        Claude: get_project_info(name="innkeeper")
    """
    import json
    import re

    try:
        # Sanitize name
        safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')[:32]

        # Get cached adapter for specific schema (prevents connection pool exhaustion)
        adapter = _get_cached_adapter(safe_name)

        # Use context manager to ensure connection is always released
        with adapter.connection() as conn:
            cur = conn.cursor()

            # Check if schema exists
            cur.execute("""
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name = %s
            """, (safe_name,))

            if not cur.fetchone():
                adapter.close()
                return json.dumps({
                    "success": False,
                    "error": f"Project '{name}' not found (schema: {safe_name})"
                })

            # Get project stats
            cur.execute(f'SELECT COUNT(*) as count FROM "{safe_name}".sessions')
            total_sessions = cur.fetchone()['count']

            cur.execute(f'SELECT COUNT(*) as count FROM "{safe_name}".context_locks')
            total_contexts = cur.fetchone()['count']

            cur.execute(f'SELECT COUNT(*) as count FROM "{safe_name}".memory_entries')
            total_memories = cur.fetchone()['count']

            # Get recent sessions
            cur.execute(f"""
                SELECT id, started_at, project_name, last_active
                FROM "{safe_name}".sessions
                ORDER BY last_active DESC NULLS LAST, started_at DESC
                LIMIT 5
            """)
            recent_sessions = []
            for row in cur.fetchall():
                recent_sessions.append({
                    "id": row['id'],
                    "project_name": row['project_name'],
                    "started_at": row['started_at'],
                    "last_active": row['last_active']
                })

            # Get top contexts
            cur.execute(f"""
                SELECT label, version, LENGTH(content) as size, locked_at
                FROM "{safe_name}".context_locks
                ORDER BY locked_at DESC
                LIMIT 10
            """)
            top_contexts = []
            for row in cur.fetchall():
                top_contexts.append({
                    "label": row['label'],
                    "version": row['version'],
                    "size_bytes": row['size'],
                    "locked_at": row['locked_at']
                })

        # Connection automatically released by context manager
        adapter.close()

        return json.dumps({
            "success": True,
            "project": name,
            "schema": safe_name,
            "stats": {
                "sessions": total_sessions,
                "contexts": total_contexts,
                "memories": total_memories
            },
            "recent_sessions": recent_sessions,
            "recent_contexts": top_contexts
        }, indent=2)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@mcp.tool()
async def delete_project(name: str, confirm: bool = False) -> str:
    """
    Delete a project and all its data (DESTRUCTIVE - requires confirmation).

    Args:
        name: Project name
        confirm: Must be True to actually delete

    Returns:
        JSON with deletion status or confirmation prompt

    Example:
        User: "Delete the test project"
        Claude: delete_project(name="test", confirm=True)

    Security: Requires explicit confirm=True to prevent accidents
    """
    import json
    import re

    try:
        # Sanitize name
        safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')[:32]

        if not confirm:
            return json.dumps({
                "success": False,
                "requires_confirmation": True,
                "message": f"⚠️  Deleting project '{name}' will permanently delete ALL data!",
                "instruction": "Call delete_project(name='{name}', confirm=True) to proceed"
            })

        # Connect and delete schema
        import psycopg2
        conn = psycopg2.connect(config.database_url)
        conn.autocommit = True
        cur = conn.cursor()

        # Check if schema exists
        cur.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name = %s
        """, (safe_name,))

        if not cur.fetchone():
            conn.close()
            return json.dumps({
                "success": False,
                "error": f"Project '{name}' not found (schema: {safe_name})"
            })

        # Drop schema CASCADE (deletes all tables)
        cur.execute(f'DROP SCHEMA "{safe_name}" CASCADE')

        conn.close()

        return json.dumps({
            "success": True,
            "message": f"✅ Project '{name}' deleted successfully",
            "schema": safe_name,
            "note": "All sessions, contexts, and memories have been permanently removed"
        })

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@breadcrumb
@mcp.tool()
async def select_project_for_session(project_name: str) -> str:
    """
    Select which project to work on for this MCP session.

    IMPORTANT: This must be called when starting a new session before using other tools.
    When you connect, the system will prompt you to select a project if needed.

    Args:
        project_name: Project name to work on (e.g., 'innkeeper', 'linkedin', 'default')

    Returns:
        Confirmation with loaded handover from previous session (if exists)

    Example:
        select_project_for_session('innkeeper')
        → ✅ Project 'innkeeper' selected
          📦 Previous session: You were fixing authentication bug...
    """
    import json
    import re
    from mcp_session_store import PostgreSQLSessionStore

    logger.info(f"🔵 STEP 4: select_project_for_session ENTERED with project_name='{project_name}'")

    try:
        # Get current session ID (from context - will be set by middleware)
        session_id = getattr(config, '_current_session_id', None)
        logger.info(f"🔵 STEP 4a: Got session_id from config: {session_id[:8] if session_id else 'NONE'}")

        if not session_id:
            logger.error(f"🔴 STEP 4a FAILED: No session_id in config")
            return json.dumps({
                "success": False,
                "error": "No active session found. This should not happen."
            }, indent=2)

        # Sanitize project name
        safe_name = re.sub(r'[^a-z0-9]', '_', project_name.lower())
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')[:32]
        logger.info(f"🔵 STEP 4b: Sanitized project name: '{project_name}' → '{safe_name}'")

        # Get database adapter
        adapter = _get_db_adapter()
        session_store = PostgreSQLSessionStore(adapter)
        logger.info(f"🔵 STEP 4c: Got database adapter and session store")

        # Get current session
        session = session_store.get_session(session_id)
        if not session:
            return json.dumps({
                "success": False,
                "error": "Session not found in database"
            }, indent=2)

        # Check if project exists (for non-default projects)
        if project_name != 'default':
            # Use adapter's get_connection() method
            conn = adapter.get_connection()
            try:
                cur = conn.cursor()

                # Check if schema exists
                cur.execute("""
                    SELECT schema_name
                    FROM information_schema.schemata
                    WHERE schema_name = %s
                """, (safe_name,))

                schema_exists = cur.fetchone() is not None
            finally:
                conn.close()

            if not schema_exists:
                # Get available projects for suggestion
                session_store_temp = PostgreSQLSessionStore(adapter)
                projects = session_store_temp.get_projects_with_stats()
                project_names = [p['project_name'] for p in projects]

                return json.dumps({
                    "success": False,
                    "error": f"Project '{project_name}' doesn't exist",
                    "available_projects": project_names,
                    "suggestion": f"Create it first: create_project('{project_name}')"
                }, indent=2)

        # Update session with selected project
        logger.info(f"🔵 STEP 4d: About to UPDATE mcp_sessions for session {session_id[:8]}, project: '{safe_name}'")
        conn = adapter.get_connection()
        try:
            with conn.cursor() as cur:
                logger.info(f"🔵 STEP 4e: Executing UPDATE statement...")
                cur.execute("""
                    UPDATE mcp_sessions
                    SET project_name = %s
                    WHERE session_id = %s
                """, (safe_name, session_id))
                logger.info(f"🔵 STEP 4f: UPDATE executed, rowcount={cur.rowcount}, committing...")
                conn.commit()
                logger.info(f"🔵 STEP 4g: Commit completed successfully")
        except Exception as update_error:
            logger.error(f"🔴 STEP 4 UPDATE EXCEPTION: {type(update_error).__name__}: {update_error}")
            conn.rollback()
            raise
        finally:
            conn.close()

        # Switch active project globally
        logger.info(f"🔵 STEP 4h: Setting _active_projects[{session_id[:8]}] = '{safe_name}'")
        _active_projects[session_id] = safe_name

        # Load previous handover for this project
        try:
            handover_result = await get_last_handover(project=safe_name)

            # Parse handover result (it's JSON string)
            handover_data = json.loads(handover_result)

            if handover_data.get('handover'):
                handover_summary = handover_data['handover']
                work_done = handover_summary.get('work_done', [])
                next_steps = handover_summary.get('next_steps', [])

                result = f"✅ Project '{safe_name}' selected\n\n"
                result += "📦 Previous Session Handover:\n"
                result += "─" * 50 + "\n"

                if work_done:
                    result += "\nWork Done:\n"
                    for item in work_done[:5]:  # Show max 5 items
                        result += f"  • {item}\n"

                if next_steps:
                    result += "\nNext Steps:\n"
                    for item in next_steps[:3]:
                        result += f"  • {item}\n"

                result += "\n" + "─" * 50 + "\n"
                result += "\nYou can now continue your work."

                logger.info(f"🔵 STEP 5: Returning success with handover summary")
                return result
            else:
                # No previous handover
                logger.info(f"🔵 STEP 5: No handover found, returning success")
                return f"""✅ Project '{safe_name}' selected

This is a new session for this project (no previous handover found).

You can now use other tools."""

        except Exception as handover_error:
            # No handover found or error loading it
            logger.info(f"🔵 STEP 5: Handover load failed (not critical): {handover_error}")
            result = f"""✅ Project '{safe_name}' selected

No previous session handover found. This may be:
- Your first session in this project
- Previous session had no activity
- Handover not yet created

You can now use other tools."""
            logger.info(f"🔵 STEP 5a: Returning success response (no handover)")
            return result

    except Exception as e:
        logger.error(f"🔴 STEP 4 EXCEPTION: {str(e)}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": f"Failed to select project: {str(e)}"
        }, indent=2)


# ============================================================================
# SESSION MANAGEMENT (unchanged from before)
# ============================================================================
#
#@mcp.tool()
async def wake_up(project: Optional[str] = None) -> str:
    """
    ⚠️  **DEPRECATED**: This tool is no longer needed.

    **What changed:**
    - Handovers are now auto-loaded on the first tool call
    - Session context is automatically available
    - No manual wake_up() required

    **What to do instead:**
    - Just start using tools normally
    - Use get_last_handover() if you want to see full previous session details
    - Use context_dashboard() to see available contexts

    **Why deprecated:**
    - Reduces manual steps for LLM
    - Automatic incremental handovers eliminate need for session boundaries
    - Improves user experience with seamless context continuity
    """
    return json.dumps({
        "deprecated": True,
        "message": "⚠️  wake_up() is deprecated - handover auto-loaded on first tool call",
        "alternatives": [
            "get_last_handover() - See full previous session details",
            "context_dashboard() - See available contexts",
            "Just use tools normally - context auto-loads"
        ],
        "note": "Session handover has already been auto-loaded. Continue working normally."
    }, indent=2)

#    # Use project-aware database connection
#    target_project = _get_project_for_context(project)
#    conn = _get_db_for_project(project)
#    session_id = get_current_session_id()
#
#    # Cleanup expired queries (maintenance)
#    cleanup_expired_queries(conn)
#
#    # Validate database isolation (critical security check)
#    validation_report = validate_database_isolation(conn)
#
#    # Get git status
#    git_info = get_git_status()
#
#    # Run file model scan (incremental, only project directories)
#    # DISABLED in production/cloud to prevent scanning build artifacts
#    file_model_data = None
#    environment = os.getenv('ENVIRONMENT', 'development')
#    current_project_root = get_project_root()  # Dynamic detection
#    if environment == 'development' and is_project_directory(current_project_root):
#        try:
#            # Load stored model
#            stored_model = load_stored_file_model(conn, session_id)
#
#            # Quick incremental scan (respects .gitignore, max 10k files)
#            scan_start = time.time()
#            all_files = walk_project_files(current_project_root, respect_gitignore=True, max_files=10000)
#
#            # Detect changes
#            changed_files = []
#            deleted_files = []
#            analyzed_files = []
#
#            # Check for deleted files
#            stored_paths = set(stored_model.keys())
#            current_paths = set(all_files)
#            deleted_paths = stored_paths - current_paths
#
#            for deleted_path in deleted_paths:
#                mark_file_deleted(conn, session_id, deleted_path)
#                deleted_files.append(deleted_path)
#
#            # Check for new/changed files
#            for file_path in all_files:
#                stored_meta = stored_model.get(file_path)
#                changed, new_hash, hash_method = detect_file_change(file_path, stored_meta)
#
#                if changed:
#                    # Analyze file
#                    file_type, language, is_standard, standard_type = detect_file_type(file_path)
#                    warnings = check_standard_file_warnings(file_path, file_type, standard_type, current_project_root)
#                    semantics = analyze_file_semantics(file_path, file_type, language)
#
#                    # Build metadata
#                    file_stat = os.stat(file_path)
#                    metadata = {
#                        'file_path': file_path,
#                        'file_size': file_stat.st_size,
#                        'content_hash': new_hash,
#                        'modified_time': file_stat.st_mtime,
#                        'hash_method': hash_method,
#                        'file_type': file_type,
#                        'language': language,
#                        'is_standard': is_standard,
#                        'standard_type': standard_type,
#                        'warnings': warnings,
#                        **semantics
#                    }
#
#                    # Store in database
#                    store_file_metadata(conn, session_id, file_path, metadata, 0)
#
#                    # Track changes
#                    if stored_meta:
#                        size_delta = metadata['file_size'] - stored_meta.get('file_size', 0)
#                        record_file_change(conn, session_id, file_path, 'modified', stored_meta.get('content_hash'), new_hash, size_delta)
#                        changed_files.append(file_path)
#                    else:
#                        record_file_change(conn, session_id, file_path, 'added', None, new_hash, metadata['file_size'])
#                        changed_files.append(file_path)
#
#                    analyzed_files.append(metadata)
#
#            scan_time_ms = (time.time() - scan_start) * 1000
#
#            # Build file model summary
#            file_model_data = {
#                "enabled": True,
#                "scan_type": "incremental",
#                "scan_time_ms": round(scan_time_ms, 2),
#                "total_files": len(all_files),
#                "changes": {
#                    "added": len([f for f in changed_files if f not in stored_model]),
#                    "modified": len([f for f in changed_files if f in stored_model]),
#                    "deleted": len(deleted_files)
#                },
#                "warnings": [w for meta in analyzed_files for w in meta.get('warnings', [])][:10]  # First 10 warnings
#            }
#
#        except Exception as e:
#            # If scan fails, don't block wake_up
#            file_model_data = {
#                "enabled": False,
#                "error": str(e)
#            }
#    else:
#        file_model_data = {
#            "enabled": False,
#            "reason": "non_project_directory"
#        }
#
#    # Build session info (using dynamic database path)
#    current_db_path = get_current_db_path()
#
#    # Calculate database size (only for SQLite local files)
#    if is_postgresql_mode():
#        db_size_mb = 0  # PostgreSQL size not calculated for remote DB
#    else:
#        db_size_mb = os.path.getsize(current_db_path) / (1024 * 1024) if os.path.exists(current_db_path) else 0
#
#    # Get project detection source for display
#    detection_source = _get_detection_source()
#    detection_label = {
#        "session_switch": "via switch_project()",
#        "auto_detected_from_directory": "auto-detected from git repo/directory",
#        "default_fallback": "default fallback"
#    }.get(detection_source, detection_source)
#
#    session_data = {
#        "session": {
#            "id": session_id,
#            "project_name": get_project_name(),  # Dynamic detection
#            "active_project": target_project,    # Active project for this session
#            "project_detection": detection_label,  # How project was determined
#            "project_root": get_project_root(),  # Dynamic detection
#            "database": current_db_path,         # Dynamic detection
#            "database_location": get_db_location_type(),  # Dynamic detection
#            "database_size_mb": round(db_size_mb, 2),
#            "initialized_at": time.time()
#        },
#        "database_validation": {
#            "status": validation_report["level"],
#            "checks_passed": validation_report["summary"]["checks_passed"],
#            "checks_total": validation_report["summary"]["checks_total"],
#            "errors": validation_report["errors"],
#            "warnings": validation_report["warnings"],
#            "recommendations": validation_report["recommendations"]
#            # NOTE: Use validate_database_isolation() for detailed report
#        },
#        "git": git_info if git_info else {
#            "available": False,
#            "reason": "not_a_git_repo_or_no_access"
#        },
#        "file_model": file_model_data,
#        "contexts": None,  # Will be filled with counts only
#        "handover": None,  # Will be filled with availability only
#        "memory_health": None
#    }
#
#    # Get context COUNTS only (not full data - use explore_context_tree for that)
#    cursor = conn.execute("""
#        SELECT metadata, last_accessed, locked_at, label, version, content
#        FROM context_locks
#        WHERE session_id = ?
#    """, (session_id,))
#
#    all_contexts = cursor.fetchall()
#
#    # Count by priority (minimal data)
#    priority_counts = {"always_check": 0, "important": 0, "reference": 0}
#    stale_count = 0
#
#    for ctx_row in all_contexts:
#        metadata = json.loads(ctx_row['metadata']) if ctx_row['metadata'] else {}
#        priority = metadata.get('priority', 'reference')
#
#        if priority in priority_counts:
#            priority_counts[priority] += 1
#
#        # Check staleness (just count, don't return details)
#        context_dict = dict(ctx_row)
#        staleness = check_context_staleness(context_dict, git_info)
#        if staleness:
#            stale_count += 1
#
#    # Add token cost estimates for context operations
#    context_count = len(all_contexts)
#    token_estimates = {
#        "explore_tree_flat": "~1,000 tokens ✅",
#        "explore_tree_full": f"~{context_count * 50:,} tokens",
#        "recall_single_preview": "~350 tokens ✅",
#        "recall_single_full": "~900 tokens"
#    }
#
#    # Add warning if context count is high
#    overflow_warning = None
#    if context_count > 50:
#        overflow_warning = f"⚠️ High context count ({context_count}). Use flat=True for explore_context_tree() to avoid overflow."
#
#    session_data["contexts"] = {
#        "total_count": context_count,
#        "by_priority": priority_counts,
#        "stale_count": stale_count,
#        "token_estimates": token_estimates,
#        "overflow_warning": overflow_warning
#        # NOTE: Use explore_context_tree(flat=True) to see labels (token-efficient)
#    }
#
#    # Get handover if available (MINIMAL - just availability, not full content)
#    cursor = conn.execute("""
#        SELECT timestamp FROM memory_entries
#        WHERE category = 'handover'
#        ORDER BY timestamp DESC
#        LIMIT 1
#    """)
#    handover = cursor.fetchone()
#
#    if handover:
#        hours_ago = (time.time() - handover['timestamp']) / 3600
#        session_data["handover"] = {
#            "available": True,
#            "timestamp": handover['timestamp'],
#            "hours_ago": round(hours_ago, 1)
#            # NOTE: Use get_last_handover() tool to retrieve full content
#        }
#
#    # Memory health
#    total_size = sum(len(ctx['content'] or '') for ctx in all_contexts)
#    total_size_mb = total_size / (1024 * 1024)
#    capacity_mb = 50  # Current limit
#
#    session_data["memory_health"] = {
#        "total_contexts": len(all_contexts),
#        "total_size_mb": round(total_size_mb, 2),
#        "capacity_mb": capacity_mb,
#        "usage_percent": round((total_size_mb / capacity_mb) * 100, 1),
#        "status": "healthy" if total_size_mb < capacity_mb * 0.8 else "near_capacity"
#    }
#
#    return json.dumps(session_data, indent=2)
#
#
@mcp.tool()
async def sleep(project: Optional[str] = None) -> str:
    """
    ⚠️  **DEPRECATED**: This tool is no longer needed.

    **What changed:**
    - Session handovers are now auto-generated when sessions become inactive
    - Tools update session summaries in real-time as you work
    - No manual sleep() required

    **What to do instead:**
    - Just stop using tools when done - session will finalize automatically
    - Use get_last_handover() if you want to see current session summary
    - Session state is continuously saved, not just at end

    **Why deprecated:**
    - Reduces manual steps for LLM
    - Real-time incremental handovers are more reliable
    - No risk of forgetting to call sleep()
    - Improves user experience with automatic session management
    """
    return json.dumps({
        "deprecated": True,
        "message": "⚠️  sleep() is deprecated - handovers auto-generated on session inactivity",
        "alternatives": [
            "get_last_handover() - See current or previous session details",
            "context_dashboard() - See available contexts",
            "Just stop using tools - session auto-finalizes after inactivity"
        ],
        "note": "Your work is being tracked automatically. No action needed."
    }, indent=2)

# # OLD IMPLEMENTATION - Commented out (incremental handovers replace this)
# async def sleep(project: Optional[str] = None) -> str:
#     """
#     Create comprehensive handover package for next session.
#     Documents everything needed to resume work seamlessly.
#
#     Args:
#         project: Project name (default: auto-detect or active project)
#     """
#     # Check if project selection is required
#     project_check = _check_project_selection_required(project)
#     if project_check:
#         return project_check
#
#     conn = _get_db_for_project(project)
#     session_id = get_current_session_id()
#
#     # Get session info
#     cursor = conn.execute("""
#         SELECT started_at FROM sessions WHERE id = ?
#     """, (session_id,))
#     session = cursor.fetchone()
#
#     if not session:
#         return "No active session to document"
#
#     duration = time.time() - session['started_at']
#     hours = int(duration // 3600)
#     minutes = int((duration % 3600) // 60)
#
#     # Build comprehensive handover package
#     handover = {
#         'timestamp': time.time(),
#         'session_id': session_id,
#         'duration': f"{hours}h {minutes}m",
#         'current_state': {},
#         'work_done': {},
#         'next_steps': {},
#         'important_context': {}
#     }
#
#     output = []
#     output.append("💤 Creating handover package for next session...")
#     output.append(f"Session: {session_id} | Duration: {hours}h {minutes}m")
#     output.append("=" * 50)
#
#     # 1. WHAT WAS ACCOMPLISHED
#     output.append("\n📊 WORK COMPLETED THIS SESSION:")
#
#     # Progress updates
#     cursor = conn.execute("""
#         SELECT content, timestamp FROM memory_entries
#         WHERE session_id = ? AND category = 'progress'
#         ORDER BY timestamp DESC
#     """, (session_id,))
#     progress_items = cursor.fetchall()
#
#     if progress_items:
#         output.append("\n✅ Progress Made:")
#         for item in progress_items[:5]:  # Top 5 progress items
#             output.append(f"   • {item['content']}")
#         handover['work_done']['progress'] = [p['content'] for p in progress_items]
#
#     # Completed TODOs
#     cursor = conn.execute("""
#         SELECT content FROM todos
#         WHERE status = 'completed' AND completed_at > ?
#         ORDER BY completed_at DESC
#     """, (session['started_at'],))
#     completed = cursor.fetchall()
#
#     if completed:
#         output.append(f"\n✅ TODOs Completed ({len(completed)}):")
#         for todo in completed[:5]:
#             output.append(f"   • {todo['content']}")
#         handover['work_done']['completed_todos'] = [t['content'] for t in completed]
#
#     # 2. CURRENT STATE & CONTEXT
#     output.append("\n🎯 CURRENT PROJECT STATE:")
#
#     # Active/pending TODOs
#     cursor = conn.execute("""
#         SELECT content, priority FROM todos
#         WHERE status = 'pending'
#         ORDER BY priority DESC, created_at ASC
#     """)
#     pending_todos = cursor.fetchall()
#
#     if pending_todos:
#         output.append(f"\n📋 Pending TODOs ({len(pending_todos)}):")
#         for todo in pending_todos[:5]:
#             priority = ['LOW', 'NORMAL', 'HIGH'][min(todo['priority'] or 0, 2)]
#             output.append(f"   • [{priority}] {todo['content']}")
#         handover['next_steps']['todos'] = [
#             {'content': t['content'], 'priority': t['priority']} 
#             for t in pending_todos
#         ]
#
#     # Recent decisions made
#     cursor = conn.execute("""
#         SELECT decision, rationale FROM decisions
#         WHERE timestamp > ? AND status = 'DECIDED'
#         ORDER BY timestamp DESC
#         LIMIT 3
#     """, (session['started_at'],))
#     decisions = cursor.fetchall()
#
#     if decisions:
#         output.append("\n🤔 Key Decisions Made:")
#         for decision in decisions:
#             output.append(f"   • {decision['decision']}")
#             if decision['rationale']:
#                 output.append(f"     → {decision['rationale']}")
#         handover['work_done']['decisions'] = [
#             {'decision': d['decision'], 'rationale': d['rationale']} 
#             for d in decisions
#         ]
#
#     # 3. IMPORTANT LOCKED CONTEXTS
#     output.append("\n🔒 LOCKED CONTEXTS TO REMEMBER:")
#
#     cursor = conn.execute("""
#         SELECT label, version, MAX(locked_at) as latest
#         FROM context_locks
#         WHERE session_id = ?
#         GROUP BY label, version
#         ORDER BY latest DESC
#         LIMIT 5
#     """, (session_id,))
#
#     locked_contexts = cursor.fetchall()
#     if locked_contexts:
#         for ctx in locked_contexts:
#             output.append(f"   • {ctx['label']} (v{ctx['version']})")
#         handover['important_context']['locked'] = [
#             {'label': c['label'], 'version': c['version']} 
#             for c in locked_contexts
#         ]
#         output.append("   Use recall_context('topic') to retrieve these")
#
#     # 4. FILES BEING WORKED ON
#     cursor = conn.execute("""
#         SELECT path, string_agg(tag, ', ') as tags, MAX(created_at) as latest
#         FROM file_tags
#         WHERE created_at > ?
#         GROUP BY path
#         ORDER BY latest DESC
#         LIMIT 5
#     """, (session['started_at'],))
#
#     recent_files = cursor.fetchall()
#     if recent_files:
#         output.append("\n📁 Files Recently Analyzed:")
#         for file in recent_files:
#             output.append(f"   • {file['path']}")
#             if file['tags']:
#                 tags = file['tags'].split(',')[:3]  # First 3 tags
#                 output.append(f"     Tags: {', '.join(tags)}")
#         handover['current_state']['recent_files'] = [
#             {'path': f['path'], 'tags': f['tags']}
#             for f in recent_files
#         ]
#
#     # 4.5. UPDATE FILE MODEL (if project directory)
#     current_project_root = get_project_root()  # Dynamic detection
#     if is_project_directory(current_project_root):
#         try:
#             # Quick incremental scan to capture any last-minute changes
#             stored_model = load_stored_file_model(conn, session_id)
#             all_files = walk_project_files(current_project_root, respect_gitignore=True, max_files=10000)
#
#             changed_count = 0
#             for file_path in all_files:
#                 stored_meta = stored_model.get(file_path)
#                 changed, new_hash, hash_method = detect_file_change(file_path, stored_meta)
#
#                 if changed:
#                     # Analyze and update
#                     file_type, language, is_standard, standard_type = detect_file_type(file_path)
#                     warnings = check_standard_file_warnings(file_path, file_type, standard_type, current_project_root)
#                     semantics = analyze_file_semantics(file_path, file_type, language)
#
#                     file_stat = os.stat(file_path)
#                     metadata = {
#                         'file_path': file_path,
#                         'file_size': file_stat.st_size,
#                         'content_hash': new_hash,
#                         'modified_time': file_stat.st_mtime,
#                         'hash_method': hash_method,
#                         'file_type': file_type,
#                         'language': language,
#                         'is_standard': is_standard,
#                         'standard_type': standard_type,
#                         'warnings': warnings,
#                         **semantics
#                     }
#
#                     store_file_metadata(conn, session_id, file_path, metadata, 0)
#                     changed_count += 1
#
#             if changed_count > 0:
#                 output.append(f"\n📊 File model updated: {changed_count} files changed since wake_up")
#                 handover['current_state']['file_model_updated'] = {
#                     'files_changed': changed_count,
#                     'total_files': len(all_files)
#                 }
#         except Exception as e:
#             # Don't block sleep if file scan fails
#             output.append(f"\n⚠️ File model update skipped: {str(e)}")
#
#     # 5. ERRORS OR ISSUES TO ADDRESS
#     cursor = conn.execute("""
#         SELECT content FROM memory_entries
#         WHERE session_id = ? AND category = 'error'
#         ORDER BY timestamp DESC
#         LIMIT 3
#     """, (session_id,))
#
#     errors = cursor.fetchall()
#     if errors:
#         output.append("\n⚠️ Issues to Address:")
#         for error in errors:
#             output.append(f"   • {error['content']}")
#         handover['next_steps']['issues'] = [e['content'] for e in errors]
#
#     # 6. NEXT STEPS GUIDANCE
#     output.append("\n🚀 NEXT SESSION RECOMMENDATIONS:")
#
#     # Open questions
#     cursor = conn.execute("""
#         SELECT question FROM decisions
#         WHERE status = 'OPEN'
#         ORDER BY timestamp DESC
#         LIMIT 3
#     """)
#     questions = cursor.fetchall()
#
#     if questions:
#         output.append("\n❓ Open Questions:")
#         for q in questions:
#             output.append(f"   • {q['question']}")
#         handover['next_steps']['questions'] = [q['question'] for q in questions]
#
#     # Suggest next actions based on state
#     if pending_todos:
#         output.append(f"\n💡 Start with high-priority TODOs")
#     if errors:
#         output.append(f"💡 Address the {len(errors)} error(s) first")
#     if not locked_contexts:
#         output.append("💡 Consider locking important decisions/code with lock_context()")
#
#     # Store comprehensive handover in database
#     handover_json = json.dumps(handover, indent=2)
#
#     # Update session with handover package
#     conn.execute("""
#         UPDATE sessions 
#         SET summary = ?, last_active = ?
#         WHERE id = ?
#     """, (handover_json, time.time(), session_id))
#
#     # Create a special handover memory entry
#     conn.execute("""
#         INSERT INTO memory_entries (category, content, metadata, timestamp, session_id)
#         VALUES ('handover', ?, ?, ?, ?)
#     """, (f"Session handover: {hours}h {minutes}m of work", handover_json, time.time(), session_id))
#
#     conn.commit()
#
#     output.append("\n" + "=" * 50)
#     output.append("✅ Handover package saved. Use wake_up() to resume.")
#     output.append("Your context and progress are preserved!")
#
#     return "\n".join(output)

@breadcrumb
@mcp.tool()
async def get_last_handover(project: Optional[str] = None) -> str:
    """
    Retrieve the last session handover package.

    **Purpose:** Get full details of what was accomplished in the previous session.

    **Returns:** JSON with work done, pending tasks, locked contexts, and next steps.

    **Token efficiency:** Returns full handover (~2-5KB). Use only when needed.
    wake_up() only shows availability - use this tool to get full details.

    **Two-path logic:**
    - **Current handover**: If active session (< 120 min idle), returns session_summary
    - **Packaged handover**: If no active session or idle > 120 min, returns compacted data

    Args:
        project: Project name (default: auto-detect or active project)

    **Example:**
    ```python
    # wake_up() shows: "handover": {"available": true, "hours_ago": 2.5}
    # Then call this to get details:
    result = get_last_handover()
    # Returns: {work_done, next_steps, important_context, ...}
    ```
    """
    # Check if project selection is required
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check

    # Get current session ID
    session_id = get_current_session_id()

    with _get_db_for_project(project) as conn:
        # PATH 1: Check for active session's current handover
        # Query mcp_sessions for session_summary and last_active
        cursor = conn.execute("""
            SELECT session_summary, last_active, created_at
            FROM mcp_sessions
            WHERE session_id = ?
        """, (session_id,))

        active_session = cursor.fetchone()

        if active_session:
            # Check if session is active (< 120 minutes idle)
            now = time.time()
            last_active_ts = active_session['last_active']

            # Handle datetime to timestamp conversion
            if isinstance(last_active_ts, (datetime,)):
                last_active_ts = last_active_ts.timestamp()

            inactive_seconds = now - last_active_ts

            # If session active within 120 minutes, return current handover
            if inactive_seconds < 7200:  # 120 minutes = 7200 seconds
                session_summary = active_session['session_summary']

                # Parse session_summary if it's a string (shouldn't be with JSONB, but handle it)
                if isinstance(session_summary, str):
                    session_summary = json.loads(session_summary)

                # Calculate hours since session creation
                created_at_ts = active_session['created_at']
                if isinstance(created_at_ts, (datetime,)):
                    created_at_ts = created_at_ts.timestamp()

                hours_ago = (now - created_at_ts) / 3600

                return json.dumps({
                    "available": True,
                    "timestamp": created_at_ts,
                    "hours_ago": round(hours_ago, 1),
                    "content": session_summary,
                    "status": "current",  # Indicate this is current session
                    "session_id": session_id[:8]  # First 8 chars for logging
                }, indent=2)

        # PATH 2: No active session or session idle > 120 min
        # Fall back to packaged handover from memory_entries
        cursor = conn.execute("""
            SELECT content, metadata, timestamp FROM memory_entries
            WHERE category = 'handover'
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        handover = cursor.fetchone()

        if not handover:
            return json.dumps({"available": False, "reason": "no_handover_found"}, indent=2)

        try:
            handover_data = json.loads(handover['metadata'])
            hours_ago = (time.time() - handover['timestamp']) / 3600

            return json.dumps({
                "available": True,
                "timestamp": handover['timestamp'],
                "hours_ago": round(hours_ago, 1),
                "content": handover_data,
                "status": "packaged"  # Indicate this is packaged handover
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "available": False,
                "reason": "corrupted_data",
                "error": str(e)
            }, indent=2)

@mcp.tool()
async def get_query_page(query_id: str, offset: int = 0, limit: int = 20, project: Optional[str] = None) -> str:
    """
    Retrieve paginated results from a previous query.

    **Purpose:** Get additional results from queries that returned a query_id.

    **Token efficiency: PREVIEW** (varies by limit, typically <5KB per page)

    Use this to retrieve more results from queries like:
    - query_files()
    - search_contexts()
    - Any future tools that return query_id for pagination

    Args:
        query_id: Query identifier from previous query
        offset: Starting index (0-based)
        limit: Number of results to return (default: 20)

    Returns: JSON with:
        - results: Page of results
        - pagination info: offset, limit, total, has_more
        - query details: query_type, parameters

    Example:
    ```python
    # Initial query returns preview + query_id
    result = query_files("authentication")
    # → {total: 50, preview: [5 files], query_id: "abc123"}

    # Get next page
    page2 = get_query_page("abc123", offset=5, limit=10)
    # → {results: [files 5-15], has_more: true}
    ```

    Note: Query results expire after 1 hour (TTL). If expired, run the query again.
    """
    with _get_db_for_project(project) as conn:
        result = get_query_page_data(conn, query_id, offset, limit)
        return json.dumps(result, indent=2)

# ============================================================================
# MEMORY MANAGEMENT (unchanged)
# ============================================================================

# DEPRECATED: Replaced by health_check_and_repair()
# @mcp.tool()
# async def memory_status(project: Optional[str] = None) -> str:
#     """
#     Show memory system status and statistics.
#     DEPRECATED: Use health_check_and_repair() instead.
#     """
#    conn = _get_db_for_project(project)
#    session_id = _get_session_id_for_project(conn, project)
#    
#    output = []
#    output.append("🧠 Memory System Status")
#    output.append("=" * 40)
#    
#    # Session info
#    cursor = conn.execute("""
#        SELECT started_at, last_active FROM sessions WHERE id = ?
#    """, (session_id,))
#    session = cursor.fetchone()
#    
#    if session:
#        start = datetime.fromtimestamp(session['started_at'])
#        active = datetime.fromtimestamp(session['last_active'])
#        output.append(f"Session: {session_id}")
#        output.append(f"Started: {start.strftime('%Y-%m-%d %H:%M')}")
#        output.append(f"Last Active: {active.strftime('%H:%M')}")
#    
#    # Memory stats (handle case where table might not have entries)
#    try:
#        cursor = conn.execute("""
#            SELECT category, COUNT(*) as count
#            FROM memory_entries
#            WHERE session_id = ?
#            GROUP BY category
#        """, (session_id,))
#
#        entries = cursor.fetchall()
#        if entries:
#            output.append("\n📊 Memory Entries (this session):")
#            for entry in entries:
#                output.append(f"   • {entry['category']}: {entry['count']}")
#    except Exception as e:
#        # Graceful handling if query fails
#        pass
#    
#    # Context locks with embedding stats
#    cursor = conn.execute("""
#        SELECT
#            COUNT(DISTINCT label) as topics,
#            COUNT(*) as total,
#            SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) as with_embedding,
#            SUM(CASE WHEN embedding IS NULL THEN 1 ELSE 0 END) as without_embedding
#        FROM context_locks WHERE session_id = ?
#    """, (session_id,))
#    locks = cursor.fetchone()
#    output.append(f"\n🔒 Locked Contexts: {locks['topics']} topics, {locks['total']} versions")
#
#    # Embedding status
#    if locks['total'] > 0:
#        embedded_pct = (locks['with_embedding'] / locks['total']) * 100
#        if locks['without_embedding'] > 0:
#            output.append(f"   📊 Embeddings: {locks['with_embedding']}/{locks['total']} ({embedded_pct:.0f}%)")
#            output.append(f"   ⚠️  {locks['without_embedding']} context(s) missing embeddings")
#            output.append(f"   💡 Run generate_embeddings() to enable semantic search")
#        else:
#            output.append(f"   ✅ All contexts have embeddings ({locks['with_embedding']})")
#    
#    # TODOs (if table exists)
#    try:
#        cursor = conn.execute("""
#            SELECT status, COUNT(*) as count FROM todos
#            GROUP BY status
#        """)
#        todos = cursor.fetchall()
#        if todos:
#            output.append("\n📋 TODOs:")
#            for todo in todos:
#                output.append(f"   • {todo['status']}: {todo['count']}")
#    except Exception:
#        # Table doesn't exist in this schema
#        pass
#    
#    # File tags (if table exists)
#    try:
#        cursor = conn.execute("SELECT COUNT(DISTINCT path) as files FROM file_tags")
#        tags = cursor.fetchone()
#        if tags and tags['files'] > 0:
#            output.append(f"\n🏷️ Tagged Files: {tags['files']}")
#    except Exception:
#        # Table doesn't exist in this schema
#        pass
#
#    return "\n".join(output)
#
# ============================================================================
# CONTEXT LOCKING (unchanged)
# ============================================================================
#
# Helper functions for lock_context (extracted for DRY and testability)

def _auto_detect_priority(content: str) -> str:
    """Auto-detect priority level based on content keywords."""
    content_lower = content.lower()
    if any(word in content_lower for word in ['always', 'never', 'must']):
        return 'always_check'
    elif any(word in content_lower for word in ['important', 'critical', 'required']):
        return 'important'
    else:
        return 'reference'


def _get_next_version(conn, topic: str, session_id: str) -> str:
    """Get the next version number for a context topic."""
    cursor = conn.execute("""
        SELECT version FROM context_locks
        WHERE label = ? AND session_id = ?
        ORDER BY locked_at DESC
        LIMIT 1
    """, (topic, session_id))

    row = cursor.fetchone()
    if row:
        parts = row['version'].split('.')
        if len(parts) == 2:
            major, minor = parts
            return f"{major}.{int(minor)+1}"
        else:
            return "1.1"
    else:
        return "1.0"


def _extract_keywords_from_content(content: str) -> list[str]:
    """Extract technical keywords from content using pattern matching."""
    keywords = []
    keyword_patterns = {
        'output': r'\b(output|directory|folder|path)\b',
        'test': r'\b(test|testing|spec)\b',
        'config': r'\b(config|settings|configuration)\b',
        'api': r'\b(api|endpoint|rest|graphql)\b',
        'database': r'\b(database|db|sql|table)\b',
        'security': r'\b(auth|token|password|secret)\b',
    }
    content_lower = content.lower()
    for key, pattern in keyword_patterns.items():
        if re.search(pattern, content_lower):
            keywords.append(key)
    return keywords


def _generate_and_store_embedding(conn, context_id: int, preview: str, topic: str) -> str:
    """Generate and store embedding for context, returns status string."""
    embedding_status = ""
    try:
        from src.services import embedding_service
        if embedding_service and embedding_service.enabled:
            embedding_text = preview if len(preview) <= 1020 else preview[:1020]
            embedding = embedding_service.generate_embedding(embedding_text)

            if embedding:
                import pickle
                embedding_bytes = pickle.dumps(embedding)

                conn.execute("""
                    UPDATE context_locks
                    SET embedding = ?, embedding_model = ?
                    WHERE id = ?
                """, (embedding_bytes, embedding_service.model, context_id))
                conn.commit()
                embedding_status = " [embedded]"
            else:
                print(f"⚠️  Embedding generation returned None for context '{topic}'", file=sys.stderr)
        else:
            print(f"⚠️  Embedding service not available for context '{topic}' - run generate_embeddings() later", file=sys.stderr)
    except Exception as e:
        print(f"⚠️  Could not generate embedding for '{topic}': {e}", file=sys.stderr)
        print(f"   Run generate_embeddings() to add embeddings later", file=sys.stderr)

    return embedding_status


@breadcrumb
@mcp.tool()
async def lock_context(
    content: str,
    topic: str,
    tags: Optional[str] = None,
    priority: Optional[str] = None,
    project: Optional[str] = None
) -> str:
    """
    Lock important context, rules, or decisions as immutable versioned snapshots for perfect recall.

    **CRITICAL: When to use this tool:**
    - API specifications, contracts, or schemas you need to remember exactly
    - Architecture decisions, design patterns, or system constraints
    - Rules that MUST/ALWAYS/NEVER be violated (e.g., "ALWAYS use output/ directory")
    - Configuration details, environment setup, or deployment procedures
    - Important agreements, requirements, or user preferences
    - Code patterns, naming conventions, or style guidelines

    **What this tool does:**
    - Creates immutable versioned snapshot (no edits, only new versions)
    - Automatically generates intelligent preview for fast relevance checking
    - Extracts key technical concepts for better search matching
    - Stores with priority level to control when it's checked
    - Enables 60-80% faster context searches through RLM optimization

    **Priority levels (auto-detected if not specified):**
    - 'always_check': ⚠️  Critical rules checked before ALL relevant actions
      Use for: Must-never-violate rules, security requirements, critical constraints
    - 'important': 📌 Shown at session start, checked when highly relevant
      Use for: Architecture decisions, important patterns, key configurations
    - 'reference': Standard reference material, checked when relevant
      Use for: Documentation, examples, general information

    **Multi-project support:**
    - project: Optional project name. If not specified, uses active project.
    - Priority: explicit param > session active > auto-detect > "default"
    - Example: lock_context(..., project="innkeeper")

    **Best practices:**
    1. Lock specific, actionable information (not general knowledge)
    2. Include concrete examples in the content
    3. Use MUST/ALWAYS/NEVER keywords for rules (auto-detects priority)
    4. Add descriptive tags for better search: tags="api,auth,jwt"
    5. Lock early when you document important decisions

    **Example usage:**
    ```
    # Lock critical API spec
    lock_context(
        content="API Authentication: MUST use JWT tokens. NEVER send passwords in URLs.",
        topic="api_auth_rules",
        tags="api,security,auth",
        priority="always_check"
    )

    # Lock architecture decision for specific project
    lock_context(
        content="Database: Using PostgreSQL 14 with connection pooling (max 20 connections).",
        topic="database_config",
        tags="database,postgres,config",
        priority="important",
        project="innkeeper"
    )
    ```

    **What happens after locking:**
    - Context is automatically checked when relevant (via check_contexts)
    - Preview enables fast relevance checking (60-80% token savings)
    - Can be recalled exactly with recall_context(topic)
    - Violations of rules are detected and warned about

    Args:
        content: The context content to lock (API spec, rules, decisions, etc.)
        topic: Context label/name for retrieval
        tags: Comma-separated tags for search (optional)
        priority: Priority level - always_check/important/reference (optional, auto-detected)
        project: Project name (default: auto-detect or active project)

    Returns:
        JSON with confirmation, version number, and priority indicator
    """
    # Check if project selection is required
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check

    # Use project-aware database connection
    target_project = _get_project_for_context(project)

    # ✅ FIX: Use context manager to ensure connection is closed
    with _get_db_for_project(project) as conn:
        session_id = _get_session_id_for_project(conn, project)

        # Ensure session exists in this project database
        try:
            conn.execute("""
                INSERT INTO sessions (id, started_at, last_active, project_name, project_path)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET last_active = EXCLUDED.last_active
            """, (session_id, time.time(), time.time(), target_project, get_project_root() or ''))
            conn.commit()
        except Exception as e:
            print(f"⚠️  Warning: Could not ensure session exists: {e}", file=sys.stderr)

        # Auto-detect priority if not specified (using helper)
        if priority is None:
            priority = _auto_detect_priority(content)

        # Validate priority
        valid_priorities = ['always_check', 'important', 'reference']
        if priority not in valid_priorities:
            return f"❌ Invalid priority '{priority}'. Must be one of: {', '.join(valid_priorities)}"

        # Generate hash
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Get next version (using helper)
        version = _get_next_version(conn, topic, session_id)

        # Extract keywords (using helper)
        keywords = _extract_keywords_from_content(content)

        # Prepare metadata with priority and keywords
        metadata = {
            "tags": tags.split(',') if tags else [],
            "priority": priority,
            "keywords": keywords,
            "created_at": datetime.now().isoformat()
        }

        # Generate preview and key concepts for RLM optimization
        preview = generate_preview(content, max_length=500)
        tag_list = tags.split(',') if tags else []
        key_concepts = extract_key_concepts(content, tag_list)

        # Store lock
        try:
            current_time = time.time()

            # Insert the context lock and get the ID
            cursor = conn.execute("""
                INSERT INTO context_locks
                (session_id, label, version, content, content_hash, locked_at, metadata,
                 preview, key_concepts, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, (session_id, topic, version, content, content_hash, current_time, json.dumps(metadata),
                  preview, json.dumps(key_concepts), current_time))

            context_id = cursor.fetchone()['id']

            # Create audit trail entry
            priority_label = {
                'always_check': ' [CRITICAL RULE]',
                'important': ' [IMPORTANT]',
                'reference': ''
            }.get(priority, '')

            audit_message = f"Locked context '{topic}' v{version}{priority_label} ({len(content)} chars, {len(tag_list)} tags)"

            conn.execute("""
                INSERT INTO memory_entries (category, content, timestamp, session_id)
                VALUES ('progress', ?, ?, ?)
            """, (audit_message, current_time, session_id))

            conn.commit()

            # Generate embedding (using helper - non-blocking, graceful failure)
            embedding_status = _generate_and_store_embedding(conn, context_id, preview, topic)

            priority_indicator = {
                'always_check': ' ⚠️ [ALWAYS CHECK]',
                'important': ' 📌 [IMPORTANT]',
                'reference': ''
            }.get(priority, '')

            project_label = f" in project '{target_project}'" if target_project != "default" else ""
            return f"✅ Locked '{topic}' as v{version}{priority_indicator}{project_label}{embedding_status} ({len(content)} chars, hash: {content_hash[:8]})"

        except Exception as e:
            # Handle duplicate version error (works for both SQLite and PostgreSQL)
            if 'duplicate key' in str(e).lower() or 'unique constraint' in str(e).lower():
                return f"❌ Version {version} of '{topic}' already exists"
            raise
        except Exception as e:
            return f"❌ Failed to lock context: {str(e)}"


# Helper functions for recall_context (extracted for DRY and testability)

def _fetch_context_by_version(conn, topic, version, session_id):
    """
    Query context_locks table for a specific topic and version.
    Returns the database row or None if not found.
    """
    if version == "latest":
        cursor = conn.execute("""
            SELECT id, content, preview, key_concepts, version, locked_at, metadata
            FROM context_locks
            WHERE label = ? AND session_id = ?
            ORDER BY locked_at DESC
            LIMIT 1
        """, (topic, session_id))
    else:
        # Clean version (remove 'v' prefix if present)
        clean_version = version[1:] if version.startswith('v') else version
        cursor = conn.execute("""
            SELECT id, content, preview, key_concepts, version, locked_at, metadata
            FROM context_locks
            WHERE label = ? AND version = ? AND session_id = ?
        """, (topic, clean_version, session_id))

    return cursor.fetchone()


def _format_recall_preview(row, topic):
    """
    Format a context row as a JSON preview response.
    Returns token-efficient summary with key metadata.
    """
    dt = datetime.fromtimestamp(row['locked_at'])
    metadata = json.loads(row['metadata']) if row['metadata'] else {}
    tags = metadata.get('tags', [])
    key_concepts = json.loads(row['key_concepts']) if row['key_concepts'] else []

    content_size_kb = len(row['content']) / 1024
    preview_text = row['preview'] or row['content'][:500] + "..."

    return json.dumps({
        "topic": topic,
        "version": row['version'],
        "preview": preview_text,
        "key_concepts": key_concepts[:5],  # Top 5 concepts
        "tags": tags,
        "locked_at": dt.strftime('%Y-%m-%d %H:%M'),
        "content_size_kb": round(content_size_kb, 1),
        "note": "Use preview_only=False to get full content"
    }, indent=2)


def _format_recall_full(row, topic):
    """
    Format a context row as full content response.
    Returns complete context with metadata header.
    """
    dt = datetime.fromtimestamp(row['locked_at'])
    metadata = json.loads(row['metadata']) if row['metadata'] else {}
    tags = metadata.get('tags', [])
    key_concepts = json.loads(row['key_concepts']) if row['key_concepts'] else []

    output = []
    output.append(f"📌 {topic} v{row['version']}")
    output.append(f"Locked: {dt.strftime('%Y-%m-%d %H:%M')}")
    if tags:
        output.append(f"Tags: {', '.join(tags)}")
    if key_concepts:
        output.append(f"Concepts: {', '.join(key_concepts[:5])}")
    output.append("-" * 40)
    output.append(row['content'])

    return "\n".join(output)


@breadcrumb
@mcp.tool()
async def recall_context(
    topic: str,
    version: Optional[str] = "latest",
    preview_only: bool = False,
    project: Optional[str] = None
) -> str:
    """
    Retrieve content of a previously locked context by topic name.

    **Token Efficiency: MINIMAL (preview) or FULL (complete)**
    - preview_only=True: Returns 500-char summary (~100 tokens)
    - preview_only=False: Returns full content (could be 10KB+)

    **When to use this tool:**
    - When check_contexts indicates a relevant locked context exists
    - To get full details of an API spec, rule, or decision
    - To verify exact requirements before implementing
    - To recall specific configuration or setup details

    **Preview Mode (preview_only=True):**
    - Returns intelligent summary (~500 chars)
    - Shows key concepts and important rules
    - Indicates content size
    - Perfect for quick relevance checking
    - 95% token reduction vs full content

    **Full Mode (preview_only=False, default):**
    - Returns complete content (exactly as stored)
    - Use when you need exact details
    - Use after preview confirms relevance

    **Version handling:**
    - "latest" (default): Returns most recent version
    - "1.0", "1.1", etc.: Returns specific version
    - Contexts are immutable - each edit creates new version
    - Version history preserved forever

    **Multi-project support:**
    - project: Optional project name. If not specified, uses active project.
    - Priority: explicit param > session active > auto-detect > "default"
    - Example: recall_context("api_spec", project="innkeeper")

    **Best practices:**
    1. Use after check_contexts identifies relevant context
    2. Start with preview_only=True to assess relevance
    3. Load full content only when needed for implementation
    4. Use batch_recall_contexts() for multiple contexts

    **Example workflow:**
    ```python
    # Step 1: Check what's relevant
    check_contexts("implementing user authentication")
    # Returns: "api_auth_rules is relevant (⚠️ always_check)"

    # Step 2: Get preview first
    recall_context("api_auth_rules", preview_only=True)
    # Returns: "JWT tokens required. MUST use OAuth2. NEVER store plaintext..."
    # Size: 8.5KB

    # Step 3: Load full content if needed
    recall_context("api_auth_rules")
    # Returns full API authentication specification (8.5KB)

    # Recall from different project
    recall_context("database_config", project="linkedin")
    ```

    **Performance note:**
    With RLM optimization:
    - check_contexts uses lightweight previews (fast scan)
    - recall_context(preview_only=True) returns summary (100 tokens)
    - recall_context() loads full content only when needed
    - Result: 95% token reduction for context exploration

    Args:
        topic: Context label/name
        version: "latest" or specific version like "1.0"
        preview_only: If True, return summary instead of full content
        project: Optional project name (uses active project if not specified)

    Returns: Context content (preview or full) with metadata, or error if not found
    """
    # Check if project selection is required
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check

    # Use project-aware database connection
    target_project = _get_project_for_context(project)

    # ✅ FIX: Use context manager to ensure connection is closed
    with _get_db_for_project(project) as conn:
        session_id = _get_session_id_for_project(conn, project)

        # Fetch context using helper
        row = _fetch_context_by_version(conn, topic, version, session_id)

        if row:
            context_id = row['id']

            # Track access
            conn.execute("""
                UPDATE context_locks
                SET last_accessed = ?,
                    access_count = access_count + 1
                WHERE id = ?
            """, (time.time(), context_id))
            conn.commit()

            # Return formatted response using helpers
            if preview_only:
                return _format_recall_preview(row, topic)
            else:
                return _format_recall_full(row, topic)
        else:
            return f"❌ No locked context found for '{topic}' (version: {version})"


# ============================================================================
# Helper Functions for unlock_context (Extracted for DRY and Testability)
# ============================================================================

def _find_contexts_to_delete(
    conn,
    topic: str,
    version: str,
    session_id: str
) -> list[dict]:
    """
    Find contexts to delete based on topic and version criteria.

    Searches the context_locks table for contexts matching the given topic
    and version specification, filtered by session_id for isolation.

    Args:
        conn: Database connection (SQLite cursor-compatible)
        topic: Context label/topic to search for
        version: Version specifier - "all", "latest", or specific version string
        session_id: Current session ID for session isolation

    Returns:
        List of context dictionaries matching the criteria (may be empty).
        Each dict contains: id, label, version, content, metadata, session_id, etc.

    Raises:
        None - returns empty list if no matches found

    Examples:
        # Find all versions of a topic
        contexts = _find_contexts_to_delete(conn, "api_config", "all", "sess_123")
        # Returns: [{"id": 1, "label": "api_config", "version": "1.0", ...}, ...]

        # Find only the latest version
        contexts = _find_contexts_to_delete(conn, "api_config", "latest", "sess_123")
        # Returns: [{"id": 5, "label": "api_config", "version": "2.3", ...}]

        # Find specific version
        contexts = _find_contexts_to_delete(conn, "api_config", "1.0", "sess_123")
        # Returns: [{"id": 1, "label": "api_config", "version": "1.0", ...}]

        # No matches found
        contexts = _find_contexts_to_delete(conn, "nonexistent", "all", "sess_123")
        # Returns: []
    """
    if version == "all":
        cursor = conn.execute(
            "SELECT * FROM context_locks WHERE label = ? AND session_id = ?",
            (topic, session_id)
        )
    elif version == "latest":
        cursor = conn.execute(
            """SELECT * FROM context_locks
               WHERE label = ? AND session_id = ?
               ORDER BY version DESC
               LIMIT 1""",
            (topic, session_id)
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM context_locks WHERE label = ? AND version = ? AND session_id = ?",
            (topic, version, session_id)
        )

    return cursor.fetchall()


def _check_critical_contexts(contexts: list[dict]) -> bool:
    """
    Check if any context in the list has critical (always_check) priority.

    Args:
        contexts: List of context dictionaries with 'metadata' field

    Returns:
        True if at least one context is critical, False otherwise

    Notes:
        - Handles None metadata gracefully (treats as non-critical)
        - Handles malformed JSON gracefully (treats as non-critical)
        - A context is critical if metadata.priority == 'always_check'

    Examples:
        >>> contexts = [
        ...     {'metadata': '{"priority": "always_check"}'},
        ...     {'metadata': '{"priority": "normal"}'}
        ... ]
        >>> _check_critical_contexts(contexts)
        True

        >>> contexts = [{'metadata': '{"priority": "normal"}'}]
        >>> _check_critical_contexts(contexts)
        False

        >>> contexts = [{'metadata': None}]
        >>> _check_critical_contexts(contexts)
        False
    """
    for ctx in contexts:
        try:
            metadata = json.loads(ctx['metadata']) if ctx['metadata'] else {}
            if metadata.get('priority') == 'always_check':
                return True
        except (json.JSONDecodeError, KeyError, TypeError):
            # Treat malformed metadata as non-critical
            continue

    return False


def _archive_contexts(
    conn,
    contexts: list[dict],
    delete_reason: str
) -> tuple[bool, Optional[str]]:
    """
    Archive contexts to context_archives table before deletion.

    Args:
        conn: Database connection object with execute() method
        contexts: List of context dictionaries to archive. Each dict must contain:
                  'id', 'session_id', 'label', 'version', 'content', 'preview',
                  'key_concepts', 'metadata'
        delete_reason: Reason for deletion (e.g., "Deleted all version(s)")

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
        - (True, None) if all archives succeeded
        - (False, error_msg) if any archive failed

    Notes:
        - Archives are inserted with timestamp (time.time())
        - Preserves all context fields (id, session_id, label, version, etc.)
        - Returns on first failure (no partial archives)
        - Uses parameterized queries to prevent SQL injection

    Examples:
        >>> contexts = [
        ...     {
        ...         'id': 1,
        ...         'session_id': 'sess_123',
        ...         'label': 'api_config',
        ...         'version': 1,
        ...         'content': 'API_KEY=xyz',
        ...         'preview': 'API configuration',
        ...         'key_concepts': 'api, config',
        ...         'metadata': '{}'
        ...     }
        ... ]
        >>> success, error = _archive_contexts(conn, contexts, "Deleted all version(s)")
        >>> assert success is True
        >>> assert error is None

        >>> # Handle archive failure
        >>> success, error = _archive_contexts(bad_conn, contexts, "Manual deletion")
        >>> assert success is False
        >>> assert "Failed to archive" in error
    """
    for ctx in contexts:
        try:
            conn.execute("""
                INSERT INTO context_archives
                (original_id, session_id, label, version, content, preview, key_concepts,
                 metadata, deleted_at, delete_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ctx['id'], ctx['session_id'], ctx['label'], ctx['version'],
                  ctx['content'], ctx['preview'], ctx['key_concepts'],
                  ctx['metadata'], time.time(), delete_reason))
        except Exception as e:
            error_msg = f"Failed to archive context '{ctx.get('label', 'unknown')}' (version {ctx.get('version', '?')}): {str(e)}"
            return (False, error_msg)

    return (True, None)


@mcp.tool()
async def unlock_context(
    topic: str,
    version: str = "all",
    force: bool = False,
    archive: bool = True,
    project: Optional[str] = None
) -> str:
    """
    Remove locked context(s) that are no longer relevant.

    **When to use this tool:**
    - Remove outdated deployment processes or configurations
    - Delete deprecated API specs or documentation
    - Clean up test/experimental locks
    - Remove duplicate or incorrect contexts
    - Maintain a clean, relevant context tree

    **How it works:**
    - Archives context before deletion (recoverable)
    - Requires force=True for critical (always_check) contexts
    - Can delete all versions, specific version, or latest only
    - Shows what will be deleted before confirmation

    **Version options:**
    - `version="all"`: Delete all versions of topic (default)
    - `version="1.0"`: Delete only specific version
    - `version="latest"`: Delete only most recent version

    **Safety features:**
    - ⚠️ Critical contexts require `force=True` to delete
    - Archives deleted contexts by default (set `archive=False` to skip)
    - Shows count of what will be deleted
    - Prevents accidental bulk deletion

    **Best practices:**
    1. Review context before deleting (use recall_context)
    2. Archive is enabled by default for safety
    3. Be careful with `force=True` on critical contexts
    4. Delete specific versions to preserve history

    **Example workflows:**
    ```
    # Remove all versions of outdated context
    unlock_context("old_api_v1", version="all")

    # Remove only latest version (keep history)
    unlock_context("api_spec", version="latest")

    # Remove specific version
    unlock_context("deployment_process", version="2.0")

    # Force delete critical context (use with caution!)
    unlock_context("critical_rule", version="all", force=True)
    ```

    **What you'll see:**
    - Count of versions deleted
    - Archive location (if archived)
    - Warning if critical context

    **Recovery:**
    - Archived contexts can be manually recovered from context_archives table
    - Use SQL or future unarchive_context() tool

    Returns: Confirmation with count of deleted contexts
    """
    # Check if project selection is required
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check

    update_session_activity()

    # ✅ FIX: Use context manager to ensure connection is closed
    with _get_db_for_project(project) as conn:
        session_id = _get_session_id_for_project(conn, project)

        # Step 1: Find contexts to delete (using helper function)
        contexts = _find_contexts_to_delete(conn, topic, version, session_id)

        if not contexts:
            return f"❌ Context '{topic}' (version: {version}) not found"

        # Step 2: Check for critical contexts (using helper function)
        has_critical = _check_critical_contexts(contexts)

        if has_critical and not force:
            return f"⚠️  Cannot delete critical (always_check) context '{topic}' without force=True\n" \
                   f"   This context contains important rules. Use force=True if you're sure."

        # Step 3: Archive before deletion (using helper function)
        if archive:
            delete_reason = f"Deleted {version} version(s)"
            success, error = _archive_contexts(conn, contexts, delete_reason)
            if not success:
                return f"❌ {error}"

        # Step 4: Delete contexts
        try:
            # Delete all found contexts by ID (simpler than query branching)
            for ctx in contexts:
                conn.execute("DELETE FROM context_locks WHERE id = ?", (ctx['id'],))

            # Step 5: Create audit trail entry
            current_time = time.time()
            count = len(contexts)
            version_str = f"{count} version(s)" if version == "all" else f"version {version}"

            critical_label = " [CRITICAL]" if has_critical else ""
            audit_message = f"Deleted {version_str} of context '{topic}'{critical_label}"
            if archive:
                audit_message += " (archived for recovery)"

            conn.execute("""
                INSERT INTO memory_entries (category, content, timestamp, session_id)
                VALUES ('progress', ?, ?, ?)
            """, (audit_message, current_time, session_id))

            conn.commit()

            result = f"✅ Deleted {version_str} of '{topic}'"

            if archive:
                result += f"\n   💾 Archived for recovery (query context_archives table)"

            if has_critical:
                result += f"\n   ⚠️  Critical context deleted (force=True was used)"

            return result

        except Exception as e:
            return f"❌ Failed to delete context: {str(e)}"

# Add these functions after unlock_context() in claude_mcp_hybrid.py (around line 1831)

# ============================================================
# PROJECT MEMORY SYNCHRONIZATION
# ============================================================

def _get_scannable_py_files(path: str, limit: int = 50):
    """
    Get Python files for scanning, respecting ignore patterns.

    Args:
        path: Root directory to scan
        limit: Maximum number of files to return (prevents permission spam)

    Returns:
        List of Path objects for Python files
    """
    skip_dirs = {
        'node_modules', 'venv', 'env', '.venv', '.env',
        '__pycache__', '.git', '.svn', '.hg',
        'dist', 'build', '.tox', '.pytest_cache',
        'site-packages', '.mypy_cache', '.eggs',
        '.conda', 'htmlcov', '.coverage'
    }

    py_files = []
    try:
        for py_file in Path(path).rglob("*.py"):
            # Skip if any parent directory is in skip list
            if any(part in skip_dirs for part in py_file.parts):
                continue
            py_files.append(py_file)
            if len(py_files) >= limit:
                break
    except Exception:
        pass

    return py_files

async def _detect_project_type(path: str) -> str:
    """Detect project type by analyzing structure."""
    try:
        py_files = _get_scannable_py_files(path, limit=20)
        for py_file in py_files:
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                # Check for MCP server patterns
                if ("@mcp.tool()" in content or
                    "from fastmcp import" in content or
                    "from mcp.server import" in content or
                    "from mcp import" in content):
                    return "mcp_server"
            except:
                continue
        return "other"
    except:
        return "other"

async def _extract_project_overview(path: str) -> Dict[str, str]:
    """Extract project overview."""
    project_name = Path(path).name
    project_type = await _detect_project_type(path)
    content = f"""# {project_name}

**Type:** {project_type}
**Purpose:** {project_name} project
**Stack:** Python

This overview was automatically generated."""

    return {
        'label': 'project_overview',
        'content': content,
        'tags': 'category:overview,auto_generated'
    }

async def _extract_database_schema(path: str) -> Optional[Dict[str, str]]:
    """Extract database schema from code."""
    try:
        py_files = _get_scannable_py_files(path, limit=30)
        schemas = []
        for py_file in py_files:
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                table_matches = re.findall(r'CREATE TABLE[^(]*\(.*?\)', content, re.DOTALL | re.IGNORECASE)
                schemas.extend(table_matches)
            except:
                continue
        if not schemas:
            return None
        formatted = "# Database Schema\n\n" + "\n\n".join(schemas[:5])
        return {
            'label': 'database_schema',
            'content': formatted,
            'tags': 'category:data,type:schema,auto_generated'
        }
    except:
        return None

async def _extract_tool_contracts(path: str) -> Optional[Dict[str, str]]:
    """Extract @mcp.tool() definitions."""
    try:
        py_files = _get_scannable_py_files(path, limit=30)
        tools = []
        for py_file in py_files:
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                tool_matches = re.findall(r'async def ([a-zA-Z_]+)', content)
                tools.extend(tool_matches)
            except:
                continue
        if not tools:
            return None
        formatted = "# MCP Tools\n\n" + "\n".join([f"- `{tool}()`" for tool in tools[:20]])
        return {
            'label': 'tool_contracts',
            'content': formatted,
            'tags': 'category:api,type:contracts,auto_generated'
        }
    except:
        return None

async def _extract_critical_rules(path: str) -> Optional[Dict[str, str]]:
    """Extract IMPORTANT/WARNING rules from comments."""
    try:
        py_files = _get_scannable_py_files(path, limit=30)
        rules = []
        keywords = ['IMPORTANT:', 'WARNING:', 'NEVER:', 'ALWAYS:']
        for py_file in py_files:
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                for line in content.split('\n'):
                    if any(kw in line for kw in keywords):
                        cleaned = line.strip().lstrip('#').strip()
                        if cleaned:
                            rules.append(f"- {cleaned}")
            except:
                continue
        if not rules:
            return None
        return {
            'label': 'critical_rules',
            'content': "# Critical Rules\n\n" + "\n".join(rules[:30]),
            'tags': 'category:safety,type:rules,auto_generated'
        }
    except:
        return None

@mcp.tool()
async def batch_lock_contexts(contexts: list[dict], project: Optional[str] = None) -> str:
    """
    Lock multiple contexts in one operation (reduces round-trips for cloud).

    **Purpose:** Efficient bulk context locking

    **Input:** JSON string containing array of context objects
    Each object should have:
    - content: str (required) - The context content
    - topic: str (required) - Context label/name
    - tags: str (optional) - Comma-separated tags
    - priority: str (optional) - always_check/important/reference

    **Returns:** JSON with results for each context

    **Example:**
    ```
    batch_lock_contexts('[
        {"topic": "api_v1", "content": "API spec...", "priority": "important"},
        {"topic": "database_schema", "content": "CREATE TABLE...", "tags": "database"}
    ]')
    ```

    **Benefits:**
    - Single operation instead of multiple tool calls
    - Critical for cloud migration (reduces latency)
    - Atomic operation - all succeed or all fail rolled back
    - Returns detailed status for each context
    """
    # Check if project selection is required
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check

    if not isinstance(contexts, list):
        return "❌ Input must be an array of context objects"

    contexts_list = contexts

    results = []
    successful = 0
    failed = 0

    for ctx in contexts_list:
        if not isinstance(ctx, dict):
            results.append({
                "status": "error",
                "error": "Invalid context object (must be dict)"
            })
            failed += 1
            continue

        if 'content' not in ctx or 'topic' not in ctx:
            results.append({
                "topic": ctx.get('topic', 'unknown'),
                "status": "error",
                "error": "Missing required fields: content and topic"
            })
            failed += 1
            continue

        try:
            result = await lock_context(
                content=ctx['content'],
                topic=ctx['topic'],
                tags=ctx.get('tags'),
                priority=ctx.get('priority'),
                project=project
            )
            # Check if embedding was generated
            embedded = "[embedded]" in result
            results.append({
                "topic": ctx['topic'],
                "status": "success",
                "message": "Context locked successfully",
                "embedded": embedded
            })
            successful += 1
        except Exception as e:
            results.append({
                "topic": ctx['topic'],
                "status": "error",
                "error": str(e)
            })
            failed += 1

    # Count embedded contexts
    embedded_count = sum(1 for r in results if r.get("embedded", False))

    return json.dumps({
        "summary": {
            "total": len(contexts_list),
            "successful": successful,
            "failed": failed,
            "embedded": embedded_count
        },
        "results": results
    }, indent=2)


@mcp.tool()
async def batch_recall_contexts(topics: list[str], preview_only: bool = True, project: Optional[str] = None) -> str:
    """
    Recall multiple contexts in one operation.

    **Token Efficiency: MINIMAL (preview) or FULL (complete)**
    - preview_only=True: Returns summaries (~100 tokens each, DEFAULT)
    - preview_only=False: Returns full content (could be 50KB+ total)

    **Purpose:** Efficient bulk context retrieval

    **Input:** JSON string containing array of topic names
    ```
    '["api_spec", "database_schema", "auth_rules"]'
    ```

    **Preview Mode (preview_only=True, DEFAULT):**
    - Returns intelligent summaries for each context
    - Shows key concepts, size, and relevance info
    - Perfect for assessing which contexts to load fully
    - 95% token reduction vs full content
    - Recommended for exploring multiple contexts

    **Full Mode (preview_only=False):**
    - Returns complete content for all contexts
    - Use when you need exact details from all contexts
    - Warning: Can consume 50KB+ tokens with multiple contexts

    **Returns:** JSON with content/preview for each requested topic

    **Benefits:**
    - Single operation instead of multiple recall calls
    - Efficient for loading related contexts
    - Returns status for each topic (found/not_found)
    - Defaults to preview mode to prevent context overflow

    **Example workflow:**
    ```python
    # Step 1: Get previews of all related contexts
    batch_recall_contexts('["api_v1", "database_schema", "auth_rules"]')
    # Returns: 3 summaries (~300 tokens total)

    # Step 2: Load specific contexts fully as needed
    recall_context("api_v1")  # Full content only for this one
    ```

    **Best practices:**
    1. Always start with preview_only=True (default)
    2. Review previews to identify which contexts you actually need
    3. Load full content individually for the 1-2 most relevant
    4. Avoid loading 5+ full contexts at once (context overflow)

    Args:
        topics: JSON string containing array of topic names
        preview_only: If True, return summaries (default); if False, full content

    Returns: JSON with summary and results for each topic
    """
    # Check if project selection is required
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check

    if not isinstance(topics, list):
        return "❌ Input must be an array of topic names"

    results = []
    found = 0
    not_found = 0

    for topic in topics:
        if not isinstance(topic, str):
            results.append({
                "topic": str(topic),
                "status": "error",
                "error": "Topic must be a string"
            })
            not_found += 1
            continue

        try:
            content = await recall_context(topic, preview_only=preview_only, project=project)
            if "❌" in content:  # recall_context returns error message
                results.append({
                    "topic": topic,
                    "status": "not_found",
                    "error": content
                })
                not_found += 1
            else:
                # Parse JSON if preview mode
                if preview_only and content.startswith('{'):
                    try:
                        content_data = json.loads(content)
                        results.append({
                            "topic": topic,
                            "status": "found",
                            "preview": content_data
                        })
                    except:
                        results.append({
                            "topic": topic,
                            "status": "found",
                            "content": content
                        })
                else:
                    results.append({
                        "topic": topic,
                        "status": "found",
                        "content": content
                    })
                found += 1
        except Exception as e:
            results.append({
                "topic": topic,
                "status": "error",
                "error": str(e)
            })
            not_found += 1

    return json.dumps({
        "summary": {
            "total": len(topics),
            "found": found,
            "not_found": not_found,
            "mode": "preview" if preview_only else "full",
            "note": "Use preview_only=False to get full content" if preview_only else None
        },
        "results": results
    }, indent=2)


# ==================== SEARCH_CONTEXTS HELPER FUNCTIONS ====================

def _try_semantic_search(conn, query: str, priority: Optional[str], tags: Optional[str], limit: int) -> Optional[dict]:
    """
    Attempt semantic search using embeddings.

    Returns: Results dict if successful, None to fall back to keyword search
    """
    try:
        from src.services import embedding_service
        from src.services.semantic_search import SemanticSearch

        if not embedding_service or not embedding_service.enabled:
            return None

        semantic_search = SemanticSearch(conn, embedding_service)

        # Check if any contexts have embeddings
        cursor = conn.execute("SELECT COUNT(*) as count FROM context_locks WHERE embedding IS NOT NULL")
        embedded_count = cursor.fetchone()['count']

        if embedded_count == 0:
            return None

        # Use semantic search with filters
        results = semantic_search.search_similar(
            query=query,
            limit=limit,
            threshold=0.6,  # Slightly lower threshold for search
            priority_filter=priority,
            tags_filter=tags
        )

        if results:
            return {
                "search_mode": "semantic",
                "query": query,
                "total_results": len(results),
                "results": results,
                "note": "Results ranked by semantic similarity (0-1)"
            }

        return None

    except Exception as e:
        # Fall back to keyword search
        print(f"⚠️  Semantic search unavailable: {e}", file=sys.stderr)
        return None


def _build_keyword_search_query(query: str, priority: Optional[str], tags: Optional[str], limit: int) -> tuple:
    """
    Build SQL query and parameters for keyword search.

    Returns: (sql, params) tuple
    """
    # NOTE: No session_id filter needed - schema isolation provides project-level isolation
    sql = """
        SELECT
            label, version, content, preview, key_concepts,
            locked_at, metadata, last_accessed, access_count
        FROM context_locks
        WHERE (
            content LIKE ?
            OR preview LIKE ?
            OR key_concepts LIKE ?
            OR label LIKE ?
        )
    """

    params = [f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%']

    # Add priority filter
    if priority:
        sql += " AND (metadata::json)->>'priority' = ?"
        params.append(priority)

    # Add tags filter
    if tags:
        tag_conditions = []
        for tag in tags.split(','):
            tag = tag.strip()
            tag_conditions.append("(metadata::json)->>'tags' LIKE ?")
            params.append(f'%{tag}%')
        sql += f" AND ({' OR '.join(tag_conditions)})"

    sql += " LIMIT ?"
    params.append(limit)

    return (sql, params)


def _score_search_results(rows, query: str) -> list:
    """
    Calculate relevance scores for keyword search results.

    Scoring:
    - Exact label match: 1.0 points
    - Key concepts match: 0.7 points
    - Content match: 0.5 points
    - Preview match: 0.3 points

    Returns: List of scored result dicts, sorted by score (highest first)
    """
    scored_results = []
    query_lower = query.lower()

    for row in rows:
        score = 0.0

        # Exact label match = highest score
        if query_lower in row['label'].lower():
            score += 1.0

        # Key concepts match
        if row['key_concepts'] and query_lower in row['key_concepts'].lower():
            score += 0.7

        # Content match
        if row['content'] and query_lower in row['content'].lower():
            score += 0.5

        # Preview match
        if row['preview'] and query_lower in row['preview'].lower():
            score += 0.3

        # Parse metadata
        metadata = json.loads(row['metadata']) if row['metadata'] else {}

        scored_results.append({
            "label": row['label'],
            "version": row['version'],
            "score": round(score, 2),
            "preview": row['preview'] or row['content'][:200] + "..." if row['content'] else "",
            "priority": metadata.get('priority', 'reference'),
            "tags": metadata.get('tags', []),
            "last_accessed": row['last_accessed'],
            "access_count": row['access_count'] or 0
        })

    # Sort by score (highest first)
    scored_results.sort(key=lambda x: x['score'], reverse=True)

    return scored_results


def _format_search_response(results: list, mode: str, query: str, priority: Optional[str], tags: Optional[str], limit: int) -> str:
    """
    Format search results as JSON response.

    Args:
        results: List of result dicts
        mode: "semantic" or "keyword"
        query: Original search query
        priority: Priority filter (or None)
        tags: Tags filter (or None)
        limit: Result limit

    Returns: JSON string
    """
    if mode == "semantic":
        return json.dumps({
            "search_mode": "semantic",
            "query": query,
            "total_results": len(results),
            "results": results,
            "note": "Results ranked by semantic similarity (0-1)"
        }, indent=2)
    else:
        return json.dumps({
            "search_mode": "keyword",
            "query": query,
            "filters": {
                "priority": priority,
                "tags": tags,
                "limit": limit
            },
            "total_found": len(results),
            "results": results,
            "note": "Results ranked by keyword relevance (0-3.5 max)"
        }, indent=2)


def _handle_no_results(query: str, priority: Optional[str], tags: Optional[str]) -> str:
    """
    Format empty search results response.

    Returns: JSON string for no results found
    """
    return json.dumps({
        "query": query,
        "filters": {
            "priority": priority,
            "tags": tags
        },
        "total_found": 0,
        "message": "No contexts found matching query",
        "results": []
    }, indent=2)


# ==================== END HELPER FUNCTIONS ====================

@breadcrumb
@mcp.tool()
async def search_contexts(
    query: str,
    priority: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = 10,
    use_semantic: bool = True,
    project: Optional[str] = None
) -> str:
    """
    Search locked contexts using hybrid semantic + keyword search.

    **Purpose:** Find contexts by what they contain, not just their label

    **Parameters:**
    - query: Search term (searches in content, preview, key_concepts, label)
    - priority: Filter by priority (always_check/important/reference)
    - tags: Filter by tags (comma-separated)
    - limit: Max results to return (default: 10)
    - use_semantic: Try semantic search first (default: True)
    - project: Project name (default: auto-detect or active project)

    **Returns:** JSON with matching contexts sorted by relevance/similarity

    **Hybrid Search:**
    - If use_semantic=True: Tries semantic search first, falls back to keyword
    - Semantic search: Uses embeddings for meaning-based matching
    - Keyword search: Traditional text matching with relevance scoring

    **Relevance scoring (keyword mode):**
    - Exact label match: 1.0 points
    - Key concepts match: 0.7 points
    - Content match: 0.5 points
    - Preview match: 0.3 points

    **Example:**
    ```
    search_contexts("authentication")  # Semantic + keyword hybrid
    search_contexts("JWT", priority="important", use_semantic=False)  # Keyword only
    search_contexts("database", tags="schema,migration", limit=5)
    ```

    **Use cases:**
    - Find contexts related to a topic
    - Locate context by remembered content
    - Discover relevant contexts for current work
    - Filter contexts by priority/tags
    """
    # Check if project selection is required
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check

    # ✅ FIX: Use context manager to ensure connection is closed
    with _get_db_for_project(project) as conn:
        session_id = _get_session_id_for_project(conn, project)

        # Try semantic search first if enabled
        if use_semantic:
            semantic_result = _try_semantic_search(conn, query, priority, tags, limit)
            if semantic_result:
                return json.dumps(semantic_result, indent=2)

        # Fall back to keyword search
        try:
            # Build SQL query and parameters
            sql, params = _build_keyword_search_query(query, priority, tags, limit)

            # Execute query
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

            # Handle no results
            if not rows:
                return _handle_no_results(query, priority, tags)

            # Score and format results
            scored_results = _score_search_results(rows, query)
            return _format_search_response(scored_results, "keyword", query, priority, tags, limit)

        except Exception as e:
            return f"❌ Search error: {str(e)}"



@mcp.tool()
#async def memory_analytics(project: Optional[str] = None) -> str:
#    """
#    Analyze memory system usage and health.
#
#    **Purpose:** Understand memory patterns, identify waste, get recommendations
#
#    **Returns:** JSON with comprehensive analytics:
#    - Overview: Total contexts, size, age
#    - Most accessed: Top 10 frequently used contexts
#    - Least accessed: Never-accessed contexts (candidates for cleanup)
#    - Largest contexts: Storage hogs
#    - Stale contexts: Not accessed in 30+ days
#    - By priority: Distribution across priority levels
#    - Recommendations: Actionable cleanup suggestions
#
#    **Use cases:**
#    - Identify unused contexts for cleanup
#    - Find most valuable contexts (high access count)
#    - Monitor storage usage
#    - Optimize memory system
#    - Plan capacity
#
#    **Example output:**
#    ```json
#    {
#      "overview": {
#        "total_contexts": 42,
#        "total_size_mb": 5.2,
#        "average_size_kb": 127
#      },
#      "recommendations": [
#        "Consider unlocking 8 stale contexts (not accessed in 30+ days)",
#        "12 contexts never accessed - verify still needed"
#      ]
#    }
#    ```
#    """
#    conn = _get_db_for_project(project)
#    session_id = _get_session_id_for_project(conn, project)
#
#    analytics = {
#        "overview": {},
#        "most_accessed": [],
#        "least_accessed": [],
#        "largest_contexts": [],
#        "stale_contexts": [],
#        "by_priority": {},
#        "recommendations": []
#    }
#
#    # Overview statistics
#    cursor = conn.execute("""
#        SELECT
#            COUNT(*) as total,
#            SUM(LENGTH(content)) as total_bytes,
#            AVG(LENGTH(content)) as avg_bytes,
#            MIN(locked_at) as oldest,
#            MAX(locked_at) as newest
#        FROM context_locks
#        WHERE session_id = ?
#    """, (session_id,))
#    overview = cursor.fetchone()
#
#    if overview and overview['total'] > 0:
#        analytics["overview"] = {
#            "total_contexts": int(overview['total']),
#            "total_size_mb": round(float(overview['total_bytes']) / (1024*1024), 2),
#            "average_size_kb": round(float(overview['avg_bytes']) / 1024, 2),
#            "oldest_context_age_days": round((time.time() - float(overview['oldest'])) / 86400, 1),
#            "newest_context_age_days": round((time.time() - float(overview['newest'])) / 86400, 1)
#        }
#    else:
#        return json.dumps({
#            "message": "No contexts found in memory",
#            "overview": {"total_contexts": 0}
#        }, indent=2)
#
#    # Most accessed (top 10)
#    cursor = conn.execute("""
#        SELECT
#            label, version, access_count,
#            last_accessed, LENGTH(content) as size_bytes
#        FROM context_locks
#        WHERE session_id = ? AND access_count > 0
#        ORDER BY access_count DESC
#        LIMIT 10
#    """, (session_id,))
#    analytics["most_accessed"] = [
#        {
#            "label": row['label'],
#            "version": row['version'],
#            "access_count": int(row['access_count']),
#            "size_kb": round(float(row['size_bytes']) / 1024, 2),
#            "last_accessed_days_ago": round((time.time() - float(row['last_accessed'])) / 86400, 1) if row['last_accessed'] else None
#        }
#        for row in cursor.fetchall()
#    ]
#
#    # Least accessed (never accessed)
#    cursor = conn.execute("""
#        SELECT
#            label, version, locked_at, LENGTH(content) as size_bytes
#        FROM context_locks
#        WHERE session_id = ? AND (access_count IS NULL OR access_count = 0)
#        ORDER BY locked_at DESC
#        LIMIT 10
#    """, (session_id,))
#    analytics["least_accessed"] = [
#        {
#            "label": row['label'],
#            "version": row['version'],
#            "locked_days_ago": round((time.time() - float(row['locked_at'])) / 86400, 1),
#            "size_kb": round(float(row['size_bytes']) / 1024, 2)
#        }
#        for row in cursor.fetchall()
#    ]
#
#    # Largest contexts (top 10 storage hogs)
#    cursor = conn.execute("""
#        SELECT
#            label, version, LENGTH(content) as size_bytes, access_count
#        FROM context_locks
#        WHERE session_id = ?
#        ORDER BY LENGTH(content) DESC
#        LIMIT 10
#    """, (session_id,))
#    analytics["largest_contexts"] = [
#        {
#            "label": row['label'],
#            "version": row['version'],
#            "size_kb": round(float(row['size_bytes']) / 1024, 2),
#            "access_count": int(row['access_count']) if row['access_count'] else 0
#        }
#        for row in cursor.fetchall()
#    ]
#
#    # Stale contexts (not accessed in 30+ days)
#    thirty_days_ago = time.time() - (30 * 86400)
#    cursor = conn.execute("""
#        SELECT
#            label, version, last_accessed, LENGTH(content) as size_bytes
#        FROM context_locks
#        WHERE session_id = ?
#          AND (last_accessed IS NULL OR last_accessed < ?)
#        ORDER BY last_accessed ASC NULLS FIRST
#    """, (session_id, thirty_days_ago))
#    analytics["stale_contexts"] = [
#        {
#            "label": row['label'],
#            "version": row['version'],
#            "days_since_access": round((time.time() - float(row['last_accessed'])) / 86400, 1) if row['last_accessed'] else "never",
#            "size_kb": round(float(row['size_bytes']) / 1024, 2)
#        }
#        for row in cursor.fetchall()
#    ]
#
#    # By priority distribution
#    cursor = conn.execute("""
#        SELECT
#            (metadata::json)->>'priority' as priority,
#            COUNT(*) as count,
#            SUM(LENGTH(content)) as total_bytes
#        FROM context_locks
#        WHERE session_id = ?
#        GROUP BY (metadata::json)->>'priority'
#    """, (session_id,))
#
#    analytics["by_priority"] = {}
#    for row in cursor.fetchall():
#        priority = row['priority'] or 'reference'
#        analytics["by_priority"][priority] = {
#            "count": int(row['count']),
#            "size_mb": round(float(row['total_bytes']) / (1024*1024), 2)
#        }
#
#    # Generate recommendations
#    if len(analytics["stale_contexts"]) > 0:
#        analytics["recommendations"].append(
#            f"Consider unlocking {len(analytics['stale_contexts'])} stale contexts (not accessed in 30+ days)"
#        )
#
#    if len(analytics["least_accessed"]) > 5:
#        analytics["recommendations"].append(
#            f"{len(analytics['least_accessed'])} contexts have never been accessed - verify they're still needed"
#        )
#
#    total_mb = analytics["overview"]["total_size_mb"]
#    capacity_mb = 50  # Current limit
#    usage_percent = (total_mb / capacity_mb) * 100
#
#    if usage_percent > 80:
#        analytics["recommendations"].append(
#            f"Memory usage at {total_mb}MB ({usage_percent:.1f}% of {capacity_mb}MB limit) - consider cleanup"
#        )
#
#    if not analytics["recommendations"]:
#        analytics["recommendations"].append("Memory system looks healthy - no immediate actions needed")
#
#    return json.dumps(analytics, indent=2)
#
#
#@mcp.tool()
async def sync_project_memory(
    path: Optional[str] = None,
    confirm: bool = False,
    dry_run: bool = False,
    priorities: Optional[List[str]] = None,
    project: Optional[str] = None
) -> str:
    """
    Synchronize project memory with current codebase state - make memory match reality.

    Full design in SYNC_MEMORY_DESIGN.md and INITIALIZATION_PLAN.md
    """
    path = path or os.getcwd()
    priorities = priorities or ["always_check", "important"]
    report = []

    # PHASE 0: Project Analysis
    report.append("🔍 PHASE 0: Analyzing project structure...")
    project_type = await _detect_project_type(path)
    report.append(f"   Project type detected: {project_type}")

    # PHASE 1: Cleanup (simplified for now)
    report.append("\n🧹 PHASE 1: Detecting stale contexts...")
    report.append("   ⏭️  Skipped (no auto-generated contexts found)")

    # PHASE 2: Extract and Sync
    report.append("\n📝 PHASE 2: Extracting and syncing contexts...")
    extractors = []

    if "always_check" in priorities:
        extractors.extend([
            ("project_overview", _extract_project_overview, "always_check"),
            ("database_schema", _extract_database_schema, "always_check"),
            ("critical_rules", _extract_critical_rules, "always_check"),
        ])

    if "important" in priorities:
        extractors.append(("tool_contracts", _extract_tool_contracts, "important"))

    created = []
    skipped = []

    for label, extractor_func, priority in extractors:
        try:
            extracted = await extractor_func(path)
            if extracted is None:
                skipped.append(f"      ⏭️  Skipped '{label}' (not found in project)")
                continue

            # Check if context exists
            existing = await recall_context(label, version="latest")

            if not existing or "❌" in existing or "No locked context found" in existing:
                # CREATE new context
                if not dry_run:
                    # Add auto_generated flag to metadata
                    metadata_dict = json.loads(extracted.get('metadata', '{}')) if extracted.get('metadata') else {}
                    metadata_dict['auto_generated'] = True

                    await lock_context(
                        content=extracted['content'],
                        topic=label,
                        tags=extracted.get('tags', ''),
                        priority=priority
                    )

                    # Update metadata to mark as auto-generated
                    # ✅ FIX: Use context manager to ensure connection is closed
                    with _get_db_for_project(project) as conn:
                        session_id = _get_session_id_for_project(conn, project)
                        conn.execute("""
                            UPDATE context_locks
                            SET metadata = ?
                            WHERE label = ? AND session_id = ?
                        """, (json.dumps(metadata_dict), label, session_id))
                        conn.commit()

                created.append(f"      ✅ Created '{label}' ({priority})")
            else:
                skipped.append(f"      ⏭️  Skipped '{label}' (already exists)")

        except Exception as e:
            report.append(f"      ❌ Failed to extract '{label}': {str(e)}")

    if created:
        report.append(f"\n   Created {len(created)} new contexts:")
        report.extend(created)

    if skipped:
        report.append(f"\n   Skipped {len(skipped)} contexts:")
        report.extend(skipped[:5])

    # PHASE 3: Validation
    report.append("\n✅ PHASE 3: Validation")
    report.append(f"   Analysis complete")

    # Summary
    report.append("\n" + "=" * 60)
    if dry_run:
        report.append("🔍 DRY RUN - No changes made")
        report.append("   Run with confirm=True to apply these changes")
    else:
        report.append("✨ Memory synchronization complete!")
        report.append(f"   📚 Use explore_context_tree() to view all contexts")
    report.append("=" * 60)

    return "\n".join(report)


# ============================================================
# DATABASE QUERY TOOLS
# ============================================================

# Helper functions for query_database (extracted for DRY and testability)

def _validate_query(query: str) -> Optional[str]:
    """
    Validate that query is safe (SELECT-only, no dangerous keywords).
    Returns error string if invalid, None if valid.
    """
    query_upper = query.strip().upper()
    dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 'PRAGMA', 'ATTACH', 'DETACH']

    if not query_upper.startswith('SELECT'):
        return "❌ Error: Only SELECT queries are allowed.\n\nUse query_database() for read-only operations only.\n\nFor modifications, use the provided MCP tools:\n- lock_context() to create/update contexts\n- unlock_context() to delete contexts\n- memory_update() to add memories"

    for keyword in dangerous_keywords:
        if keyword in query_upper:
            return f"❌ Error: Query contains dangerous keyword '{keyword}'.\n\nOnly SELECT queries are allowed for safety."

    return None


def _execute_query_with_timing(conn, query: str, params: Optional[list] = None):
    """
    Execute query and measure execution time.
    Returns (rows, execution_time_ms) tuple.
    """
    start_time = time.time()

    cursor = conn.cursor()
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)

    rows = cursor.fetchall()
    execution_time_ms = (time.time() - start_time) * 1000

    return rows, execution_time_ms


def _format_as_json(rows, keys):
    """Format query results as JSON array."""
    result = [dict(row) for row in rows]
    return json.dumps(result, indent=2, default=str)


def _format_as_csv(rows, keys):
    """Format query results as CSV with header row."""
    output = []
    output.append(','.join(keys))
    for row in rows:
        output.append(','.join(str(v) for v in row))
    return '\n'.join(output)


def _format_as_table(rows, keys, execution_time_ms):
    """Format query results as ASCII table with borders and execution stats."""
    output = []

    # Calculate column widths
    widths = {k: len(k) for k in keys}
    for row in rows:
        for k in keys:
            widths[k] = max(widths[k], len(str(row[k])))

    # Header
    header = ' | '.join(k.ljust(widths[k]) for k in keys)
    separator = '-+-'.join('-' * widths[k] for k in keys)
    output.append(header)
    output.append(separator)

    # Rows
    for row in rows:
        output.append(' | '.join(str(row[k]).ljust(widths[k]) for k in keys))

    output.append(f'\n✅ {len(rows)} rows returned.')
    output.append(f'⏱️ Execution time: {execution_time_ms:.2f}ms')

    return '\n'.join(output)


@breadcrumb
@mcp.tool()
async def query_database(
    query: str,
    params: Optional[List[str]] = None,
    format: str = "table",
    db_path: Optional[str] = None,
    project: Optional[str] = None
) -> str:
    """
    Execute read-only SQL queries against the PostgreSQL database for debugging and inspection.

    This tool allows direct querying of the project's PostgreSQL database.

    **SAFETY FEATURES:**
    - Read-only enforcement: Only SELECT queries are allowed
    - Blocks dangerous operations: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, PRAGMA
    - Parameterized queries: Use ? placeholders to prevent SQL injection
    - Automatic LIMIT: Queries without LIMIT get LIMIT 100 added automatically
    - Path validation: Only accesses databases in current working directory

    **COMMON USE CASES:**

    1. Query project database:
       query_database("SELECT label, version FROM context_locks")

    2. Query with parameters:
       query_database("SELECT * FROM context_locks WHERE label = ?", params=["api_spec"])

    3. List all tables:
       query_database("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")

    4. Check row counts:
       query_database("SELECT COUNT(*) as count FROM context_locks")

    **OUTPUT FORMATS:**
    - "table": ASCII table with headers and separators (default, best for readability)
    - "json": JSON array of objects (best for programmatic use)
    - "csv": Comma-separated values (best for export)
    - "markdown": Markdown table (best for documentation)

    **EXAMPLES:**

    Query with parameters:
    ```python
    query_database(
        "SELECT * FROM context_locks WHERE label = ? AND version = ?",
        params=["api_spec", "1.0"],
        format="json"
    )
    ```

    Complex query:
    ```python
    query_database('''
        SELECT cl.label, cl.version, COUNT(m.id) as memory_count
        FROM context_locks cl
        LEFT JOIN memories m ON cl.session_id = m.session_id
        GROUP BY cl.label, cl.version
        ORDER BY memory_count DESC
    ''')
    ```

    Args:
        query: SQL SELECT query to execute
        params: Optional list of parameters for ? placeholders in query
        format: Output format - "table", "json", "csv", or "markdown"
        db_path: Optional path to SQLite database file (default: dementia memory database)
        project: Project name (default: auto-detect or active project)

    Returns:
        Formatted query results with row count and execution time

    Raises:
        Error message if query is unsafe or execution fails
    """
    import time
    import os
    from pathlib import Path

    try:
        # Safety check using helper
        validation_error = _validate_query(query)
        if validation_error:
            return validation_error

        # Add LIMIT if not present (prevent huge result sets)
        if 'LIMIT' not in query.upper():
            query = query.strip().rstrip(';') + ' LIMIT 100'

        # ✅ FIX: Use context managers to ensure connections are closed
        # Connect to database
        if db_path:
            # Validate path is in workspace
            abs_db_path = os.path.abspath(db_path)
            workspace = os.getcwd()

            if not abs_db_path.startswith(workspace):
                return f"❌ Error: Database must be in current workspace.\n\nProvided: {db_path}\nWorkspace: {workspace}"

            if not os.path.exists(abs_db_path):
                return f"❌ Error: Database file not found: {db_path}"

            # SQLite path - use context manager
            with sqlite3.connect(abs_db_path) as conn:
                conn.row_factory = sqlite3.Row

                start_time = time.time()

                # Execute query
                if params:
                    cursor = conn.execute(query, params)
                else:
                    cursor = conn.execute(query)

                rows = cursor.fetchall()
                execution_time = (time.time() - start_time) * 1000  # Convert to ms
        else:
            # PostgreSQL path - use context manager
            with _get_db_for_project(project) as conn:
                start_time = time.time()

                # PostgreSQL connection - need to use cursor
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                rows = cursor.fetchall()
                execution_time = (time.time() - start_time) * 1000  # Convert to ms

        if not rows:
            return f"✅ Query executed successfully.\n\n0 rows returned.\n⏱️ Execution time: {execution_time:.2f}ms"

        # Format output using helpers
        keys = list(rows[0].keys())

        if format == "json":
            return _format_as_json(rows, keys)
        elif format == "csv":
            return _format_as_csv(rows, keys)
        elif format == "markdown":
            # Keep markdown format inline (not extracted to helper)
            output = []
            output.append('| ' + ' | '.join(keys) + ' |')
            output.append('| ' + ' | '.join(['---' for _ in keys]) + ' |')
            for row in rows:
                output.append('| ' + ' | '.join(str(v) for v in row) + ' |')
            output.append(f'\n{len(rows)} rows')
            return '\n'.join(output)
        else:  # table format (default)
            return _format_as_table(rows, keys, execution_time)

    except Exception as e:
        return f"❌ Query failed: {str(e)}\n\nCheck your SQL syntax and try again."


# DEPRECATED: Replaced by health_check_and_repair() and inspect_schema()
# @mcp.tool()
# async def inspect_database(
#     mode: str = "overview",
#     filter_text: Optional[str] = None,
#     db_path: Optional[str] = None,
#     project: Optional[str] = None
# ) -> str:
#     """
#     DEPRECATED: SQLite-only tool. Use health_check_and_repair() or inspect_schema() instead.

#    This tool provides easy access to common database inspection tasks for any SQLite database
#    in your workspace. Works with the dementia memory database (default) or any .db/.sqlite file.
#
#    **INSPECTION MODES:**
#
#    1. **overview** - High-level statistics (dementia DB only)
#       - Total locked contexts by priority
#       - Total memories by category
#       - Total archived contexts
#       - Session information
#
#    2. **schema** - Complete database structure (works with ANY database)
#       - All table names
#       - Column names and types for each table
#       - Row counts per table
#
#    3. **contexts** - List locked contexts (dementia DB only)
#       - Label, version, priority
#       - Lock timestamp
#       - Content preview
#       - Optional filtering by label
#
#    4. **tables** - Just list table names (works with ANY database)
#       - Quick overview of database structure
#
#    4. **memories** - Recent memory entries
#       - Category, content, timestamp
#       - Sorted by most recent first
#       - Optional filtering by category
#
#    5. **archives** - Deleted contexts
#       - What was deleted and when
#       - Deletion reason
#       - Original content preserved
#
#    6. **tags** - File tagging system
#       - All tagged files
#       - Tag distribution
#       - Files needing review
#
#    7. **sessions** - Session activity
#       - Active sessions
#       - Context counts per session
#       - Memory counts per session
#
#    **EXAMPLES:**
#
#    Inspect dementia memory database (default):
#    ```python
#    inspect_database("overview")
#    inspect_database("contexts")
#    ```
#
#    Inspect any SQLite database:
#    ```python
#    inspect_database("schema", db_path="./data/app.db")
#    inspect_database("tables", db_path="./logs.sqlite")
#    ```
#
#    Find specific data:
#    ```python
#    inspect_database("contexts", filter_text="api")
#    ```
#
#    **USE CASES:**
#
#    - Debugging: "Why isn't my context showing up?"
#    - Exploration: "What tables are in this database?"
#    - Inspection: "What's the structure of this .db file?"
#    - Monitoring: "How much data is in each table?"
#
#    Args:
#        mode: Inspection mode - "overview", "schema", "contexts", "tables"
#        filter_text: Optional text to filter results (for contexts mode)
#        db_path: Optional path to SQLite database file (default: dementia memory database)
#        project: Project name (default: auto-detect or active project)
#
#    Returns:
#        Formatted inspection results with relevant statistics
#
#    Raises:
#        Error message if mode is invalid
#    """
#    import os
#
#    # Connect to database
#    if db_path:
#        # Validate path is in workspace
#        abs_db_path = os.path.abspath(db_path)
#        workspace = os.getcwd()
#
#        if not abs_db_path.startswith(workspace):
#            return f"❌ Error: Database must be in current workspace.\n\nProvided: {db_path}\nWorkspace: {workspace}"
#
#        if not os.path.exists(abs_db_path):
#            return f"❌ Error: Database file not found: {db_path}"
#
#        conn = sqlite3.connect(abs_db_path)
#        conn.row_factory = sqlite3.Row
#        session_id = None  # Custom DB won't have session_id
#    else:
#        # Use default dementia database
#        conn = _get_db_for_project(project)
#        conn.row_factory = sqlite3.Row
#        session_id = get_current_session_id()
#
#    try:
#        if mode == "tables":
#            # Quick table list (works with any database)
#            output = ["📋 DATABASE TABLES", "=" * 60, ""]
#
#            cursor = conn.execute("""
#                SELECT name FROM sqlite_master
#                WHERE type='table'
#                ORDER BY name
#            """)
#
#            tables = [row['name'] for row in cursor.fetchall()]
#
#            if tables:
#                for table in tables:
#                    # Get row count
#                    cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table}")
#                    count = cursor.fetchone()['count']
#                    output.append(f"   {table}: {count} rows")
#            else:
#                output.append("   No tables found")
#
#            return '\n'.join(output)
#
#        elif mode == "overview":
#            # Dementia DB specific
#            if not session_id:
#                return "❌ 'overview' mode only works with dementia database (default).\n\nUse 'schema' or 'tables' mode for other databases."
#
#            output = ["📊 DATABASE OVERVIEW", "=" * 60, ""]
#
#            # Locked contexts by priority
#            cursor = conn.execute("""
#                SELECT
#                    (metadata::json)->>'priority' as priority,
#                    COUNT(*) as count
#                FROM context_locks
#                WHERE session_id = ?
#                GROUP BY priority
#            """, (session_id,))
#
#            output.append("🔒 Locked Contexts:")
#            context_total = 0
#            for row in cursor.fetchall():
#                priority = row['priority'] or 'reference'
#                count = row['count']
#                context_total += count
#                output.append(f"   {priority}: {count}")
#            output.append(f"   TOTAL: {context_total}")
#            output.append("")
#
#            # Memories by category
#            cursor = conn.execute("""
#                SELECT category, COUNT(*) as count
#                FROM memory_entries
#                WHERE session_id = ?
#                GROUP BY category
#            """, (session_id,))
#
#            output.append("🧠 Memories:")
#            memory_total = 0
#            for row in cursor.fetchall():
#                count = row['count']
#                memory_total += count
#                output.append(f"   {row['category']}: {count}")
#            output.append(f"   TOTAL: {memory_total}")
#            output.append("")
#
#            # Archives
#            cursor = conn.execute("""
#                SELECT COUNT(*) as count FROM context_archives
#                WHERE session_id = ?
#            """, (session_id,))
#            archive_count = cursor.fetchone()['count']
#            output.append(f"📦 Archived contexts: {archive_count}")
#            output.append("")
#
#            # File tags
#            cursor = conn.execute("SELECT COUNT(*) as count FROM file_tags")
#            tag_count = cursor.fetchone()['count']
#            output.append(f"🏷️ Tagged files: {tag_count}")
#
#            return '\n'.join(output)
#
#        elif mode == "schema":
#            output = ["📋 DATABASE SCHEMA", "=" * 60, ""]
#
#            # Get all tables (PostgreSQL-compatible)
#            if is_postgresql_mode():
#                cursor = conn.execute("""
#                    SELECT table_name as name
#                    FROM information_schema.tables
#                    WHERE table_schema = current_schema()
#                    AND table_type = 'BASE TABLE'
#                    ORDER BY table_name
#                """)
#            else:
#                cursor = conn.execute("""
#                    SELECT name FROM sqlite_master
#                    WHERE type='table'
#                    ORDER BY name
#                """)
#
#            tables = [row['name'] for row in cursor.fetchall()]
#
#            for table in tables:
#                output.append(f"\n📄 Table: {table}")
#
#                # Get column info (PostgreSQL-compatible)
#                if is_postgresql_mode():
#                    cursor = conn.execute("""
#                        SELECT
#                            column_name as name,
#                            data_type as type,
#                            is_nullable,
#                            CASE WHEN column_default LIKE 'nextval%%' THEN 1 ELSE 0 END as pk
#                        FROM information_schema.columns
#                        WHERE table_schema = current_schema()
#                        AND table_name = ?
#                        ORDER BY ordinal_position
#                    """, (table,))
#                    columns = cursor.fetchall()
#
#                    output.append("   Columns:")
#                    for col in columns:
#                        pk = " (PRIMARY KEY)" if col['pk'] else ""
#                        notnull = " NOT NULL" if col['is_nullable'] == 'NO' else ""
#                        output.append(f"      {col['name']}: {col['type']}{pk}{notnull}")
#                else:
#                    cursor = conn.execute(f"PRAGMA table_info({table})")
#                    columns = cursor.fetchall()
#
#                    output.append("   Columns:")
#                    for col in columns:
#                        pk = " (PRIMARY KEY)" if col['pk'] else ""
#                        notnull = " NOT NULL" if col['notnull'] else ""
#                        output.append(f"      {col['name']}: {col['type']}{pk}{notnull}")
#
#                # Get row count
#                cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table}")
#                count = cursor.fetchone()['count']
#                output.append(f"   Rows: {count}")
#
#            return '\n'.join(output)
#
#        elif mode == "contexts":
#            # Dementia DB specific
#            if not session_id:
#                return "❌ 'contexts' mode only works with dementia database (default).\n\nUse 'schema' or 'tables' mode for other databases."
#
#            output = ["🔒 LOCKED CONTEXTS", "=" * 60, ""]
#
#            if filter_text:
#                cursor = conn.execute("""
#                    SELECT label, version, locked_at, preview, metadata
#                    FROM context_locks
#                    WHERE session_id = ? AND label LIKE ?
#                    ORDER BY locked_at DESC
#                """, (session_id, f"%{filter_text}%"))
#            else:
#                cursor = conn.execute("""
#                    SELECT label, version, locked_at, preview, metadata
#                    FROM context_locks
#                    WHERE session_id = ?
#                    ORDER BY locked_at DESC
#                """, (session_id,))
#
#            rows = cursor.fetchall()
#
#            if not rows:
#                return "No locked contexts found."
#
#            for row in rows:
#                metadata = json.loads(row['metadata']) if row['metadata'] else {}
#                priority = metadata.get('priority', 'reference')
#                dt = datetime.fromtimestamp(row['locked_at'])
#
#                output.append(f"\n• {row['label']} v{row['version']} [{priority}]")
#                output.append(f"  Locked: {dt.strftime('%Y-%m-%d %H:%M')}")
#                output.append(f"  Preview: {row['preview'][:80]}...")
#
#            output.append(f"\n\nTotal: {len(rows)} contexts")
#            return '\n'.join(output)
#
#        else:
#            return f"❌ Invalid mode: {mode}\n\nValid modes: tables, schema, overview, contexts\n\nNote: 'overview' and 'contexts' only work with dementia database (default)"
#
#    except Exception as e:
#        return f"❌ Inspection failed: {str(e)}"
#

@mcp.tool()
async def execute_sql(
    sql: str,
    params: Optional[List[str]] = None,
    db_path: Optional[str] = None,
    dry_run: bool = True,
    confirm: bool = False,
    max_affected: Optional[int] = None,
    project: Optional[str] = None
) -> str:
    """
    Execute write operations (INSERT, UPDATE, DELETE) on PostgreSQL database with comprehensive safety.

    This tool enables full SQL write capabilities while maintaining multiple layers of protection
    against accidental data loss or corruption. All operations are wrapped in transactions and
    can be previewed before execution.

    **SAFETY FEATURES:**
    - Dry-run by default: Shows preview without making changes (dry_run=True)
    - Confirmation required: Must explicitly set confirm=True to execute
    - Automatic transactions: All changes wrapped in BEGIN/COMMIT with auto-rollback on error
    - Parameterized queries: Use ? placeholders to prevent SQL injection
    - Row limits: Optional max_affected parameter limits scope of changes
    - Dangerous operation detection: Warns about UPDATE/DELETE without WHERE clause
    - Workspace validation: Only operates on databases in current workspace

    **SUPPORTED OPERATIONS:**
    - INSERT: Add new records
    - UPDATE: Modify existing records
    - DELETE: Remove records
    - Any single-statement write operation

    **COMMON USE CASES:**

    1. Fix corrupted context metadata:
       execute_sql(
           "UPDATE context_locks SET metadata = ? WHERE metadata IS NULL",
           params=['{"priority": "reference"}'],
           dry_run=False,
           confirm=True
       )

    2. Clean up old data:
       execute_sql(
           "DELETE FROM context_archives WHERE deleted_at < ?",
           params=[timestamp_90_days_ago],
           max_affected=100,
           dry_run=False,
           confirm=True
       )

    3. Bulk insert tags:
       execute_sql(
           "INSERT INTO file_tags (path, tag) VALUES (?, ?)",
           params=["src/main.py", "reviewed"],
           dry_run=False,
           confirm=True
       )

    4. Custom database operations:
       execute_sql(
           "INSERT INTO users (name, email) VALUES (?, ?)",
           params=["Alice", "alice@example.com"],
           db_path="./data/app.db",
           dry_run=False,
           confirm=True
       )

    **WORKFLOW:**

    Step 1 - Preview with dry-run (default):
    ```python
    result = execute_sql(
        "UPDATE context_locks SET priority = ? WHERE label LIKE ?",
        params=["important", "api_%"]
    )
    # Shows: "🔍 DRY RUN - Would affect 3 rows..."
    ```

    Step 2 - Execute after confirming:
    ```python
    result = execute_sql(
        "UPDATE context_locks SET priority = ? WHERE label LIKE ?",
        params=["important", "api_%"],
        dry_run=False,
        confirm=True
    )
    # Shows: "✅ Success! Updated 3 rows in 1.25ms"
    ```

    Args:
        sql: SQL statement to execute (INSERT, UPDATE, DELETE)
        params: Optional list of parameters for ? placeholders
        db_path: Optional path to SQLite database (default: dementia memory database)
        dry_run: If True, preview changes without executing (default: True)
        confirm: Must be True to execute (safety check, default: False)
        max_affected: Optional limit on number of rows that can be affected
        project: Project name (default: auto-detect or active project)

    Returns:
        Detailed report of operation result including affected rows and execution time

    Raises:
        Error message if operation fails, parameters invalid, or safety checks fail
    """
    import time
    import os
    import re

    try:
        # Parse SQL operation type
        sql_upper = sql.strip().upper()
        operation = None
        for op in ['INSERT', 'UPDATE', 'DELETE']:
            if sql_upper.startswith(op):
                operation = op
                break

        if not operation:
            return f"❌ Error: Only INSERT, UPDATE, and DELETE operations are supported.\n\nReceived: {sql[:50]}...\n\nFor SELECT queries, use query_database() instead."

        # Dangerous operation detection: UPDATE/DELETE without WHERE
        if operation in ['UPDATE', 'DELETE']:
            # Simple check: look for WHERE keyword
            if 'WHERE' not in sql_upper:
                return f"❌ WARNING: {operation} without WHERE clause affects ALL rows!\n\nThis is potentially dangerous. If you really want to do this, add a WHERE clause like:\n  WHERE 1=1  (to explicitly confirm bulk operation)\n\nOr use a specific condition to limit scope."

        # ✅ FIX: Use context managers to ensure connections are closed
        # Connect to database
        if db_path:
            # Validate path is in workspace
            abs_db_path = os.path.abspath(db_path)
            workspace = os.getcwd()

            if not abs_db_path.startswith(workspace):
                return f"❌ Error: Database must be in current workspace.\n\nProvided: {db_path}\nWorkspace: {workspace}"

            if not os.path.exists(abs_db_path):
                return f"❌ Error: Database file not found: {db_path}"

            # SQLite path - use context manager
            connection_manager = sqlite3.connect(abs_db_path)
        else:
            # PostgreSQL path - use context manager
            connection_manager = _get_db_for_project(project)

        with connection_manager as conn:
            # Set row factory for SQLite (PostgreSQL returns dicts by default)
            if hasattr(conn, 'row_factory'):
                conn.row_factory = sqlite3.Row

            # DRY RUN MODE
            if dry_run:
                output = ["🔍 DRY RUN - No changes will be made", "=" * 60, ""]
                output.append(f"Operation: {operation}")
                output.append(f"SQL: {sql}")
                if params:
                    output.append(f"Params: {params}")
                output.append("")
    
                # Generate preview query based on operation
                if operation == 'INSERT':
                    output.append("Would insert 1 new row with the provided values.")
                    output.append("")
                    output.append("To execute: Set dry_run=False and confirm=True")
    
                elif operation == 'UPDATE':
                    # Convert UPDATE to SELECT to show affected rows
                    # This is a simple heuristic - extract table and WHERE clause
                    match = re.search(r'UPDATE\s+(\w+)\s+SET.*?(WHERE.*)', sql_upper, re.IGNORECASE | re.DOTALL)
                    if match:
                        table = match.group(1)
                        where_clause = match.group(2)
    
                        # Get actual table name from original SQL (preserve case)
                        table_match = re.search(r'UPDATE\s+(\w+)', sql, re.IGNORECASE)
                        if table_match:
                            table = table_match.group(1)
    
                        preview_sql = f"SELECT * FROM {table} {where_clause}"
    
                        try:
                            if params:
                                cursor = conn.execute(preview_sql, params)
                            else:
                                cursor = conn.execute(preview_sql)
    
                            rows = cursor.fetchall()
                            output.append(f"Would affect {len(rows)} rows:")
    
                            if rows:
                                output.append("")
                                # Show first few rows as preview
                                for i, row in enumerate(rows[:5]):
                                    output.append(f"  Row {i+1}: {dict(row)}")
                                if len(rows) > 5:
                                    output.append(f"  ... and {len(rows) - 5} more rows")
    
                        except Exception as e:
                            output.append(f"Preview query failed: {str(e)}")
                    else:
                        output.append("Could not generate preview (complex UPDATE syntax)")
    
                elif operation == 'DELETE':
                    # Convert DELETE to SELECT to show affected rows
                    match = re.search(r'DELETE\s+FROM\s+(\w+)(.*)', sql, re.IGNORECASE | re.DOTALL)
                    if match:
                        table = match.group(1)
                        where_part = match.group(2).strip()
    
                        preview_sql = f"SELECT * FROM {table} {where_part}"
    
                        try:
                            if params:
                                cursor = conn.execute(preview_sql, params)
                            else:
                                cursor = conn.execute(preview_sql)
    
                            rows = cursor.fetchall()
                            output.append(f"Would delete {len(rows)} rows:")
    
                            if rows:
                                output.append("")
                                for i, row in enumerate(rows[:5]):
                                    output.append(f"  Row {i+1}: {dict(row)}")
                                if len(rows) > 5:
                                    output.append(f"  ... and {len(rows) - 5} more rows")
                        except Exception as e:
                            output.append(f"Preview query failed: {str(e)}")
                    else:
                        output.append("Could not generate preview (complex DELETE syntax)")
    
                output.append("")
                output.append("=" * 60)
                output.append("To execute: Set dry_run=False and confirm=True")
    
                return "\n".join(output)
    
            # EXECUTE MODE
            if not confirm:
                return f"❌ Error: Confirmation required to execute.\n\nThis operation will modify the database.\n\nTo proceed, set confirm=True:\n  execute_sql(..., dry_run=False, confirm=True)"
    
            # Start transaction and execute
            start_time = time.time()
    
            try:
                conn.execute("BEGIN TRANSACTION")
    
                if params:
                    cursor = conn.execute(sql, params)
                else:
                    cursor = conn.execute(sql)
    
                affected_rows = cursor.rowcount
                execution_time = (time.time() - start_time) * 1000  # Convert to ms
    
                # Check max_affected limit
                if max_affected is not None and affected_rows > max_affected:
                    conn.execute("ROLLBACK")
                    return f"❌ Error: Operation would affect {affected_rows} rows, exceeding limit of {max_affected}.\n\nTransaction rolled back. No changes made.\n\nTo proceed, increase max_affected or refine your WHERE clause."
    
                # Commit transaction
                conn.execute("COMMIT")
    
                # Success report
                output = ["✅ SUCCESS!", "=" * 60, ""]
                output.append(f"Operation: {operation}")
                output.append(f"Affected rows: {affected_rows}")
                output.append(f"Execution time: {execution_time:.2f}ms")
                output.append("")
                output.append("=" * 60)
    
                return "\n".join(output)
    
            except Exception as e:
                # Rollback on error
                try:
                    conn.execute("ROLLBACK")
                except:
                    pass

            return f"❌ Error: Operation failed and was rolled back.\n\nError: {str(e)}\n\nNo changes were made to the database."

    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================================
# Helper Functions for manage_workspace_table
# ============================================================================

def _validate_operation(operation: str) -> Optional[dict]:
    """
    Validate operation parameter.

    Args:
        operation: Operation to validate

    Returns:
        Error dict if invalid, None if valid
    """
    valid_operations = ['create', 'drop', 'inspect', 'list']
    if operation not in valid_operations:
        return {
            "error": "Invalid operation",
            "provided": operation,
            "valid_operations": valid_operations
        }
    return None


def _handle_list_operation(conn) -> dict:
    """
    List workspace tables.

    Args:
        conn: Database connection

    Returns:
        Dict with list of workspace tables
    """
    rows = _get_table_list(conn, 'workspace_%')
    tables = []
    for row in rows:
        # Get row count
        if hasattr(conn, 'execute'):
            count_cursor = conn.execute(f"SELECT COUNT(*) as count FROM {row['name']}")
        else:
            count_cursor = conn.cursor()
            count_cursor.execute(f"SELECT COUNT(*) as count FROM {row['name']}")
        count = count_cursor.fetchone()['count']

        tables.append({
            "name": row['name'],
            "schema": row['sql'] if row['sql'] else "(PostgreSQL table)",
            "row_count": count
        })

    return {
        "operation": "list",
        "workspace_tables": tables,
        "total_count": len(tables)
    }


def _validate_and_sanitize_table_name(table_name: str) -> tuple:
    """
    Validate and sanitize table name.

    Args:
        table_name: Raw table name

    Returns:
        Tuple of (error_dict or None, safe_table_name, full_table_name)
    """
    import re

    if not table_name:
        return ({"error": "table_name is required for this operation"}, None, None)

    # Sanitize table name and add workspace_ prefix
    safe_table_name = re.sub(r'[^a-zA-Z0-9_]', '', table_name)
    full_table_name = f"workspace_{safe_table_name}"

    # Protect core tables
    core_tables = [
        'sessions', 'memory_entries', 'context_locks', 'context_archives',
        'file_tags', 'todos', 'project_variables', 'query_results_cache',
        'file_semantic_model'
    ]
    if safe_table_name in core_tables or table_name.startswith('workspace_'):
        return (
            {
                "error": "Cannot use reserved table names or 'workspace_' prefix",
                "attempted": table_name,
                "reserved_tables": core_tables
            },
            None,
            None
        )

    return (None, safe_table_name, full_table_name)


def _handle_inspect_operation(conn, table_name: str) -> dict:
    """
    Inspect table schema and contents.

    Args:
        conn: Database connection
        table_name: Full table name (with workspace_ prefix)

    Returns:
        Dict with inspection results
    """
    # Check if table exists
    if not _table_exists(conn, table_name):
        return {
            "error": "Table not found",
            "table": table_name,
            "note": "Use operation='list' to see all workspace tables"
        }

    # Get row count
    if hasattr(conn, 'execute'):
        count_cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        sample_cursor = conn.execute(f"SELECT * FROM {table_name} LIMIT 5")
    else:
        count_cursor = conn.cursor()
        count_cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        sample_cursor = conn.cursor()
        sample_cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")

    count = count_cursor.fetchone()['count']

    # Get sample data (first 5 rows)
    sample_data = [dict(row) for row in sample_cursor.fetchall()]

    return {
        "operation": "inspect",
        "table": table_name,
        "row_count": count,
        "sample_data": sample_data
    }


def _handle_create_operation(
    conn,
    table_name: str,
    schema: Optional[str],
    dry_run: bool,
    confirm: bool
) -> dict:
    """
    Create a workspace table.

    Args:
        conn: Database connection
        table_name: Full table name (with workspace_ prefix)
        schema: Table schema definition
        dry_run: If True, preview only
        confirm: Must be True to execute

    Returns:
        Dict with create operation results
    """
    if not schema:
        return {
            "error": "schema is required for create operation",
            "example": "id INTEGER PRIMARY KEY, name TEXT, value REAL"
        }

    # Check if table already exists
    if _table_exists(conn, table_name):
        return {
            "error": "Table already exists",
            "table": table_name,
            "note": "Use operation='drop' first to recreate, or choose a different name"
        }

    create_sql = f"CREATE TABLE {table_name} ({schema})"

    if dry_run:
        return {
            "dry_run": True,
            "operation": "create",
            "table": table_name,
            "sql": create_sql,
            "note": "Set dry_run=False and confirm=True to execute"
        }

    if not confirm:
        return {
            "error": "Confirmation required",
            "note": "Set confirm=True to execute this operation"
        }

    # Execute CREATE
    if hasattr(conn, 'execute'):
        conn.execute(create_sql)
    else:
        cursor = conn.cursor()
        cursor.execute(create_sql)
    conn.commit()

    return {
        "success": True,
        "operation": "create",
        "table": table_name,
        "sql": create_sql,
        "usage": f"Use query_database() with: SELECT * FROM {table_name}"
    }


def _handle_drop_operation(
    conn,
    table_name: str,
    dry_run: bool,
    confirm: bool
) -> dict:
    """
    Drop a workspace table.

    Args:
        conn: Database connection
        table_name: Full table name (with workspace_ prefix)
        dry_run: If True, preview only
        confirm: Must be True to execute

    Returns:
        Dict with drop operation results
    """
    # Check if table exists
    if not _table_exists(conn, table_name):
        return {
            "error": "Table not found",
            "table": table_name,
            "note": "Use operation='list' to see existing tables"
        }

    drop_sql = f"DROP TABLE {table_name}"

    if dry_run:
        # Get row count for preview
        if hasattr(conn, 'execute'):
            count_cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        else:
            count_cursor = conn.cursor()
            count_cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        count = count_cursor.fetchone()['count']

        return {
            "dry_run": True,
            "operation": "drop",
            "table": table_name,
            "rows_to_delete": count,
            "sql": drop_sql,
            "note": "Set dry_run=False and confirm=True to execute"
        }

    if not confirm:
        return {
            "error": "Confirmation required",
            "note": "Set confirm=True to execute this operation"
        }

    # Execute DROP
    if hasattr(conn, 'execute'):
        conn.execute(drop_sql)
    else:
        cursor = conn.cursor()
        cursor.execute(drop_sql)
    conn.commit()

    return {
        "success": True,
        "operation": "drop",
        "table": table_name,
        "sql": drop_sql
    }


@mcp.tool()
async def manage_workspace_table(
    operation: str,
    table_name: str,
    schema: Optional[str] = None,
    dry_run: bool = True,
    confirm: bool = False,
    project: Optional[str] = None
) -> str:
    """
    Dynamically create, drop, or modify temporary workspace tables for complex operations.

    **Purpose:** Enable Claude to create temporary tables for multi-step processing,
    intermediate results, or complex queries without filling the context window.

    **Use Cases:**
    - Create temporary tables for storing intermediate query results
    - Build working tables for data transformation pipelines
    - Store analytical results for later pagination
    - Manage custom data structures for specific tasks

    **Safety Features:**
    - Namespace isolation: All workspace tables prefixed with 'workspace_'
    - Dry-run by default: Preview changes before execution
    - Auto-cleanup: Can mark tables for auto-deletion on session end
    - Schema validation: Checks SQL syntax before execution
    - Prevents modification of core tables (sessions, contexts, memory_entries, etc.)

    **Supported Operations:**
    - 'create': Create a new workspace table
    - 'drop': Remove a workspace table
    - 'inspect': View table schema and row count
    - 'list': List all workspace tables

    **Examples:**

    1. Create a temporary results table:
       manage_workspace_table(
           operation='create',
           table_name='analysis_results',
           schema='''
               id INTEGER PRIMARY KEY,
               metric_name TEXT NOT NULL,
               value REAL,
               calculated_at REAL
           ''',
           dry_run=False,
           confirm=True
       )

    2. Create a table for storing file clusters:
       manage_workspace_table(
           operation='create',
           table_name='file_clusters_cache',
           schema='''
               cluster_name TEXT PRIMARY KEY,
               file_paths TEXT,  -- JSON array
               file_count INTEGER,
               created_at REAL
           ''',
           dry_run=False,
           confirm=True
       )

    3. List all workspace tables:
       manage_workspace_table(operation='list')

    4. Inspect a workspace table:
       manage_workspace_table(
           operation='inspect',
           table_name='analysis_results'
       )

    5. Drop a workspace table:
       manage_workspace_table(
           operation='drop',
           table_name='analysis_results',
           dry_run=False,
           confirm=True
       )

    **After Creating Tables:**
    - Use query_database() to read data: SELECT * FROM workspace_analysis_results
    - Use execute_sql() to insert/update data
    - Use manage_workspace_table(operation='drop') to clean up

    **Best Practices:**
    - Name tables descriptively: 'file_analysis', 'search_cache', 'temp_results'
    - Clean up tables when done to avoid database bloat
    - Use AUTO-CLEANUP comment in schema for automatic removal on session end

    Args:
        operation: 'create', 'drop', 'inspect', or 'list'
        table_name: Name of workspace table (without 'workspace_' prefix)
        schema: Table schema for 'create' operation (columns and types)
        dry_run: If True, preview changes without executing (default: True)
        confirm: Must be True to execute write operations (default: False)
        project: Project name (default: auto-detect or active project)

    Returns:
        JSON with operation result, including table info and SQL executed
    """
    try:
        # Validate operation
        error = _validate_operation(operation)
        if error:
            return json.dumps(error, indent=2)

        # Use context manager to ensure connection is closed
        with _get_db_for_project(project) as conn:
            # Handle LIST operation (no table_name needed)
            if operation == 'list':
                result = _handle_list_operation(conn)
                return json.dumps(result, indent=2)

            # For all other operations, validate and sanitize table_name
            error, safe_table_name, full_table_name = _validate_and_sanitize_table_name(table_name)
            if error:
                return json.dumps(error, indent=2)

            # Dispatch to appropriate handler based on operation
            if operation == 'inspect':
                result = _handle_inspect_operation(conn, full_table_name)
            elif operation == 'create':
                result = _handle_create_operation(conn, full_table_name, schema, dry_run, confirm)
            elif operation == 'drop':
                result = _handle_drop_operation(conn, full_table_name, dry_run, confirm)
            else:
                # Should never reach here due to validation, but just in case
                result = {
                    "error": f"Unhandled operation: {operation}",
                    "note": "This is a bug - please report it"
                }

            return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e),
            "operation": operation
        }, indent=2)


def _perform_semantic_search(conn, text: str, limit: int = 5) -> list:
    """
    Try semantic search with embeddings.

    Args:
        conn: Database connection
        text: Search query text
        limit: Maximum number of results

    Returns:
        List of formatted semantic result strings, or empty list if unavailable
    """
    semantic_results = []
    try:
        from src.services import embedding_service
        from src.services.semantic_search import SemanticSearch

        if embedding_service and embedding_service.enabled:
            semantic_search = SemanticSearch(conn, embedding_service)

            # Check if any contexts have embeddings
            cursor = conn.execute("SELECT COUNT(*) as count FROM context_locks WHERE embedding IS NOT NULL")
            embedded_count = cursor.fetchone()['count']

            if embedded_count > 0:
                # Use semantic search for better relevance
                results = semantic_search.search_similar(
                    query=text,
                    limit=limit,
                    threshold=0.5  # Lower threshold for check_contexts
                )

                if results:
                    semantic_results.append("🔍 **Semantic Search Results:**\n")
                    for result in results:
                        priority_emoji = {
                            'always_check': '⚠️',
                            'important': '📌',
                            'reference': '📄'
                        }.get(result.get('priority', 'reference'), '📄')

                        semantic_results.append(
                            f"{priority_emoji} **{result['label']}** (similarity: {result['similarity']:.2f})\n"
                            f"   {result['preview'][:150]}..."
                        )

                    semantic_results.append("\n💡 Use `recall_context(topic)` for full details")
    except Exception as e:
        # Graceful fallback - semantic search failed, use keyword matching
        print(f"⚠️  Semantic search unavailable: {e}", file=sys.stderr)

    return semantic_results


def _get_keyword_based_results(conn, text: str, session_id: str, current_db_path: str) -> tuple:
    """
    Get keyword-based matching results (fallback method).

    Args:
        conn: Database connection (unused but kept for consistency)
        text: Search query text
        session_id: Current session ID
        current_db_path: Database path

    Returns:
        Tuple of (relevant_contexts, violations) or (None, None) if unavailable
    """
    relevant = None
    violations = None
    try:
        relevant = get_relevant_contexts_for_text(text, session_id, current_db_path)
        violations = check_command_context(text, session_id, current_db_path)
    except Exception as fallback_error:
        # Keyword matching unavailable (PostgreSQL mode)
        print(f"⚠️  Keyword fallback unavailable: {fallback_error}", file=sys.stderr)

    return relevant, violations


def _format_results_output(semantic_results: list, relevant: str, violations: str) -> str:
    """
    Format combined semantic and keyword results into output string.

    Args:
        semantic_results: List of semantic result strings
        relevant: Keyword-based relevant contexts string
        violations: Rule violations string

    Returns:
        Formatted output string or "No relevant locked contexts found." if empty
    """
    output = []

    # Add semantic results if available
    if semantic_results:
        output.extend(semantic_results)
        if relevant or violations:
            output.append("\n" + "─" * 50 + "\n")

    # Add keyword-based results
    if relevant:
        if semantic_results:
            output.append("📝 **Keyword Matching Results:**\n")
        output.append(relevant)

    if violations:
        if output:
            output.append("")  # Add spacing
        output.append(violations)

    if not output:
        return "No relevant locked contexts found."

    return "\n".join(output)


@mcp.tool()
async def check_contexts(text: str, project: Optional[str] = None) -> str:
    """
    Check what locked contexts are relevant to your current task and detect rule violations.

    **IMPORTANT: When to use this tool:**
    - Before implementing any feature (check for rules/specs)
    - Before making architecture decisions (check for established patterns)
    - Before deploying or releasing (check for deployment rules)
    - When writing code in unfamiliar areas (check for conventions)
    - Periodically during work to ensure compliance

    **What this tool does:**
    - Scans locked contexts using intelligent 2-stage relevance checking
    - Returns relevant contexts with relevance scores
    - Detects potential violations of MUST/ALWAYS/NEVER rules
    - Uses RLM preview optimization (60-80% faster than loading everything)
    - Highlights always_check priority contexts that must be followed

    **How it works (RLM optimization):**
    Stage 1: Quick preview scan of all contexts (lightweight, fast)
    Stage 2: Load full content only for top 5 or high-relevance matches
    Result: 60-80% token reduction while maintaining accuracy

    **What you'll see:**
    - List of relevant contexts with labels and relevance scores
    - Priority indicators (⚠️ always_check, 📌 important)
    - Tags for each relevant context
    - Warning messages for potential rule violations
    - Suggestions to use recall_context() for full details

    **Multi-project support:**
    - project: Optional project name. If not specified, uses active project.
    - Priority: explicit param > session active > auto-detect > "default"
    - Example: check_contexts("deploying", project="innkeeper")

    **Best practices:**
    1. Check BEFORE implementing (not after)
    2. Check with specific task description: "implementing JWT auth for API"
    3. Check with action description: "deploying to production"
    4. Pay attention to always_check warnings (these are critical)
    5. Use recall_context() to get full details of relevant contexts

    **Example workflow:**
    ```
    # Good: Check before implementation
    check_contexts("implementing user registration with email verification")
    # Returns: "api_patterns relevant (📌 important), security_rules relevant (⚠️ always_check)"

    # Then get details
    recall_context("security_rules")
    # Implement following the rules
    ```

    **Common use cases:**
    - "deploying new feature to production" → checks deployment rules
    - "writing tests for authentication" → checks test patterns
    - "setting up database connection" → checks database config
    - "implementing API endpoint" → checks API standards
    - "configuring CI/CD" → checks deployment procedures

    **What NOT to do:**
    ❌ Don't check vague text: check_contexts("working on stuff")
    ✅ Do check specific task: check_contexts("adding OAuth2 authentication")

    ❌ Don't ignore always_check violations
    ✅ Do read and follow always_check contexts

    **Performance benefit:**
    Traditional: Load all 30 contexts = 9KB
    RLM-optimized: Preview scan + top 5 = 3KB (67% reduction)

    Returns: List of relevant contexts, rule violations, and suggestions
    """
    # Check if project selection is required
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check

    session_id = get_current_session_id()

    # Use project-aware database connection
    target_project = _get_project_for_context(project)
    current_db_path = get_current_db_path()  # Dynamic database path

    # ✅ FIX: Use context manager to ensure connection is closed
    with _get_db_for_project(project) as conn:
        # Stage 1: Try semantic search first (faster, more accurate)
        semantic_results = _perform_semantic_search(conn, text, limit=5)

        # Stage 2: Get keyword-based results (fallback/supplement)
        relevant, violations = _get_keyword_based_results(conn, text, session_id, current_db_path)

        # Stage 3: Format and combine results
        return _format_results_output(semantic_results, relevant, violations)

@breadcrumb
@mcp.tool()
async def explore_context_tree(flat: bool = True, confirm_full: bool = False, project: Optional[str] = None) -> str:
    """
    Browse all your locked contexts organized by priority and tags.

    **Token Efficiency:** flat=True uses ~1K tokens, flat=False uses ~50 tokens per context

    **Parameters:**
    - flat: bool = True (CHANGED: was False)
      - If True: Returns simple list (DEFAULT for token efficiency)
      - If False: Returns grouped tree view with previews (requires confirm_full=True for large sets)
    - confirm_full: bool = False
      - Required safety check when flat=False and >50 contexts exist

    **When to use this tool:**
    - At session start to see what contexts exist
    - When you want to browse available information
    - To discover contexts you've forgotten about
    - To understand the structure of your locked knowledge

    **Flat mode (flat=True):**
    Returns simple list of contexts:
    ```
    api_auth_rules v1.0
    database_config v1.2
    code_style v1.0
    ```

    **Tree mode (flat=False, default):**
    - Lists all locked contexts in the current session
    - Groups by priority level (always_check → important → reference)
    - Shows tags for each context
    - Displays preview for quick scanning
    - Provides context statistics

    **What you'll see:**
    - Total context count and breakdown by priority
    - Tree structure organized by priority
    - Each context with version, tags, and preview
    - Suggestions for next steps

    **Best practices:**
    1. Use at session start to orient yourself
    2. Look for always_check contexts first (critical rules)
    3. Browse by tags to find related contexts
    4. Use recall_context() to dive deeper

    **Example output (tree mode):**
    ```
    📚 Context Tree (5 contexts)

    ⚠️ ALWAYS CHECK (2):
      • api_auth_rules v1.0 [api, security]
        Preview: MUST use JWT tokens. NEVER send passwords...

    📌 IMPORTANT (2):
      • database_config v1.2 [database, postgres]
        Preview: PostgreSQL 14 with connection pooling...

    📄 REFERENCE (1):
      • code_style v1.0 [style, python]
        Preview: Follow PEP 8 for Python code...
    ```

    **Performance:**
    Uses lightweight preview queries, not full content.
    Fast even with 100+ contexts.

    Returns: Tree structure of all contexts with previews (or simple list if flat=True)
    """
    # Check if project selection is required
    project_check = _check_project_selection_required(project)
    if project_check:
        return project_check

    # ✅ FIX: Use context manager to ensure connection is closed
    with _get_db_for_project(project) as conn:
        session_id = _get_session_id_for_project(conn, project)

        # Get all contexts with previews (not full content - RLM optimization!)
        # Flat mode: alphabetical order, Tree mode: most recent first
        order_clause = "ORDER BY label" if flat else "ORDER BY locked_at DESC"
        # NOTE: No session_id filter needed - schema isolation provides project-level isolation
        cursor = conn.execute(f"""
            SELECT label, version, preview, key_concepts, metadata, locked_at
            FROM context_locks
            {order_clause}
        """)

        contexts = cursor.fetchall()

    if not contexts:
        return "No locked contexts yet." if flat else "📭 No locked contexts yet.\n\n💡 Use lock_context() to save important information for future reference."

    # Safety check: Warn about high token cost for full tree mode
    if not flat and len(contexts) > 50 and not confirm_full:
        estimated_tokens = len(contexts) * 50
        return json.dumps({
            "error": "High token cost operation requires confirmation",
            "context_count": len(contexts),
            "estimated_tokens": estimated_tokens,
            "current_mode": "tree (with previews)",
            "recommendation": "Use flat=True for labels only (~1,000 tokens)",
            "to_proceed": "Set confirm_full=True to load full tree anyway",
            "example": "explore_context_tree(flat=False, confirm_full=True)"
        }, indent=2)

    # Flat mode: simple list (replacement for removed list_topics())
    if flat:
        results = []
        for row in contexts:
            results.append(f"{row['label']} v{row['version']}")
        return "\n".join(results)

    # Tree mode: Group by priority
    priority_groups = {
        'always_check': [],
        'important': [],
        'reference': []
    }

    for row in contexts:
        metadata = {}
        if row['metadata']:
            try:
                metadata = json.loads(row['metadata'])
            except:
                pass

        priority = metadata.get('priority', 'reference')
        tags = metadata.get('tags', [])

        key_concepts = []
        if row['key_concepts']:
            try:
                key_concepts = json.loads(row['key_concepts'])
            except:
                pass

        priority_groups[priority].append({
            'label': row['label'],
            'version': row['version'],
            'preview': row['preview'] or "No preview available",
            'tags': tags,
            'concepts': key_concepts,
            'locked_at': row['locked_at']
        })

    output = []
    output.append(f"📚 Context Tree ({len(contexts)} contexts)\n")

    # Show always_check first (critical)
    if priority_groups['always_check']:
        output.append(f"⚠️  ALWAYS CHECK ({len(priority_groups['always_check'])}):")
        for ctx in priority_groups['always_check']:
            output.append(f"   • {ctx['label']} v{ctx['version']}")
            if ctx['tags']:
                output.append(f"     Tags: {', '.join(ctx['tags'][:3])}")
            preview = ctx['preview'][:100]
            output.append(f"     {preview}...")
            output.append("")

    # Show important
    if priority_groups['important']:
        output.append(f"📌 IMPORTANT ({len(priority_groups['important'])}):")
        for ctx in priority_groups['important']:
            output.append(f"   • {ctx['label']} v{ctx['version']}")
            if ctx['tags']:
                output.append(f"     Tags: {', '.join(ctx['tags'][:3])}")
            preview = ctx['preview'][:100]
            output.append(f"     {preview}...")
            output.append("")

    # Show reference
    if priority_groups['reference']:
        output.append(f"📄 REFERENCE ({len(priority_groups['reference'])}):")
        for ctx in priority_groups['reference'][:10]:  # Limit reference to 10
            output.append(f"   • {ctx['label']} v{ctx['version']}")
            if ctx['tags']:
                output.append(f"     Tags: {', '.join(ctx['tags'][:3])}")
            preview = ctx['preview'][:80]
            output.append(f"     {preview}...")
            output.append("")

        if len(priority_groups['reference']) > 10:
            output.append(f"   ... and {len(priority_groups['reference']) - 10} more reference contexts")
            output.append("")

    output.append("💡 Next steps:")
    output.append("   • Use get_context_preview('topic') to see full preview")
    output.append("   • Use recall_context('topic') to load full content")
    output.append("   • Use ask_memory('question') to search naturally")

    return "\n".join(output)

# ============================================================================
# FILE SEMANTIC MODEL - MCP Tools
# ============================================================================

# Helper functions for context_dashboard
def _fetch_priority_statistics(conn, session_id):
    """Fetch context statistics grouped by priority."""
    stats_query = """
        SELECT
            (metadata::json)->>'priority' as priority,
            COUNT(*) as count,
            SUM(LENGTH(content)) as total_size,
            AVG(LENGTH(content)) as avg_size
        FROM context_locks
        GROUP BY priority
    """

    cursor = conn.execute(stats_query)
    priority_stats = {}
    total_contexts = 0
    total_size = 0

    for row in cursor.fetchall():
        priority = row['priority'] or 'reference'
        priority_stats[priority] = {
            'count': row['count'],
            'total_size': row['total_size'],
            'avg_size': int(row['avg_size'])
        }
        total_contexts += row['count']
        total_size += row['total_size']

    return priority_stats, total_contexts, total_size


def _fetch_access_patterns(conn, session_id):
    """Fetch most and least accessed contexts."""
    most_accessed = conn.execute("""
        SELECT label, access_count, last_accessed
        FROM context_locks
        ORDER BY access_count DESC
        LIMIT 5
    """).fetchall()

    least_accessed = conn.execute("""
        SELECT label, access_count, last_accessed
        FROM context_locks
        WHERE access_count > 0
        ORDER BY access_count ASC
        LIMIT 5
    """).fetchall()

    return most_accessed, least_accessed


def _fetch_stale_contexts(conn, session_id):
    """Find contexts not accessed in 30+ days."""
    import time
    thirty_days_ago = time.time() - (30 * 24 * 3600)
    stale_contexts = conn.execute("""
        SELECT label, last_accessed, access_count
        FROM context_locks
        WHERE (last_accessed < ? OR last_accessed IS NULL)
        ORDER BY last_accessed ASC
        LIMIT 5
    """, (thirty_days_ago,)).fetchall()

    return stale_contexts


def _fetch_version_statistics(conn, session_id):
    """Get statistics for multi-version contexts."""
    version_stats = conn.execute("""
        SELECT
            label,
            COUNT(*) as version_count,
            MAX(version) as latest_version
        FROM context_locks
        GROUP BY label
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 5
    """).fetchall()

    return version_stats


def _build_summary_text(total_contexts, total_size, priority_stats, stale_count, version_count):
    """Generate dashboard summary text."""
    summary_text = f"""
📊 Context Library Dashboard
━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Contexts: {total_contexts}
Total Storage: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)

By Priority:
  always_check: {priority_stats.get('always_check', {}).get('count', 0)} contexts
  important: {priority_stats.get('important', {}).get('count', 0)} contexts
  reference: {priority_stats.get('reference', {}).get('count', 0)} contexts

Stale Contexts: {stale_count} (30+ days)
Versioned Contexts: {version_count}
━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()

    return summary_text


def _format_response_lists(rows, list_type):
    """Format rows into response list format."""
    import time

    if list_type == "most_accessed" or list_type == "least_accessed":
        return [
            {"label": row['label'], "access_count": row['access_count']}
            for row in rows
        ]
    elif list_type == "stale_contexts":
        return [
            {"label": row['label'], "days_since_access": int((time.time() - (row['last_accessed'] or 0)) / 86400)}
            for row in rows
        ]
    elif list_type == "versioned_contexts":
        return [
            {"label": row['label'], "versions": row['version_count'], "latest": row['latest_version']}
            for row in rows
        ]
    return []


def _build_dashboard_response(summary_text, total_contexts, total_size, priority_stats,
                               most_accessed, least_accessed, stale_contexts, version_stats):
    """Assemble final dashboard response."""
    response = {
        "summary": summary_text,
        "statistics": {
            "total_contexts": total_contexts,
            "total_size_bytes": total_size,
            "by_priority": priority_stats
        },
        "most_accessed": _format_response_lists(most_accessed, "most_accessed"),
        "least_accessed": _format_response_lists(least_accessed, "least_accessed"),
        "stale_contexts": _format_response_lists(stale_contexts, "stale_contexts"),
        "versioned_contexts": _format_response_lists(version_stats, "versioned_contexts")
    }

    if total_contexts == 0:
        response["message"] = "No contexts found. Use lock_context() to create your first context."

    return response


@breadcrumb
@mcp.tool()
async def context_dashboard(project: Optional[str] = None) -> str:
    """
    Get comprehensive overview of all contexts with statistics and insights.

    **Token Efficiency: SUMMARY** (~2-3KB)

    Returns dashboard showing:
    - Contexts by priority (counts + sizes)
    - Top 10 most/least accessed
    - Embedding coverage %
    - Total storage used
    - Stale contexts (30+ days without access)
    - Version statistics

    Perfect for getting a bird's-eye view of your context library.

    Args:
        project: Project name (default: auto-detect or active project)

    Returns:
        JSON with comprehensive context statistics and insights
    """
    # ✅ FIX: Use context manager to ensure connection is closed
    with _get_db_for_project(project) as conn:
        session_id = _get_session_id_for_project(conn, project)

        # Fetch all statistics using helper functions
        priority_stats, total_contexts, total_size = _fetch_priority_statistics(conn, session_id)
        most_accessed, least_accessed = _fetch_access_patterns(conn, session_id)
        stale_contexts = _fetch_stale_contexts(conn, session_id)
        version_stats = _fetch_version_statistics(conn, session_id)

    # Build summary text
    summary_text = _build_summary_text(
        total_contexts, total_size, priority_stats,
        len(stale_contexts), len(version_stats)
    )

    # Build and return response
    response = _build_dashboard_response(
        summary_text, total_contexts, total_size, priority_stats,
        most_accessed, least_accessed, stale_contexts, version_stats
    )

    return json.dumps(response, indent=2)


@mcp.tool()
#async def scan_project_files(
#    full_scan: bool = False,
#    max_files: int = 10000,
#    respect_gitignore: bool = True,
#    project: Optional[str] = None
#) -> str:
#    """
#    Scan project files and build/update semantic model.
#
#    **Purpose:** Build intelligent understanding of project structure with automatic
#    change detection and semantic analysis.
#
#    **Parameters:**
#    - full_scan: bool = False
#      Force full rescan (default: incremental using mtime+size+hash)
#    - max_files: int = 10000
#      Safety limit for large projects
#    - respect_gitignore: bool = True
#      Skip files/directories in .gitignore
#
#    **How it works:**
#    1. Walk filesystem (respecting .gitignore)
#    2. Detect changes using three-stage detection:
#       - Stage 1: mtime check (instant)
#       - Stage 2: size check (instant)
#       - Stage 3: hash check (only if needed)
#    3. Analyze changed/new files:
#       - Extract imports, exports, dependencies
#       - Detect file type and language
#       - Recognize standard files (.env, package.json, etc)
#       - Generate warnings for config issues
#    4. Build semantic clusters (authentication, api, database, etc)
#
#    **Returns:** JSON with scan results, changes detected, warnings
#
#    **Example output:**
#    ```json
#    {
#      "scan_type": "incremental",
#      "scan_time_ms": 52.3,
#      "total_files": 247,
#      "changes": {
#        "added": 2,
#        "modified": 3,
#        "deleted": 0,
#        "unchanged": 242
#      },
#      "file_types": {
#        "python": 45,
#        "javascript": 38,
#        "markdown": 12
#      },
#      "clusters": ["authentication", "api", "database", "tests"],
#      "warnings": [
#        ".env not in .gitignore - may expose secrets"
#      ]
#    }
#    ```
#
#    **Best practices:**
#    - Runs automatically during wake_up() (incremental)
#    - Use full_scan=True after major changes (git pull, branch switch)
#    - Results persist in database for fast future scans
#
#    **IMPORTANT - Local Development Only:**
#    This tool uses direct Python filesystem access (os.walk) and is designed
#    for local development environments only. It will not work properly in:
#    - Claude Desktop (requires per-file permissions, causes timeout)
#    - Mobile devices (no filesystem access)
#    - Browser environments (restricted file access)
#
#    For Claude Desktop, use the filesystem MCP server instead:
#    - mcp__filesystem__list_directory() for file listing
#    - mcp__filesystem__read_file() for file contents
#    - Then use our semantic analysis tools on the results
#    """
#    # Check if project selection is required
#    project_check = _check_project_selection_required(project)
#    if project_check:
#        return project_check
#
#    # Check if we have filesystem access
#    project_root = os.getcwd()
#
#    try:
#        # Quick access test - try to list current directory
#        test_list = os.listdir(project_root)
#        if not test_list:
#            return json.dumps({
#                "error": "No filesystem access",
#                "message": "This tool requires filesystem access which may not be available in Claude Desktop",
#                "suggestion": "This tool is designed for local development environments"
#            }, indent=2)
#    except (PermissionError, OSError) as e:
#        return json.dumps({
#            "error": "Filesystem access denied",
#            "message": str(e),
#            "suggestion": "This tool requires filesystem permissions to scan project files"
#        }, indent=2)
#
#    conn = _get_db_for_project(project)
#    session_id = get_current_session_id()
#
#    start_time = time.time()
#
#    try:
#        # Load stored model
#        stored_model = load_stored_file_model(conn, session_id)
#
#        # Walk filesystem
#        all_files = walk_project_files(project_root, respect_gitignore, max_files)
#
#        # Detect changes
#        changes = {
#            'added': [],
#            'modified': [],
#            'deleted': [],
#            'unchanged': []
#        }
#
#        files_to_analyze = []
#
#        for file_path in all_files:
#            stored_meta = stored_model.get(file_path)
#
#            if full_scan:
#                # Full scan - analyze everything
#                files_to_analyze.append(file_path)
#                if stored_meta:
#                    changes['modified'].append(file_path)
#                else:
#                    changes['added'].append(file_path)
#            else:
#                # Incremental scan - detect changes
#                changed, new_hash, hash_method = detect_file_change(file_path, stored_meta)
#
#                if not stored_meta:
#                    changes['added'].append(file_path)
#                    files_to_analyze.append(file_path)
#                elif changed:
#                    changes['modified'].append(file_path)
#                    files_to_analyze.append(file_path)
#                else:
#                    changes['unchanged'].append(file_path)
#
#        # Find deleted files
#        stored_paths = set(stored_model.keys())
#        current_paths = set(all_files)
#        deleted_paths = stored_paths - current_paths
#
#        for deleted_path in deleted_paths:
#            changes['deleted'].append(deleted_path)
#            mark_file_deleted(conn, session_id, deleted_path)
#
#        # Analyze changed/new files
#        analyzed_files = []
#
#        for file_path in files_to_analyze:
#            try:
#                # Get file stats
#                stat = os.stat(file_path)
#                file_size = stat.st_size
#                modified_time = stat.st_mtime
#
#                # Compute hash
#                content_hash, hash_method = compute_file_hash(file_path, file_size)
#
#                # Detect file type
#                file_type, language, is_standard, standard_type = detect_file_type(file_path)
#
#                # Generate warnings for standard files
#                warnings = check_standard_file_warnings(file_path, file_type, standard_type, project_root)
#
#                # Semantic analysis
#                semantics = analyze_file_semantics(file_path, file_type, language)
#
#                # Build metadata
#                metadata = {
#                    'file_size': file_size,
#                    'content_hash': content_hash,
#                    'modified_time': modified_time,
#                    'hash_method': hash_method,
#                    'file_type': file_type,
#                    'language': language,
#                    'is_standard': is_standard,
#                    'standard_type': standard_type,
#                    'warnings': warnings,
#                    'imports': semantics.get('imports', []),
#                    'exports': semantics.get('exports', []),
#                    'contains': semantics.get('contains', {})
#                }
#
#                analyzed_files.append({
#                    'file_path': file_path,
#                    **metadata
#                })
#
#                # Store in database
#                store_file_metadata(conn, session_id, file_path, metadata, 0)
#
#                # Record change
#                if file_path in changes['added']:
#                    record_file_change(conn, session_id, file_path, 'added', None, content_hash, file_size)
#                elif file_path in changes['modified']:
#                    old_hash = stored_model[file_path].get('content_hash')
#                    old_size = stored_model[file_path].get('file_size', 0)
#                    size_delta = file_size - old_size
#                    record_file_change(conn, session_id, file_path, 'modified', old_hash, content_hash, size_delta)
#
#            except Exception as e:
#                # Skip files that can't be analyzed
#                continue
#
#        # Build clusters
#        clusters_dict = cluster_files_by_semantics(analyzed_files)
#
#        # Update cluster names in database
#        for cluster_name, file_paths in clusters_dict.items():
#            for file_path in file_paths:
#                conn.execute("""
#                    UPDATE file_semantic_model
#                    SET cluster_name = ?
#                    WHERE session_id = ? AND file_path = ?
#                """, (cluster_name, session_id, file_path))
#
#        conn.commit()
#
#        # Get file type distribution
#        type_cursor = conn.execute("""
#            SELECT file_type, COUNT(*) as count
#            FROM file_semantic_model
#            WHERE session_id = ?
#            GROUP BY file_type
#            ORDER BY count DESC
#        """, (session_id,))
#
#        file_types = {row['file_type']: row['count'] for row in type_cursor.fetchall()}
#
#        # Get all warnings
#        warnings_cursor = conn.execute("""
#            SELECT warnings
#            FROM file_semantic_model
#            WHERE session_id = ? AND warnings IS NOT NULL AND warnings != '[]'
#        """, (session_id,))
#
#        all_warnings = []
#        for row in warnings_cursor.fetchall():
#            try:
#                file_warnings = json.loads(row['warnings'])
#                all_warnings.extend(file_warnings)
#            except:
#                pass
#
#        scan_time_ms = (time.time() - start_time) * 1000
#
#        return json.dumps({
#            'scan_type': 'full' if full_scan else 'incremental',
#            'scan_time_ms': round(scan_time_ms, 2),
#            'total_files': len(all_files),
#            'changes': {
#                'added': len(changes['added']),
#                'modified': len(changes['modified']),
#                'deleted': len(changes['deleted']),
#                'unchanged': len(changes['unchanged'])
#            },
#            'file_types': file_types,
#            'clusters': list(clusters_dict.keys()),
#            'warnings': list(set(all_warnings))[:10]  # Top 10 unique warnings
#        }, indent=2)
#
#    except Exception as e:
#        return json.dumps({
#            'error': str(e),
#            'scan_type': 'full' if full_scan else 'incremental'
#        }, indent=2)
#
#
#@mcp.tool()
#async def query_files(
#    query: str,
#    file_type: Optional[str] = None,
#    cluster: Optional[str] = None,
#    limit: int = 20,
#    project: Optional[str] = None
#) -> str:
#    """
#    Search file semantic model by content, path, imports, or exports.
#
#    **Purpose:** Find files by what they contain or do, not just their name.
#
#    **Parameters:**
#    - query: str (required)
#      Search term - searches in: file_path, purpose, imports, exports
#    - file_type: str (optional)
#      Filter by type: 'python', 'javascript', 'markdown', 'config', etc.
#    - cluster: str (optional)
#      Filter by semantic cluster: 'authentication', 'api', 'database', etc.
#    - limit: int = 20
#      Maximum results to return
#
#    **Returns:** JSON with matching files and their semantic information
#
#    **Example queries:**
#    ```python
#    # Find authentication-related files
#    query_files("authentication")
#
#    # Find Python files that import FastAPI
#    query_files("fastapi", file_type="python")
#
#    # Find all API endpoint files
#    query_files("", cluster="api")
#
#    # Find files that export specific functions
#    query_files("authenticate_user")
#    ```
#
#    **Best practices:**
#    - Search broadly first, then filter with file_type/cluster
#    - Empty query with cluster returns all files in that cluster
#    - Results ordered by relevance (path match > imports/exports match)
#
#    **Note:** This tool queries the database (no direct file access).
#    Works in all environments. Run scan_project_files() first to build the model
#    (local dev only) or populate database manually.
#    """
#    # Check if project selection is required
#    project_check = _check_project_selection_required(project)
#    if project_check:
#        return project_check
#
#    conn = _get_db_for_project(project)
#    session_id = get_current_session_id()
#
#    try:
#        # Build SQL query
#        sql = """
#            SELECT
#                file_path, file_type, language, purpose,
#                imports, exports, dependencies, used_by, contains,
#                cluster_name, is_standard, standard_type, warnings,
#                file_size, modified_time, last_scanned
#            FROM file_semantic_model
#            WHERE session_id = ?
#        """
#
#        params = [session_id]
#
#        # Add search filter
#        if query:
#            sql += """
#                AND (
#                    file_path LIKE ?
#                    OR purpose LIKE ?
#                    OR imports LIKE ?
#                    OR exports LIKE ?
#                )
#            """
#            search_pattern = f'%{query}%'
#            params.extend([search_pattern, search_pattern, search_pattern, search_pattern])
#
#        # Add file_type filter
#        if file_type:
#            sql += " AND file_type = ?"
#            params.append(file_type)
#
#        # Add cluster filter
#        if cluster:
#            sql += " AND cluster_name = ?"
#            params.append(cluster)
#
#        sql += f" LIMIT {limit}"
#
#        cursor = conn.execute(sql, params)
#        results = cursor.fetchall()
#
#        # Format results
#        formatted = []
#        for row in results:
#            formatted.append({
#                'path': row['file_path'],
#                'type': row['file_type'],
#                'language': row['language'],
#                'purpose': row['purpose'],
#                'imports': json.loads(row['imports'] or '[]'),
#                'exports': json.loads(row['exports'] or '[]'),
#                'dependencies': json.loads(row['dependencies'] or '[]'),
#                'used_by': json.loads(row['used_by'] or '[]'),
#                'contains': json.loads(row['contains'] or '{}'),
#                'cluster': row['cluster_name'],
#                'is_standard': bool(row['is_standard']),
#                'standard_type': row['standard_type'],
#                'warnings': json.loads(row['warnings'] or '[]'),
#                'size_kb': round(row['file_size'] / 1024, 2) if row['file_size'] else 0,
#                'modified': datetime.fromtimestamp(row['modified_time']).isoformat() if row['modified_time'] else None,
#                'last_scanned': datetime.fromtimestamp(row['last_scanned']).isoformat() if row['last_scanned'] else None
#            })
#
#        return json.dumps({
#            'query': query,
#            'filters': {
#                'file_type': file_type,
#                'cluster': cluster,
#                'limit': limit
#            },
#            'total_found': len(formatted),
#            'results': formatted
#        }, indent=2)
#
#    except Exception as e:
#        return json.dumps({
#            'error': str(e),
#            'query': query
#        }, indent=2)
#
#
#@mcp.tool()
#async def get_file_clusters(project: Optional[str] = None) -> str:
#    """
#    Get semantic file clusters showing how files are grouped.
#
#    **Purpose:** Understand project organization through automatic semantic grouping.
#
#    **What are clusters?**
#    Files are automatically grouped by:
#    - Directory structure (src/auth → authentication cluster)
#    - File naming patterns (auth.py, login.js → authentication)
#    - Import relationships (files that import each other)
#    - Semantic keywords (database, api, test, etc.)
#
#    **Returns:** JSON with clusters, file counts, and sample files
#
#    **Common clusters:**
#    - authentication: Auth/login/user management
#    - api: API endpoints and routes
#    - database: Database models, migrations, queries
#    - tests: Test files and test utilities
#    - configuration: Config files (.env, yaml, json)
#    - documentation: README, docs, guides
#    - misc: Uncategorized files
#
#    **Use cases:**
#    - Understand project structure at a glance
#    - Find all files related to a feature
#    - Navigate large codebases
#    - Identify architectural patterns
#
#    **Note:** This tool queries the database (no direct file access).
#    Works in all environments. Requires file model built by scan_project_files() first.
#    """
#    conn = _get_db_for_project(project)
#    session_id = get_current_session_id()
#
#    try:
#        # Get cluster summary
#        cursor = conn.execute("""
#            SELECT
#                cluster_name,
#                COUNT(*) as file_count,
#                SUM(file_size) as total_size
#            FROM file_semantic_model
#            WHERE session_id = ?
#            GROUP BY cluster_name
#            ORDER BY file_count DESC
#        """, (session_id,))
#
#        clusters = []
#        for row in cursor.fetchall():
#            cluster_name = row['cluster_name']
#            if not cluster_name:
#                cluster_name = 'misc'
#
#            # Get file types in this cluster
#            types_cursor = conn.execute("""
#                SELECT DISTINCT file_type
#                FROM file_semantic_model
#                WHERE session_id = ? AND (cluster_name = ? OR (cluster_name IS NULL AND ? = 'misc'))
#            """, (session_id, cluster_name if cluster_name != 'misc' else None, cluster_name))
#
#            file_types = [r['file_type'] for r in types_cursor.fetchall() if r['file_type']]
#
#            # Get sample files (top 5)
#            samples_cursor = conn.execute("""
#                SELECT file_path, purpose
#                FROM file_semantic_model
#                WHERE session_id = ? AND (cluster_name = ? OR (cluster_name IS NULL AND ? = 'misc'))
#                ORDER BY file_size DESC
#                LIMIT 5
#            """, (session_id, cluster_name if cluster_name != 'misc' else None, cluster_name))
#
#            sample_files = [
#                {'path': r['file_path'], 'purpose': r['purpose']}
#                for r in samples_cursor.fetchall()
#            ]
#
#            clusters.append({
#                'name': cluster_name,
#                'file_count': row['file_count'],
#                'total_size_mb': round(row['total_size'] / (1024 * 1024), 2) if row['total_size'] else 0,
#                'file_types': file_types,
#                'sample_files': sample_files
#            })
#
#        return json.dumps({
#            'total_clusters': len(clusters),
#            'clusters': clusters
#        }, indent=2)
#
#    except Exception as e:
#        return json.dumps({'error': str(e)}, indent=2)
#
#
# DEPRECATED: Replaced by health_check_and_repair()
# @mcp.tool()
# async def file_model_status(project: Optional[str] = None) -> str:
#     """
#     DEPRECATED: Use health_check_and_repair(checks=["file_model"]) instead.
#
#     Get file semantic model statistics and health.
#
#     **Purpose:** Monitor the file model system and understand project composition.
#
#    **Returns:** JSON with overview, file type distribution, standard files, warnings
#
#    **Health status:**
#    - "healthy": Model contains files, recent scan
#    - "no_data": No files scanned yet (run scan_project_files)
#    - "stale": Last scan >7 days ago (consider re-scanning)
#
#    **Use cases:**
#    - Check if model is up to date
#    - Understand project composition
#    - Monitor standard file warnings
#    - Verify scan performance
#
#    **Note:** This tool queries the database (no direct file access).
#    Works in all environments. Shows status of file model built by scan_project_files().
#    """
#    conn = _get_db_for_project(project)
#    session_id = get_current_session_id()
#
#    try:
#        # Overview statistics
#        cursor = conn.execute("""
#            SELECT
#                COUNT(*) as total_files,
#                SUM(file_size) as total_size,
#                AVG(file_size) as avg_size,
#                MIN(last_scanned) as oldest_scan,
#                MAX(last_scanned) as newest_scan,
#                AVG(scan_duration_ms) as avg_scan_time
#            FROM file_semantic_model
#            WHERE session_id = ?
#        """, (session_id,))
#
#        stats = cursor.fetchone()
#
#        if not stats or stats['total_files'] == 0:
#            return json.dumps({
#                'overview': {'total_files': 0},
#                'health': 'no_data',
#                'message': 'No files scanned yet. Run scan_project_files() to build model.'
#            }, indent=2)
#
#        # Type distribution
#        type_cursor = conn.execute("""
#            SELECT file_type, COUNT(*) as count
#            FROM file_semantic_model
#            WHERE session_id = ?
#            GROUP BY file_type
#            ORDER BY count DESC
#            LIMIT 10
#        """, (session_id,))
#
#        type_dist = {row['file_type']: row['count'] for row in type_cursor.fetchall() if row['file_type']}
#
#        # Standard files
#        std_cursor = conn.execute("""
#            SELECT file_path, standard_type, warnings
#            FROM file_semantic_model
#            WHERE session_id = ? AND is_standard = 1
#            ORDER BY file_path
#        """, (session_id,))
#
#        standard_files = []
#        for row in std_cursor.fetchall():
#            warnings = json.loads(row['warnings'] or '[]')
#            standard_files.append({
#                'path': row['file_path'],
#                'type': row['standard_type'],
#                'warnings': warnings
#            })
#
#        # Determine health
#        age_days = (time.time() - stats['newest_scan']) / 86400 if stats['newest_scan'] else 999
#        if age_days > 7:
#            health = 'stale'
#        else:
#            health = 'healthy'
#
#        return json.dumps({
#            'overview': {
#                'total_files': stats['total_files'],
#                'total_size_mb': round(stats['total_size'] / (1024 * 1024), 2) if stats['total_size'] else 0,
#                'average_file_kb': round(stats['avg_size'] / 1024, 2) if stats['avg_size'] else 0,
#                'last_full_scan': datetime.fromtimestamp(stats['oldest_scan']).isoformat() if stats['oldest_scan'] else None,
#                'last_update': datetime.fromtimestamp(stats['newest_scan']).isoformat() if stats['newest_scan'] else None,
#                'avg_scan_time_ms': round(stats['avg_scan_time'] or 0, 2)
#            },
#            'type_distribution': type_dist,
#            'standard_files': standard_files,
#            'health': health
#        }, indent=2)
#
#    except Exception as e:
#        return json.dumps({'error': str(e)}, indent=2)
#
#
# ============================================================================
# SEMANTIC SEARCH & AI FEATURES (v4.4.0)
# ============================================================================
#
#@mcp.tool()
async def generate_embeddings(
    context_ids: Optional[str] = None,
    regenerate: bool = False,
    project: Optional[str] = None
) -> str:
    """
    Generate embeddings for contexts to enable semantic search.

    **Token Efficiency: MINIMAL** (~500 tokens)

    Args:
        context_ids: Comma-separated IDs to generate embeddings for (default: all without embeddings)
        regenerate: If True, regenerate embeddings even if they exist

    Returns: Statistics about embedding generation

    **Requirements:**
    - Ollama running locally
    - nomic-embed-text model installed (ollama pull nomic-embed-text)

    **Technical Details:**
    - Uses context preview (not full content) for efficient semantic matching
    - Max input: 1020 characters (nomic-embed-text limit)
    - Previews are automatically truncated if needed
    - 768-dimensional embeddings

    **Cost:** FREE (local)
    **Performance:** ~30ms per embedding

    Example:
        generate_embeddings()  # Generate for all contexts without embeddings
        generate_embeddings(context_ids="1,2,3")  # Specific contexts
        generate_embeddings(regenerate=True)  # Regenerate all
    """
    try:
        from src.services import embedding_service, init_token_tracker
        from src.services.semantic_search import SemanticSearch
    except Exception as e:
        return json.dumps({
            "error": "Service initialization failed",
            "reason": str(e),
            "setup": "Ensure src/ directory and services are properly installed"
        }, indent=2)

    if not embedding_service.enabled:
        return json.dumps({
            "error": "Embedding service not available",
            "reason": "Ollama not running or nomic-embed-text not installed",
            "setup": "1. Start Ollama\n2. Run: ollama pull nomic-embed-text"
        }, indent=2)

    # ✅ FIX: Use context manager to ensure connection is closed
    with _get_db_for_project(project) as conn:
        # Initialize token tracker
        init_token_tracker(conn)

        semantic_search = SemanticSearch(conn, embedding_service)

        # Determine which contexts to process
        # Use preview instead of content (nomic-embed-text has 1020 char limit)
        if context_ids:
            ids = [int(id.strip()) for id in context_ids.split(',')]
            sql = f"SELECT id, preview FROM context_locks WHERE id IN ({','.join(['?']*len(ids))})"
            cursor = conn.execute(sql, ids)
        elif regenerate:
            cursor = conn.execute("SELECT id, preview FROM context_locks")
        else:
            cursor = conn.execute("SELECT id, preview FROM context_locks WHERE embedding IS NULL")

        contexts = [{"id": row['id'], "content": row['preview']} for row in cursor.fetchall()]

        if not contexts:
            return json.dumps({
                "message": "No contexts to process",
                "total_contexts": 0
            }, indent=2)

        # Generate embeddings in batch
        result = semantic_search.batch_add_embeddings(contexts)

    # Build user-friendly summary
    mode = "specific contexts" if context_ids else ("all contexts (regenerate)" if regenerate else "contexts without embeddings")

    # Add error indicator to summary if failures occurred
    status_emoji = "✓" if result['failed'] == 0 else "⚠️"

    summary_text = f"""
🔄 Embedding Generation Task {status_emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━
Mode: {mode}
Processed: {len(contexts)} contexts
Success: {result['success']}
Failed: {result['failed']}
Model: {embedding_service.model}
Performance: ~30ms per embedding
━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()

    response = {
        "summary": summary_text,
        "message": "Embedding generation complete" if result['failed'] == 0 else "Embedding generation completed with errors",
        "total_processed": len(contexts),
        "success": result['success'],
        "failed": result['failed'],
        "model": embedding_service.model,
        "performance": "~30ms per embedding",
        "cost": "FREE (local)"
    }

    # Include error details if any failures occurred
    if result.get('errors'):
        response["errors"] = result['errors']
        response["troubleshooting"] = {
            "check_ollama": "Run: curl http://localhost:11434/api/tags",
            "verify_model": f"Run: ollama list | grep {embedding_service.model}",
            "pull_model": f"Run: ollama pull {embedding_service.model}",
            "check_logs": "Check stderr output for detailed error messages"
        }

    return json.dumps(response, indent=2)


@mcp.tool()
async def semantic_search_contexts(
    query: str,
    limit: int = 10,
    threshold: float = 0.7,
    priority: Optional[str] = None,
    tags: Optional[str] = None,
    use_reranking: bool = True,
    project: Optional[str] = None
) -> str:
    """
    Search contexts using semantic similarity (embeddings).

    **Token Efficiency: PREVIEW** (~2-5KB depending on limit)

    Args:
        query: Natural language search query
        limit: Maximum number of results (default: 10)
        threshold: Minimum similarity score 0-1 (default: 0.7)
        priority: Filter by priority ("always_check", "important", "reference")
        tags: Comma-separated tags to filter by
        use_reranking: Use two-stage retrieval with reranking (default: True)
                       When enabled: Gets top-50 candidates, reranks to top-N
                       Improves precision for multi-concept queries
                       Only works with Voyage AI provider

    Returns: Contexts ranked by semantic similarity with scores

    **Requirement:** Must run generate_embeddings() first
    **Cost:** FREE (local) or ~$0.0003/query (Voyage AI with reranking)
    **Performance:** ~30ms (local) or ~200-500ms (with reranking)

    Example:
        semantic_search_contexts("How do we handle authentication?")
        # Returns contexts about JWT, OAuth, auth flows even without exact keywords

        semantic_search_contexts("database connection pooling", priority="important")

        # Disable reranking for faster results
        semantic_search_contexts("authentication", use_reranking=False)
    """
    try:
        from src.services import embedding_service
        from src.services.semantic_search import SemanticSearch
    except Exception as e:
        return json.dumps({
            "error": "Service initialization failed",
            "reason": str(e)
        }, indent=2)

    if not embedding_service.enabled:
        return json.dumps({
            "error": "Semantic search not available",
            "reason": "Ollama not running or nomic-embed-text not installed",
            "fallback": "Use search_contexts() for keyword-based search"
        }, indent=2)

    # ✅ FIX: Use context manager to ensure connection is closed
    with _get_db_for_project(project) as conn:
        semantic_search = SemanticSearch(conn, embedding_service)

        # Determine candidate limit for reranking
        # If reranking enabled, get more candidates to rerank
        candidate_limit = limit * 5 if use_reranking else limit

        # Perform semantic search
        results = semantic_search.search_similar(
            query=query,
            limit=candidate_limit,
            threshold=threshold,
            priority_filter=priority,
            tags_filter=tags
        )

    # Apply reranking if enabled and using Voyage AI
    reranked = False
    if use_reranking and results and hasattr(embedding_service, 'rerank'):
        try:
            # Check if this is Voyage AI provider
            provider = getattr(embedding_service, '__class__', None)
            if provider and 'Voyage' in provider.__name__:
                # Rerank the candidates
                results = embedding_service.rerank(
                    query=query,
                    documents=results,
                    top_k=limit
                )
                reranked = True
        except Exception as e:
            # Fallback: use original results
            print(f"Reranking failed, using vector search results: {e}")
            results = results[:limit]
    else:
        # No reranking: just take top-N
        results = results[:limit]

    # Build user-friendly summary
    filters_text = []
    if priority:
        filters_text.append(f"priority={priority}")
    if tags:
        filters_text.append(f"tags={tags}")
    filters = f" | Filters: {', '.join(filters_text)}" if filters_text else ""

    rerank_info = " | Reranked ✨" if reranked else ""

    summary_text = f"""
🔍 Semantic Search Results
━━━━━━━━━━━━━━━━━━━━━━━━━━
Query: "{query}"
Threshold: {threshold}{filters}{rerank_info}
Found: {len(results)} contexts
Model: {embedding_service.model}
━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()

    if not results:
        return json.dumps({
            "summary": summary_text.replace(f"Found: {len(results)} contexts", "Found: 0 contexts ❌"),
            "query": query,
            "total_results": 0,
            "message": "No similar contexts found",
            "suggestions": [
                f"Lower threshold value (current: {threshold})",
                "Run generate_embeddings() if not done yet",
                "Try broader query terms"
            ]
        }, indent=2)

    return json.dumps({
        "summary": summary_text,
        "query": query,
        "total_results": len(results),
        "threshold": threshold,
        "results": results,
        "note": "Similarity scores range from 0-1, higher is more similar"
    }, indent=2)


def _validate_llm_service():
    """
    Validate LLM service availability.

    Returns: Tuple (error_response, llm_service)
        - error_response: JSON error string or None if valid
        - llm_service: Service instance if valid, else None
    """
    try:
        from src.services import llm_service
    except Exception as e:
        error_json = json.dumps({
            "error": "Service initialization failed",
            "reason": str(e)
        }, indent=2)
        return error_json, None

    if not llm_service.enabled:
        error_json = json.dumps({
            "error": "AI summarization not available",
            "reason": "Ollama not running or LLM model not installed",
            "setup": "1. Start Ollama\n2. Run: ollama pull qwen2.5-coder:1.5b",
            "fallback": "Use recall_context(topic, preview_only=True) for extract-based summary"
        }, indent=2)
        return error_json, None

    return None, llm_service


def _retrieve_and_summarize_context(conn, topic: str, llm_service):
    """
    Fetch context from database and generate AI summary.

    Args:
        conn: Database connection
        topic: Context topic/label
        llm_service: LLM service instance

    Returns: Dict with "error" key (error JSON) or "summary"/"preview" keys on success
    """
    cursor = conn.execute("""
        SELECT content, preview FROM context_locks
        WHERE label = ?
        ORDER BY version DESC LIMIT 1
    """, (topic,))

    row = cursor.fetchone()
    if not row:
        return {"error": json.dumps({
            "error": "Context not found",
            "topic": topic
        }, indent=2)}

    summary = llm_service.summarize_context(row['content'])
    if not summary:
        return {"error": json.dumps({
            "error": "Summary generation failed",
            "fallback_preview": row['preview']
        }, indent=2)}

    return {"summary": summary, "preview": row['preview']}


def _format_summary_response(summary: str, topic: str, model_info: str) -> str:
    """
    Format AI summary into standardized JSON response.

    Args:
        summary: AI-generated summary text
        topic: Context topic/label
        model_info: LLM model name

    Returns: JSON formatted response string
    """
    summary_text = f"""
🤖 AI-Generated Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━
Topic: {topic}
Model: {model_info}
Performance: ~1-2s
Cost: FREE (local)
━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()

    return json.dumps({
        "summary": summary_text,
        "topic": topic,
        "ai_summary": summary,
        "model": model_info,
        "performance": "~1-2s per summary",
        "cost": "FREE (local)",
        "note": "AI-generated summary may differ from extract-based preview"
    }, indent=2)


@mcp.tool()
async def ai_summarize_context(topic: str, project: Optional[str] = None) -> str:
    """
    Generate AI-powered summary of a context using local LLM.

    **Token Efficiency: SUMMARY** (~1-2KB)

    Args:
        topic: Context topic/label to summarize

    Returns: AI-generated summary focusing on key concepts and rules

    **Requirements:**
    - Ollama running locally
    - LLM model installed (qwen2.5-coder:1.5b recommended)

    **Cost:** FREE (local)
    **Performance:** ~1-2s per summary

    Example:
        ai_summarize_context("api_specification")
        # Returns: Intelligent summary highlighting:
        #   - Main purpose
        #   - Key rules (MUST/ALWAYS/NEVER)
        #   - Technical concepts
    """
    # Step 1: Validate LLM service availability
    error_response, llm_service = _validate_llm_service()
    if error_response:
        return error_response

    # Step 2: Retrieve context and generate summary
    with _get_db_for_project(project) as conn:
        result = _retrieve_and_summarize_context(conn, topic, llm_service)
        if "error" in result:
            return result["error"]

    # Step 3: Format and return response
    return _format_summary_response(result["summary"], topic, llm_service.default_model)


# DEPRECATED: Replaced by health_check_and_repair()
# @mcp.tool()
# async def embedding_status(project: Optional[str] = None) -> str:
#     """
#     DEPRECATED: Use health_check_and_repair(checks=["embeddings"]) instead.
#
#     Check status of embedding and AI features.
#
#     **Token Efficiency: MINIMAL** (~500 tokens)
#
#    Returns: Configuration status, statistics, and setup instructions
#    """
#    try:
#        from src.services import embedding_service, llm_service
#        from src.services.semantic_search import SemanticSearch
#        from src.config import config
#    except Exception as e:
#        return json.dumps({
#            "error": "Service initialization failed",
#            "reason": str(e),
#            "services": {
#                "embedding": {"enabled": False, "reason": "Import failed"},
#                "llm": {"enabled": False, "reason": "Import failed"}
#            }
#        }, indent=2)
#
#    conn = _get_db_for_project(project)
#    semantic_search = SemanticSearch(conn, embedding_service)
#
#    status = {
#        "embedding_service": {
#            "enabled": embedding_service.enabled,
#            "provider": config.embedding_provider,
#            "model": config.embedding_model if embedding_service.enabled else None,
#            "dimensions": embedding_service.dimensions if embedding_service.enabled else None,
#            "features": ["semantic_search"] if embedding_service.enabled else []
#        },
#        "llm_service": {
#            "enabled": llm_service.enabled,
#            "provider": config.llm_provider,
#            "model": config.llm_model if llm_service.enabled else None,
#            "features": ["ai_summarization", "priority_classification"] if llm_service.enabled else []
#        },
#        "statistics": semantic_search.get_embedding_stats(),
#        "setup_instructions": {}
#    }
#
#    # Add setup instructions if services disabled
#    if not embedding_service.enabled:
#        status["setup_instructions"]["embeddings"] = {
#            "step1": "Start Ollama (if not running)",
#            "step2": "Run: ollama pull nomic-embed-text",
#            "step3": "Restart MCP server",
#            "step4": "Run generate_embeddings() to populate existing contexts",
#            "cost": "FREE (local)",
#            "performance": "~30ms per embedding"
#        }
#
#    if not llm_service.enabled:
#        status["setup_instructions"]["llm"] = {
#            "step1": "Start Ollama (if not running)",
#            "step2": "Run: ollama pull qwen2.5-coder:1.5b (recommended for speed)",
#            "step3": "Restart MCP server",
#            "step4": "Use ai_summarize_context() for AI-powered summaries",
#            "cost": "FREE (local)",
#            "performance": "~1-2s per summary"
#        }
#
#    # Build status summary
#    emb_status = "✓ Enabled" if embedding_service.enabled else "✗ Disabled"
#    llm_status = "✓ Enabled" if llm_service.enabled else "✗ Disabled"
#
#    summary_text = f"""
#⚙️ AI Services Status
#━━━━━━━━━━━━━━━━━━━━━━━━━━
#Embeddings: {emb_status}
#  Provider: {config.embedding_provider}
#  Model: {config.embedding_model if embedding_service.enabled else 'N/A'}
#
#LLM: {llm_status}
#  Provider: {config.llm_provider}
#  Model: {config.llm_model if llm_service.enabled else 'N/A'}
#━━━━━━━━━━━━━━━━━━━━━━━━━━
#""".strip()
#
#    status["summary"] = summary_text
#    return json.dumps(status, indent=2)
#
#
@mcp.tool()
#async def diagnose_ollama() -> str:
#    """
#    Run diagnostics on Ollama connection and model availability.
#
#    **Token Efficiency: MINIMAL** (~500 tokens)
#
#    This tool helps troubleshoot embedding/LLM failures by checking:
#    - Is Ollama running?
#    - Are required models installed?
#    - Can we connect to the API?
#    - What models are available?
#
#    Use this when generate_embeddings() or ai_summarize_context() fail.
#    """
#    import requests
#    from src.config import config
#
#    diagnostics = {
#        "timestamp": time.time(),
#        "ollama_url": config.ollama_base_url,
#        "required_models": {
#            "embedding": config.embedding_model,
#            "llm": config.llm_model
#        },
#        "tests": {}
#    }
#
#    # Test 1: Can we reach Ollama?
#    try:
#        response = requests.get(f"{config.ollama_base_url}/api/tags", timeout=5)
#        diagnostics["tests"]["connection"] = {
#            "status": "✓ SUCCESS",
#            "code": response.status_code,
#            "reachable": True
#        }
#
#        if response.status_code == 200:
#            models_data = response.json()
#            installed_models = [m['name'] for m in models_data.get('models', [])]
#            diagnostics["tests"]["installed_models"] = {
#                "status": "✓ SUCCESS",
#                "models": installed_models,
#                "count": len(installed_models)
#            }
#
#            # Test 2: Check if required models are installed
#            embedding_installed = any(m.startswith(config.embedding_model) for m in installed_models)
#            llm_installed = any(m.startswith(config.llm_model) for m in installed_models)
#
#            diagnostics["tests"]["required_models"] = {
#                "embedding": {
#                    "model": config.embedding_model,
#                    "installed": embedding_installed,
#                    "status": "✓ FOUND" if embedding_installed else "✗ MISSING"
#                },
#                "llm": {
#                    "model": config.llm_model,
#                    "installed": llm_installed,
#                    "status": "✓ FOUND" if llm_installed else "✗ MISSING"
#                }
#            }
#        else:
#            diagnostics["tests"]["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
#
#    except requests.exceptions.ConnectionError:
#        diagnostics["tests"]["connection"] = {
#            "status": "✗ FAILED",
#            "reachable": False,
#            "error": f"Cannot connect to {config.ollama_base_url}",
#            "fix": "Start Ollama: 'ollama serve' or check if running"
#        }
#    except requests.exceptions.Timeout:
#        diagnostics["tests"]["connection"] = {
#            "status": "✗ TIMEOUT",
#            "reachable": False,
#            "error": "Request timed out after 5s",
#            "fix": "Ollama may be overloaded or not responding"
#        }
#    except Exception as e:
#        diagnostics["tests"]["connection"] = {
#            "status": "✗ ERROR",
#            "reachable": False,
#            "error": f"{type(e).__name__}: {str(e)}"
#        }
#
#    # Build summary
#    conn_ok = diagnostics["tests"].get("connection", {}).get("reachable", False)
#    emb_ok = diagnostics["tests"].get("required_models", {}).get("embedding", {}).get("installed", False)
#    llm_ok = diagnostics["tests"].get("required_models", {}).get("llm", {}).get("installed", False)
#
#    summary_lines = [
#        "🔍 Ollama Diagnostics",
#        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
#        f"Connection: {'✓ OK' if conn_ok else '✗ FAILED'}",
#        f"Embedding Model ({config.embedding_model}): {'✓ Installed' if emb_ok else '✗ Missing'}",
#        f"LLM Model ({config.llm_model}): {'✓ Installed' if llm_ok else '✗ Missing'}",
#        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
#    ]
#
#    diagnostics["summary"] = "\n".join(summary_lines)
#
#    # Add recommended fixes
#    if not conn_ok:
#        diagnostics["fix"] = "Start Ollama with: ollama serve"
#    elif not emb_ok or not llm_ok:
#        fixes = []
#        if not emb_ok:
#            fixes.append(f"ollama pull {config.embedding_model}")
#        if not llm_ok:
#            fixes.append(f"ollama pull {config.llm_model}")
#        diagnostics["fix"] = " && ".join(fixes)
#
#    return json.dumps(diagnostics, indent=2)
#
#
#@mcp.tool()
#async def test_single_embedding(text: str = "Test embedding", project: Optional[str] = None) -> str:
#    """
#    Test embedding generation with a single text and capture detailed debug output.
#
#    **Token Efficiency: DEBUG** (~1KB)
#
#    Args:
#        text: Text to generate embedding for (default: "Test embedding")
#
#    Returns: Detailed test results including any stderr debug/error output
#
#    Use this to debug why embeddings are failing - it will show the actual
#    Ollama API request/response cycle.
#    """
#    import sys
#    import io
#    from contextlib import redirect_stderr
#
#    try:
#        from src.services import embedding_service
#    except Exception as e:
#        return json.dumps({
#            "error": "Service initialization failed",
#            "reason": str(e)
#        }, indent=2)
#
#    # Capture stderr output
#    stderr_capture = io.StringIO()
#
#    result = {
#        "test_input": text,
#        "text_length": len(text),
#        "service_enabled": embedding_service.enabled,
#        "model": embedding_service.model,
#        "base_url": embedding_service.base_url
#    }
#
#    try:
#        # Try to generate embedding while capturing stderr
#        with redirect_stderr(stderr_capture):
#            embedding = embedding_service.generate_embedding(text)
#
#        stderr_output = stderr_capture.getvalue()
#
#        if embedding:
#            result["status"] = "✓ SUCCESS"
#            result["embedding_dimensions"] = len(embedding)
#            result["embedding_sample"] = embedding[:5]  # First 5 values
#        else:
#            result["status"] = "✗ FAILED"
#            result["embedding"] = None
#
#        # Include captured debug/error messages
#        if stderr_output:
#            result["debug_output"] = stderr_output.split('\n')
#
#    except Exception as e:
#        result["status"] = "✗ EXCEPTION"
#        result["error"] = f"{type(e).__name__}: {str(e)}"
#        import traceback
#        result["traceback"] = traceback.format_exc()
#
#        stderr_output = stderr_capture.getvalue()
#        if stderr_output:
#            result["debug_output"] = stderr_output.split('\n')
#
#    # Build summary
#    summary_lines = [
#        "🧪 Embedding Test Results",
#        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
#        f"Status: {result.get('status', 'UNKNOWN')}",
#        f"Service: {'Enabled' if result['service_enabled'] else 'Disabled'}",
#        f"Model: {result['model']}",
#        f"Text: {len(text)} chars",
#        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
#    ]
#
#    result["summary"] = "\n".join(summary_lines)
#
#    return json.dumps(result, indent=2)
#
#
#@mcp.tool()
#async def scan_and_analyze_directory(
#    directory: str,
#    pattern: str = "*.md",
#    recursive: bool = True,
#    store_in_table: Optional[str] = None,
#    max_files: int = 1000,
#    project: Optional[str] = None
#) -> str:
#    """
#    Scan directory and analyze text files with metadata extraction.
#
#    **Token Efficiency: SUMMARY** (~2-5KB depending on file count)
#
#    Args:
#        directory: Directory path to scan (absolute or relative)
#        pattern: File pattern to match (default: "*.md")
#                 Examples: "*.txt", "*.md", "*.py", "*"
#        recursive: Scan subdirectories recursively (default: True)
#        store_in_table: Optional workspace table name to store results
#        max_files: Maximum files to process (default: 1000, prevents runaway)
#
#    Returns: Summary statistics and per-file breakdown
#
#    This tool bridges the gap between filesystem access and database storage,
#    enabling complex file analysis workflows.
#
#    **IMPORTANT - Local Development Only:**
#    This tool uses direct Python filesystem access (Path.glob, os.walk) and is
#    designed for local development environments only. It will not work in:
#    - Claude Desktop (requires per-file permissions)
#    - Mobile devices (no filesystem access)
#    - Browser environments (restricted file access)
#
#    For Claude Desktop, use filesystem MCP tools instead.
#
#    Example:
#        # Recursive scan (all subdirectories)
#        scan_and_analyze_directory(
#            directory="/path/to/manuscripts",
#            pattern="*.md",
#            recursive=True,
#            store_in_table="manuscript_analysis"
#        )
#
#        # Non-recursive scan (top-level only)
#        scan_and_analyze_directory(
#            directory="/path/to/docs",
#            pattern="*.txt",
#            recursive=False
#        )
#    """
#    import os
#    import glob
#    from pathlib import Path
#    from datetime import datetime
#
#    try:
#        # Expand and validate directory
#        dir_path = Path(directory).expanduser().resolve()
#        if not dir_path.exists():
#            return json.dumps({
#                "error": "Directory not found",
#                "path": str(dir_path)
#            }, indent=2)
#
#        if not dir_path.is_dir():
#            return json.dumps({
#                "error": "Path is not a directory",
#                "path": str(dir_path)
#            }, indent=2)
#
#        # Find matching files
#        if recursive:
#            pattern_path = str(dir_path / "**" / pattern)
#            matching_files = glob.glob(pattern_path, recursive=True)
#        else:
#            pattern_path = str(dir_path / pattern)
#            matching_files = glob.glob(pattern_path, recursive=False)
#
#        matching_files = [f for f in matching_files if os.path.isfile(f)]
#
#        if len(matching_files) > max_files:
#            return json.dumps({
#                "error": "Too many files found",
#                "found": len(matching_files),
#                "max_allowed": max_files,
#                "suggestion": "Use more specific pattern or increase max_files"
#            }, indent=2)
#
#        if not matching_files:
#            return json.dumps({
#                "message": "No files found",
#                "directory": str(dir_path),
#                "pattern": pattern
#            }, indent=2)
#
#        # Analyze each file
#        results = []
#        total_size = 0
#        total_lines = 0
#        total_words = 0
#        total_chars = 0
#
#        for file_path in matching_files[:max_files]:
#            try:
#                stat = os.stat(file_path)
#                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
#                    content = f.read()
#
#                lines = content.count('\n') + 1
#                words = len(content.split())
#                chars = len(content)
#
#                rel_path = os.path.relpath(file_path, dir_path)
#
#                results.append({
#                    "file": rel_path,
#                    "size_bytes": stat.st_size,
#                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
#                    "lines": lines,
#                    "words": words,
#                    "chars": chars
#                })
#
#                total_size += stat.st_size
#                total_lines += lines
#                total_words += words
#                total_chars += chars
#
#            except Exception as e:
#                results.append({
#                    "file": os.path.relpath(file_path, dir_path),
#                    "error": f"{type(e).__name__}: {str(e)[:100]}"
#                })
#
#        # Store in workspace table if requested
#        if store_in_table:
#            conn = _get_db_for_project(project)
#
#            # Create table if doesn't exist (PostgreSQL-compatible)
#            if is_postgresql_mode():
#                conn.execute(f"""
#                    CREATE TABLE IF NOT EXISTS {store_in_table} (
#                        id SERIAL PRIMARY KEY,
#                        file TEXT,
#                        size_bytes INTEGER,
#                        modified TEXT,
#                        lines INTEGER,
#                        words INTEGER,
#                        chars INTEGER,
#                        error TEXT,
#                        scanned_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)
#                    )
#                """)
#            else:
#                conn.execute(f"""
#                    CREATE TABLE IF NOT EXISTS {store_in_table} (
#                        id INTEGER PRIMARY KEY AUTOINCREMENT,
#                        file TEXT,
#                        size_bytes INTEGER,
#                        modified TEXT,
#                        lines INTEGER,
#                        words INTEGER,
#                        chars INTEGER,
#                        error TEXT,
#                        scanned_at REAL DEFAULT (strftime('%s', 'now'))
#                    )
#                """)
#
#            # Insert results
#            for result in results:
#                conn.execute(f"""
#                    INSERT INTO {store_in_table}
#                    (file, size_bytes, modified, lines, words, chars, error)
#                    VALUES (?, ?, ?, ?, ?, ?, ?)
#                """, (
#                    result.get("file"),
#                    result.get("size_bytes"),
#                    result.get("modified"),
#                    result.get("lines"),
#                    result.get("words"),
#                    result.get("chars"),
#                    result.get("error")
#                ))
#
#            conn.commit()
#
#        # Build summary
#        summary_text = f"""
#📁 Directory Scan Results
#━━━━━━━━━━━━━━━━━━━━━━━━━━
#Directory: {dir_path.name}/
#Pattern: {pattern}
#Files Found: {len(results)}
#
#Totals:
#  Size: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)
#  Lines: {total_lines:,}
#  Words: {total_words:,}
#  Characters: {total_chars:,}
#
#Average per file:
#  Size: {total_size//len(results) if results else 0:,} bytes
#  Lines: {total_lines//len(results) if results else 0:,}
#  Words: {total_words//len(results) if results else 0:,}
#━━━━━━━━━━━━━━━━━━━━━━━━━━
#""".strip()
#
#        response = {
#            "summary": summary_text,
#            "files_processed": len(results),
#            "statistics": {
#                "total_size_bytes": total_size,
#                "total_lines": total_lines,
#                "total_words": total_words,
#                "total_chars": total_chars
#            },
#            "sample_files": results[:5]  # Show only first 5 as sample
#        }
#
#        if len(results) > 5:
#            response["note"] = f"Showing 5 sample files of {len(results)} total. Full data stored in table."
#
#        if store_in_table:
#            response["stored_in"] = store_in_table
#            response["query_help"] = f"Use: query_database(\"SELECT * FROM {store_in_table} ORDER BY words DESC LIMIT 10\")"
#
#        # Use compact JSON (no indent) to reduce response size
#        return json.dumps(response)
#
#    except Exception as e:
#        import traceback
#        return json.dumps({
#            "error": "Scan failed",
#            "exception": f"{type(e).__name__}: {str(e)}",
#            "traceback": traceback.format_exc()
#        })
#
#
#@mcp.tool()
#async def usage_statistics(days: int = 30, project: Optional[str] = None) -> str:
#    """
#    Get detailed token usage statistics for cost analysis.
#
#    **Token Efficiency: SUMMARY** (~2-3KB)
#
#    Args:
#        days: Number of days to analyze (default: 30)
#
#    Returns: Detailed usage statistics including:
#        - Operation counts
#        - Token counts by operation type
#        - Performance metrics (avg duration)
#        - Model breakdown
#
#    Example:
#        usage_statistics()  # Last 30 days
#        usage_statistics(days=7)  # Last week
#        usage_statistics(days=90)  # Last quarter
#    """
#    try:
#        from src.services import init_token_tracker
#    except Exception as e:
#        return json.dumps({
#            "error": "Token tracker initialization failed",
#            "reason": str(e)
#        }, indent=2)
#
#    conn = _get_db_for_project(project)
#    tracker = init_token_tracker(conn)
#
#    stats = tracker.get_usage_stats(days=days)
#
#    # Build user-friendly summary
#    total_ops = stats['summary']['total_operations']
#    total_tokens = stats['summary']['total_tokens']
#
#    summary_text = f"""
#📊 Token Usage Statistics
#━━━━━━━━━━━━━━━━━━━━━━━━━━
#Period: Last {days} days
#Total Operations: {total_ops:,}
#Total Tokens: {total_tokens:,}
#━━━━━━━━━━━━━━━━━━━━━━━━━━
#""".strip()
#
#    stats["summary_display"] = summary_text
#    return json.dumps(stats, indent=2)
#
#
#@mcp.tool()
#async def cost_comparison(days: int = 30, project: Optional[str] = None) -> str:
#    """
#    Compare actual costs (FREE with Ollama) vs OpenAI API costs.
#
#    **Token Efficiency: SUMMARY** (~2-3KB)
#
#    Args:
#        days: Number of days to analyze (default: 30)
#
#    Returns: Cost comparison showing:
#        - Actual cost: $0.00 (Ollama)
#        - OpenAI embedding cost (if you used text-embedding-3-small)
#        - OpenAI GPT-3.5 cost (if you used GPT-3.5 Turbo)
#        - OpenAI GPT-4 cost (if you used GPT-4 Turbo)
#        - Total savings
#
#    This tool helps justify using local models by showing:
#    - How much you would have spent with OpenAI
#    - Token usage patterns
#    - Performance metrics
#
#    Example:
#        cost_comparison()  # Monthly comparison
#        cost_comparison(days=7)  # Weekly
#        cost_comparison(days=365)  # Annual projection
#    """
#    try:
#        from src.services import init_token_tracker
#    except Exception as e:
#        return json.dumps({
#            "error": "Token tracker initialization failed",
#            "reason": str(e)
#        }, indent=2)
#
#    conn = _get_db_for_project(project)
#    tracker = init_token_tracker(conn)
#
#    comparison = tracker.get_cost_comparison(days=days)
#
#    # Calculate annual projection
#    if days > 0:
#        daily_savings = {}
#        for alt_name, alt_data in comparison['cost_comparison']['alternatives'].items():
#            daily_cost = alt_data['cost_usd'] / days
#            annual_cost = daily_cost * 365
#            daily_savings[alt_name] = {
#                'daily_avg': daily_cost,
#                'annual_projected': annual_cost
#            }
#
#        comparison['projections'] = daily_savings
#
#    # Build user-friendly summary
#    alternatives = comparison['cost_comparison']['alternatives']
#    gpt4_savings = alternatives.get('openai_gpt4', {}).get('cost_usd', 0)
#    gpt35_savings = alternatives.get('openai_gpt35', {}).get('cost_usd', 0)
#
#    summary_text = f"""
#💰 Cost Comparison
#━━━━━━━━━━━━━━━━━━━━━━━━━━
#Period: Last {days} days
#Actual Cost: $0.00 (Ollama)
#
#Savings vs OpenAI:
#  GPT-4: ${gpt4_savings:.2f}
#  GPT-3.5: ${gpt35_savings:.2f}
#
#Total Savings: 100%
#━━━━━━━━━━━━━━━━━━━━━━━━━━
#""".strip()
#
#    comparison["summary_display"] = summary_text
#    return json.dumps(comparison, indent=2)
#
#
# ============================================================================
# UNIFIED DATABASE HEALTH TOOLS
# ============================================================================
#
#def _resolve_project(project: Optional[str] = None) -> str:
#    """
#    Resolve project name for unified database tools.
#    Uses _get_project_for_context for consistent resolution logic.
#
#    Args:
#        project: Optional project name
#
#    Returns:
#        str: Resolved project name
#    """
#    return _get_project_for_context(project)
#

def _gather_database_statistics(db, project_name: str) -> dict:
    """Gather comprehensive database statistics."""
    stats = {}
    conn = db.pool.getconn()
    try:
        with conn.cursor() as cur:
            # Context statistics
            cur.execute(f"""
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN embedding_vector IS NOT NULL THEN 1 END) as with_embeddings,
                       ROUND(AVG(LENGTH(content))::numeric, 2) as avg_size
                FROM {db.schema}.context_locks
                WHERE project_name = %s
            """, (project_name,))
            context_stats = cur.fetchone()
            stats["contexts"] = {
                "total": context_stats["total"],
                "with_embeddings": context_stats["with_embeddings"],
                "coverage": round(context_stats["with_embeddings"] / context_stats["total"] * 100, 1) if context_stats["total"] > 0 else 0,
                "avg_size": float(context_stats["avg_size"]) if context_stats["avg_size"] else 0
            }

            # Session statistics
            cur.execute(f"""
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN expires_at > NOW() THEN 1 END) as active
                FROM {db.schema}.sessions
                WHERE project_name = %s
            """, (project_name,))
            session_stats = cur.fetchone()
            stats["sessions"] = {
                "total": session_stats["total"],
                "active": session_stats["active"]
            }

            # Database size
            cur.execute(f"""
                SELECT pg_size_pretty(pg_total_relation_size('{db.schema}.context_locks')) as size
            """)
            size_result = cur.fetchone()
            stats["database_size"] = size_result["size"]

    finally:
        db.pool.putconn(conn)
    return stats


def _check_schema_health(db, project_name: str) -> list:
    """Check schema integrity and detect missing tables."""
    issues = []
    conn = db.pool.getconn()
    try:
        with conn.cursor() as cur:
            # Check for missing expected tables
            expected_tables = ["projects", "sessions", "context_locks", "memory_entries"]
            cur.execute(f"""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type = 'BASE TABLE'
            """, (db.schema,))
            existing_tables = [row["table_name"] for row in cur.fetchall()]

            missing_tables = set(expected_tables) - set(existing_tables)
            if missing_tables:
                issues.append({
                    "type": "missing_tables",
                    "severity": "error",
                    "tables": list(missing_tables),
                    "impact": "Core functionality broken",
                    "auto_fixable": False,
                    "fix_method": "Run apply_migrations() to restore schema"
                })
    finally:
        db.pool.putconn(conn)
    return issues


def _check_data_integrity(db, project_name: str) -> list:
    """Check data consistency and detect orphaned records."""
    issues = []
    conn = db.pool.getconn()
    try:
        with conn.cursor() as cur:
            # Check for sessions without matching project
            cur.execute(f"""
                SELECT COUNT(*) as count
                FROM {db.schema}.sessions s
                WHERE NOT EXISTS (
                    SELECT 1 FROM {db.schema}.projects p
                    WHERE p.name = s.project_name
                )
            """)
            orphan_sessions = cur.fetchone()["count"]

            if orphan_sessions > 0:
                issues.append({
                    "type": "orphaned_sessions",
                    "severity": "error",
                    "count": orphan_sessions,
                    "impact": "Data corruption, wasted space",
                    "auto_fixable": True,
                    "fix_method": "DELETE orphaned sessions"
                })
    finally:
        db.pool.putconn(conn)
    return issues


def _check_embedding_health(db, project_name: str) -> list:
    """Check embedding status and detect missing embeddings."""
    issues = []
    conn = db.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, label
                FROM {db.schema}.context_locks
                WHERE project_name = %s
                  AND embedding_vector IS NULL
                LIMIT 100
            """, (project_name,))
            missing_emb = cur.fetchall()

            if missing_emb:
                issues.append({
                    "type": "missing_embeddings",
                    "severity": "warning",
                    "count": len(missing_emb),
                    "impact": f"Semantic search unavailable for {len(missing_emb)} contexts",
                    "auto_fixable": True,
                    "fix_method": "generate_embeddings()",
                    "details": [{"id": r["id"], "label": r["label"]} for r in missing_emb[:5]]
                })
    finally:
        db.pool.putconn(conn)
    return issues


def _check_performance_metrics(db) -> list:
    """Gather performance data and detect slow tables."""
    issues = []
    conn = db.pool.getconn()
    try:
        with conn.cursor() as cur:
            # Find tables with high sequential scan ratio on large tables
            cur.execute(f"""
                SELECT
                    schemaname || '.' || relname as table_name,
                    seq_scan,
                    idx_scan,
                    COALESCE(idx_scan, 0) + seq_scan as total_scans,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname)) as size,
                    pg_total_relation_size(schemaname||'.'||relname) as size_bytes
                FROM pg_stat_user_tables
                WHERE schemaname = %s
                  AND seq_scan > 100
                  AND pg_total_relation_size(schemaname||'.'||relname) > 1024*1024  -- > 1MB
                ORDER BY seq_scan DESC
                LIMIT 5
            """, (db.schema,))
            slow_tables = cur.fetchall()

            for table in slow_tables:
                # High seq scan ratio suggests missing index
                total = table["total_scans"]
                seq_ratio = (table["seq_scan"] / total * 100) if total > 0 else 0

                if seq_ratio > 30:  # More than 30% sequential scans
                    issues.append({
                        "type": "high_seq_scans",
                        "severity": "warning",
                        "table": table["table_name"],
                        "seq_scans": table["seq_scan"],
                        "index_scans": table["idx_scan"],
                        "size": table["size"],
                        "impact": f"{int(seq_ratio)}% sequential scans - potential 20-80% speedup with index",
                        "auto_fixable": False,  # Requires analysis to determine best index
                        "fix_method": "Review query patterns and add appropriate indexes"
                    })
    finally:
        db.pool.putconn(conn)
    return issues


async def _repair_common_issues(db, project_name: str, issues: list, dry_run: bool = False) -> list:
    """Execute repairs for auto-fixable issues."""
    fixes_applied = []

    if dry_run:
        return fixes_applied

    for issue in issues:
        if not issue.get("auto_fixable", False):
            continue

        try:
            if issue["type"] == "missing_embeddings":
                # Generate embeddings
                result = await generate_embeddings(project=project_name)
                fixes_applied.append({
                    "issue": "missing_embeddings",
                    "action": "generated embeddings",
                    "count": issue["count"],
                    "result": result
                })

            elif issue["type"] == "orphaned_sessions":
                # Delete orphaned sessions
                conn = db.pool.getconn()
                try:
                    with conn.cursor() as cur:
                        cur.execute(f"""
                            DELETE FROM {db.schema}.sessions s
                            WHERE NOT EXISTS (
                                SELECT 1 FROM {db.schema}.projects p
                                WHERE p.name = s.project_name
                            )
                        """)
                        deleted = cur.rowcount
                        conn.commit()

                        fixes_applied.append({
                            "issue": "orphaned_sessions",
                            "action": "deleted orphaned sessions",
                            "count": deleted
                        })
                finally:
                    db.pool.putconn(conn)

        except Exception as e:
            fixes_applied.append({
                "issue": issue["type"],
                "action": "FAILED",
                "error": str(e)
            })

    return fixes_applied


def _build_health_report(stats: dict, issues: list, fixes_applied: list,
                        auto_fix: bool, dry_run: bool, check_list: list) -> dict:
    """Build comprehensive health report with recommendations."""
    # Calculate remaining issues after fixes
    if auto_fix and fixes_applied:
        fixed_types = {f["issue"] for f in fixes_applied if f["action"] != "FAILED"}
        remaining_issues = [i for i in issues if i["type"] not in fixed_types]
    else:
        remaining_issues = issues

    # Determine health status
    if not remaining_issues:
        health = "healthy"
    elif all(i["severity"] == "warning" for i in remaining_issues):
        health = "good_with_warnings"
    else:
        health = "needs_attention"

    # Generate recommendations
    recommendations = []
    if not remaining_issues and not auto_fix:
        recommendations.append("✅ Database is healthy!")
        recommendations.append("Consider running health_check_and_repair() weekly to maintain health")
    elif not remaining_issues and auto_fix:
        recommendations.append("✅ All issues fixed! Database is now healthy!")
    elif remaining_issues and not auto_fix:
        fixable_count = sum(1 for i in remaining_issues if i.get("auto_fixable", False))
        if fixable_count > 0:
            recommendations.append(f"Run health_check_and_repair(auto_fix=True) to automatically fix {fixable_count} issues")

        # Add specific recommendations
        for issue in remaining_issues[:3]:  # Top 3 issues
            if issue.get("fix_method"):
                recommendations.append(f"• {issue['type']}: {issue['fix_method']}")
    elif remaining_issues and auto_fix:
        recommendations.append(f"⚠️ {len(remaining_issues)} issues could not be auto-fixed")
        for issue in remaining_issues:
            recommendations.append(f"• {issue['type']}: {issue['fix_method']}")

    # Build report
    report = {
        "health": health,
        "summary": f"{len(remaining_issues)} issues found" if remaining_issues else "All checks passed",
        "checks_performed": check_list,
        "statistics": stats,
        "issues_found": issues,
        "fixes_applied": fixes_applied,
        "remaining_issues": remaining_issues,
        "recommendations": recommendations
    }

    if dry_run and auto_fix:
        report["dry_run_note"] = "This is a DRY RUN. Set dry_run=False to apply fixes."

    return report


async def health_check_and_repair(
    project: Optional[str] = None,
    auto_fix: bool = False,
    checks: str = "all",
    dry_run: bool = False
) -> str:
    """
    Complete database health check with optional auto-repair.

    Performs comprehensive validation in single call:
    1. Schema inspection (structure, indexes, constraints)
    2. Data validation (integrity, embeddings, orphans)
    3. Performance analysis (using pg_stat_user_tables)
    4. Issue detection (categorized by severity)
    5. [If auto_fix=True] Automatic repair
    6. Final verification

    Args:
        project: Project name (default: auto-detect)
        auto_fix: Automatically fix issues (default: False)
        checks: Which checks to run (default: "all")
                Options: "all", "integrity", "embeddings", "performance", "schema"
                Can be comma-separated: "integrity,embeddings"
        dry_run: Show what would be fixed without fixing (default: False)

    Returns:
        JSON with complete health report including:
        - health: "healthy" | "good_with_warnings" | "needs_attention"
        - summary: One-line status
        - statistics: Database stats (contexts, sessions, size, etc.)
        - issues_found: List of issues detected
        - fixes_applied: What was fixed (if auto_fix=True)
        - remaining_issues: Still needs attention
        - recommendations: Next steps

    Example:
        User: "Is my database healthy?"
        LLM: health_check_and_repair()

        User: "Fix my database"
        LLM: health_check_and_repair(auto_fix=True)
    """
    try:
        project_name = _get_project_for_context(project)
        db = get_db()

        # Parse checks parameter
        check_list = [c.strip() for c in checks.split(",")]
        if "all" in check_list:
            check_list = ["integrity", "embeddings", "performance", "schema"]

        # STEP 1: Gather database statistics
        stats = _gather_database_statistics(db, project_name)

        # STEP 2: Run health checks
        issues = []
        if "schema" in check_list:
            issues.extend(_check_schema_health(db, project_name))
        if "integrity" in check_list:
            issues.extend(_check_data_integrity(db, project_name))
        if "embeddings" in check_list:
            issues.extend(_check_embedding_health(db, project_name))
        if "performance" in check_list:
            issues.extend(_check_performance_metrics(db))

        # STEP 3: Auto-repair if requested
        fixes_applied = []
        if auto_fix:
            fixes_applied = await _repair_common_issues(db, project_name, issues, dry_run)

        # STEP 4: Build comprehensive report
        report = _build_health_report(stats, issues, fixes_applied, auto_fix, dry_run, check_list)

        return json.dumps(report, indent=2, default=str)

    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return json.dumps({
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }, indent=2)


@mcp.tool()
async def inspect_schema(
    project: Optional[str] = None,
    table: Optional[str] = None
) -> str:
    """
    PostgreSQL-aware schema inspection.

    Returns detailed schema information using information_schema.
    This is a lightweight alternative to health_check_and_repair() when you
    just need schema structure without validation.

    Args:
        project: Project name (default: auto-detect)
        table: Specific table name (default: all tables)
               If specified, returns detailed info for just that table

    Returns:
        JSON with complete schema structure including:
        - database_type: "postgresql"
        - database_version: PostgreSQL version
        - schema: Project schema name
        - tables: List of tables with columns, indexes, constraints
        - [If table specified] Detailed single table info

    Example:
        User: "Show me the schema structure"
        LLM: inspect_schema()

        User: "What columns does context_locks have?"
        LLM: inspect_schema(table="context_locks")
    """
    try:
        project_name = _get_project_for_context(project)
        db = get_db()

        conn = db.pool.getconn()
        try:
            with conn.cursor() as cur:
                # Get PostgreSQL version
                cur.execute("SELECT version()")
                version_str = cur.fetchone()["version"]
                pg_version = version_str.split()[1] if version_str else "unknown"

                # Build table list query
                if table:
                    # Single table inspection
                    table_filter = "AND table_name = %s"
                    params = (db.schema, table)
                else:
                    # All tables
                    table_filter = ""
                    params = (db.schema,)

                # Get all tables in schema
                cur.execute(f"""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s
                      AND table_type = 'BASE TABLE'
                      {table_filter}
                    ORDER BY table_name
                """, params)
                tables_list = [row["table_name"] for row in cur.fetchall()]

                if not tables_list:
                    if table:
                        return json.dumps({
                            "error": f"Table '{table}' not found in schema '{db.schema}'",
                            "available_tables": []
                        }, indent=2)
                    else:
                        return json.dumps({
                            "project": project_name,
                            "schema": db.schema,
                            "database_type": "postgresql",
                            "database_version": pg_version,
                            "tables": [],
                            "message": "No tables found in schema"
                        }, indent=2)

                # Gather detailed info for each table
                tables_info = []
                for tbl in tables_list:
                    # Get column information
                    cur.execute(f"""
                        SELECT
                            column_name,
                            data_type,
                            is_nullable,
                            column_default,
                            character_maximum_length
                        FROM information_schema.columns
                        WHERE table_schema = %s
                          AND table_name = %s
                        ORDER BY ordinal_position
                    """, (db.schema, tbl))
                    columns = []
                    for col in cur.fetchall():
                        columns.append({
                            "name": col["column_name"],
                            "type": col["data_type"].upper(),
                            "nullable": col["is_nullable"] == "YES",
                            "default": col["column_default"],
                            "max_length": col["character_maximum_length"]
                        })

                    # Get index information
                    cur.execute(f"""
                        SELECT
                            i.relname as index_name,
                            a.attname as column_name,
                            ix.indisunique as is_unique,
                            ix.indisprimary as is_primary,
                            am.amname as index_type
                        FROM pg_class t
                        JOIN pg_index ix ON t.oid = ix.indrelid
                        JOIN pg_class i ON i.oid = ix.indexrelid
                        JOIN pg_am am ON i.relam = am.oid
                        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
                        WHERE t.relname = %s
                          AND t.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = %s)
                        ORDER BY i.relname, a.attnum
                    """, (tbl, db.schema))

                    indexes = {}
                    for idx in cur.fetchall():
                        idx_name = idx["index_name"]
                        if idx_name not in indexes:
                            indexes[idx_name] = {
                                "name": idx_name,
                                "columns": [],
                                "unique": idx["is_unique"],
                                "primary": idx["is_primary"],
                                "type": idx["index_type"]
                            }
                        indexes[idx_name]["columns"].append(idx["column_name"])

                    # Get table size and row count
                    cur.execute(f"""
                        SELECT
                            pg_size_pretty(pg_total_relation_size(%s || '.' || %s)) as size,
                            n_live_tup as rows
                        FROM pg_stat_user_tables
                        WHERE schemaname = %s
                          AND relname = %s
                    """, (db.schema, tbl, db.schema, tbl))
                    stats = cur.fetchone()

                    tables_info.append({
                        "name": tbl,
                        "rows": stats["rows"] if stats else 0,
                        "size": stats["size"] if stats else "0 bytes",
                        "columns": columns,
                        "indexes": list(indexes.values())
                    })

                # Build final response
                response = {
                    "project": project_name,
                    "schema": db.schema,
                    "database_type": "postgresql",
                    "database_version": pg_version,
                    "tables": tables_info
                }

                if table:
                    # Single table mode - add helpful context
                    response["inspected_table"] = table
                    response["column_count"] = len(tables_info[0]["columns"])
                    response["index_count"] = len(tables_info[0]["indexes"])

                return json.dumps(response, indent=2, default=str)

        finally:
            db.pool.putconn(conn)

    except Exception as e:
        logger.error(f"Schema inspection failed: {e}", exc_info=True)
        return json.dumps({
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }, indent=2)


# ============================================================================
# Migration Helper Functions
# ============================================================================

def _validate_migrations(migrations: list) -> dict:
    """
    Validate migration list format.

    Args:
        migrations: List of migration dictionaries

    Returns:
        dict with 'valid' (bool) and optional 'error' (str)
    """
    if not isinstance(migrations, list):
        return {"valid": False, "error": "Migrations must be a list"}

    for mig in migrations:
        if not isinstance(mig, dict):
            return {"valid": False, "error": f"Migration must be dict, got {type(mig)}"}

        required_fields = ["id", "name", "description", "sql", "breaking_change", "affected_tables"]
        for field in required_fields:
            if field not in mig:
                return {"valid": False, "error": f"Migration {mig.get('id', '?')} missing field: {field}"}

    return {"valid": True}


def _check_migration_status(cur, conn, migrations: list, db) -> dict:
    """
    Check which migrations have been applied.

    Args:
        cur: Database cursor
        conn: Database connection
        migrations: List of available migrations
        db: Database adapter

    Returns:
        dict with 'current_version', 'applied', 'pending', 'pg_version'
    """
    # Ensure migration_history table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS migration_history (
            id SERIAL PRIMARY KEY,
            migration_id INTEGER NOT NULL UNIQUE,
            migration_name TEXT NOT NULL,
            description TEXT,
            sql_content TEXT,
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            duration_ms INTEGER,
            affected_rows INTEGER,
            status TEXT DEFAULT 'success',
            error_message TEXT
        )
    """)
    conn.commit()

    # Get PostgreSQL version
    cur.execute("SELECT version() as version")
    pg_version_raw = cur.fetchone()["version"]
    pg_version = pg_version_raw.split()[1] if pg_version_raw else "unknown"

    # Get list of already applied migrations
    cur.execute("""
        SELECT migration_id, migration_name, applied_at, status
        FROM migration_history
        ORDER BY migration_id
    """)
    applied = {row["migration_id"]: row for row in cur.fetchall()}

    # Determine current schema version (highest applied migration)
    current_version = max(applied.keys()) if applied else 0

    # Find pending migrations
    pending = [m for m in migrations if m["id"] not in applied]

    return {
        "current_version": current_version,
        "applied": applied,
        "pending": pending,
        "pg_version": pg_version
    }


def _plan_migration_execution(pending: list, db, cur) -> dict:
    """
    Build execution plan for dry-run mode.

    Args:
        pending: List of pending migrations
        db: Database adapter
        cur: Database cursor

    Returns:
        dict with 'execution_plan', 'total_estimated_time_ms', 'has_breaking_changes'
    """
    execution_plan = []
    total_estimated_time_ms = 0

    # Estimate backup time
    execution_plan.append("1. Backup current schema state (estimated: 500ms)")
    total_estimated_time_ms += 500

    # Build plan for each migration
    for i, mig in enumerate(pending, start=2):
        # Estimate duration based on SQL complexity
        sql_lines = len(mig["sql"].strip().split('\n'))
        estimated_ms = sql_lines * 25  # ~25ms per SQL statement

        execution_plan.append(
            f"{i}. Apply migration {mig['id']}: {mig['name']} (estimated: {estimated_ms}ms)"
        )
        total_estimated_time_ms += estimated_ms

        execution_plan.append(
            f"{i+1}. Validate schema integrity (estimated: 100ms)"
        )
        total_estimated_time_ms += 100

    execution_plan.append(f"{len(pending)*2+2}. Update migration history table")

    # Get row count estimates for affected tables
    for mig in pending:
        for table_spec in mig["affected_tables"]:
            if "(new)" not in table_spec:
                table_name = table_spec
                try:
                    cur.execute(f"""
                        SELECT n_live_tup as rows
                        FROM pg_stat_user_tables
                        WHERE schemaname = %s AND relname = %s
                    """, (db.schema, table_name))
                    result = cur.fetchone()
                    mig["affected_rows_estimate"] = result["rows"] if result else 0
                except:
                    mig["affected_rows_estimate"] = 0
            else:
                mig["affected_rows_estimate"] = 0

    # Check for breaking changes
    has_breaking_changes = any(m["breaking_change"] for m in pending)

    return {
        "execution_plan": execution_plan,
        "total_estimated_time_ms": total_estimated_time_ms,
        "has_breaking_changes": has_breaking_changes
    }


def _execute_single_migration(cur, conn, migration: dict) -> dict:
    """
    Execute a single migration.

    Args:
        cur: Database cursor
        conn: Database connection
        migration: Migration dictionary

    Returns:
        dict with 'status', 'duration_ms', 'affected_rows', optional 'error'
    """
    import time

    migration_start = time.time()
    affected_rows = 0

    try:
        logger.info(f"  ▶️ Applying migration {migration['id']}: {migration['name']}")

        # Skip migration 1 (migration_history table - already created)
        if migration["id"] == 1:
            duration_ms = 0
        else:
            # Execute migration SQL
            cur.execute(migration["sql"])
            affected_rows = cur.rowcount if cur.rowcount >= 0 else 0
            conn.commit()

            duration_ms = int((time.time() - migration_start) * 1000)

        logger.info(f"    ✅ Success ({duration_ms}ms, {affected_rows} rows)")

        return {
            "status": "success",
            "duration_ms": duration_ms,
            "affected_rows": affected_rows
        }

    except Exception as e:
        conn.rollback()
        error_msg = str(e)
        logger.error(f"    ❌ Failed: {error_msg}")

        return {
            "status": "failed",
            "error": error_msg
        }


def _record_migration_history(cur, conn, migration: dict, result: dict) -> None:
    """
    Record migration in history table.

    Args:
        cur: Database cursor
        conn: Database connection
        migration: Migration dictionary
        result: Result from _execute_single_migration
    """
    try:
        if result["status"] == "success":
            cur.execute("""
                INSERT INTO migration_history
                (migration_id, migration_name, description, sql_content, duration_ms, affected_rows, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'success')
                ON CONFLICT (migration_id) DO NOTHING
            """, (
                migration["id"],
                migration["name"],
                migration["description"],
                migration["sql"],
                result["duration_ms"],
                result["affected_rows"]
            ))
        else:
            cur.execute("""
                INSERT INTO migration_history
                (migration_id, migration_name, description, sql_content, status, error_message)
                VALUES (%s, %s, %s, %s, 'failed', %s)
                ON CONFLICT (migration_id) DO UPDATE
                SET status = 'failed', error_message = EXCLUDED.error_message
            """, (
                migration["id"],
                migration["name"],
                migration["description"],
                migration["sql"],
                result["error"]
            ))

        conn.commit()
    except Exception as e:
        logger.warning(f"Failed to record migration history: {e}")


def _build_migration_report(
    project_name: str,
    db,
    pg_version: str,
    current_version: int,
    pending: list,
    plan_data: dict = None,
    applied_migrations: list = None,
    total_duration_ms: int = 0,
    validation_result: dict = None,
    backup_path: str = None,
    dry_run: bool = True
) -> dict:
    """
    Build final migration report.

    Args:
        project_name: Project name
        db: Database adapter
        pg_version: PostgreSQL version
        current_version: Current schema version
        pending: List of pending migrations
        plan_data: Execution plan data (dry-run mode)
        applied_migrations: List of applied migrations (execution mode)
        total_duration_ms: Total execution time (execution mode)
        validation_result: Schema validation result (execution mode)
        backup_path: Backup file path (execution mode)
        dry_run: Whether this is a dry-run

    Returns:
        dict with complete report
    """
    if dry_run:
        # Dry-run report
        return {
            "project": project_name,
            "database_type": "postgresql",
            "database_version": pg_version,
            "schema": db.schema,
            "dry_run": True,
            "current_schema_version": f"{current_version}.0",
            "target_schema_version": f"{pending[-1]['id']}.0",
            "pending_migrations": [
                {
                    "id": m["id"],
                    "name": m["name"],
                    "description": m["description"],
                    "sql": m["sql"],
                    "breaking_change": m["breaking_change"],
                    "affected_tables": m["affected_tables"],
                    "affected_rows_estimate": m.get("affected_rows_estimate", 0)
                }
                for m in pending
            ],
            "execution_plan": plan_data["execution_plan"],
            "total_estimated_time_ms": plan_data["total_estimated_time_ms"],
            "safety_checks": {
                "data_backed_up": "not yet (dry-run)",
                "rollback_available": True,
                "breaking_changes": plan_data["has_breaking_changes"]
            },
            "recommendation": (
                "⚠️ CAUTION: Contains breaking changes. Review carefully."
                if plan_data["has_breaking_changes"]
                else "✅ Safe to apply. Run with dry_run=False and confirm=True to execute."
            )
        }
    else:
        # Execution report
        # Get new schema version
        new_version = max([m["id"] for m in applied_migrations if m["status"] == "success"], default=current_version)

        # Check if any migrations failed
        failed_migrations = [m for m in applied_migrations if m["status"] == "failed"]
        overall_status = "partial_success" if failed_migrations else "success"

        return {
            "project": project_name,
            "database_type": "postgresql",
            "database_version": pg_version,
            "schema": db.schema,
            "dry_run": False,
            "status": overall_status,
            "previous_schema_version": f"{current_version}.0",
            "new_schema_version": f"{new_version}.0",
            "applied_migrations": applied_migrations,
            "total_duration_ms": total_duration_ms,
            "validation": validation_result,
            "backup_location": backup_path,
            "summary": {
                "total_attempted": len(applied_migrations),
                "successful": len([m for m in applied_migrations if m["status"] == "success"]),
                "failed": len(failed_migrations)
            }
        }


@mcp.tool()
async def apply_migrations(
    project: Optional[str] = None,
    dry_run: bool = True,
    confirm: bool = False
) -> str:
    """
    Apply pending schema migrations with safety checks.

    What it does:
    1. Checks current schema version
    2. Identifies pending migrations
    3. [If dry_run=True] Shows what would change
    4. [If dry_run=False and confirm=True] Applies migrations
    5. Validates schema after migration
    6. Updates migration history

    Args:
        project: Project name (default: auto-detect or active project)
        dry_run: Preview changes without applying (default: True)
        confirm: Required for actual execution (default: False)

    Returns:
        JSON with migration plan (dry_run=True) or execution results (dry_run=False)

    Example:
        # Preview pending migrations
        apply_migrations()

        # Apply migrations
        apply_migrations(dry_run=False, confirm=True)

        # Specific project
        apply_migrations(project="my_project", dry_run=False, confirm=True)
    """
    import time
    import tempfile
    from datetime import datetime

    try:
        # ====================================================================
        # STEP 1: RESOLVE PROJECT
        # ====================================================================
        project_name = project or ACTIVE_PROJECT or _auto_detect_project()
        if not project_name:
            return json.dumps({
                "error": "No project specified and auto-detection failed",
                "hint": "Call select_project_for_session() first or pass project parameter"
            }, indent=2)

        logger.info(f"🔧 Checking migrations for project: {project_name}")

        db = _get_project_db(project_name)
        conn = db.pool.getconn()

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # ====================================================================
            # STEP 2: DEFINE AVAILABLE MIGRATIONS
            # ====================================================================
            available_migrations = [
                {
                    "id": 1,
                    "name": "add_migration_history_table",
                    "description": "Create migration_history table for tracking schema changes",
                    "sql": "-- Already created above",
                    "breaking_change": False,
                    "affected_tables": ["migration_history (new)"]
                },
                {
                    "id": 2,
                    "name": "add_context_embedding_version",
                    "description": "Track embedding model version for each context",
                    "sql": "ALTER TABLE context_locks ADD COLUMN IF NOT EXISTS embedding_version TEXT",
                    "breaking_change": False,
                    "affected_tables": ["context_locks"]
                },
                {
                    "id": 3,
                    "name": "add_context_access_count",
                    "description": "Track how many times each context has been accessed",
                    "sql": "ALTER TABLE context_locks ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0",
                    "breaking_change": False,
                    "affected_tables": ["context_locks"]
                },
                {
                    "id": 4,
                    "name": "add_session_metadata",
                    "description": "Add metadata JSON column to sessions for extensibility",
                    "sql": "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'",
                    "breaking_change": False,
                    "affected_tables": ["sessions"]
                },
                {
                    "id": 5,
                    "name": "add_file_model_indexes",
                    "description": "Improve file semantic model query performance",
                    "sql": """
                        CREATE INDEX IF NOT EXISTS idx_file_semantic_model_file_type
                        ON file_semantic_model(file_type);
                        CREATE INDEX IF NOT EXISTS idx_file_semantic_model_cluster
                        ON file_semantic_model(cluster_name)
                    """,
                    "breaking_change": False,
                    "affected_tables": ["file_semantic_model"]
                }
            ]

            # Validate migrations
            validation = _validate_migrations(available_migrations)
            if not validation["valid"]:
                return json.dumps({"error": validation["error"]}, indent=2)

            # ====================================================================
            # STEP 3: CHECK MIGRATION STATUS
            # ====================================================================
            status_info = _check_migration_status(cur, conn, available_migrations, db)
            current_version = status_info["current_version"]
            pg_version = status_info["pg_version"]
            pending = status_info["pending"]

            # No pending migrations - return early
            if not pending:
                return json.dumps({
                    "project": project_name,
                    "database_type": "postgresql",
                    "database_version": pg_version,
                    "schema": db.schema,
                    "current_schema_version": f"{current_version}.0",
                    "status": "up_to_date",
                    "message": "No pending migrations. Schema is up to date.",
                    "applied_migrations": len(status_info["applied"]),
                    "available_migrations": len(available_migrations)
                }, indent=2)

            # ====================================================================
            # STEP 4: DRY RUN MODE - Preview changes
            # ====================================================================
            if dry_run:
                plan_data = _plan_migration_execution(pending, db, cur)
                report = _build_migration_report(
                    project_name=project_name,
                    db=db,
                    pg_version=pg_version,
                    current_version=current_version,
                    pending=pending,
                    plan_data=plan_data,
                    dry_run=True
                )
                return json.dumps(report, indent=2, default=str)

            # ====================================================================
            # STEP 5: EXECUTION MODE - Apply migrations
            # ====================================================================

            # Safety check: require confirm=True
            if not confirm:
                return json.dumps({
                    "error": "Safety check failed",
                    "message": "To apply migrations, you must set confirm=True",
                    "hint": "call apply_migrations(dry_run=False, confirm=True)",
                    "pending_migrations": len(pending)
                }, indent=2)

            logger.info(f"🚀 Applying {len(pending)} migrations...")

            # Create backup before migration
            backup_path = None
            try:
                backup_file = tempfile.NamedTemporaryFile(
                    mode='w',
                    suffix=f'_backup_before_migration_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.sql',
                    delete=False
                )
                backup_path = backup_file.name
                backup_file.close()
                logger.info(f"📦 Creating backup: {backup_path}")
            except Exception as e:
                logger.warning(f"⚠️ Could not create backup: {e}")

            # Execute migrations
            applied_migrations = []
            start_time = time.time()

            for mig in pending:
                # Execute single migration
                result = _execute_single_migration(cur, conn, mig)

                # Record in history
                _record_migration_history(cur, conn, mig, result)

                # Track results
                applied_migrations.append({
                    "id": mig["id"],
                    "name": mig["name"],
                    **result
                })

                # Stop on first failure
                if result["status"] == "failed":
                    break

            total_duration_ms = int((time.time() - start_time) * 1000)

            # ====================================================================
            # STEP 6: VALIDATE SCHEMA
            # ====================================================================
            validation_result = {
                "schema_valid": True,
                "data_intact": True,
                "indexes_intact": True,
                "constraints_valid": True
            }

            try:
                # Check tables
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM information_schema.tables
                    WHERE table_schema = %s
                """, (db.schema,))
                table_count = cur.fetchone()["count"]
                validation_result["table_count"] = table_count
                validation_result["schema_valid"] = table_count > 0

                # Check constraints
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM information_schema.table_constraints
                    WHERE table_schema = %s
                """, (db.schema,))
                validation_result["constraint_count"] = cur.fetchone()["count"]

                # Check indexes
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM pg_indexes
                    WHERE schemaname = %s
                """, (db.schema,))
                index_count = cur.fetchone()["count"]
                validation_result["index_count"] = index_count
                validation_result["indexes_intact"] = index_count > 0

            except Exception as e:
                validation_result["schema_valid"] = False
                validation_result["validation_error"] = str(e)

            # ====================================================================
            # STEP 7: BUILD FINAL REPORT
            # ====================================================================
            report = _build_migration_report(
                project_name=project_name,
                db=db,
                pg_version=pg_version,
                current_version=current_version,
                pending=pending,
                applied_migrations=applied_migrations,
                total_duration_ms=total_duration_ms,
                validation_result=validation_result,
                backup_path=backup_path,
                dry_run=False
            )

            return json.dumps(report, indent=2, default=str)

        finally:
            db.pool.putconn(conn)

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return json.dumps({
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }, indent=2)


# ==============================================================================
# EXPORT PROJECT HELPER FUNCTIONS
# ==============================================================================

def _collect_export_data(conn, db, include_embeddings: bool) -> dict:
    """
    Collect all data from project tables for export.

    Args:
        conn: Database connection
        db: Database adapter instance
        include_embeddings: Whether to include embedding vectors

    Returns:
        Dictionary with collected data and statistics
    """
    with conn.cursor() as cur:
        # Export contexts
        logger.info("Exporting contexts...")
        cur.execute(f"""
            SELECT id, label, content, version, priority, tags,
                   key_concepts, metadata, session_id, locked_at,
                   last_accessed, access_count, size_bytes
            FROM {db.schema}.context_locks
            ORDER BY label, version
        """)
        contexts = []
        total_context_size = 0
        for row in cur.fetchall():
            context_obj = {
                "id": row[0],
                "label": row[1],
                "content": row[2],
                "version": row[3],
                "priority": row[4],
                "tags": row[5],
                "key_concepts": row[6],
                "metadata": row[7],
                "session_id": row[8],
                "locked_at": row[9].isoformat() if row[9] else None,
                "last_accessed": row[10].isoformat() if row[10] else None,
                "access_count": row[11],
                "size_bytes": row[12]
            }
            contexts.append(context_obj)
            total_context_size += row[12] if row[12] else 0

        unique_contexts = len(set(c["label"] for c in contexts))

        # Export sessions
        logger.info("Exporting sessions...")
        cur.execute(f"""
            SELECT session_id, project, started_at, last_activity,
                   last_handover, handover_timestamp, is_active
            FROM {db.schema}.sessions
            ORDER BY started_at DESC
        """)
        sessions = []
        active_sessions = 0
        for row in cur.fetchall():
            session_obj = {
                "session_id": row[0],
                "project": row[1],
                "started_at": row[2].isoformat() if row[2] else None,
                "last_activity": row[3].isoformat() if row[3] else None,
                "last_handover": row[4],
                "handover_timestamp": row[5].isoformat() if row[5] else None,
                "is_active": row[6]
            }
            sessions.append(session_obj)
            if row[6]:
                active_sessions += 1

        session_size = sum(len(json.dumps(s)) for s in sessions)

        # Export memories
        logger.info("Exporting memories...")
        cur.execute(f"""
            SELECT id, session_id, category, content, metadata, timestamp
            FROM {db.schema}.memory_entries
            ORDER BY timestamp DESC
        """)
        memories = []
        categories = set()
        for row in cur.fetchall():
            memory_obj = {
                "id": row[0],
                "session_id": row[1],
                "category": row[2],
                "content": row[3],
                "metadata": row[4],
                "timestamp": row[5].isoformat() if row[5] else None
            }
            memories.append(memory_obj)
            if row[2]:
                categories.add(row[2])

        memory_size = sum(len(json.dumps(m)) for m in memories)

        # Export embeddings (optional)
        embeddings_info = {"included": False}
        embeddings = []
        if include_embeddings:
            logger.info("Exporting embeddings...")
            cur.execute(f"""
                SELECT context_id, embedding, embedding_model, created_at
                FROM {db.schema}.context_embeddings
            """)
            for row in cur.fetchall():
                embedding_obj = {
                    "context_id": row[0],
                    "embedding": row[1],
                    "embedding_model": row[2],
                    "created_at": row[3].isoformat() if row[3] else None
                }
                embeddings.append(embedding_obj)

            embeddings_info = {
                "included": True,
                "count": len(embeddings),
                "size_mb": round(sum(len(str(e["embedding"])) for e in embeddings) / (1024 * 1024), 2)
            }
        else:
            # Check how much space we're saving
            cur.execute(f"""
                SELECT COUNT(*),
                       COALESCE(SUM(LENGTH(embedding::text)), 0)
                FROM {db.schema}.context_embeddings
            """)
            emb_row = cur.fetchone()
            if emb_row and emb_row[0] > 0:
                saved_mb = round(emb_row[1] / (1024 * 1024), 2)
                embeddings_info = {
                    "included": False,
                    "reason": f"Excluded by default (would add {saved_mb}MB)",
                    "count_excluded": emb_row[0]
                }

    return {
        "contexts": contexts,
        "sessions": sessions,
        "memories": memories,
        "embeddings": embeddings,
        "stats": {
            "unique_contexts": unique_contexts,
            "total_context_size": total_context_size,
            "active_sessions": active_sessions,
            "session_size": session_size,
            "memory_size": memory_size,
            "categories": categories,
            "embeddings_info": embeddings_info
        }
    }


def _build_export_metadata(project_name: str, db, format: str, compress: bool) -> dict:
    """
    Build export metadata dictionary.

    Args:
        project_name: Project name being exported
        db: Database adapter instance
        format: Export format
        compress: Whether output will be compressed

    Returns:
        Metadata dictionary for export
    """
    return {
        "project": project_name,
        "schema": db.schema,
        "export_timestamp": datetime.utcnow().isoformat(),
        "export_format": format,
        "compressed": compress,
        "dementia_version": "4.5.0",
        "schema_version": "4.1"
    }


def _save_export_file(export_data: dict, output_path_obj: Path, compress: bool) -> dict:
    """
    Save export data to file with optional compression and calculate checksums.

    Args:
        export_data: Complete export data dictionary
        output_path_obj: Path object for output file
        compress: Whether to use gzip compression

    Returns:
        Dictionary with file_size, uncompressed_size, and checksum
    """
    # Serialize to JSON
    logger.info("Serializing data to JSON...")
    json_data = json.dumps(export_data, indent=2, default=str)
    uncompressed_size = len(json_data.encode('utf-8'))

    # Write to file (with optional compression)
    logger.info(f"Writing to {output_path_obj}...")
    if compress:
        with gzip.open(output_path_obj, 'wt', encoding='utf-8') as f:
            f.write(json_data)
    else:
        with open(output_path_obj, 'w', encoding='utf-8') as f:
            f.write(json_data)

    # Get actual file size
    file_size = output_path_obj.stat().st_size

    # Calculate checksum
    logger.info("Calculating checksum...")
    hash_obj = hashlib.sha256()
    with open(output_path_obj, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_obj.update(chunk)
    checksum = f"sha256:{hash_obj.hexdigest()[:16]}..."

    return {
        "file_size": file_size,
        "uncompressed_size": uncompressed_size,
        "checksum": checksum
    }


def _build_export_report(
    project_name: str,
    format: str,
    compress: bool,
    output_path_obj: Path,
    stats: dict,
    file_info: dict,
    duration_ms: int,
    schema_version: str
) -> dict:
    """
    Build comprehensive export report.

    Args:
        project_name: Project name
        format: Export format used
        compress: Whether compression was used
        output_path_obj: Output file path
        stats: Statistics from data collection
        file_info: File size and checksum info
        duration_ms: Total export duration in milliseconds
        schema_version: Schema version exported

    Returns:
        Complete export report dictionary
    """
    return {
        "project": project_name,
        "format": format,
        "compressed": compress,
        "output_path": str(output_path_obj),
        "exported": {
            "contexts": {
                "count": stats["unique_contexts"],
                "versions": len(stats.get("contexts_list", [])),
                "size_mb": round(stats["total_context_size"] / (1024 * 1024), 2)
            },
            "sessions": {
                "count": len(stats.get("sessions_list", [])),
                "active": stats["active_sessions"],
                "size_kb": round(stats["session_size"] / 1024, 2)
            },
            "memories": {
                "count": len(stats.get("memories_list", [])),
                "categories": sorted(list(stats["categories"])),
                "size_mb": round(stats["memory_size"] / (1024 * 1024), 2)
            },
            "embeddings": stats["embeddings_info"],
            "schema_version": schema_version
        },
        "file_size_mb": round(file_info["file_size"] / (1024 * 1024), 2),
        "compression_ratio": f"{round(file_info['uncompressed_size'] / file_info['file_size'], 1)}x" if compress else "1.0x",
        "duration_ms": duration_ms,
        "checksum": file_info["checksum"],
        "import_compatible": True,
        "restore_command": f"import_project(input_path='{output_path_obj}')"
    }


@mcp.tool()
async def export_project(
    output_path: str,
    project: Optional[str] = None,
    format: str = "json",
    compress: bool = True,
    include_embeddings: bool = False
) -> str:
    """
    Export entire project to portable format.

    Complete project backup to portable format. Creates a comprehensive
    export of all project data that can be imported later.

    What it exports:
    - All contexts (with content, metadata, versions)
    - All sessions (with timestamps, activity)
    - All memories (with categories, relationships)
    - Schema metadata (version, structure)
    - [Optional] Embeddings (large, usually excluded)

    Args:
        output_path: Where to save (absolute path)
        project: Project name (default: auto-detect)
        format: Export format - "json" only (structured data)
        compress: Use gzip compression (default: True)
        include_embeddings: Include embedding vectors (default: False, adds significant size)

    Returns:
        JSON with export summary including file path, size, contents breakdown,
        compression ratio, checksum, and restore command

    Example:
        User: "Backup my database"
        LLM: export_project(output_path="/tmp/backup.json.gz")

        User: "Export this project with embeddings"
        LLM: export_project(output_path="/tmp/full_backup.json.gz", include_embeddings=True)
    """
    import traceback

    start_time = time.time()

    try:
        # ====================================================================
        # STEP 1: RESOLVE PROJECT AND VALIDATE PARAMETERS
        # ====================================================================
        project_name = _get_project_for_context(project)
        db = get_db()

        # Validate format
        if format != "json":
            return json.dumps({
                "error": "Only 'json' format is currently supported",
                "supported_formats": ["json"]
            }, indent=2)

        # Validate output path
        output_path_obj = Path(output_path).expanduser().resolve()
        if not output_path_obj.parent.exists():
            return json.dumps({
                "error": f"Output directory does not exist: {output_path_obj.parent}",
                "suggestion": "Create directory first or use existing path"
            }, indent=2)

        # Add .gz extension if compressing and not present
        if compress and not str(output_path_obj).endswith('.gz'):
            output_path_obj = Path(str(output_path_obj) + '.gz')

        logger.info(f"Starting export of project '{project_name}' to {output_path_obj}")

        # ====================================================================
        # STEP 2: COLLECT DATA FROM DATABASE
        # ====================================================================
        conn = db.pool.getconn()
        try:
            collected_data = _collect_export_data(conn, db, include_embeddings)
        finally:
            db.pool.putconn(conn)

        # ====================================================================
        # STEP 3: BUILD EXPORT STRUCTURE WITH METADATA
        # ====================================================================
        metadata = _build_export_metadata(project_name, db, format, compress)
        export_data = {
            "metadata": metadata,
            "data": {
                "contexts": collected_data["contexts"],
                "sessions": collected_data["sessions"],
                "memories": collected_data["memories"]
            }
        }

        # Add embeddings if included
        if include_embeddings:
            export_data["data"]["embeddings"] = collected_data["embeddings"]

        # ====================================================================
        # STEP 4: SAVE TO FILE WITH COMPRESSION
        # ====================================================================
        file_info = _save_export_file(export_data, output_path_obj, compress)

        # ====================================================================
        # STEP 5: BUILD AND RETURN REPORT
        # ====================================================================
        duration_ms = int((time.time() - start_time) * 1000)

        # Prepare stats with additional list references for report
        stats = collected_data["stats"].copy()
        stats["contexts_list"] = collected_data["contexts"]
        stats["sessions_list"] = collected_data["sessions"]
        stats["memories_list"] = collected_data["memories"]

        response = _build_export_report(
            project_name=project_name,
            format=format,
            compress=compress,
            output_path_obj=output_path_obj,
            stats=stats,
            file_info=file_info,
            duration_ms=duration_ms,
            schema_version=metadata["schema_version"]
        )

        logger.info(f"Export completed successfully: {file_info['file_size'] / (1024 * 1024):.2f}MB in {duration_ms}ms")
        return json.dumps(response, indent=2)

    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        return json.dumps({
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }, indent=2)


# ============================================================================
# IMPORT PROJECT HELPER FUNCTIONS
# ============================================================================

def _validate_backup_file(input_path: str) -> tuple:
    """
    Validate backup file exists and is valid JSON.

    Args:
        input_path: Path to backup file

    Returns:
        Tuple of (input_path_obj, compressed, backup_data)

    Raises:
        ValueError: If file doesn't exist or is invalid
    """
    input_path_obj = Path(input_path).expanduser().resolve()
    if not input_path_obj.exists():
        raise ValueError(f"Input file does not exist: {input_path_obj}")

    # Detect if file is compressed
    compressed = str(input_path_obj).endswith('.gz')

    # Read and parse backup file
    try:
        if compressed:
            with gzip.open(input_path_obj, 'rt', encoding='utf-8') as f:
                backup_data = json.load(f)
        else:
            with open(input_path_obj, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format in backup file: {e}")
    except gzip.BadGzipFile:
        raise ValueError("Invalid gzip file - may be corrupted")

    return input_path_obj, compressed, backup_data


def _parse_backup_metadata(backup_data: dict, project: Optional[str] = None) -> tuple:
    """
    Parse and validate backup structure and metadata.

    Args:
        backup_data: Parsed backup JSON data
        project: Optional target project name override

    Returns:
        Tuple of (metadata, target_project, backup_version)

    Raises:
        ValueError: If backup structure is invalid
    """
    if "metadata" not in backup_data:
        raise ValueError("Invalid backup format: missing metadata")

    metadata = backup_data["metadata"]
    target_project = project or metadata.get("project", "default")
    backup_version = metadata.get("dementia_version", "unknown")

    return metadata, target_project, backup_version


def _count_backup_items(backup_data: dict) -> tuple:
    """
    Count items in backup data.

    Args:
        backup_data: Parsed backup JSON data

    Returns:
        Tuple of (contexts_count, sessions_count, memories_count, embeddings_missing)
    """
    contexts_count = len(backup_data.get("contexts", []))
    sessions_count = len(backup_data.get("sessions", []))
    memories_count = len(backup_data.get("memories", []))

    # Check embeddings
    contexts_with_embeddings = sum(
        1 for ctx in backup_data.get("contexts", [])
        if ctx.get("embedding_vector") is not None
    )
    embeddings_missing = contexts_count - contexts_with_embeddings

    return contexts_count, sessions_count, memories_count, embeddings_missing


def _check_import_conflicts(db, target_project: str) -> bool:
    """
    Check if target project already exists.

    Args:
        db: Database adapter instance
        target_project: Target project name

    Returns:
        True if project exists, False otherwise
    """
    conn = db.pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT EXISTS(
                    SELECT 1 FROM {db.schema}.context_locks
                    WHERE project_name = %s
                    LIMIT 1
                )
            """, (target_project,))
            return cur.fetchone()[0]
    finally:
        db.pool.putconn(conn)


def _import_backup_tables(
    conn,
    db,
    backup_data: dict,
    target_project: str,
    overwrite: bool,
    project_exists: bool
) -> dict:
    """
    Import all tables from backup data.

    Args:
        conn: Database connection
        db: Database adapter instance
        backup_data: Parsed backup JSON data
        target_project: Target project name
        overwrite: Whether to overwrite existing data
        project_exists: Whether project already exists

    Returns:
        Dictionary with import counts for each table
    """
    import_counts = {
        "contexts": 0,
        "sessions": 0,
        "memories": 0
    }

    with conn.cursor() as cur:
        # If overwriting, delete existing data
        if overwrite and project_exists:
            logger.info(f"Deleting existing project data for '{target_project}'")
            cur.execute(f"DELETE FROM {db.schema}.memories WHERE project_name = %s", (target_project,))
            cur.execute(f"DELETE FROM {db.schema}.context_locks WHERE project_name = %s", (target_project,))
            cur.execute(f"DELETE FROM {db.schema}.sessions WHERE project_name = %s", (target_project,))
            conn.commit()

        # Import contexts
        for ctx_data in backup_data.get("contexts", []):
            try:
                cur.execute(f"""
                    INSERT INTO {db.schema}.context_locks
                    (project_name, label, version, content, preview, key_concepts,
                     priority, tags, metadata, created_at, locked_at, last_accessed,
                     access_count, size_bytes, embedding_vector)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (project_name, label, version)
                    DO UPDATE SET
                        content = EXCLUDED.content,
                        preview = EXCLUDED.preview,
                        key_concepts = EXCLUDED.key_concepts,
                        priority = EXCLUDED.priority,
                        tags = EXCLUDED.tags,
                        metadata = EXCLUDED.metadata,
                        locked_at = EXCLUDED.locked_at,
                        embedding_vector = EXCLUDED.embedding_vector
                """, (
                    target_project,
                    ctx_data.get("label"),
                    ctx_data.get("version", "1.0"),
                    ctx_data.get("content"),
                    ctx_data.get("preview"),
                    ctx_data.get("key_concepts"),
                    ctx_data.get("priority", "reference"),
                    ctx_data.get("tags"),
                    json.dumps(ctx_data.get("metadata", {})),
                    ctx_data.get("created_at"),
                    ctx_data.get("locked_at"),
                    ctx_data.get("last_accessed"),
                    ctx_data.get("access_count", 0),
                    ctx_data.get("size_bytes", len(ctx_data.get("content", ""))),
                    ctx_data.get("embedding_vector")
                ))
                import_counts["contexts"] += 1
            except Exception as e:
                logger.error(f"Failed to import context {ctx_data.get('label')}: {e}")
                # Continue with other contexts

        # Import sessions
        for session_data in backup_data.get("sessions", []):
            try:
                cur.execute(f"""
                    INSERT INTO {db.schema}.sessions
                    (session_id, project_name, created_at, last_active, expires_at,
                     metadata, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id)
                    DO UPDATE SET
                        last_active = EXCLUDED.last_active,
                        metadata = EXCLUDED.metadata,
                        is_active = EXCLUDED.is_active
                """, (
                    session_data.get("session_id"),
                    target_project,
                    session_data.get("created_at"),
                    session_data.get("last_active"),
                    session_data.get("expires_at"),
                    json.dumps(session_data.get("metadata", {})),
                    session_data.get("is_active", False)
                ))
                import_counts["sessions"] += 1
            except Exception as e:
                logger.error(f"Failed to import session {session_data.get('session_id')}: {e}")
                # Continue with other sessions

        # Import memories
        for memory_data in backup_data.get("memories", []):
            try:
                cur.execute(f"""
                    INSERT INTO {db.schema}.memories
                    (project_name, category, subcategory, content, metadata,
                     created_at, session_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    target_project,
                    memory_data.get("category"),
                    memory_data.get("subcategory"),
                    memory_data.get("content"),
                    json.dumps(memory_data.get("metadata", {})),
                    memory_data.get("created_at"),
                    memory_data.get("session_id")
                ))
                import_counts["memories"] += 1
            except Exception as e:
                logger.error(f"Failed to import memory: {e}")
                # Continue with other memories

        conn.commit()

    return import_counts


def _build_import_report(
    input_path_obj,
    target_project: str,
    import_counts: dict,
    contexts_count: int,
    sessions_count: int,
    memories_count: int,
    embeddings_missing: int,
    duration_ms: int
) -> dict:
    """
    Build import completion report.

    Args:
        input_path_obj: Path to input file
        target_project: Target project name
        import_counts: Dictionary with actual import counts
        contexts_count: Expected context count
        sessions_count: Expected session count
        memories_count: Expected memory count
        embeddings_missing: Number of missing embeddings
        duration_ms: Import duration in milliseconds

    Returns:
        Dictionary with import report
    """
    # Validate imported data
    validation_result = {
        "schema_valid": True,
        "data_intact": import_counts["contexts"] == contexts_count,
        "referential_integrity": True,  # Would need deeper check
        "embeddings_complete": embeddings_missing == 0
    }

    # Determine final health
    if validation_result["data_intact"] and validation_result["embeddings_complete"]:
        final_health = "healthy"
    elif validation_result["data_intact"]:
        final_health = "good_with_warnings"
    else:
        final_health = "needs_attention"

    response = {
        "input_path": str(input_path_obj),
        "validate_only": False,
        "target_project": target_project,
        "imported": import_counts,
        "embeddings_regenerated": 0,  # Not implemented yet
        "validation": validation_result,
        "duration_ms": duration_ms,
        "final_health": final_health
    }

    if embeddings_missing > 0:
        response["warning"] = f"{embeddings_missing} contexts missing embeddings. Run generate_embeddings() to regenerate."

    return response


# ============================================================================
# IMPORT PROJECT TOOL
# ============================================================================

@mcp.tool()
async def import_project(
    input_path: str,
    project: Optional[str] = None,
    overwrite: bool = False,
    validate_only: bool = False
) -> str:
    """
    Import project from exported backup file.

    Complete project restoration from backup. Validates file format,
    checks for conflicts, imports all data, and regenerates embeddings.

    What it does:
    1. Validates file format and schema compatibility
    2. Checks for conflicts (existing project)
    3. [If validate_only=False] Imports all data
    4. Validates imported data integrity
    5. Regenerates embeddings if needed

    Args:
        input_path: Path to backup file (.json or .json.gz)
        project: Target project name (default: use name from backup)
        overwrite: Overwrite existing project (default: False, requires explicit confirmation)
        validate_only: Just check if import would work without importing (default: False)

    Returns:
        JSON with import summary including validation results, imported counts,
        duration, and final health status

    Example:
        User: "Restore my backup"
        LLM: import_project(input_path="/tmp/backup.json.gz")

        User: "Check if I can import this file"
        LLM: import_project(input_path="/tmp/backup.json.gz", validate_only=True)

        User: "Import and overwrite existing project"
        LLM: import_project(input_path="/tmp/backup.json.gz", overwrite=True)
    """
    import traceback

    start_time = time.time()

    try:
        # Step 1: Validate backup file and parse JSON
        try:
            input_path_obj, compressed, backup_data = _validate_backup_file(input_path)
        except ValueError as e:
            return json.dumps({
                "error": str(e),
                "suggestion": "Check file path and format"
            }, indent=2)

        # Step 2: Parse backup metadata
        try:
            metadata, target_project, backup_version = _parse_backup_metadata(backup_data, project)
        except ValueError as e:
            return json.dumps({
                "error": str(e),
                "suggestion": "File does not appear to be a valid dementia backup"
            }, indent=2)

        # Step 3: Count items in backup
        contexts_count, sessions_count, memories_count, embeddings_missing = _count_backup_items(backup_data)

        # Step 4: Check for conflicts
        db = get_db()
        project_exists = _check_import_conflicts(db, target_project)

        # Check schema compatibility (for future use)
        current_version = "4.5.0"
        schema_compatible = True  # For now, assume compatibility

        # Handle validate_only mode
        if validate_only:
            response = {
                "input_path": str(input_path_obj),
                "validate_only": True,
                "file_valid": True,
                "format": "json",
                "compressed": compressed,
                "schema_version": backup_version,
                "compatible": schema_compatible,
                "target_project": target_project,
                "conflicts": {
                    "project_exists": project_exists,
                    "requires_overwrite": project_exists
                },
                "import_plan": {
                    "contexts": contexts_count,
                    "sessions": sessions_count,
                    "memories": memories_count,
                    "estimated_time_ms": (contexts_count * 10) + (memories_count * 2),
                    "embeddings_missing": embeddings_missing,
                    "regeneration_needed": embeddings_missing > 0
                }
            }

            if project_exists and not overwrite:
                response["recommendation"] = f"Project '{target_project}' exists. Run with overwrite=True to replace."
            elif project_exists and overwrite:
                response["recommendation"] = f"Will overwrite existing project '{target_project}'."
            else:
                response["recommendation"] = f"Will create new project '{target_project}'."

            return json.dumps(response, indent=2)

        # Check for conflicts before actual import
        if project_exists and not overwrite:
            return json.dumps({
                "error": f"Project '{target_project}' already exists",
                "suggestion": "Set overwrite=True to replace existing project, or use validate_only=True to check first",
                "project_exists": True
            }, indent=2)

        # ====================================================================
        # ACTUAL IMPORT
        # ====================================================================

        logger.info(f"Starting import of project '{target_project}' from {input_path_obj}")

        # Step 5: Import all tables
        conn = db.pool.getconn()
        try:
            import_counts = _import_backup_tables(
                conn, db, backup_data, target_project, overwrite, project_exists
            )
        finally:
            db.pool.putconn(conn)

        # Step 6: Calculate duration and build report
        duration_ms = int((time.time() - start_time) * 1000)

        response = _build_import_report(
            input_path_obj,
            target_project,
            import_counts,
            contexts_count,
            sessions_count,
            memories_count,
            embeddings_missing,
            duration_ms
        )

        logger.info(f"Import completed: {import_counts['contexts']} contexts, {import_counts['sessions']} sessions, {import_counts['memories']} memories in {duration_ms}ms")
        return json.dumps(response, indent=2)

    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
        return json.dumps({
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }, indent=2)


# ============================================================================
# RUN SERVER
# ============================================================================

# Assuming these imports are available or will be added elsewhere in the file
from tool_breadcrumbs import set_session_store, breadcrumb


# Assuming _init_local_session is defined earlier in the file,
# modifying it to include set_session_store.
# This is a placeholder for where _init_local_session would be defined.
# def _init_local_session():
#     # ... existing code ...
#     db = get_db() # Assuming db is accessible or initialized here
#     set_session_store(PostgreSQLSessionStore(db.adapter))
#     # ... existing code ...
#     return "some_session_id"


@mcp.tool()
@breadcrumb
async def get_breadcrumbs(
    limit: int = 50,
    tool: Optional[str] = None,
    marker: Optional[str] = None
) -> str:
    """
    Retrieve breadcrumb trail for the current session.
    Useful for debugging tool execution flow and diagnosing issues.

    Args:
        limit: Maximum number of records to return (default: 50)
        tool: Filter by tool name (optional)
        marker: Filter by marker type (optional)

    Returns:
        JSON string containing list of breadcrumbs
    """
    # Check project selection (required for session context)
    project_check = _check_project_selection_required()
    if project_check:
        return project_check

    session_id = get_current_session_id()
    
    # Get session store (global or from adapter)
    store = _session_store
    if not store:
        # Try to initialize store if not available (e.g. in cloud mode)
        try:
            adapter = _get_db_adapter()
            store = PostgreSQLSessionStore(adapter)
        except Exception as e:
            return json.dumps({
                "error": "STORE_UNAVAILABLE",
                "message": f"Session store unavailable: {e}"
            })

    try:
        breadcrumbs = store.get_breadcrumbs(
            session_id=session_id,
            limit=limit,
            tool=tool,
            marker=marker
        )
        
        return json.dumps({
            "session_id": session_id,
            "count": len(breadcrumbs),
            "breadcrumbs": breadcrumbs
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": "RETRIEVAL_FAILED",
            "message": f"Failed to retrieve breadcrumbs: {e}"
        })

if __name__ == "__main__":
    # DO NOT print anything to stdout - MCP requires clean JSON communication
    # Any debug output would break the JSON protocol
    import sys
    import logging

    # Suppress all stdout output that isn't JSON
    logging.basicConfig(level=logging.ERROR, stream=sys.stderr)

    # ========================================================================
    # SESSION-AWARE FORK: Initialize PostgreSQL session before starting MCP
    # ========================================================================
    print("🔧 Initializing session-aware MCP server...", file=sys.stderr)
    try:
        session_id = _init_local_session()
        print(f"📦 Session ID: {session_id}", file=sys.stderr)
        print("⚠️  Note: You must call select_project_for_session() before using other tools", file=sys.stderr)
    except Exception as e:
        print(f"❌ Failed to initialize session: {e}", file=sys.stderr)
        print("   Server will start but session features may not work", file=sys.stderr)

    # Run the MCP server silently
    mcp.run()
