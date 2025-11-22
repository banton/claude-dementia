"""
Async PostgreSQL Adapter for Claude Dementia
Uses asyncpg for non-blocking database operations.

Replaces the blocking psycopg2-based PostgreSQLAdapter with fully async
asyncpg implementation to eliminate event loop blocking in async middleware.
"""

import os
import asyncpg
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
import subprocess
import hashlib
import re

load_dotenv()


class PostgreSQLAdapterAsync:
    """
    Fully async PostgreSQL adapter using asyncpg.

    Key differences from sync adapter:
    - All methods are async (require await)
    - Uses asyncpg.Pool for connection pooling
    - SQL placeholders: $1, $2, $3 (not %s)
    - Returns list of dicts (no cursor needed)
    - Non-blocking database operations
    """

    def __init__(self, database_url: Optional[str] = None, schema: Optional[str] = None):
        """
        Initialize async adapter.

        Args:
            database_url: PostgreSQL connection string (default: from DATABASE_URL env)
            schema: Schema name (default: auto-detect from project)
        """
        self.database_url = database_url or os.getenv('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")

        self.schema = schema or self._get_schema_name()
        self._pool: Optional[asyncpg.Pool] = None

    def _get_schema_name(self) -> str:
        """Auto-detect schema from project directory (same logic as sync adapter)."""
        schema = os.getenv('DEMENTIA_SCHEMA')
        if schema:
            return schema

        project_name = self._detect_project_name()
        return self._sanitize_identifier(project_name)

    def _detect_project_name(self) -> str:
        """Detect project name from git repo or directory."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                capture_output=True,
                text=True,
                check=True
            )
            repo_path = result.stdout.strip()
            return os.path.basename(repo_path)
        except:
            return os.path.basename(os.getcwd())

    def _sanitize_identifier(self, name: str) -> str:
        """Sanitize identifier for PostgreSQL schema name."""
        safe_name = re.sub(r'[^a-z0-9_]', '_', name.lower())
        safe_name = re.sub(r'_+', '_', safe_name)
        safe_name = safe_name.strip('_')[:63]
        return safe_name or 'default'

    async def get_pool(self) -> asyncpg.Pool:
        """
        Get or create connection pool.

        Returns:
            asyncpg.Pool: Connection pool
        """
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=30,
                server_settings={
                    'application_name': 'claude_dementia_async'
                }
            )
        return self._pool

    async def execute_query(
        self,
        query: str,
        params: Optional[List[Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute SELECT query and return rows as list of dicts.

        Args:
            query: SQL query with $1, $2, $3 placeholders (asyncpg style)
            params: Query parameters

        Returns:
            List of dictionaries (one per row)

        Example:
            rows = await adapter.execute_query(
                "SELECT * FROM contexts WHERE label = $1",
                ["api_spec"]
            )
        """
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            # Set search_path to project schema
            await conn.execute(f"SET search_path TO {self.schema}")

            # Execute query
            rows = await conn.fetch(query, *(params or []))

            # Convert asyncpg.Record to dict
            return [dict(row) for row in rows]

    async def execute_update(
        self,
        query: str,
        params: Optional[List[Any]] = None
    ) -> str:
        """
        Execute INSERT/UPDATE/DELETE query.

        Args:
            query: SQL query with $1, $2, $3 placeholders
            params: Query parameters

        Returns:
            Result status string (e.g., "INSERT 0 1")

        Example:
            result = await adapter.execute_update(
                "INSERT INTO contexts (label, content) VALUES ($1, $2)",
                ["api_spec", "API documentation..."]
            )
        """
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"SET search_path TO {self.schema}")
            result = await conn.execute(query, *(params or []))
            return result

    async def ensure_schema_exists(self):
        """Create schema and tables if they don't exist."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            # Create schema
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            await conn.execute(f"SET search_path TO {self.schema}")

            # Create tables (copied from sync adapter)
            await self._create_tables(conn)

    async def _create_tables(self, conn):
        """Create all required tables."""
        # Sessions table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                project_name TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
                status TEXT DEFAULT 'active',
                client_info JSONB DEFAULT '{}'::jsonb
            )
        """)

        # Context locks table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS context_locks (
                id SERIAL PRIMARY KEY,
                label TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1.0',
                content TEXT NOT NULL,
                preview TEXT,
                key_concepts TEXT[],
                tags TEXT[],
                priority TEXT DEFAULT 'reference',
                locked_at TIMESTAMPTZ DEFAULT NOW(),
                session_id TEXT,
                embedding vector(1024),
                UNIQUE(label, version)
            )
        """)

        # Memory entries table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id SERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # File tags table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS file_tags (
                id SERIAL PRIMARY KEY,
                path TEXT NOT NULL,
                tag TEXT NOT NULL,
                value TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(path, tag)
            )
        """)

        # Context archives table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS context_archives (
                id SERIAL PRIMARY KEY,
                label TEXT NOT NULL,
                version TEXT NOT NULL,
                content TEXT NOT NULL,
                deleted_at TIMESTAMPTZ DEFAULT NOW(),
                deleted_by TEXT
            )
        """)

    async def test_connection(self) -> bool:
        """Test database connection."""
        try:
            pool = await self.get_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False

    async def close(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    def get_info(self) -> dict:
        """Get adapter info (non-async for compatibility)."""
        return {
            'database_url': self.database_url.split('@')[1] if '@' in self.database_url else 'unknown',
            'schema': self.schema,
            'pool_active': self._pool is not None,
            'adapter_type': 'async'
        }
