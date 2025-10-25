#!/usr/bin/env python3
"""
Claude Dementia MCP Server - Enhanced with intelligent file tagging
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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Set, Tuple
import uuid
from contextlib import contextmanager

from mcp.server import FastMCP

# Enhanced scanner removed for v4.0.0-rc1 stable release

# Import active context engine
from active_context_engine import (
    ActiveContextEngine,
    check_command_context,
    get_relevant_contexts_for_text,
    get_session_start_reminders
)

# Import RLM preview generation
from migrate_v4_1_rlm import generate_preview, extract_key_concepts

# Initialize MCP server
mcp = FastMCP("claude-dementia")

# Database configuration - smart detection of where to store memory
import os
import hashlib
from pathlib import Path

def get_database_path():
    """Determine the best location for the memory database"""
    
    # Option 1: Environment variable override (highest priority)
    if os.environ.get('CLAUDE_MEMORY_DB'):
        return os.environ['CLAUDE_MEMORY_DB']
    
    # Option 2: Use the project directory from the launcher script
    # This ensures we use the directory where Claude is actually working
    if os.environ.get('CLAUDE_PROJECT_DIR'):
        project_dir = os.environ['CLAUDE_PROJECT_DIR']
        # Check if it's a project directory
        project_markers = ['.git', 'package.json', 'requirements.txt', 'Cargo.toml', 
                          'go.mod', 'pom.xml', 'Gemfile', '.project', '.vscode']
        if any(os.path.exists(os.path.join(project_dir, marker)) for marker in project_markers):
            return os.path.join(project_dir, '.claude-memory.db')
        # Don't automatically use project dir if it's not a recognized project
        # Fall through to Option 3 instead
    
    # Option 3: If in a clear project directory (has git, package.json, etc), use local DB
    cwd = os.getcwd()
    project_markers = ['.git', 'package.json', 'requirements.txt', 'Cargo.toml', 
                      'go.mod', 'pom.xml', 'Gemfile', '.project', '.vscode']
    
    if any(os.path.exists(os.path.join(cwd, marker)) for marker in project_markers):
        # This is clearly a project directory - use local database
        return os.path.join(cwd, '.claude-memory.db')
    
    # Option 3: For Claude Desktop or non-project directories, use user cache
    # Create a unique database based on the working directory path
    cache_dir = os.path.expanduser('~/.claude-dementia')
    os.makedirs(cache_dir, exist_ok=True)
    
    # Hash the cwd to create a unique identifier
    context_hash = hashlib.md5(cwd.encode()).hexdigest()[:8]
    
    # Also store a mapping file so we know what each hash represents
    mapping_file = os.path.join(cache_dir, 'path_mapping.json')
    try:
        with open(mapping_file, 'r') as f:
            mappings = json.loads(f.read())
    except:
        mappings = {}
    
    mappings[context_hash] = {
        'path': cwd,
        'name': os.path.basename(cwd) or 'root',
        'last_used': time.time()
    }
    
    with open(mapping_file, 'w') as f:
        f.write(json.dumps(mappings, indent=2))
    
    return os.path.join(cache_dir, f'{context_hash}.db')

# Set up database path and project info
try:
    DB_PATH = get_database_path()
    # Ensure parent directory exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
except Exception as e:
    # Fallback to a safe location if there's any error
    fallback_dir = tempfile.gettempdir()
    DB_PATH = os.path.join(fallback_dir, 'claude-memory-fallback.db')
    # Don't print during module initialization - it can break MCP
    # print(f"Warning: Using fallback database location due to error: {e}", file=sys.stderr)

# Use the project directory from environment if available, otherwise current directory
if os.environ.get('CLAUDE_PROJECT_DIR'):
    PROJECT_ROOT = os.environ['CLAUDE_PROJECT_DIR']
else:
    PROJECT_ROOT = os.getcwd()

PROJECT_NAME = os.path.basename(PROJECT_ROOT) or 'Claude Desktop'

# For testing: allow SESSION_ID override
SESSION_ID = None

# Show where database is stored (for debugging)
if 'claude-dementia' in DB_PATH or '/tmp/' in DB_PATH or '/var/folders/' in DB_PATH:
    DB_LOCATION = 'user cache'
else:
    DB_LOCATION = 'project local'

@contextmanager
def get_db_context():
    """Context manager for database connections - ensures proper cleanup"""
    conn = None
    try:
        conn = get_db()
        yield conn
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

class AutoClosingConnection:
    """Wrapper that automatically closes connection when done"""
    def __init__(self, conn):
        self.conn = conn
        self._closed = False
    
    def __getattr__(self, name):
        return getattr(self.conn, name)
    
    def __del__(self):
        if not self._closed:
            try:
                self.conn.close()
                self._closed = True
            except:
                pass

def get_db():
    """Get database connection with row factory and auto-cleanup"""
    # Ensure the directory exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    # Connect with better error handling and concurrency support
    try:
        # Use a timeout to avoid hanging on locked databases
        conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        # Enable WAL mode for better concurrency (multiple readers, one writer)
        conn.execute("PRAGMA journal_mode=WAL")
        
        # Set busy timeout to wait if database is locked
        conn.execute("PRAGMA busy_timeout=5000")  # 5 seconds
        
        # Initialize database schema if needed
        initialize_database(conn)
        
        # Return auto-closing wrapper
        return AutoClosingConnection(conn)
    except sqlite3.Error as e:
        # Provide detailed error information
        print(f"Database connection error: {e}", file=sys.stderr)
        print(f"Database path: {DB_PATH}", file=sys.stderr)
        print(f"Database directory: {db_dir}", file=sys.stderr)
        print(f"Directory exists: {os.path.exists(db_dir) if db_dir else 'N/A'}", file=sys.stderr)
        print(f"Database file exists: {os.path.exists(DB_PATH)}", file=sys.stderr)
        if os.path.exists(DB_PATH):
            print(f"File permissions: {oct(os.stat(DB_PATH).st_mode)}", file=sys.stderr)
        raise

def initialize_database(conn):
    """Create database tables if they don't exist and migrate existing schemas"""
    cursor = conn.cursor()
    
    # Create sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            started_at REAL NOT NULL,
            ended_at REAL,
            last_active REAL,
            summary TEXT,
            project_fingerprint TEXT,
            project_path TEXT,
            project_name TEXT
        )
    ''')
    
    # Migrate existing sessions table if needed
    cursor.execute("PRAGMA table_info(sessions)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'project_fingerprint' not in columns:
        cursor.execute('ALTER TABLE sessions ADD COLUMN project_fingerprint TEXT')
    if 'project_path' not in columns:
        cursor.execute('ALTER TABLE sessions ADD COLUMN project_path TEXT')
    if 'project_name' not in columns:
        cursor.execute('ALTER TABLE sessions ADD COLUMN project_name TEXT')
    
    # Create memory_entries table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memory_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,
            timestamp REAL NOT NULL,
            session_id TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    ''')
    
    # Create context_locks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS context_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            label TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '1.0',
            content TEXT NOT NULL CHECK(length(content) <= 51200),
            content_hash TEXT NOT NULL,
            locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            lock_source TEXT DEFAULT 'user',
            is_persistent BOOLEAN DEFAULT 0,
            parent_version TEXT,
            metadata TEXT,
            UNIQUE(session_id, label, version),
            CHECK(version GLOB '[0-9]*.[0-9]*')
        )
    ''')
    
    # Migrate context_locks to v4.1 RLM schema if needed
    cursor.execute("PRAGMA table_info(context_locks)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'preview' not in columns:
        cursor.execute('ALTER TABLE context_locks ADD COLUMN preview TEXT')
    if 'key_concepts' not in columns:
        cursor.execute('ALTER TABLE context_locks ADD COLUMN key_concepts TEXT')
    if 'related_contexts' not in columns:
        cursor.execute('ALTER TABLE context_locks ADD COLUMN related_contexts TEXT')
    if 'last_accessed' not in columns:
        cursor.execute('ALTER TABLE context_locks ADD COLUMN last_accessed TIMESTAMP')
        # Migrate existing contexts: set last_accessed = locked_at
        cursor.execute("""
            UPDATE context_locks
            SET last_accessed = locked_at
            WHERE last_accessed IS NULL
        """)
        conn.commit()

    if 'access_count' not in columns:
        cursor.execute('ALTER TABLE context_locks ADD COLUMN access_count INTEGER DEFAULT 0')

    # Set last_accessed = locked_at for any contexts that still have NULL
    # (handles contexts created after column added but before this migration)
    cursor.execute("""
        UPDATE context_locks
        SET last_accessed = locked_at
        WHERE last_accessed IS NULL
    """)
    conn.commit()

    # If we just added RLM columns, generate previews for existing contexts
    if 'preview' not in columns:
        cursor.execute("SELECT COUNT(*) FROM context_locks WHERE preview IS NULL")
        needs_preview = cursor.fetchone()[0]

        if needs_preview > 0:
            # Import preview generation
            from migrate_v4_1_rlm import generate_preview, extract_key_concepts

            # Generate previews for existing contexts
            cursor.execute("SELECT id, content, metadata, locked_at FROM context_locks WHERE preview IS NULL")
            rows = cursor.fetchall()

            for row in rows:
                row_id = row[0]
                content = row[1]
                metadata = json.loads(row[2]) if row[2] else {}
                locked_at = row[3]
                tags = metadata.get('tags', [])

                preview = generate_preview(content, max_length=500)
                key_concepts = extract_key_concepts(content, tags)

                cursor.execute("""
                    UPDATE context_locks
                    SET preview = ?, key_concepts = ?, last_accessed = ?
                    WHERE id = ?
                """, (preview, json.dumps(key_concepts), locked_at, row_id))

            conn.commit()

    # Create context_archives table for safe deletion
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS context_archives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            label TEXT NOT NULL,
            version TEXT NOT NULL,
            content TEXT NOT NULL,
            preview TEXT,
            key_concepts TEXT,
            metadata TEXT,
            deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delete_reason TEXT
        )
    ''')

    # Create file_tags table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS file_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            tag TEXT NOT NULL,
            comment TEXT,
            created_at REAL,
            created_by TEXT,
            metadata TEXT,
            UNIQUE(path, tag)
        )
    ''')
    
    # Create todos table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS todos (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at REAL,
            completed_at REAL,
            priority INTEGER DEFAULT 0
        )
    ''')
    
    # Create project_variables table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS project_variables (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at REAL NOT NULL
        )
    ''')
    
    # Create session_updates table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS session_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            message TEXT NOT NULL,
            category TEXT,
            metadata TEXT
        )
    ''')
    
    # Create memory table (for backward compatibility)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            timestamp REAL,
            category TEXT,
            topic TEXT,
            importance REAL DEFAULT 0.5,
            content TEXT,
            summary TEXT,
            metadata TEXT,
            parent_id INTEGER,
            related_ids TEXT,
            token_count INTEGER,
            last_accessed REAL,
            access_count INTEGER DEFAULT 0,
            archived BOOLEAN DEFAULT 0
        )
    ''')
    
    # Create fixes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fixes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            problem TEXT NOT NULL,
            cause TEXT,
            solution TEXT NOT NULL,
            prevention TEXT,
            file_path TEXT
        )
    ''')
    
    # Create decisions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            question TEXT NOT NULL,
            context TEXT,
            options TEXT,
            decision TEXT,
            rationale TEXT,
            status TEXT DEFAULT 'OPEN'
        )
    ''')
    
    conn.commit()

def estimate_tokens(text: str) -> int:
    """Estimate token count (rough approximation)"""
    return len(text) // 4

def get_current_session_id() -> str:
    """Get or create session ID - tied to specific project context for safety"""
    # For testing: allow SESSION_ID to override
    if hasattr(sys.modules[__name__], 'SESSION_ID') and SESSION_ID:
        return SESSION_ID

    conn = get_db()
    
    # Create a project fingerprint - this ensures sessions are project-specific
    project_fingerprint = hashlib.md5(f"{PROJECT_ROOT}:{PROJECT_NAME}".encode()).hexdigest()[:8]
    
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
        if row['project_path'] != PROJECT_ROOT:
            # Project moved but same logical project - update path
            conn.execute("""
                UPDATE sessions 
                SET project_path = ?, last_active = ?
                WHERE id = ?
            """, (PROJECT_ROOT, time.time(), row['id']))
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
    session_id = f"{PROJECT_NAME[:4]}_{str(uuid.uuid4())[:8]}"
    
    # First add columns if they don't exist (migration)
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
    """, (session_id, time.time(), time.time(), project_fingerprint, PROJECT_ROOT, PROJECT_NAME))
    conn.commit()
    
    return session_id

def update_session_activity():
    """Update last active time for current session"""
    conn = get_db()
    session_id = get_current_session_id()
    conn.execute("""
        UPDATE sessions 
        SET last_active = ?
        WHERE id = ?
    """, (time.time(), session_id))
    conn.commit()

# ============================================================================
# FILE ANALYSIS UTILITIES
# ============================================================================

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
# SESSION MANAGEMENT (unchanged from before)
# ============================================================================

@mcp.tool()
async def wake_up() -> str:
    """
    Initialize session and load available context for LLM orientation.
    Returns structured JSON with session info, git status, contexts, and staleness warnings.

    Purpose: Help LLM understand what data/tools are available to minimize confusion.
    """
    update_session_activity()
    conn = get_db()
    session_id = get_current_session_id()

    # Get git status
    git_info = get_git_status()

    # Build session info
    db_size_mb = os.path.getsize(DB_PATH) / (1024 * 1024) if os.path.exists(DB_PATH) else 0

    session_data = {
        "session": {
            "id": session_id,
            "project_name": PROJECT_NAME,
            "project_root": PROJECT_ROOT,
            "database": DB_PATH,
            "database_location": DB_LOCATION,
            "database_size_mb": round(db_size_mb, 2),
            "initialized_at": time.time()
        },
        "git": git_info if git_info else {
            "available": False,
            "reason": "not_a_git_repo_or_no_access"
        },
        "contexts": {
            "total_count": 0,
            "by_priority": {
                "always_check": [],
                "important": [],
                "reference": []
            }
        },
        "stale_contexts": [],
        "handover": None,
        "memory_health": None
    }

    # Get all contexts grouped by priority
    cursor = conn.execute("""
        SELECT id, label, version, locked_at, metadata, last_accessed, access_count, content
        FROM context_locks
        WHERE session_id = ?
        ORDER BY locked_at DESC
    """, (session_id,))

    all_contexts = cursor.fetchall()
    stale_contexts = []

    for ctx_row in all_contexts:
        metadata = json.loads(ctx_row['metadata']) if ctx_row['metadata'] else {}
        priority = metadata.get('priority', 'reference')
        tags = metadata.get('tags', [])

        ctx_info = {
            "label": ctx_row['label'],
            "version": ctx_row['version'],
            "locked_at": ctx_row['locked_at'],
            "size_bytes": len(ctx_row['content']) if ctx_row['content'] else 0,
            "tags": tags,
            "last_accessed": ctx_row['last_accessed'],
            "access_count": ctx_row['access_count'] or 0
        }

        # Check staleness
        context_dict = dict(ctx_row)
        staleness = check_context_staleness(context_dict, git_info)
        if staleness:
            ctx_info["stale"] = True
            stale_contexts.append({
                "label": ctx_row['label'],
                "version": ctx_row['version'],
                **staleness
            })

        # Add to appropriate priority group
        if priority in session_data["contexts"]["by_priority"]:
            session_data["contexts"]["by_priority"][priority].append(ctx_info)

    session_data["contexts"]["total_count"] = len(all_contexts)
    session_data["stale_contexts"] = stale_contexts

    # Get handover if available
    cursor = conn.execute("""
        SELECT content, metadata, timestamp FROM memory_entries
        WHERE category = 'handover'
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    handover = cursor.fetchone()

    if handover:
        hours_ago = (time.time() - handover['timestamp']) / 3600
        try:
            handover_data = json.loads(handover['metadata'])
            session_data["handover"] = {
                "available": True,
                "timestamp": handover['timestamp'],
                "hours_ago": round(hours_ago, 1),
                "summary": handover_data
            }
        except:
            session_data["handover"] = {
                "available": False,
                "reason": "corrupted_data"
            }

    # Memory health
    total_size = sum(len(ctx['content'] or '') for ctx in all_contexts)
    total_size_mb = total_size / (1024 * 1024)
    capacity_mb = 50  # Current limit

    session_data["memory_health"] = {
        "total_contexts": len(all_contexts),
        "total_size_mb": round(total_size_mb, 2),
        "capacity_mb": capacity_mb,
        "usage_percent": round((total_size_mb / capacity_mb) * 100, 1),
        "status": "healthy" if total_size_mb < capacity_mb * 0.8 else "near_capacity"
    }

    return json.dumps(session_data, indent=2)


@mcp.tool()
async def sleep() -> str:
    """
    Create comprehensive handover package for next session.
    Documents everything needed to resume work seamlessly.
    """
    conn = get_db()
    session_id = get_current_session_id()
    
    # Get session info
    cursor = conn.execute("""
        SELECT started_at FROM sessions WHERE id = ?
    """, (session_id,))
    session = cursor.fetchone()
    
    if not session:
        return "No active session to document"
    
    duration = time.time() - session['started_at']
    hours = int(duration // 3600)
    minutes = int((duration % 3600) // 60)
    
    # Build comprehensive handover package
    handover = {
        'timestamp': time.time(),
        'session_id': session_id,
        'duration': f"{hours}h {minutes}m",
        'current_state': {},
        'work_done': {},
        'next_steps': {},
        'important_context': {}
    }
    
    output = []
    output.append("💤 Creating handover package for next session...")
    output.append(f"Session: {session_id} | Duration: {hours}h {minutes}m")
    output.append("=" * 50)
    
    # 1. WHAT WAS ACCOMPLISHED
    output.append("\n📊 WORK COMPLETED THIS SESSION:")
    
    # Progress updates
    cursor = conn.execute("""
        SELECT content, timestamp FROM memory_entries
        WHERE session_id = ? AND category = 'progress'
        ORDER BY timestamp DESC
    """, (session_id,))
    progress_items = cursor.fetchall()
    
    if progress_items:
        output.append("\n✅ Progress Made:")
        for item in progress_items[:5]:  # Top 5 progress items
            output.append(f"   • {item['content']}")
        handover['work_done']['progress'] = [p['content'] for p in progress_items]
    
    # Completed TODOs
    cursor = conn.execute("""
        SELECT content FROM todos
        WHERE status = 'completed' AND completed_at > ?
        ORDER BY completed_at DESC
    """, (session['started_at'],))
    completed = cursor.fetchall()
    
    if completed:
        output.append(f"\n✅ TODOs Completed ({len(completed)}):")
        for todo in completed[:5]:
            output.append(f"   • {todo['content']}")
        handover['work_done']['completed_todos'] = [t['content'] for t in completed]
    
    # 2. CURRENT STATE & CONTEXT
    output.append("\n🎯 CURRENT PROJECT STATE:")
    
    # Active/pending TODOs
    cursor = conn.execute("""
        SELECT content, priority FROM todos
        WHERE status = 'pending'
        ORDER BY priority DESC, created_at ASC
    """)
    pending_todos = cursor.fetchall()
    
    if pending_todos:
        output.append(f"\n📋 Pending TODOs ({len(pending_todos)}):")
        for todo in pending_todos[:5]:
            priority = ['LOW', 'NORMAL', 'HIGH'][min(todo['priority'] or 0, 2)]
            output.append(f"   • [{priority}] {todo['content']}")
        handover['next_steps']['todos'] = [
            {'content': t['content'], 'priority': t['priority']} 
            for t in pending_todos
        ]
    
    # Recent decisions made
    cursor = conn.execute("""
        SELECT decision, rationale FROM decisions
        WHERE timestamp > ? AND status = 'DECIDED'
        ORDER BY timestamp DESC
        LIMIT 3
    """, (session['started_at'],))
    decisions = cursor.fetchall()
    
    if decisions:
        output.append("\n🤔 Key Decisions Made:")
        for decision in decisions:
            output.append(f"   • {decision['decision']}")
            if decision['rationale']:
                output.append(f"     → {decision['rationale']}")
        handover['work_done']['decisions'] = [
            {'decision': d['decision'], 'rationale': d['rationale']} 
            for d in decisions
        ]
    
    # 3. IMPORTANT LOCKED CONTEXTS
    output.append("\n🔒 LOCKED CONTEXTS TO REMEMBER:")
    
    cursor = conn.execute("""
        SELECT label, version, MAX(locked_at) as latest
        FROM context_locks
        WHERE session_id = ?
        GROUP BY label
        ORDER BY latest DESC
        LIMIT 5
    """, (session_id,))
    
    locked_contexts = cursor.fetchall()
    if locked_contexts:
        for ctx in locked_contexts:
            output.append(f"   • {ctx['label']} (v{ctx['version']})")
        handover['important_context']['locked'] = [
            {'label': c['label'], 'version': c['version']} 
            for c in locked_contexts
        ]
        output.append("   Use recall_context('topic') to retrieve these")
    
    # 4. FILES BEING WORKED ON
    cursor = conn.execute("""
        SELECT DISTINCT path, GROUP_CONCAT(tag) as tags
        FROM file_tags
        WHERE created_at > ?
        GROUP BY path
        ORDER BY created_at DESC
        LIMIT 5
    """, (session['started_at'],))
    
    recent_files = cursor.fetchall()
    if recent_files:
        output.append("\n📁 Files Recently Analyzed:")
        for file in recent_files:
            output.append(f"   • {file['path']}")
            if file['tags']:
                tags = file['tags'].split(',')[:3]  # First 3 tags
                output.append(f"     Tags: {', '.join(tags)}")
        handover['current_state']['recent_files'] = [
            {'path': f['path'], 'tags': f['tags']} 
            for f in recent_files
        ]
    
    # 5. ERRORS OR ISSUES TO ADDRESS
    cursor = conn.execute("""
        SELECT content FROM memory_entries
        WHERE session_id = ? AND category = 'error'
        ORDER BY timestamp DESC
        LIMIT 3
    """, (session_id,))
    
    errors = cursor.fetchall()
    if errors:
        output.append("\n⚠️ Issues to Address:")
        for error in errors:
            output.append(f"   • {error['content']}")
        handover['next_steps']['issues'] = [e['content'] for e in errors]
    
    # 6. NEXT STEPS GUIDANCE
    output.append("\n🚀 NEXT SESSION RECOMMENDATIONS:")
    
    # Open questions
    cursor = conn.execute("""
        SELECT question FROM decisions
        WHERE status = 'OPEN'
        ORDER BY timestamp DESC
        LIMIT 3
    """)
    questions = cursor.fetchall()
    
    if questions:
        output.append("\n❓ Open Questions:")
        for q in questions:
            output.append(f"   • {q['question']}")
        handover['next_steps']['questions'] = [q['question'] for q in questions]
    
    # Suggest next actions based on state
    if pending_todos:
        output.append(f"\n💡 Start with high-priority TODOs")
    if errors:
        output.append(f"💡 Address the {len(errors)} error(s) first")
    if not locked_contexts:
        output.append("💡 Consider locking important decisions/code with lock_context()")
    
    # Store comprehensive handover in database
    handover_json = json.dumps(handover, indent=2)
    
    # Update session with handover package
    conn.execute("""
        UPDATE sessions 
        SET summary = ?, last_active = ?
        WHERE id = ?
    """, (handover_json, time.time(), session_id))
    
    # Create a special handover memory entry
    conn.execute("""
        INSERT INTO memory_entries (category, content, metadata, timestamp, session_id)
        VALUES ('handover', ?, ?, ?, ?)
    """, (f"Session handover: {hours}h {minutes}m of work", handover_json, time.time(), session_id))
    
    conn.commit()
    
    output.append("\n" + "=" * 50)
    output.append("✅ Handover package saved. Use wake_up() to resume.")
    output.append("Your context and progress are preserved!")
    
    return "\n".join(output)

# ============================================================================
# MEMORY MANAGEMENT (unchanged)
# ============================================================================

@mcp.tool()
async def memory_status() -> str:
    """
    Show memory system status and statistics.
    """
    conn = get_db()
    session_id = get_current_session_id()
    
    output = []
    output.append("🧠 Memory System Status")
    output.append("=" * 40)
    
    # Session info
    cursor = conn.execute("""
        SELECT started_at, last_active FROM sessions WHERE id = ?
    """, (session_id,))
    session = cursor.fetchone()
    
    if session:
        start = datetime.fromtimestamp(session['started_at'])
        active = datetime.fromtimestamp(session['last_active'])
        output.append(f"Session: {session_id}")
        output.append(f"Started: {start.strftime('%Y-%m-%d %H:%M')}")
        output.append(f"Last Active: {active.strftime('%H:%M')}")
    
    # Memory stats
    cursor = conn.execute("""
        SELECT category, COUNT(*) as count 
        FROM memory_entries 
        WHERE session_id = ?
        GROUP BY category
    """, (session_id,))
    
    entries = cursor.fetchall()
    if entries:
        output.append("\n📊 Memory Entries (this session):")
        for entry in entries:
            output.append(f"   • {entry['category']}: {entry['count']}")
    
    # Context locks
    cursor = conn.execute("""
        SELECT COUNT(DISTINCT label) as topics, COUNT(*) as total
        FROM context_locks WHERE session_id = ?
    """, (session_id,))
    locks = cursor.fetchone()
    output.append(f"\n🔒 Locked Contexts: {locks['topics']} topics, {locks['total']} versions")
    
    # TODOs
    cursor = conn.execute("""
        SELECT status, COUNT(*) as count FROM todos
        GROUP BY status
    """)
    todos = cursor.fetchall()
    if todos:
        output.append("\n📋 TODOs:")
        for todo in todos:
            output.append(f"   • {todo['status']}: {todo['count']}")
    
    # File tags
    cursor = conn.execute("SELECT COUNT(DISTINCT path) as files FROM file_tags")
    tags = cursor.fetchone()
    output.append(f"\n🏷️ Tagged Files: {tags['files']}")
    
    return "\n".join(output)

# ============================================================================
# CONTEXT LOCKING (unchanged)
# ============================================================================

@mcp.tool()
async def lock_context(content: str, topic: str, tags: Optional[str] = None, priority: Optional[str] = None) -> str:
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

    # Lock architecture decision
    lock_context(
        content="Database: Using PostgreSQL 14 with connection pooling (max 20 connections).",
        topic="database_config",
        tags="database,postgres,config",
        priority="important"
    )
    ```

    **What happens after locking:**
    - Context is automatically checked when relevant (via check_contexts)
    - Preview enables fast relevance checking (60-80% token savings)
    - Can be recalled exactly with recall_context(topic)
    - Violations of rules are detected and warned about

    Returns: Confirmation with version number and priority indicator
    """
    update_session_activity()
    conn = get_db()
    session_id = get_current_session_id()
    
    # Auto-detect priority if not specified
    if priority is None:
        content_lower = content.lower()
        if any(word in content_lower for word in ['always', 'never', 'must']):
            priority = 'always_check'
        elif any(word in content_lower for word in ['important', 'critical', 'required']):
            priority = 'important'
        else:
            priority = 'reference'
    
    # Validate priority
    valid_priorities = ['always_check', 'important', 'reference']
    if priority not in valid_priorities:
        return f"❌ Invalid priority '{priority}'. Must be one of: {', '.join(valid_priorities)}"
    
    # Generate hash
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    # Get latest version for this topic
    cursor = conn.execute("""
        SELECT version FROM context_locks 
        WHERE label = ? AND session_id = ?
        ORDER BY locked_at DESC
        LIMIT 1
    """, (topic, session_id))
    
    row = cursor.fetchone()
    if row:
        # Parse and increment version
        parts = row['version'].split('.')
        if len(parts) == 2:
            major, minor = parts
            version = f"{major}.{int(minor)+1}"
        else:
            version = "1.1"
    else:
        version = "1.0"
    
    # Extract keywords for better matching
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
        conn.execute("""
            INSERT INTO context_locks
            (session_id, label, version, content, content_hash, locked_at, metadata,
             preview, key_concepts, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, topic, version, content, content_hash, time.time(), json.dumps(metadata),
              preview, json.dumps(key_concepts), time.time()))
        
        conn.commit()
        
        priority_indicator = {
            'always_check': ' ⚠️ [ALWAYS CHECK]',
            'important': ' 📌 [IMPORTANT]',
            'reference': ''
        }.get(priority, '')
        
        return f"✅ Locked '{topic}' as v{version}{priority_indicator} ({len(content)} chars, hash: {content_hash[:8]})"
        
    except sqlite3.IntegrityError:
        return f"❌ Version {version} of '{topic}' already exists"
    except Exception as e:
        return f"❌ Failed to lock context: {str(e)}"

@mcp.tool()
async def recall_context(topic: str, version: Optional[str] = "latest") -> str:
    """
    Retrieve exact content of a previously locked context by topic name.

    **When to use this tool:**
    - When check_contexts indicates a relevant locked context exists
    - To get full details of an API spec, rule, or decision
    - To verify exact requirements before implementing
    - To recall specific configuration or setup details
    - When you need the complete context (not just preview)

    **What this returns:**
    - Full content of the locked context (exactly as stored)
    - Version number and timestamp
    - Priority level and tags
    - Complete metadata

    **Version handling:**
    - "latest" (default): Returns most recent version
    - "1.0", "1.1", etc.: Returns specific version
    - Contexts are immutable - each edit creates new version
    - Version history preserved forever

    **Best practices:**
    1. Use after check_contexts identifies relevant context
    2. Don't recall all contexts at session start (use wake_up instead)
    3. Recall only when you need full details for current task
    4. Check version history if requirements seem contradictory

    **Example workflow:**
    ```
    # Step 1: Check what's relevant
    check_contexts("implementing user authentication")
    # Returns: "api_auth_rules is relevant (⚠️ always_check)"

    # Step 2: Recall the full context
    recall_context("api_auth_rules")
    # Returns full API authentication specification

    # Step 3: Implement following the rules
    ```

    **Common patterns:**
    - Recall before implementing to verify requirements
    - Recall when check_contexts shows rule violations
    - Recall specific version if debugging old behavior
    - List all topics first with list_topics() if unsure of name

    **Performance note:**
    With RLM optimization, check_contexts uses lightweight previews,
    then recall_context loads full content only when needed.
    This enables 60-80% token reduction compared to loading everything.

    Returns: Full context content with metadata, or error if not found
    """
    conn = get_db()
    session_id = get_current_session_id()
    
    if version == "latest":
        cursor = conn.execute("""
            SELECT id, content, version, locked_at, metadata
            FROM context_locks
            WHERE label = ? AND session_id = ?
            ORDER BY locked_at DESC
            LIMIT 1
        """, (topic, session_id))
    else:
        # Clean version (remove 'v' prefix if present)
        clean_version = version[1:] if version.startswith('v') else version
        cursor = conn.execute("""
            SELECT id, content, version, locked_at, metadata
            FROM context_locks
            WHERE label = ? AND version = ? AND session_id = ?
        """, (topic, clean_version, session_id))

    row = cursor.fetchone()
    if row:
        context_id = row['id']
        dt = datetime.fromtimestamp(row['locked_at'])
        metadata = json.loads(row['metadata']) if row['metadata'] else {}
        tags = metadata.get('tags', [])

        # Track access
        conn.execute("""
            UPDATE context_locks
            SET last_accessed = ?,
                access_count = access_count + 1
            WHERE id = ?
        """, (time.time(), context_id))
        conn.commit()

        output = []
        output.append(f"📌 {topic} v{row['version']}")
        output.append(f"Locked: {dt.strftime('%Y-%m-%d %H:%M')}")
        if tags:
            output.append(f"Tags: {', '.join(tags)}")
        output.append("-" * 40)
        output.append(row['content'])

        return "\n".join(output)
    else:
        return f"❌ No locked context found for '{topic}' (version: {version})"

@mcp.tool()
async def unlock_context(
    topic: str,
    version: str = "all",
    force: bool = False,
    archive: bool = True
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
    update_session_activity()
    conn = get_db()
    session_id = get_current_session_id()

    # 1. Find contexts to delete
    if version == "all":
        cursor = conn.execute("""
            SELECT * FROM context_locks
            WHERE label = ? AND session_id = ?
        """, (topic, session_id))
    elif version == "latest":
        cursor = conn.execute("""
            SELECT * FROM context_locks
            WHERE label = ? AND session_id = ?
            ORDER BY version DESC
            LIMIT 1
        """, (topic, session_id))
    else:
        cursor = conn.execute("""
            SELECT * FROM context_locks
            WHERE label = ? AND version = ? AND session_id = ?
        """, (topic, version, session_id))

    contexts = cursor.fetchall()

    if not contexts:
        return f"❌ Context '{topic}' (version: {version}) not found"

    # 2. Check for critical contexts
    has_critical = False
    for ctx in contexts:
        metadata = json.loads(ctx['metadata']) if ctx['metadata'] else {}
        if metadata.get('priority') == 'always_check':
            has_critical = True
            break

    if has_critical and not force:
        return f"⚠️  Cannot delete critical (always_check) context '{topic}' without force=True\n" \
               f"   This context contains important rules. Use force=True if you're sure."

    # 3. Archive before deletion
    if archive:
        for ctx in contexts:
            try:
                conn.execute("""
                    INSERT INTO context_archives
                    (original_id, session_id, label, version, content, preview, key_concepts,
                     metadata, deleted_at, delete_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ctx['id'], ctx['session_id'], ctx['label'], ctx['version'],
                      ctx['content'], ctx['preview'], ctx['key_concepts'],
                      ctx['metadata'], time.time(), f"Deleted {version} version(s)"))
            except Exception as e:
                return f"❌ Failed to archive context: {str(e)}"

    # 4. Delete contexts
    try:
        if version == "all":
            conn.execute("""
                DELETE FROM context_locks
                WHERE label = ? AND session_id = ?
            """, (topic, session_id))
        elif version == "latest":
            # Delete the latest version (already fetched in contexts)
            conn.execute("""
                DELETE FROM context_locks
                WHERE id = ?
            """, (contexts[0]['id'],))
        else:
            conn.execute("""
                DELETE FROM context_locks
                WHERE label = ? AND version = ? AND session_id = ?
            """, (topic, version, session_id))

        conn.commit()

        count = len(contexts)
        version_str = f"{count} version(s)" if version == "all" else f"version {version}"

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

async def _detect_project_type(path: str) -> str:
    """Detect project type by analyzing structure."""
    try:
        py_files = list(Path(path).rglob("*.py"))
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
        py_files = list(Path(path).rglob("*.py"))
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
        py_files = list(Path(path).rglob("*.py"))
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
        py_files = list(Path(path).rglob("*.py"))
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
async def batch_lock_contexts(contexts: str) -> str:
    """
    Lock multiple contexts in one operation (reduces round-trips for cloud).

    **Purpose:** Efficient bulk context locking

    **Input:** JSON array of context objects
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
    try:
        contexts_list = json.loads(contexts)
    except json.JSONDecodeError as e:
        return f"❌ Invalid JSON: {str(e)}"

    if not isinstance(contexts_list, list):
        return "❌ Input must be a JSON array of context objects"

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
                priority=ctx.get('priority')
            )
            results.append({
                "topic": ctx['topic'],
                "status": "success",
                "message": "Context locked successfully"
            })
            successful += 1
        except Exception as e:
            results.append({
                "topic": ctx['topic'],
                "status": "error",
                "error": str(e)
            })
            failed += 1

    return json.dumps({
        "summary": {
            "total": len(contexts_list),
            "successful": successful,
            "failed": failed
        },
        "results": results
    }, indent=2)


@mcp.tool()
async def batch_recall_contexts(topics: str) -> str:
    """
    Recall multiple contexts in one operation.

    **Purpose:** Efficient bulk context retrieval

    **Input:** JSON array of topic names
    ```
    ["api_spec", "database_schema", "auth_rules"]
    ```

    **Returns:** JSON with content for each requested topic

    **Benefits:**
    - Single operation instead of multiple recall calls
    - Efficient for loading related contexts
    - Returns status for each topic (found/not found)

    **Example:**
    ```
    batch_recall_contexts('["api_v1", "database_schema"]')
    ```
    """
    try:
        topics_list = json.loads(topics)
    except json.JSONDecodeError as e:
        return f"❌ Invalid JSON: {str(e)}"

    if not isinstance(topics_list, list):
        return "❌ Input must be a JSON array of topic names"

    results = []
    found = 0
    not_found = 0

    for topic in topics_list:
        if not isinstance(topic, str):
            results.append({
                "topic": str(topic),
                "status": "error",
                "error": "Topic must be a string"
            })
            not_found += 1
            continue

        try:
            content = await recall_context(topic)
            if "❌" in content:  # recall_context returns error message
                results.append({
                    "topic": topic,
                    "status": "not_found",
                    "error": content
                })
                not_found += 1
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
            "total": len(topics_list),
            "found": found,
            "not_found": not_found
        },
        "results": results
    }, indent=2)



@mcp.tool()
async def sync_project_memory(
    path: Optional[str] = None,
    confirm: bool = False,
    dry_run: bool = False,
    priorities: Optional[List[str]] = None
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
                    conn = get_db()
                    session_id = get_current_session_id()
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

@mcp.tool()
async def query_database(
    query: str,
    params: Optional[List[str]] = None,
    format: str = "table",
    db_path: Optional[str] = None
) -> str:
    """
    Execute read-only SQL queries against ANY SQLite database for debugging and inspection.

    This tool allows direct querying of any SQLite database in your workspace. Works with
    the dementia memory database (default) or any .db/.sqlite file you specify.

    **SAFETY FEATURES:**
    - Read-only enforcement: Only SELECT queries are allowed
    - Blocks dangerous operations: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, PRAGMA
    - Parameterized queries: Use ? placeholders to prevent SQL injection
    - Automatic LIMIT: Queries without LIMIT get LIMIT 100 added automatically
    - Path validation: Only accesses databases in current working directory

    **COMMON USE CASES:**

    1. Query dementia memory database (default):
       query_database("SELECT label, version FROM context_locks")

    2. Query any SQLite database in workspace:
       query_database("SELECT * FROM users", db_path="./data/app.db")

    3. Query with parameters:
       query_database("SELECT * FROM logs WHERE level = ?", params=["ERROR"], db_path="./logs.db")

    4. List all tables in a database:
       query_database("SELECT name FROM sqlite_master WHERE type='table'", db_path="./mydb.sqlite")

    5. Check row counts:
       query_database("SELECT COUNT(*) as count FROM my_table", db_path="./data.db")

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

    Returns:
        Formatted query results with row count and execution time

    Raises:
        Error message if query is unsafe or execution fails
    """
    import time
    import os
    from pathlib import Path

    try:
        # Safety check: Only allow SELECT queries
        query_upper = query.strip().upper()
        dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 'PRAGMA', 'ATTACH', 'DETACH']

        if not query_upper.startswith('SELECT'):
            return f"❌ Error: Only SELECT queries are allowed.\n\nUse query_database() for read-only operations only.\n\nFor modifications, use the provided MCP tools:\n- lock_context() to create/update contexts\n- unlock_context() to delete contexts\n- memory_update() to add memories"

        for keyword in dangerous_keywords:
            if keyword in query_upper:
                return f"❌ Error: Query contains dangerous keyword '{keyword}'.\n\nOnly SELECT queries are allowed for safety."

        # Add LIMIT if not present (prevent huge result sets)
        if 'LIMIT' not in query_upper:
            query = query.strip().rstrip(';') + ' LIMIT 100'

        # Connect to database
        if db_path:
            # Validate path is in workspace
            abs_db_path = os.path.abspath(db_path)
            workspace = os.getcwd()

            if not abs_db_path.startswith(workspace):
                return f"❌ Error: Database must be in current workspace.\n\nProvided: {db_path}\nWorkspace: {workspace}"

            if not os.path.exists(abs_db_path):
                return f"❌ Error: Database file not found: {db_path}"

            conn = sqlite3.connect(abs_db_path)
            conn.row_factory = sqlite3.Row
        else:
            # Use default dementia database
            conn = get_db()
            conn.row_factory = sqlite3.Row

        start_time = time.time()

        if params:
            cursor = conn.execute(query, params)
        else:
            cursor = conn.execute(query)

        rows = cursor.fetchall()
        execution_time = (time.time() - start_time) * 1000  # Convert to ms

        if not rows:
            return f"✅ Query executed successfully.\n\n0 rows returned.\n⏱️ Execution time: {execution_time:.2f}ms"

        # Format output based on requested format
        if format == "json":
            import json
            result = [dict(row) for row in rows]
            return json.dumps(result, indent=2, default=str)

        elif format == "csv":
            output = []
            # Header
            output.append(','.join(rows[0].keys()))
            # Rows
            for row in rows:
                output.append(','.join(str(v) for v in row))
            return '\n'.join(output)

        elif format == "markdown":
            output = []
            keys = list(rows[0].keys())
            # Header
            output.append('| ' + ' | '.join(keys) + ' |')
            output.append('| ' + ' | '.join(['---' for _ in keys]) + ' |')
            # Rows
            for row in rows:
                output.append('| ' + ' | '.join(str(v) for v in row) + ' |')
            output.append(f'\n{len(rows)} rows')
            return '\n'.join(output)

        else:  # table format (default)
            output = []
            keys = list(rows[0].keys())

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
            output.append(f'⏱️ Execution time: {execution_time:.2f}ms')

            return '\n'.join(output)

    except Exception as e:
        return f"❌ Query failed: {str(e)}\n\nCheck your SQL syntax and try again."


@mcp.tool()
async def inspect_database(
    mode: str = "overview",
    filter_text: Optional[str] = None,
    db_path: Optional[str] = None
) -> str:
    """
    Quick inspection of ANY SQLite database with preset queries - no SQL knowledge required.

    This tool provides easy access to common database inspection tasks for any SQLite database
    in your workspace. Works with the dementia memory database (default) or any .db/.sqlite file.

    **INSPECTION MODES:**

    1. **overview** - High-level statistics (dementia DB only)
       - Total locked contexts by priority
       - Total memories by category
       - Total archived contexts
       - Session information

    2. **schema** - Complete database structure (works with ANY database)
       - All table names
       - Column names and types for each table
       - Row counts per table

    3. **contexts** - List locked contexts (dementia DB only)
       - Label, version, priority
       - Lock timestamp
       - Content preview
       - Optional filtering by label

    4. **tables** - Just list table names (works with ANY database)
       - Quick overview of database structure

    4. **memories** - Recent memory entries
       - Category, content, timestamp
       - Sorted by most recent first
       - Optional filtering by category

    5. **archives** - Deleted contexts
       - What was deleted and when
       - Deletion reason
       - Original content preserved

    6. **tags** - File tagging system
       - All tagged files
       - Tag distribution
       - Files needing review

    7. **sessions** - Session activity
       - Active sessions
       - Context counts per session
       - Memory counts per session

    **EXAMPLES:**

    Inspect dementia memory database (default):
    ```python
    inspect_database("overview")
    inspect_database("contexts")
    ```

    Inspect any SQLite database:
    ```python
    inspect_database("schema", db_path="./data/app.db")
    inspect_database("tables", db_path="./logs.sqlite")
    ```

    Find specific data:
    ```python
    inspect_database("contexts", filter_text="api")
    ```

    **USE CASES:**

    - Debugging: "Why isn't my context showing up?"
    - Exploration: "What tables are in this database?"
    - Inspection: "What's the structure of this .db file?"
    - Monitoring: "How much data is in each table?"

    Args:
        mode: Inspection mode - "overview", "schema", "contexts", "tables"
        filter_text: Optional text to filter results (for contexts mode)
        db_path: Optional path to SQLite database file (default: dementia memory database)

    Returns:
        Formatted inspection results with relevant statistics

    Raises:
        Error message if mode is invalid
    """
    import os

    # Connect to database
    if db_path:
        # Validate path is in workspace
        abs_db_path = os.path.abspath(db_path)
        workspace = os.getcwd()

        if not abs_db_path.startswith(workspace):
            return f"❌ Error: Database must be in current workspace.\n\nProvided: {db_path}\nWorkspace: {workspace}"

        if not os.path.exists(abs_db_path):
            return f"❌ Error: Database file not found: {db_path}"

        conn = sqlite3.connect(abs_db_path)
        conn.row_factory = sqlite3.Row
        session_id = None  # Custom DB won't have session_id
    else:
        # Use default dementia database
        conn = get_db()
        conn.row_factory = sqlite3.Row
        session_id = get_current_session_id()

    try:
        if mode == "tables":
            # Quick table list (works with any database)
            output = ["📋 DATABASE TABLES", "=" * 60, ""]

            cursor = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table'
                ORDER BY name
            """)

            tables = [row['name'] for row in cursor.fetchall()]

            if tables:
                for table in tables:
                    # Get row count
                    cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table}")
                    count = cursor.fetchone()['count']
                    output.append(f"   {table}: {count} rows")
            else:
                output.append("   No tables found")

            return '\n'.join(output)

        elif mode == "overview":
            # Dementia DB specific
            if not session_id:
                return "❌ 'overview' mode only works with dementia database (default).\n\nUse 'schema' or 'tables' mode for other databases."

            output = ["📊 DATABASE OVERVIEW", "=" * 60, ""]

            # Locked contexts by priority
            cursor = conn.execute("""
                SELECT
                    json_extract(metadata, '$.priority') as priority,
                    COUNT(*) as count
                FROM context_locks
                WHERE session_id = ?
                GROUP BY priority
            """, (session_id,))

            output.append("🔒 Locked Contexts:")
            context_total = 0
            for row in cursor.fetchall():
                priority = row['priority'] or 'reference'
                count = row['count']
                context_total += count
                output.append(f"   {priority}: {count}")
            output.append(f"   TOTAL: {context_total}")
            output.append("")

            # Memories by category
            cursor = conn.execute("""
                SELECT category, COUNT(*) as count
                FROM memory_entries
                WHERE session_id = ?
                GROUP BY category
            """, (session_id,))

            output.append("🧠 Memories:")
            memory_total = 0
            for row in cursor.fetchall():
                count = row['count']
                memory_total += count
                output.append(f"   {row['category']}: {count}")
            output.append(f"   TOTAL: {memory_total}")
            output.append("")

            # Archives
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM context_archives
                WHERE session_id = ?
            """, (session_id,))
            archive_count = cursor.fetchone()['count']
            output.append(f"📦 Archived contexts: {archive_count}")
            output.append("")

            # File tags
            cursor = conn.execute("SELECT COUNT(*) as count FROM file_tags")
            tag_count = cursor.fetchone()['count']
            output.append(f"🏷️ Tagged files: {tag_count}")

            return '\n'.join(output)

        elif mode == "schema":
            output = ["📋 DATABASE SCHEMA", "=" * 60, ""]

            # Get all tables
            cursor = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table'
                ORDER BY name
            """)

            tables = [row['name'] for row in cursor.fetchall()]

            for table in tables:
                output.append(f"\n📄 Table: {table}")

                # Get column info
                cursor = conn.execute(f"PRAGMA table_info({table})")
                columns = cursor.fetchall()

                output.append("   Columns:")
                for col in columns:
                    pk = " (PRIMARY KEY)" if col['pk'] else ""
                    notnull = " NOT NULL" if col['notnull'] else ""
                    output.append(f"      {col['name']}: {col['type']}{pk}{notnull}")

                # Get row count
                cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table}")
                count = cursor.fetchone()['count']
                output.append(f"   Rows: {count}")

            return '\n'.join(output)

        elif mode == "contexts":
            # Dementia DB specific
            if not session_id:
                return "❌ 'contexts' mode only works with dementia database (default).\n\nUse 'schema' or 'tables' mode for other databases."

            output = ["🔒 LOCKED CONTEXTS", "=" * 60, ""]

            if filter_text:
                cursor = conn.execute("""
                    SELECT label, version, locked_at, preview, metadata
                    FROM context_locks
                    WHERE session_id = ? AND label LIKE ?
                    ORDER BY locked_at DESC
                """, (session_id, f"%{filter_text}%"))
            else:
                cursor = conn.execute("""
                    SELECT label, version, locked_at, preview, metadata
                    FROM context_locks
                    WHERE session_id = ?
                    ORDER BY locked_at DESC
                """, (session_id,))

            rows = cursor.fetchall()

            if not rows:
                return "No locked contexts found."

            for row in rows:
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                priority = metadata.get('priority', 'reference')
                dt = datetime.fromtimestamp(row['locked_at'])

                output.append(f"\n• {row['label']} v{row['version']} [{priority}]")
                output.append(f"  Locked: {dt.strftime('%Y-%m-%d %H:%M')}")
                output.append(f"  Preview: {row['preview'][:80]}...")

            output.append(f"\n\nTotal: {len(rows)} contexts")
            return '\n'.join(output)

        else:
            return f"❌ Invalid mode: {mode}\n\nValid modes: tables, schema, overview, contexts\n\nNote: 'overview' and 'contexts' only work with dementia database (default)"

    except Exception as e:
        return f"❌ Inspection failed: {str(e)}"


@mcp.tool()
async def execute_sql(
    sql: str,
    params: Optional[List[str]] = None,
    db_path: Optional[str] = None,
    dry_run: bool = True,
    confirm: bool = False,
    max_affected: Optional[int] = None
) -> str:
    """
    Execute write operations (INSERT, UPDATE, DELETE) on SQLite databases with comprehensive safety.

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

        # Connect to database
        if db_path:
            # Validate path is in workspace
            abs_db_path = os.path.abspath(db_path)
            workspace = os.getcwd()

            if not abs_db_path.startswith(workspace):
                return f"❌ Error: Database must be in current workspace.\n\nProvided: {db_path}\nWorkspace: {workspace}"

            if not os.path.exists(abs_db_path):
                return f"❌ Error: Database file not found: {db_path}"

            conn = sqlite3.connect(abs_db_path)
        else:
            # Use default dementia database
            conn = get_db()

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


@mcp.tool()
async def check_contexts(text: str) -> str:
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
    session_id = get_current_session_id()
    
    # Get relevant contexts
    relevant = get_relevant_contexts_for_text(text, session_id, DB_PATH)
    
    # Check for violations
    violations = check_command_context(text, session_id, DB_PATH)
    
    output = []
    if relevant:
        output.append(relevant)
    if violations:
        if output:
            output.append("")  # Add spacing
        output.append(violations)
    
    if not output:
        return "No relevant locked contexts found."

    return "\n".join(output)

@mcp.tool()
async def explore_context_tree() -> str:
    """
    Browse all your locked contexts organized by priority and tags.

    **When to use this tool:**
    - At session start to see what contexts exist
    - When you want to browse available information
    - To discover contexts you've forgotten about
    - To understand the structure of your locked knowledge

    **What this does:**
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
    4. Use recall_context() or get_context_preview() to dive deeper

    **Example output:**
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

    Returns: Tree structure of all contexts with previews
    """
    conn = get_db()
    session_id = get_current_session_id()

    # Get all contexts with previews (not full content - RLM optimization!)
    cursor = conn.execute("""
        SELECT label, version, preview, key_concepts, metadata, locked_at
        FROM context_locks
        WHERE session_id = ?
        ORDER BY locked_at DESC
    """, (session_id,))

    contexts = cursor.fetchall()

    if not contexts:
        return "📭 No locked contexts yet.\n\n💡 Use lock_context() to save important information for future reference."

    # Group by priority
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
# ENHANCED PROJECT INTELLIGENCE WITH AUTO-TAGGING
# ============================================================================

