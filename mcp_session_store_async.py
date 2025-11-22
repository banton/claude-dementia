"""
MCP Session Store Async - PostgreSQL-backed persistent session storage using asyncpg.

Async version of PostgreSQLSessionStore to eliminate event loop blocking.
"""

import uuid
import json
import time
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

class PostgreSQLSessionStoreAsync:
    """
    Async PostgreSQL-backed MCP session storage.
    
    Features:
    - Fully async operations (non-blocking)
    - Uses PostgreSQLAdapterAsync (asyncpg)
    - Compatible with MCPSessionPersistenceMiddleware
    """

    def __init__(self, adapter):
        """
        Initialize session store with async database adapter.

        Args:
            adapter: PostgreSQLAdapterAsync instance
        """
        self.adapter = adapter

    async def create_session(
        self,
        session_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        client_info: Optional[Dict[str, Any]] = None,
        project_name: str = 'default'
    ) -> Dict[str, Any]:
        """Create a new MCP session asynchronously."""
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

                try:
                    rows = await self.adapter.execute_query("""
                        INSERT INTO mcp_sessions (
                            session_id, created_at, last_active, expires_at, capabilities, client_info, project_name
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        RETURNING session_id, created_at, last_active, expires_at, capabilities, client_info, project_name
                    """, [
                        session_id,
                        created_at,
                        created_at,
                        expires_at,
                        json.dumps(capabilities),
                        json.dumps(client_info),
                        project_name
                    ])

                    if not rows:
                        raise RuntimeError("Failed to create session: no rows returned")
                    
                    row = rows[0]
                    return self._format_session_row(row)

                except Exception as e:
                    # Check for unique violation (asyncpg raises UniqueViolationError)
                    if "unique constraint" in str(e).lower() or "duplicate key" in str(e).lower():
                        if attempt == max_retries - 1:
                            raise
                        continue
                    raise

            raise RuntimeError("Failed to create session after max retries")
        else:
            # Session ID provided - insert directly
            rows = await self.adapter.execute_query("""
                INSERT INTO mcp_sessions (
                    session_id, created_at, last_active, expires_at, capabilities, client_info, project_name
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING session_id, created_at, last_active, expires_at, capabilities, client_info, project_name
            """, [
                session_id,
                created_at,
                created_at,
                expires_at,
                json.dumps(capabilities),
                json.dumps(client_info),
                project_name
            ])

            if not rows:
                raise RuntimeError("Failed to create session: no rows returned")
            
            row = rows[0]
            return self._format_session_row(row)

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session by ID asynchronously."""
        rows = await self.adapter.execute_query("""
            SELECT session_id, created_at, last_active, expires_at, capabilities, client_info, project_name, session_summary
            FROM mcp_sessions
            WHERE session_id = $1
        """, [session_id])

        if not rows:
            return None

        return self._format_session_row(rows[0])

    async def is_expired(self, session_id: str, current_time: Optional[datetime] = None) -> bool:
        """Check if session is expired asynchronously."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        rows = await self.adapter.execute_query("""
            SELECT expires_at
            FROM mcp_sessions
            WHERE session_id = $1
        """, [session_id])

        if not rows:
            return True  # Session not found = expired

        row = rows[0]
        # Make current_time timezone-aware if needed
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        return current_time > row['expires_at']

    async def update_activity(self, session_id: str, accessed_at: Optional[datetime] = None):
        """Update session's last_active timestamp and extend expiration asynchronously."""
        if accessed_at is None:
            accessed_at = datetime.now(timezone.utc)

        expires_at = accessed_at + timedelta(hours=24)

        await self.adapter.execute_update("""
            UPDATE mcp_sessions
            SET last_active = $1, expires_at = $2
            WHERE session_id = $3
        """, [accessed_at, expires_at, session_id])

    async def update_session_project(self, session_id: str, project_name: str) -> bool:
        """Update session's project_name field asynchronously."""
        result = await self.adapter.execute_update("""
            UPDATE mcp_sessions
            SET project_name = $1
            WHERE session_id = $2
        """, [project_name, session_id])
        
        # Result string format: "UPDATE <count>"
        return self._parse_rowcount(result) > 0

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session from the database asynchronously."""
        result = await self.adapter.execute_update("""
            DELETE FROM mcp_sessions
            WHERE session_id = $1
        """, [session_id])

        return self._parse_rowcount(result) > 0

    async def cleanup_expired(self, current_time: Optional[datetime] = None) -> int:
        """Delete expired sessions from database asynchronously."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        result = await self.adapter.execute_update("""
            DELETE FROM mcp_sessions
            WHERE expires_at < $1
        """, [current_time])

        return self._parse_rowcount(result)

    async def get_projects_with_stats(self) -> list:
        """Get all projects with statistics asynchronously."""
        rows = await self.adapter.execute_query("""
            SELECT
                project_name,
                MAX(last_active) as last_activity,
                0 as lock_count
            FROM mcp_sessions
            WHERE project_name IS NOT NULL
              AND project_name != '__PENDING__'
            GROUP BY project_name
            ORDER BY last_activity DESC NULLS LAST
        """)

        projects = []
        now = datetime.now(timezone.utc)

        for row in rows:
            last_activity = row['last_activity']
            
            # Calculate human-readable time difference
            if last_activity:
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=timezone.utc)

                delta = now - last_activity
                time_str = self._format_time_delta(delta)
            else:
                time_str = "never"

            projects.append({
                'project_name': row['project_name'],
                'context_locks': row['lock_count'],
                'last_used': time_str,
                'last_used_timestamp': last_activity.isoformat() if last_activity else None
            })

        return projects

    async def update_session_summary(
        self,
        session_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        result_summary: Optional[str] = None
    ) -> bool:
        """Incrementally update session summary asynchronously."""
        # Get current summary
        rows = await self.adapter.execute_query("""
            SELECT session_summary
            FROM mcp_sessions
            WHERE session_id = $1
        """, [session_id])

        if not rows:
            return False

        row = rows[0]
        summary = row['session_summary']
        if isinstance(summary, str):
            summary = json.loads(summary)
        elif summary is None:
            summary = {'work_done': [], 'tools_used': [], 'next_steps': [], 'important_context': {}}

        # Ensure structure exists
        if 'work_done' not in summary: summary['work_done'] = []
        if 'tools_used' not in summary: summary['tools_used'] = []
        if 'important_context' not in summary: summary['important_context'] = {}

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
        await self.adapter.execute_update("""
            UPDATE mcp_sessions
            SET session_summary = $1, last_active = $2
            WHERE session_id = $3
        """, [json.dumps(summary), datetime.now(timezone.utc), session_id])

        return True

    async def finalize_handover(self, session_id: str, project_name: str) -> bool:
        """Finalize handover asynchronously."""
        rows = await self.adapter.execute_query("""
            SELECT session_summary, created_at, last_active
            FROM mcp_sessions
            WHERE session_id = $1
        """, [session_id])

        if not rows:
            return False

        row = rows[0]
        summary = row['session_summary']
        if isinstance(summary, str):
            summary = json.loads(summary)
        elif summary is None:
            summary = {}

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

        await self.adapter.execute_update("""
            INSERT INTO memory_entries (
                session_id, timestamp, category, content, metadata
            ) VALUES ($1, $2, $3, $4, $5)
        """, [
            session_id,
            time.time(),
            'handover',
            json.dumps(handover),
            json.dumps({'project_name': project_name})
        ])

        return True

    async def store_breadcrumb(
        self,
        session_id: str,
        marker: str,
        tool: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store a breadcrumb asynchronously."""
        try:
            await self.adapter.execute_update("""
                INSERT INTO breadcrumbs (
                    session_id, timestamp, marker, tool, message, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6)
            """, [
                session_id,
                time.time(),
                marker,
                tool,
                message,
                json.dumps(metadata) if metadata else '{}'
            ])
            return True
        except Exception as e:
            print(f"⚠️  Failed to store breadcrumb: {e}", file=sys.stderr)
            return False

    async def get_breadcrumbs(
        self,
        session_id: str,
        limit: int = 50,
        tool: Optional[str] = None,
        marker: Optional[str] = None
    ) -> list:
        """Retrieve breadcrumbs asynchronously."""
        query = """
            SELECT timestamp, marker, tool, message, metadata
            FROM breadcrumbs
            WHERE session_id = $1
        """
        params = [session_id]
        param_idx = 2

        if tool:
            query += f" AND tool = ${param_idx}"
            params.append(tool)
            param_idx += 1

        if marker:
            query += f" AND marker = ${param_idx}"
            params.append(marker)
            param_idx += 1

        query += f" ORDER BY timestamp DESC LIMIT ${param_idx}"
        params.append(limit)

        rows = await self.adapter.execute_query(query, params)

        breadcrumbs = []
        for row in rows:
            breadcrumbs.append({
                'timestamp': datetime.fromtimestamp(row['timestamp'], timezone.utc).isoformat(),
                'marker': row['marker'],
                'tool': row['tool'],
                'message': row['message'],
                'metadata': json.loads(row['metadata']) if isinstance(row['metadata'], str) else row['metadata']
            })

        return breadcrumbs

    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        return str(uuid.uuid4()).replace('-', '')[:12]

    def _format_session_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Format session row for return."""
        return {
            'session_id': row['session_id'],
            'created_at': row['created_at'],
            'last_active': row['last_active'],
            'expires_at': row['expires_at'],
            'capabilities': json.loads(row['capabilities']) if isinstance(row['capabilities'], str) else row['capabilities'],
            'client_info': json.loads(row['client_info']) if isinstance(row['client_info'], str) else row['client_info'],
            'project_name': row['project_name'],
            'session_summary': row.get('session_summary') if isinstance(row.get('session_summary'), dict) else json.loads(row['session_summary']) if row.get('session_summary') else {}
        }

    def _parse_rowcount(self, result_str: str) -> int:
        """Parse row count from 'INSERT 0 1' or 'UPDATE 1' string."""
        try:
            parts = result_str.split()
            return int(parts[-1])
        except:
            return 0

    def _format_time_delta(self, delta: timedelta) -> str:
        """Format timedelta to human readable string."""
        if delta.days > 365:
            return f"{delta.days // 365} year{'s' if delta.days // 365 > 1 else ''} ago"
        elif delta.days > 30:
            return f"{delta.days // 30} month{'s' if delta.days // 30 > 1 else ''} ago"
        elif delta.days > 0:
            return f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
        elif delta.seconds > 3600:
            return f"{delta.seconds // 3600} hour{'s' if delta.seconds // 3600 > 1 else ''} ago"
        elif delta.seconds > 60:
            return f"{delta.seconds // 60} minute{'s' if delta.seconds // 60 > 1 else ''} ago"
        else:
            return "just now"

    def _generate_work_description(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        result_summary: Optional[str]
    ) -> Optional[str]:
        """Generate human-readable description of work from tool execution."""
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
