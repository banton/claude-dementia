"""
MCP Session Store - PostgreSQL-backed persistent session storage.

Solves the critical UX issue where every deployment forces users to restart clients.
Sessions are stored in PostgreSQL instead of in-memory, surviving server restarts.

TDD Phase: GREEN - Minimal implementation to make tests pass.
"""

import uuid
import psycopg2
from psycopg2 import sql
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import json
import time


class PostgreSQLSessionStore:
    """
    PostgreSQL-backed MCP session storage for persistent sessions.

    Features:
    - Sessions survive server restarts
    - 24-hour expiration (sliding window)
    - Automatic cleanup of expired sessions
    - Retry logic for duplicate session IDs
    """

    def __init__(self, adapter):
        """
        Initialize session store with database connection pool.

        Args:
            adapter: PostgreSQLAdapter instance (Neon pooler)
        """
        self.adapter = adapter

    def create_session(
        self,
        session_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        client_info: Optional[Dict[str, Any]] = None,
        project_name: str = 'default'
    ) -> Dict[str, Any]:
        """
        Create a new MCP session.

        Args:
            session_id: Session ID from FastMCP (default: generate new)
            created_at: Session creation time (default: now)
            capabilities: MCP capabilities dict (default: {})
            client_info: Client metadata (default: {})
            project_name: Project name for this session (default: 'default')

        Returns:
            Session dict with session_id, created_at, last_active, expires_at, etc.

        Raises:
            psycopg2.Error: If database operation fails after retries
        """
        if created_at is None:
            created_at = datetime.now(timezone.utc)

        if capabilities is None:
            capabilities = {}

        if client_info is None:
            client_info = {}

        expires_at = created_at + timedelta(hours=24)

        # Use provided session_id or generate new one
        if session_id is None:
            # Retry up to 3 times for duplicate session ID
            max_retries = 3
            for attempt in range(max_retries):
                session_id = self._generate_session_id()

                conn = self.adapter.get_connection()
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO mcp_sessions (
                                session_id, created_at, last_active, expires_at, capabilities, client_info, project_name
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                            RETURNING session_id, created_at, last_active, expires_at, capabilities, client_info, project_name
                        """, (
                            session_id,
                            created_at,
                            created_at,
                            expires_at,
                            json.dumps(capabilities),
                            json.dumps(client_info),
                            project_name
                        ))

                        row = cur.fetchone()
                        conn.commit()

                        return {
                            'session_id': row['session_id'],
                            'created_at': row['created_at'],
                            'last_active': row['last_active'],
                            'expires_at': row['expires_at'],
                            'capabilities': json.loads(row['capabilities']) if isinstance(row['capabilities'], str) else row['capabilities'],
                            'client_info': json.loads(row['client_info']) if isinstance(row['client_info'], str) else row['client_info'],
                            'project_name': row['project_name']
                        }

                except psycopg2.errors.UniqueViolation:
                    # Duplicate session_id, retry with new ID
                    conn.rollback()
                    if attempt == max_retries - 1:
                        raise  # Last attempt failed, propagate error
                    continue  # Retry with new session_id

                finally:
                    self.adapter.release_connection(conn)

            # Should never reach here
            raise RuntimeError("Failed to create session after max retries")
        else:
            # Session ID provided - insert directly (no retry, let caller handle duplicates)
            conn = self.adapter.get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO mcp_sessions (
                            session_id, created_at, last_active, expires_at, capabilities, client_info, project_name
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING session_id, created_at, last_active, expires_at, capabilities, client_info, project_name
                    """, (
                        session_id,
                        created_at,
                        created_at,
                        expires_at,
                        json.dumps(capabilities),
                        json.dumps(client_info),
                        project_name
                    ))

                    row = cur.fetchone()
                    conn.commit()

                    return {
                        'session_id': row['session_id'],
                        'created_at': row['created_at'],
                        'last_active': row['last_active'],
                        'expires_at': row['expires_at'],
                        'capabilities': json.loads(row['capabilities']) if isinstance(row['capabilities'], str) else row['capabilities'],
                        'client_info': json.loads(row['client_info']) if isinstance(row['client_info'], str) else row['client_info'],
                        'project_name': row['project_name']
                    }

            finally:
                self.adapter.release_connection(conn)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session dict or None if not found
        """
        conn = self.adapter.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT session_id, created_at, last_active, expires_at, capabilities, client_info, project_name, session_summary
                    FROM mcp_sessions
                    WHERE session_id = %s
                """, (session_id,))

                row = cur.fetchone()
                if row is None:
                    return None

                return {
                    'session_id': row['session_id'],
                    'created_at': row['created_at'],
                    'last_active': row['last_active'],
                    'expires_at': row['expires_at'],
                    'capabilities': json.loads(row['capabilities']) if isinstance(row['capabilities'], str) else row['capabilities'],
                    'client_info': json.loads(row['client_info']) if isinstance(row['client_info'], str) else row['client_info'],
                    'project_name': row['project_name'],
                    'session_summary': row['session_summary'] if isinstance(row['session_summary'], dict) else json.loads(row['session_summary']) if row['session_summary'] else {}
                }

        finally:
            self.adapter.release_connection(conn)

    def is_expired(self, session_id: str, current_time: Optional[datetime] = None) -> bool:
        """
        Check if session is expired.

        Args:
            session_id: Session identifier
            current_time: Time to check against (default: now)

        Returns:
            True if expired, False if still valid
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        conn = self.adapter.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT expires_at
                    FROM mcp_sessions
                    WHERE session_id = %s
                """, (session_id,))

                row = cur.fetchone()
                if row is None:
                    return True  # Session not found = expired

                # Make current_time timezone-aware if needed
                if current_time.tzinfo is None:
                    current_time = current_time.replace(tzinfo=timezone.utc)

                return current_time > row['expires_at']

        finally:
            self.adapter.release_connection(conn)

    def update_activity(self, session_id: str, accessed_at: Optional[datetime] = None):
        """
        Update session's last_active timestamp and extend expiration.

        Args:
            session_id: Session identifier
            accessed_at: Access time (default: now)
        """
        if accessed_at is None:
            accessed_at = datetime.now(timezone.utc)

        expires_at = accessed_at + timedelta(hours=24)

        conn = self.adapter.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE mcp_sessions
                    SET last_active = %s, expires_at = %s
                    WHERE session_id = %s
                """, (accessed_at, expires_at, session_id))
                conn.commit()

        finally:
            self.adapter.release_connection(conn)

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session from the database.

        Args:
            session_id: Session identifier to delete

        Returns:
            True if session was deleted, False if session not found
        """
        conn = self.adapter.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM mcp_sessions
                    WHERE session_id = %s
                """, (session_id,))

                deleted = cur.rowcount > 0
                conn.commit()

                return deleted

        finally:
            self.adapter.release_connection(conn)

    def cleanup_expired(self, current_time: Optional[datetime] = None) -> int:
        """
        Delete expired sessions from database.

        Args:
            current_time: Time to check against (default: now)

        Returns:
            Number of sessions deleted
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        conn = self.adapter.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM mcp_sessions
                    WHERE expires_at < %s
                """, (current_time,))

                deleted = cur.rowcount
                conn.commit()

                return deleted

        finally:
            self.adapter.release_connection(conn)

    def get_projects_with_stats(self) -> list:
        """
        Get all projects with statistics for user selection.

        Returns:
            List of project dicts with:
            - project_name: Project name
            - context_locks: Count of locked contexts
            - last_used: Human-readable time (e.g., "2 days ago")
            - last_used_timestamp: ISO timestamp
        """
        conn = self.adapter.get_connection()
        try:
            with conn.cursor() as cur:
                # Get projects from mcp_sessions with last activity
                cur.execute("""
                    WITH project_stats AS (
                        SELECT
                            s.project_name,
                            MAX(s.last_active) as last_activity,
                            COUNT(DISTINCT c.id) as lock_count
                        FROM mcp_sessions s
                        LEFT JOIN context_locks c ON c.session_id = s.session_id
                        WHERE s.project_name IS NOT NULL
                        GROUP BY s.project_name
                    )
                    SELECT
                        project_name,
                        COALESCE(lock_count, 0) as context_locks,
                        last_activity
                    FROM project_stats
                    ORDER BY last_activity DESC NULLS LAST
                """)

                rows = cur.fetchall()

                # Convert to list of dicts with human-readable times
                projects = []
                now = datetime.now(timezone.utc)

                for row in rows:
                    last_activity = row['last_activity']

                    # Calculate human-readable time difference
                    if last_activity:
                        # Make timezone-aware if needed
                        if last_activity.tzinfo is None:
                            last_activity = last_activity.replace(tzinfo=timezone.utc)

                        delta = now - last_activity

                        if delta.days > 365:
                            time_str = f"{delta.days // 365} year{'s' if delta.days // 365 > 1 else ''} ago"
                        elif delta.days > 30:
                            time_str = f"{delta.days // 30} month{'s' if delta.days // 30 > 1 else ''} ago"
                        elif delta.days > 0:
                            time_str = f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
                        elif delta.seconds > 3600:
                            time_str = f"{delta.seconds // 3600} hour{'s' if delta.seconds // 3600 > 1 else ''} ago"
                        elif delta.seconds > 60:
                            time_str = f"{delta.seconds // 60} minute{'s' if delta.seconds // 60 > 1 else ''} ago"
                        else:
                            time_str = "just now"
                    else:
                        time_str = "never"

                    projects.append({
                        'project_name': row['project_name'],
                        'context_locks': row['context_locks'],
                        'last_used': time_str,
                        'last_used_timestamp': last_activity.isoformat() if last_activity else None
                    })

                return projects

        finally:
            self.adapter.release_connection(conn)

    def update_session_summary(
        self,
        session_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        result_summary: Optional[str] = None
    ) -> bool:
        """
        Incrementally update session summary with tool execution.

        Args:
            session_id: Session identifier
            tool_name: Tool that was executed
            tool_args: Tool arguments
            result_summary: Optional human-readable summary of result

        Returns:
            True if updated successfully, False otherwise
        """
        conn = self.adapter.get_connection()
        try:
            with conn.cursor() as cur:
                # Get current summary
                cur.execute("""
                    SELECT session_summary
                    FROM mcp_sessions
                    WHERE session_id = %s
                """, (session_id,))

                row = cur.fetchone()
                if row is None:
                    return False

                # Parse current summary
                summary = row['session_summary']
                if isinstance(summary, str):
                    summary = json.loads(summary)

                # Generate human-readable work description
                work_desc = self._generate_work_description(tool_name, tool_args, result_summary)
                if work_desc:
                    summary['work_done'].append(work_desc)

                # Add to tools_used if not already there
                if tool_name not in summary['tools_used']:
                    summary['tools_used'].append(tool_name)

                # Extract important context from specific tools
                if tool_name == 'lock_context':
                    topic = tool_args.get('topic')
                    if topic and result_summary:
                        summary['important_context'][topic] = result_summary

                # Update session_summary and last_active
                cur.execute("""
                    UPDATE mcp_sessions
                    SET session_summary = %s, last_active = %s
                    WHERE session_id = %s
                """, (json.dumps(summary), datetime.now(timezone.utc), session_id))

                conn.commit()
                return True

        finally:
            self.adapter.release_connection(conn)

    def _generate_work_description(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        result_summary: Optional[str]
    ) -> Optional[str]:
        """
        Generate human-readable description of work from tool execution.

        Args:
            tool_name: Tool name
            tool_args: Tool arguments
            result_summary: Optional result summary

        Returns:
            Human-readable work description or None
        """
        # Map tools to descriptions
        if tool_name == 'lock_context':
            topic = tool_args.get('topic', 'context')
            return f"Locked context: {topic}"

        elif tool_name == 'recall_context':
            topic = tool_args.get('topic', 'context')
            return f"Recalled context: {topic}"

        elif tool_name in ['wake_up', 'get_last_handover']:
            return "Reviewed previous session handover"

        elif tool_name == 'query_files':
            query = tool_args.get('query', '')
            return f"Searched files for: {query}"

        elif tool_name == 'scan_project_files':
            return "Scanned project files"

        elif tool_name in ['create_project', 'switch_project']:
            project = tool_args.get('name', '')
            return f"Switched to project: {project}"

        # Default: return None for generic tools (don't clutter summary)
        return None

    def finalize_handover(self, session_id: str, project_name: str) -> bool:
        """
        Finalize handover from session_summary and store in memory_entries.

        Args:
            session_id: Session identifier
            project_name: Project name for this session

        Returns:
            True if handover created successfully, False otherwise
        """
        conn = self.adapter.get_connection()
        try:
            with conn.cursor() as cur:
                # Get session with summary
                cur.execute("""
                    SELECT session_summary, created_at, last_active
                    FROM mcp_sessions
                    WHERE session_id = %s
                """, (session_id,))

                row = cur.fetchone()
                if row is None:
                    return False

                # Extract session_summary (already JSONB)
                summary = row['session_summary']
                if isinstance(summary, str):
                    summary = json.loads(summary)

                # Build handover JSON
                handover = {
                    'session_id': session_id,
                    'project_name': project_name,
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'finished_at': row['last_active'].isoformat() if row['last_active'] else None,
                    'work_done': summary.get('work_done', []),
                    'tools_used': summary.get('tools_used', []),
                    'next_steps': summary.get('next_steps', []),
                    'important_context': summary.get('important_context', {})
                }

                # Store in memory_entries
                cur.execute("""
                    INSERT INTO memory_entries (
                        session_id, timestamp, category, content, metadata
                    ) VALUES (%s, %s, %s, %s, %s)
                """, (
                    session_id,
                    time.time(),
                    'handover',
                    json.dumps(handover),
                    json.dumps({'project_name': project_name})
                ))

                conn.commit()
                return True

        finally:
            self.adapter.release_connection(conn)

    def _generate_session_id(self) -> str:
        """
        Generate unique session ID.

        Returns:
            12-character session ID (UUID fragment)
        """
        # Generate UUID and take first 12 chars for session ID
        return str(uuid.uuid4()).replace('-', '')[:12]
