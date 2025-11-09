"""
PostgreSQL Adapter for Claude Dementia

Implements project-based schema isolation for cloud-hosted PostgreSQL.
Each project automatically gets its own schema based on directory/git repo name.

Schema naming: {project_name}
- Auto-detects from git repository name or directory basename
- No manual configuration needed
- One MCP server = One user, schemas separate projects

Examples:
    /Users/banton/Sites/innkeeper/        → Schema: innkeeper
    /Users/banton/Sites/linkedin-posts/   → Schema: linkedin_posts
    /Users/banton/Sites/claude-dementia/  → Schema: claude_dementia

Usage:
    # Set environment variable in .env
    DATABASE_URL=postgresql://user:pass@host/dbname

    # Adapter auto-detects project from working directory
    from postgres_adapter import PostgreSQLAdapter
    adapter = PostgreSQLAdapter()
    conn = adapter.get_connection()

    # Optional override for testing
    DEMENTIA_SCHEMA=test_schema
"""

import os
import sys
import hashlib
import time
import random
import concurrent.futures
import psycopg2
from psycopg2 import pool, sql, OperationalError
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from typing import Optional
from contextlib import contextmanager
import json

# Load environment variables
load_dotenv()

# Shared connection pool across all schemas (prevents pool exhaustion)
# All schemas share the same database, so we only need one pool
_shared_pool = None
_shared_pool_lock = None

def _get_shared_pool(database_url: str):
    """
    Get or create the shared connection pool.

    CRITICAL: All schemas share one pool to prevent connection exhaustion.
    With Neon free tier (10 connections), we can't afford separate pools per schema.
    """
    global _shared_pool, _shared_pool_lock

    if _shared_pool is None:
        import threading
        if _shared_pool_lock is None:
            _shared_pool_lock = threading.Lock()

        with _shared_pool_lock:
            if _shared_pool is None:  # Double-check after acquiring lock
                max_retries = 5
                initial_delay = 2.0
                delay = initial_delay

                for attempt in range(max_retries):
                    try:
                        # Shared pool for ALL schemas (schema set via search_path per connection)
                        # Neon free tier: 10 connections total
                        # Stdio mode: max 3 concurrent uses across all schemas
                        _shared_pool = psycopg2.pool.SimpleConnectionPool(
                            1,  # min_connections: 1 (always keep one alive)
                            3,  # max_connections: 3 (sufficient for stdio, prevents exhaustion)
                            database_url,
                            cursor_factory=RealDictCursor,
                            connect_timeout=15
                        )
                        print(f"✅ Shared PostgreSQL connection pool initialized (min=1, max=3)", file=sys.stderr)
                        break
                    except Exception as e:
                        error_msg = str(e).lower()
                        is_cold_start = any(keyword in error_msg for keyword in [
                            'ssl', 'timeout', 'connection refused', 'temporarily unavailable',
                            'could not connect', 'server closed the connection',
                            'connection timed out', 'network unreachable', 'suspended'
                        ])

                        if is_cold_start and attempt < max_retries - 1:
                            jitter = random.uniform(0, delay * 0.3)
                            wait_time = delay + jitter
                            print(f"⏳ Neon database wakeup (attempt {attempt + 1}/{max_retries}), retrying in {wait_time:.2f}s...", file=sys.stderr)
                            time.sleep(wait_time)
                            delay *= 2
                        else:
                            raise ConnectionError(f"Failed to create shared connection pool after {max_retries} attempts: {e}")

    return _shared_pool


