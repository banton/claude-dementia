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


class PostgreSQLSessionStore:
    """
    PostgreSQL-backed MCP session storage for persistent sessions.

    Features:
    - Sessions survive server restarts
    - 24-hour expiration (sliding window)
    - Automatic cleanup of expired sessions
    - Retry logic for duplicate session IDs
    """

    def __init__(self, pool):
        """
        Initialize session store with database connection pool.

        Args:
            pool: psycopg2 connection pool
        """
        self.pool = pool

    def create_session(
        self,
        session_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        client_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new MCP session.

        Args:
            session_id: Session ID from FastMCP (default: generate new)
            created_at: Session creation time (default: now)
            capabilities: MCP capabilities dict (default: {})
            client_info: Client metadata (default: {})

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

                conn = self.pool.getconn()
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO mcp_sessions (
                                session_id, created_at, last_active, expires_at, capabilities, client_info
                            ) VALUES (%s, %s, %s, %s, %s, %s)
                            RETURNING session_id, created_at, last_active, expires_at, capabilities, client_info
                        """, (
                            session_id,
                            created_at,
                            created_at,
                            expires_at,
                            json.dumps(capabilities),
                            json.dumps(client_info)
                        ))

                        row = cur.fetchone()
                        conn.commit()

                        return {
                            'session_id': row['session_id'],
                            'created_at': row['created_at'],
                            'last_active': row['last_active'],
                            'expires_at': row['expires_at'],
                            'capabilities': json.loads(row['capabilities']) if isinstance(row['capabilities'], str) else row['capabilities'],
                            'client_info': json.loads(row['client_info']) if isinstance(row['client_info'], str) else row['client_info']
                        }

                except psycopg2.errors.UniqueViolation:
                    # Duplicate session_id, retry with new ID
                    conn.rollback()
                    if attempt == max_retries - 1:
                        raise  # Last attempt failed, propagate error
                    continue  # Retry with new session_id

                finally:
                    self.pool.putconn(conn)

            # Should never reach here
            raise RuntimeError("Failed to create session after max retries")
        else:
            # Session ID provided - insert directly (no retry, let caller handle duplicates)
            conn = self.pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO mcp_sessions (
                            session_id, created_at, last_active, expires_at, capabilities, client_info
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING session_id, created_at, last_active, expires_at, capabilities, client_info
                    """, (
                        session_id,
                        created_at,
                        created_at,
                        expires_at,
                        json.dumps(capabilities),
                        json.dumps(client_info)
                    ))

                    row = cur.fetchone()
                    conn.commit()

                    return {
                        'session_id': row['session_id'],
                        'created_at': row['created_at'],
                        'last_active': row['last_active'],
                        'expires_at': row['expires_at'],
                        'capabilities': json.loads(row['capabilities']) if isinstance(row['capabilities'], str) else row['capabilities'],
                        'client_info': json.loads(row['client_info']) if isinstance(row['client_info'], str) else row['client_info']
                    }

            finally:
                self.pool.putconn(conn)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session dict or None if not found
        """
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT session_id, created_at, last_active, expires_at, capabilities, client_info
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
                    'client_info': json.loads(row['client_info']) if isinstance(row['client_info'], str) else row['client_info']
                }

        finally:
            self.pool.putconn(conn)

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

        conn = self.pool.getconn()
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
            self.pool.putconn(conn)

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

        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE mcp_sessions
                    SET last_active = %s, expires_at = %s
                    WHERE session_id = %s
                """, (accessed_at, expires_at, session_id))
                conn.commit()

        finally:
            self.pool.putconn(conn)

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

        conn = self.pool.getconn()
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
            self.pool.putconn(conn)

    def _generate_session_id(self) -> str:
        """
        Generate unique session ID.

        Returns:
            12-character session ID (UUID fragment)
        """
        # Generate UUID and take first 12 chars for session ID
        return str(uuid.uuid4()).replace('-', '')[:12]