class PostgreSQLAdapter:
    """
    PostgreSQL database adapter with schema-based multi-tenancy.

    Features:
    - Connection pooling for performance
    - Automatic schema creation and migration
    - Schema-based isolation (set search_path per connection)
    - Compatible with existing SQLite-based code (dict-like rows)
    """

    def __init__(self, database_url: Optional[str] = None, schema: Optional[str] = None):
        """
        Initialize PostgreSQL adapter.

        Args:
            database_url: PostgreSQL connection URL (default: from DATABASE_URL env var)
            schema: Schema name for isolation (default: auto-generated from project)
        """
        self.database_url = database_url or os.getenv('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")

        # Determine schema name
        self.schema = schema or self._get_schema_name()

        # Use shared connection pool (prevents pool exhaustion with multiple schemas)
        # CRITICAL: All schemas share one pool since they're on the same database
        # Schema isolation is achieved via search_path on each connection
        self.pool = _get_shared_pool(self.database_url)

    def _get_schema_name(self) -> str:
        """
        Generate schema name for project isolation.

        Auto-detects project name from:
        1. DEMENTIA_SCHEMA environment variable (explicit override for testing)
        2. Git repository name (if in a git repo)
        3. Current directory basename (fallback)

        Returns:
            str: Schema name (e.g., "innkeeper" or "my_project")
        """
        # Priority 1: Explicit schema name (for testing/debugging)
        if os.getenv('DEMENTIA_SCHEMA'):
            return os.getenv('DEMENTIA_SCHEMA')

        # Priority 2: Detect and sanitize project name
        project_name = self._detect_project_name()
        return self._sanitize_identifier(project_name)

    def _detect_project_name(self) -> str:
        """
        Auto-detect project name from git repo or directory.

        Returns:
            str: Project name (e.g., "innkeeper", "linkedin-posts")
        """
        cwd = os.getcwd()

        # Try to get git repo name
        try:
            git_dir = cwd
            while git_dir != '/':
                if os.path.exists(os.path.join(git_dir, '.git')):
                    # Found git root - use this directory name
                    return os.path.basename(git_dir)
                git_dir = os.path.dirname(git_dir)
        except:
            pass

        # Fallback: use current directory basename
        return os.path.basename(cwd) or 'default'

    def _sanitize_identifier(self, name: str) -> str:
        """
        Sanitize string for use as PostgreSQL identifier.

        Rules:
        - Lowercase
        - Replace spaces/special chars with underscores
        - Remove consecutive underscores
        - Limit length to 32 chars
        """
        import re
        # Lowercase and replace non-alphanumeric with underscore
        safe = re.sub(r'[^a-z0-9]', '_', name.lower())
        # Remove consecutive underscores
        safe = re.sub(r'_+', '_', safe)
        # Remove leading/trailing underscores
        safe = safe.strip('_')
        # Limit length
        return safe[:32]

    def _validate_connection(self, conn):
        """
        Validate that connection is alive and ready to use.

        Neon may close idle connections when autosuspending (after 5 min inactivity).
        This prevents "SSL connection closed unexpectedly" errors.

        Args:
            conn: psycopg2 connection from pool

        Returns:
            bool: True if connection is valid, False if stale/closed

        Raises:
            Exception: Re-raises non-connection errors (e.g., permission errors)
        """
        try:
            # Quick ping to check if connection is alive
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            # Connection is stale/closed (Neon autosuspend or network issue)
            error_msg = str(e).lower()
            is_stale = any(keyword in error_msg for keyword in [
                'ssl', 'closed', 'terminated', 'broken', 'connection reset',
                'server closed the connection', 'connection lost'
            ])

            if is_stale:
                print(f"⚠️  Stale connection detected: {e}", file=sys.stderr)
                return False
            else:
                # Not a stale connection error - re-raise
                raise

    def get_connection(self, max_retries=5, initial_delay=2.0):
        """
        Get a validated connection from the pool with schema isolation applied.

        Implements:
        1. Connection validation to detect stale connections (Neon autosuspend)
        2. Automatic refresh of stale connections (transparent to caller)
        3. Retry logic for Neon database cold starts (compute autoscaling)

        Neon databases "sleep" after 5 min inactivity and close pooled connections.
        This method validates connections before returning them, ensuring no
        "SSL connection closed unexpectedly" errors reach the caller.

        Args:
            max_retries: Maximum connection attempts (default: 5)
            initial_delay: Initial retry delay in seconds (default: 2.0, doubles each retry)

        Returns:
            psycopg2.connection: Validated database connection with search_path set to schema

        Raises:
            OperationalError: If all retry attempts fail or all pooled connections are stale
        """
        last_error = None
        delay = initial_delay

        for attempt in range(max_retries):
            try:
                # Add timeout to prevent indefinite hang if pool is exhausted
                # Use concurrent.futures for timeout support
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self.pool.getconn)
                    try:
                        conn = future.result(timeout=10.0)  # 10 second timeout
                    except concurrent.futures.TimeoutError:
                        raise OperationalError("Connection pool timeout: no connections available after 10s. Pool may be exhausted due to connection leaks.")

                # VALIDATION LOOP: Check if connection is alive (handles Neon autosuspend)
                # Try up to 2 times to get a fresh connection if stale
                MAX_VALIDATION_ATTEMPTS = 2
                for validation_attempt in range(MAX_VALIDATION_ATTEMPTS):
                    if self._validate_connection(conn):
                        # ✅ Connection is alive, continue to setup
                        break
                    else:
                        # ❌ Connection is stale (Neon autosuspended), get fresh one
                        if validation_attempt < MAX_VALIDATION_ATTEMPTS - 1:
                            print(f"🔄 Refreshing stale connection (validation attempt {validation_attempt + 2}/{MAX_VALIDATION_ATTEMPTS})",
                                  file=sys.stderr)
                            try:
                                conn.close()
                            except:
                                pass
                            # Get new connection from pool
                            conn = self.pool.getconn()
                        else:
                            # All validation attempts failed
                            raise OperationalError("Failed to get valid connection: all pooled connections are stale")

                # CRITICAL FIX: search_path is now set at ROLE level (see ensure_schema_exists)
                # Only set statement_timeout per-connection (compatible with Neon transaction pooling)
                with conn.cursor() as cur:
                    # Set statement timeout (30 seconds)
                    # This is OK per-connection even with transaction pooling
                    cur.execute("SET statement_timeout = '30s'")

                # Connection successful
                if attempt > 0:
                    print(f"✅ Connection established after {attempt + 1} attempts", file=sys.stderr)

                return conn

            except (OperationalError, Exception) as e:
                last_error = e
                error_msg = str(e).lower()

                # Check if it's a cold start error (SSL, connection timeout, network issues, etc.)
                is_cold_start = any(keyword in error_msg for keyword in [
                    'ssl', 'timeout', 'connection refused', 'temporarily unavailable',
                    'could not connect', 'server closed the connection',
                    'connection timed out', 'network unreachable'
                ])

                if is_cold_start and attempt < max_retries - 1:
                    # Add random jitter to prevent thundering herd
                    jitter = random.uniform(0, delay * 0.3)
                    wait_time = delay + jitter
                    print(f"⏳ Neon cold start detected (attempt {attempt + 1}/{max_retries}), retrying in {wait_time:.2f}s...", file=sys.stderr)
                    time.sleep(wait_time)
                    delay *= 2  # Exponential backoff
                else:
                    # Not a cold start error, or final attempt - re-raise
                    break

        # All retries exhausted
        print(f"❌ Connection failed after {max_retries} attempts: {last_error}", file=sys.stderr)
        raise last_error

    def release_connection(self, conn):
        """Return connection to the pool."""
        self.pool.putconn(conn)

    @contextmanager
    def connection(self, max_retries=5, initial_delay=2.0):
        """
        Context manager for safe connection handling.

        Ensures connections are always returned to the pool, even if exceptions occur.

        Usage:
            with adapter.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM table")
                    # Connection automatically released on exit

        Args:
            max_retries: Maximum connection attempts (default: 5)
            initial_delay: Initial retry delay in seconds (default: 2.0)

        Yields:
            psycopg2.connection: Database connection with search_path set
        """
        conn = self.get_connection(max_retries=max_retries, initial_delay=initial_delay)
        try:
            yield conn
        finally:
            self.release_connection(conn)

    def ensure_schema_exists(self):
        """
        Ensure schema exists and has required tables.
        Creates schema and runs migrations if needed.

        CRITICAL FIX for Neon transaction pooling:
        Uses ALTER ROLE to set search_path permanently instead of per-connection SET.
        This is required because Neon uses pool_mode=transaction where SET statements
        only last one transaction, causing connection pool exhaustion.
        """
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                # Create schema if not exists
                cur.execute(
                    sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                        sql.Identifier(self.schema)
                    )
                )

                # CRITICAL FIX: Set search_path at ROLE level (not session level)
                # This persists across all connections for this role, compatible with Neon transaction pooling
                # Extract role name from connection
                cur.execute("SELECT CURRENT_USER")
                role_name = cur.fetchone()['current_user']

                # Set search_path permanently for this role
                # This replaces the per-connection SET which doesn't work with Neon's pool_mode=transaction
                cur.execute(
                    sql.SQL("ALTER ROLE {} SET search_path TO {}, public").format(
                        sql.Identifier(role_name),
                        sql.Identifier(self.schema)
                    )
                )
                print(f"✅ Set search_path for role '{role_name}' to '{self.schema}, public'", file=sys.stderr)

                # Create tables (PostgreSQL syntax)
                self._create_tables(cur)

                conn.commit()
                print(f"✅ Schema '{self.schema}' ready with all tables", file=sys.stderr)
        finally:
            self.pool.putconn(conn)

    def _create_tables(self, cur):
        """Create all required tables in current schema."""

        # Sessions table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                started_at DOUBLE PRECISION,
                last_active DOUBLE PRECISION,
                project_fingerprint TEXT,
                project_path TEXT,
                project_name TEXT,
                summary TEXT
            )
        """)

        # Context locks table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS context_locks (
                id SERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                label TEXT NOT NULL,
                version TEXT,
                content TEXT,
                content_hash TEXT,
                metadata TEXT,
                tags TEXT,
                locked_at DOUBLE PRECISION,
                last_accessed DOUBLE PRECISION,
                access_count INTEGER DEFAULT 0,
                preview TEXT,
                key_concepts TEXT,
                embedding BYTEA,
                embedding_model TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # Audit trail table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_trail (
                id SERIAL PRIMARY KEY,
                timestamp DOUBLE PRECISION,
                session_id TEXT,
                action TEXT,
                target_type TEXT,
                target_id TEXT,
                details TEXT,
                user_id TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # Memory entries table (for handovers)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id SERIAL PRIMARY KEY,
                session_id TEXT,
                timestamp DOUBLE PRECISION,
                category TEXT,
                content TEXT,
                metadata TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # File semantic model table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS file_semantic_model (
                id SERIAL PRIMARY KEY,
                session_id TEXT,
                file_path TEXT,
                file_size INTEGER,
                content_hash TEXT,
                modified_time DOUBLE PRECISION,
                hash_method TEXT,
                file_type TEXT,
                language TEXT,
                purpose TEXT,
                imports TEXT,
                exports TEXT,
                dependencies TEXT,
                used_by TEXT,
                contains TEXT,
                is_standard INTEGER,
                standard_type TEXT,
                warnings TEXT,
                cluster_name TEXT,
                related_files TEXT,
                last_scanned DOUBLE PRECISION,
                scan_duration_ms INTEGER,
                UNIQUE(session_id, file_path),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # File change history table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS file_change_history (
                id SERIAL PRIMARY KEY,
                session_id TEXT,
                file_path TEXT,
                change_type TEXT,
                timestamp DOUBLE PRECISION,
                old_hash TEXT,
                new_hash TEXT,
                size_delta INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # Query results cache table (for pagination)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS query_results_cache (
                query_id TEXT PRIMARY KEY,
                query_type TEXT,
                params TEXT,
                results TEXT,
                created_at DOUBLE PRECISION,
                expires_at DOUBLE PRECISION
            )
        """)

        # Todos table (permanent task tracking)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id SERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                active_form TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed')),
                created_at DOUBLE PRECISION NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL,
                completed_at DOUBLE PRECISION,
                priority TEXT,
                tags TEXT,
                metadata TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # Decisions table (track key decisions made during session)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id SERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                timestamp DOUBLE PRECISION NOT NULL,
                question TEXT NOT NULL,
                context TEXT,
                options TEXT,
                decision TEXT,
                rationale TEXT,
                status TEXT DEFAULT 'OPEN',
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # Context archives table (safe archival of deleted contexts)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS context_archives (
                id SERIAL PRIMARY KEY,
                original_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                label TEXT NOT NULL,
                version TEXT NOT NULL,
                content TEXT NOT NULL,
                preview TEXT,
                key_concepts TEXT,
                metadata TEXT,
                deleted_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP),
                delete_reason TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # File tags table (semantic file tagging)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS file_tags (
                id SERIAL PRIMARY KEY,
                path TEXT NOT NULL,
                tag TEXT NOT NULL,
                comment TEXT,
                created_at DOUBLE PRECISION,
                created_by TEXT,
                metadata TEXT,
                UNIQUE(path, tag)
            )
        """)

        # MCP sessions table (persistent session storage for cloud deployments)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mcp_sessions (
                session_id TEXT PRIMARY KEY,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_active TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                capabilities JSONB DEFAULT '{}',
                expires_at TIMESTAMP WITH TIME ZONE,
                client_info JSONB DEFAULT '{}'
            )
        """)

        # Create indexes for performance
        cur.execute("CREATE INDEX IF NOT EXISTS idx_context_locks_session ON context_locks(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_context_locks_label ON context_locks(label)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_trail_session ON audit_trail(session_id, timestamp DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_file_model_session ON file_semantic_model(session_id, file_path)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_file_changes_session ON file_change_history(session_id, timestamp DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_todos_session ON todos(session_id, status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status, updated_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_decisions_session ON decisions(session_id, timestamp DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_context_archives_session ON context_archives(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_context_archives_label ON context_archives(label, deleted_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_file_tags_path ON file_tags(path)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_file_tags_created ON file_tags(created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mcp_sessions_expires ON mcp_sessions(expires_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mcp_sessions_last_active ON mcp_sessions(last_active)")

        # Run migrations for existing schemas
        self._run_migrations(cur)

    def _run_migrations(self, cur):
        """Apply schema migrations to existing tables."""

        # Migration 1: Add session_id to memory_entries if missing
        try:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                AND table_name = 'memory_entries'
                AND column_name = 'session_id'
            """)
            if not cur.fetchone():
                print("⚠️  Migrating memory_entries: adding session_id column", file=sys.stderr)
                cur.execute("ALTER TABLE memory_entries ADD COLUMN session_id TEXT")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_entries_session ON memory_entries(session_id)")
        except Exception as e:
            # Table might not exist yet, that's okay
            pass

        # Migration 2: Add timestamp to memory_entries if missing
        try:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                AND table_name = 'memory_entries'
                AND column_name = 'timestamp'
            """)
            if not cur.fetchone():
                print("⚠️  Migrating memory_entries: adding timestamp column", file=sys.stderr)
                cur.execute("ALTER TABLE memory_entries ADD COLUMN timestamp DOUBLE PRECISION")
        except Exception as e:
            pass

        # Migration 3: Add category to memory_entries if missing
        try:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                AND table_name = 'memory_entries'
                AND column_name = 'category'
            """)
            if not cur.fetchone():
                print("⚠️  Migrating memory_entries: adding category column", file=sys.stderr)
                cur.execute("ALTER TABLE memory_entries ADD COLUMN category TEXT")
        except Exception as e:
            pass

        # Migration 4: Add summary to sessions if missing
        try:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                AND table_name = 'sessions'
                AND column_name = 'summary'
            """)
            if not cur.fetchone():
                print("⚠️  Migrating sessions: adding summary column", file=sys.stderr)
                cur.execute("ALTER TABLE sessions ADD COLUMN summary TEXT")
        except Exception as e:
            pass

        # Migration 5: Add UNIQUE constraint to file_semantic_model if missing
        try:
            cur.execute("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_schema = current_schema()
                AND table_name = 'file_semantic_model'
                AND constraint_type = 'UNIQUE'
            """)
            if not cur.fetchone():
                print("⚠️  Migrating file_semantic_model: adding UNIQUE constraint", file=sys.stderr)
                cur.execute("ALTER TABLE file_semantic_model ADD CONSTRAINT file_semantic_model_unique UNIQUE(session_id, file_path)")
        except Exception as e:
            pass

        # Migration 6: Add preview to context_locks if missing
        try:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                AND table_name = 'context_locks'
                AND column_name = 'preview'
            """)
            if not cur.fetchone():
                print("⚠️  Migrating context_locks: adding preview column", file=sys.stderr)
                cur.execute("ALTER TABLE context_locks ADD COLUMN preview TEXT")
        except Exception as e:
            pass

        # Migration 7: Add key_concepts to context_locks if missing
        try:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                AND table_name = 'context_locks'
                AND column_name = 'key_concepts'
            """)
            if not cur.fetchone():
                print("⚠️  Migrating context_locks: adding key_concepts column", file=sys.stderr)
                cur.execute("ALTER TABLE context_locks ADD COLUMN key_concepts TEXT")
        except Exception as e:
            pass

        # Migration 8: Add project_name to mcp_sessions if missing
        try:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                AND table_name = 'mcp_sessions'
                AND column_name = 'project_name'
            """)
            if not cur.fetchone():
                print("⚠️  Migrating mcp_sessions: adding project_name column", file=sys.stderr)
                cur.execute("ALTER TABLE mcp_sessions ADD COLUMN project_name TEXT DEFAULT '__PENDING__'")
                print("✅ Added project_name column to mcp_sessions", file=sys.stderr)
        except Exception as e:
            print(f"❌ Migration 8 failed: {e}", file=sys.stderr)

        # Migration 9: Add session_summary to mcp_sessions if missing
        try:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                AND table_name = 'mcp_sessions'
                AND column_name = 'session_summary'
            """)
            if not cur.fetchone():
                print("⚠️  Migrating mcp_sessions: adding session_summary column", file=sys.stderr)
                cur.execute("""
                    ALTER TABLE mcp_sessions
                    ADD COLUMN session_summary JSONB DEFAULT '{"work_done": [], "tools_used": [], "next_steps": [], "important_context": {}}'
                """)
                print("✅ Added session_summary column to mcp_sessions", file=sys.stderr)
        except Exception as e:
            print(f"❌ Migration 9 failed: {e}", file=sys.stderr)

        # Migration 10: Add index for project_name and last_active on mcp_sessions
        try:
            cur.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = current_schema()
                AND tablename = 'mcp_sessions'
                AND indexname = 'idx_sessions_project_active'
            """)
            if not cur.fetchone():
                print("⚠️  Migrating mcp_sessions: adding project+activity index", file=sys.stderr)
                cur.execute("CREATE INDEX idx_sessions_project_active ON mcp_sessions(project_name, last_active DESC)")
                print("✅ Added idx_sessions_project_active index", file=sys.stderr)
        except Exception as e:
            print(f"❌ Migration 10 failed: {e}", file=sys.stderr)

        # Migration 11: Update existing rows with project_name='default' to '__PENDING__'
        try:
            cur.execute("""
                UPDATE mcp_sessions
                SET project_name = '__PENDING__'
                WHERE project_name = 'default'
            """)
            updated_count = cur.rowcount
            if updated_count > 0:
                print(f"⚠️  Migration 11: Updated {updated_count} sessions from 'default' to '__PENDING__'", file=sys.stderr)
            print("✅ Migration 11 complete: Existing sessions updated", file=sys.stderr)
        except Exception as e:
            print(f"❌ Migration 11 failed: {e}", file=sys.stderr)

    def get_info(self) -> dict:
        """Get information about current database and schema."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Get PostgreSQL version
                cur.execute("SELECT version()")
                version = cur.fetchone()['version']

                # Get current database
                cur.execute("SELECT current_database()")
                database = cur.fetchone()['current_database']

                # Get current schema
                cur.execute("SELECT current_schema()")
                current_schema = cur.fetchone()['current_schema']

                # Get table count in current schema
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM information_schema.tables
                    WHERE table_schema = %s
                """, (self.schema,))
                table_count = cur.fetchone()['count']

                return {
                    "type": "postgresql",
                    "version": version.split('(')[0].strip(),
                    "database": database,
                    "schema": current_schema,
                    "configured_schema": self.schema,
                    "table_count": table_count,
                    "connection_pool": {
                        "min": 1,
                        "max": 1,
                        "note": "App-side pooling disabled - Neon pooler handles it"
                    }
                }
        finally:
            self.release_connection(conn)

    def close(self):
        """Close all connections in the pool."""
        if self.pool:
            self.pool.closeall()
            print(f"✅ PostgreSQL connection pool closed", file=sys.stderr)


# Convenience function for testing
def test_connection():
    """Test PostgreSQL connection and display info."""
    try:
        adapter = PostgreSQLAdapter()
        adapter.ensure_schema_exists()

        info = adapter.get_info()
        print("\n📊 Database Information:")
        print(json.dumps(info, indent=2))

        adapter.close()
        return True
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    # Run test when executed directly
    test_connection()
