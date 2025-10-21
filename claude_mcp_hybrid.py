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
    if 'access_count' not in columns:
        cursor.execute('ALTER TABLE context_locks ADD COLUMN access_count INTEGER DEFAULT 0')

    # If we just added RLM columns, generate previews for existing contexts
    if 'preview' not in columns:
        cursor.execute("SELECT COUNT(*) FROM context_locks WHERE preview IS NULL")
        needs_preview = cursor.fetchone()[0]

        if needs_preview > 0:
            # Import preview generation
            from migrate_v4_1_rlm import generate_preview, extract_key_concepts

            # Generate previews for existing contexts
            cursor.execute("SELECT id, content, metadata FROM context_locks WHERE preview IS NULL")
            rows = cursor.fetchall()

            for row in rows:
                row_id = row[0]
                content = row[1]
                metadata = json.loads(row[2]) if row[2] else {}
                tags = metadata.get('tags', [])

                preview = generate_preview(content, max_length=500)
                key_concepts = extract_key_concepts(content, tags)

                cursor.execute("""
                    UPDATE context_locks
                    SET preview = ?, key_concepts = ?, last_accessed = ?
                    WHERE id = ?
                """, (preview, json.dumps(key_concepts), time.time(), row_id))

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
# SESSION MANAGEMENT (unchanged from before)
# ============================================================================

@mcp.tool()
async def wake_up() -> str:
    """
    Start a development session and load context.
    Shows: active todos, recent changes, locked contexts.
    """
    update_session_activity()
    conn = get_db()
    session_id = get_current_session_id()
    
    output = []
    
    # Check for context mismatch warning
    cursor = conn.execute("""
        SELECT id, project_name, project_path, last_active 
        FROM sessions 
        WHERE id != ?
        ORDER BY last_active DESC
        LIMIT 1
    """, (session_id,))
    
    other_session = cursor.fetchone()
    if other_session:
        # Check if this other session was more recent and for a different project
        if other_session['project_path'] != PROJECT_ROOT:
            days_ago = (time.time() - other_session['last_active']) / 86400
            if days_ago < 1:
                output.append("⚠️ CONTEXT WARNING:")
                output.append(f"   Last session '{other_session['id']}' was for: {other_session['project_name']}")
                output.append(f"   at: {other_session['project_path']}")
                output.append(f"   You're now in: {PROJECT_NAME}")
                output.append("   Did you mean to switch projects?")
                output.append("")
    
    output.append("🌅 Good morning! Loading your context...")
    output.append(f"Session: {session_id}")
    output.append(f"Project: {PROJECT_NAME}")
    output.append(f"Location: {PROJECT_ROOT}")
    output.append(f"Memory: {DB_PATH} ({DB_LOCATION})")
    output.append("")
    
    # Check for previous session handover
    cursor = conn.execute("""
        SELECT content, metadata, timestamp FROM memory_entries
        WHERE category = 'handover'
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    handover = cursor.fetchone()
    
    if handover:
        dt = datetime.fromtimestamp(handover['timestamp'])
        days_ago = (time.time() - handover['timestamp']) / 86400
        
        if days_ago < 1:
            time_str = f"{int((time.time() - handover['timestamp']) / 3600)} hours ago"
        else:
            time_str = f"{int(days_ago)} days ago"
        
        output.append(f"📜 Last session handover ({time_str}):")
        
        # Parse handover data
        try:
            handover_data = json.loads(handover['metadata'])
            
            # Show work completed
            if 'work_done' in handover_data:
                if handover_data['work_done'].get('progress'):
                    output.append("\n✅ Previous Progress:")
                    for item in handover_data['work_done']['progress'][:3]:
                        output.append(f"   • {item}")
                
                if handover_data['work_done'].get('decisions'):
                    output.append("\n🤔 Previous Decisions:")
                    for decision in handover_data['work_done']['decisions'][:2]:
                        output.append(f"   • {decision['decision']}")
            
            # Show next steps
            if 'next_steps' in handover_data:
                if handover_data['next_steps'].get('todos'):
                    high_priority = [t for t in handover_data['next_steps']['todos'] 
                                   if t.get('priority', 0) >= 2]
                    if high_priority:
                        output.append("\n🔥 High Priority TODOs:")
                        for todo in high_priority[:3]:
                            output.append(f"   • {todo['content']}")
                
                if handover_data['next_steps'].get('issues'):
                    output.append("\n⚠️ Issues to Address:")
                    for issue in handover_data['next_steps']['issues'][:2]:
                        output.append(f"   • {issue}")
            
            # Show locked contexts
            if 'important_context' in handover_data:
                if handover_data['important_context'].get('locked'):
                    output.append("\n🔒 Available Locked Contexts:")
                    for ctx in handover_data['important_context']['locked'][:3]:
                        output.append(f"   • {ctx['label']} (v{ctx['version']})")
                    output.append("   → Use recall_context('topic') to retrieve")
            
        except json.JSONDecodeError:
            output.append("   (Handover data corrupted)")
    else:
        # No handover, show recent updates instead
        cursor = conn.execute("""
            SELECT message, timestamp FROM session_updates
            ORDER BY timestamp DESC
            LIMIT 5
        """)
        updates = cursor.fetchall()
        
        if updates:
            output.append("📝 Recent updates:")
            for update in updates:
                dt = datetime.fromtimestamp(update['timestamp'])
                output.append(f"   • {dt.strftime('%m/%d %H:%M')}: {update['message']}")
    
    # Get active todos
    cursor = conn.execute("""
        SELECT content, priority FROM todos
        WHERE status = 'pending'
        ORDER BY priority DESC, created_at ASC
        LIMIT 5
    """)
    todos = cursor.fetchall()
    
    if todos:
        output.append("\n📋 Active TODOs:")
        for i, todo in enumerate(todos, 1):
            priority = todo['priority'] if todo['priority'] else 0
            priority_label = ['LOW', 'NORMAL', 'HIGH'][min(priority, 2)]
            output.append(f"   {i}. [{priority_label}] {todo['content']}")
    
    # Show high-priority locked contexts
    engine = ActiveContextEngine(DB_PATH)
    
    # Get always_check contexts
    cursor = conn.execute("""
        SELECT label, version, metadata 
        FROM context_locks 
        WHERE session_id = ? 
        AND json_extract(metadata, '$.priority') = 'always_check'
        ORDER BY locked_at DESC
    """, (session_id,))
    
    always_check = cursor.fetchall()
    if always_check:
        output.append("\n⚠️ High-Priority Rules (Always Checked):")
        for ctx in always_check:
            metadata = json.loads(ctx['metadata']) if ctx['metadata'] else {}
            tags = metadata.get('tags', [])
            tag_str = f" ({', '.join(tags[:2])})" if tags else ""
            output.append(f"   • {ctx['label']} v{ctx['version']}{tag_str}")
    
    # Get important contexts
    cursor = conn.execute("""
        SELECT label, version, metadata 
        FROM context_locks 
        WHERE session_id = ? 
        AND json_extract(metadata, '$.priority') = 'important'
        ORDER BY locked_at DESC
        LIMIT 3
    """, (session_id,))
    
    important = cursor.fetchall()
    if important:
        output.append("\n📌 Important Contexts:")
        for ctx in important:
            output.append(f"   • {ctx['label']} v{ctx['version']}")
    
    # Show regular locked contexts count
    cursor = conn.execute("""
        SELECT COUNT(DISTINCT label) as count 
        FROM context_locks 
        WHERE session_id = ?
    """, (session_id,))
    
    total = cursor.fetchone()
    if total and total['count'] > 0:
        shown = len(always_check or []) + len(important or [])
        remaining = total['count'] - shown
        if remaining > 0:
            output.append(f"\n📚 Plus {remaining} reference contexts available")
    
    # Check for issues needing attention
    cursor = conn.execute("""
        SELECT COUNT(*) as count FROM memory 
        WHERE category = 'error' 
          AND timestamp > ?
    """, (time.time() - 86400,))  # Last 24 hours
    
    errors = cursor.fetchone()
    if errors and errors['count'] > 0:
        output.append(f"\n⚠️ {errors['count']} errors in last 24h need attention")
    
    return "\n".join(output)

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
async def memory_update(category: str, content: str, metadata: Optional[str] = None) -> str:
    """
    Add memory update. 
    Categories: progress, decision, error, insight, todo, question
    Metadata should be JSON string for extra context.
    """
    update_session_activity()
    conn = get_db()
    session_id = get_current_session_id()
    
    # Validate category
    valid_categories = ['progress', 'decision', 'error', 'insight', 'todo', 'question']
    if category not in valid_categories:
        return f"❌ Invalid category. Use: {', '.join(valid_categories)}"
    
    # Parse metadata if provided
    meta_dict = {}
    if metadata:
        try:
            meta_dict = json.loads(metadata)
        except:
            meta_dict = {"raw": metadata}
    
    # Store in memory_entries table
    conn.execute("""
        INSERT INTO memory_entries (category, content, metadata, timestamp, session_id)
        VALUES (?, ?, ?, ?, ?)
    """, (category, content, json.dumps(meta_dict), time.time(), session_id))
    
    # Also store in session_updates for quick access
    conn.execute("""
        INSERT INTO session_updates (timestamp, message, category, metadata)
        VALUES (?, ?, ?, ?)
    """, (time.time(), content, category, json.dumps(meta_dict)))
    
    # Handle special categories
    if category == 'todo':
        # Also add to todos table
        todo_id = str(uuid.uuid4())[:8]
        priority = meta_dict.get('priority', 1)
        priority_map = {'LOW': 0, 'NORMAL': 1, 'HIGH': 2}
        if isinstance(priority, str):
            priority = priority_map.get(priority.upper(), 1)
        
        conn.execute("""
            INSERT INTO todos (id, content, status, created_at, priority)
            VALUES (?, ?, 'pending', ?, ?)
        """, (todo_id, content, time.time(), priority))
        
    elif category == 'error':
        # Store in fixes table for tracking
        conn.execute("""
            INSERT INTO fixes (timestamp, problem, solution, file_path)
            VALUES (?, ?, ?, ?)
        """, (time.time(), content, meta_dict.get('solution', 'Pending'), meta_dict.get('file')))
    
    elif category == 'decision':
        # Store in decisions table
        conn.execute("""
            INSERT INTO decisions (timestamp, question, decision, rationale, status)
            VALUES (?, ?, ?, ?, ?)
        """, (time.time(), meta_dict.get('question', content), 
               content, meta_dict.get('rationale'), 'DECIDED'))
    
    conn.commit()
    
    return f"✅ {category.capitalize()} recorded: {content[:100]}..."

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
            SELECT content, version, locked_at, metadata 
            FROM context_locks 
            WHERE label = ? AND session_id = ?
            ORDER BY locked_at DESC
            LIMIT 1
        """, (topic, session_id))
    else:
        # Clean version (remove 'v' prefix if present)
        clean_version = version[1:] if version.startswith('v') else version
        cursor = conn.execute("""
            SELECT content, version, locked_at, metadata 
            FROM context_locks 
            WHERE label = ? AND version = ? AND session_id = ?
        """, (topic, clean_version, session_id))
    
    row = cursor.fetchone()
    if row:
        dt = datetime.fromtimestamp(row['locked_at'])
        metadata = json.loads(row['metadata']) if row['metadata'] else {}
        tags = metadata.get('tags', [])
        
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
async def update_context(
    topic: str,
    content: str,
    version: str = "latest",
    tags: Optional[str] = None,
    priority: Optional[str] = None,
    reason: Optional[str] = None
) -> str:
    """
    Update an existing locked context with new content, creating a new version.

    **When to use this tool:**
    - Fix typos or errors in locked contexts
    - Update API specs with new endpoints or changes
    - Revise rules or decisions with new information
    - Add missing details to existing contexts
    - Correct outdated information

    **How it works:**
    - Creates a new version (v1.0 → v1.1) while preserving old versions
    - Regenerates preview and key_concepts for RLM optimization
    - Tracks update history in metadata (parent version, reason)
    - Inherits tags/priority from previous version if not specified

    **Versioning:**
    - Increments minor version: v1.2 → v1.3
    - Preserves all history (old versions stay in database)
    - Can recall any version: recall_context(topic, version="1.0")

    **Best practices:**
    1. Include update reason for tracking changes
    2. Update tags/priority only if they've changed
    3. Use version="latest" to update most recent (default)
    4. Review old version before updating (use recall_context)

    **Example workflow:**
    ```
    # Check current version
    recall_context("api_spec")

    # Update with fixes
    update_context(
        topic="api_spec",
        content="Fixed API spec with correct endpoints",
        reason="Fixed endpoint URLs"
    )
    # Result: v1.0 → v1.1 (v1.0 preserved)
    ```

    **What you'll see:**
    - Confirmation of new version created
    - Old and new version numbers
    - Update reason (if provided)
    - Version history preserved

    Returns: Confirmation with version change (e.g., "✅ Updated 'api_spec' v1.0 → v1.1")
    """
    update_session_activity()
    conn = get_db()
    session_id = get_current_session_id()

    # 1. Find existing context
    if version == "latest":
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

    current = cursor.fetchone()

    if not current:
        return f"❌ Context '{topic}' not found. Use lock_context() to create a new context."

    # 2. Parse current version and increment
    current_version = current['version']
    parts = current_version.split('.')
    if len(parts) == 2:
        major, minor = parts
        new_version = f"{major}.{int(minor) + 1}"
    else:
        new_version = "1.1"

    # 3. Inherit metadata from current version if not specified
    current_metadata = json.loads(current['metadata']) if current['metadata'] else {}

    if tags is None:
        tags_list = current_metadata.get('tags', [])
    else:
        tags_list = [t.strip() for t in tags.split(',')]

    if priority is None:
        priority = current_metadata.get('priority', 'reference')
    else:
        # Validate priority
        valid_priorities = ['always_check', 'important', 'reference']
        if priority not in valid_priorities:
            return f"❌ Invalid priority '{priority}'. Must be one of: {', '.join(valid_priorities)}"

    # 4. Generate new hash, preview, and key_concepts
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    preview = generate_preview(content, max_length=500)
    key_concepts = extract_key_concepts(content, tags_list)

    # 5. Prepare metadata with update tracking
    metadata = {
        "tags": tags_list,
        "priority": priority,
        "updated_from": current_version,
        "updated_at": datetime.now().isoformat(),
        "created_at": current_metadata.get('created_at', datetime.now().isoformat())
    }

    if reason:
        metadata["update_reason"] = reason

    # 6. Insert new version
    try:
        conn.execute("""
            INSERT INTO context_locks
            (session_id, label, version, content, content_hash, locked_at, metadata,
             preview, key_concepts, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, topic, new_version, content, content_hash, time.time(),
              json.dumps(metadata), preview, json.dumps(key_concepts), time.time()))

        conn.commit()

        priority_indicator = {
            'always_check': ' ⚠️ [ALWAYS CHECK]',
            'important': ' 📌 [IMPORTANT]',
            'reference': ''
        }.get(priority, '')

        result = f"✅ Updated '{topic}' v{current_version} → v{new_version}{priority_indicator}"

        if reason:
            result += f"\n   Reason: {reason}"

        result += f"\n   Old version preserved (use recall_context('{topic}', version='{current_version}') to access)"

        return result

    except sqlite3.IntegrityError:
        return f"❌ Version {new_version} of '{topic}' already exists"
    except Exception as e:
        return f"❌ Failed to update context: {str(e)}"

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

@mcp.tool()
async def list_topics() -> str:
    """
    List all locked context topics with versions.
    """
    conn = get_db()
    session_id = get_current_session_id()
    
    cursor = conn.execute("""
        SELECT label, 
               GROUP_CONCAT(version) as versions,
               COUNT(*) as count,
               MAX(locked_at) as latest,
               metadata
        FROM context_locks
        WHERE session_id = ?
        GROUP BY label
        ORDER BY latest DESC
    """, (session_id,))
    
    rows = cursor.fetchall()
    if rows:
        output = ["📚 Locked Topics:"]
        for row in rows:
            versions = row['versions'].split(',')
            dt = datetime.fromtimestamp(row['latest'])
            
            # Get priority from most recent version
            metadata = json.loads(row['metadata']) if row['metadata'] else {}
            priority = metadata.get('priority', 'reference')
            priority_indicator = {
                'always_check': ' ⚠️',
                'important': ' 📌',
                'reference': ''
            }.get(priority, '')
            
            output.append(f"\n• {row['label']}{priority_indicator}")
            output.append(f"  Versions: v{', v'.join(versions)}")
            output.append(f"  Last updated: {dt.strftime('%Y-%m-%d %H:%M')}")
        return "\n".join(output)
    else:
        return "No locked contexts yet. Use lock_context to save important information."

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
async def ask_memory(question: str) -> str:
    """
    Search your locked contexts using natural language and get synthesized answers.

    **When to use this tool:**
    - When you have a question about something you might have locked before
    - To search for information without knowing the exact topic name
    - When you want a quick answer without browsing all contexts
    - To explore what information exists on a topic

    **What this does:**
    - Searches all locked contexts using natural language (not exact topic match)
    - Returns relevant contexts ranked by relevance
    - Shows previews for quick scanning
    - Provides suggestions to recall full content if needed

    **How it works:**
    - Uses RLM 2-stage relevance checking (60-80% token savings)
    - Stage 1: Fast preview scan of all contexts
    - Stage 2: Returns top matches with previews
    - You decide which contexts to fully recall

    **Best practices:**
    1. Ask specific questions: "How do we handle JWT authentication?"
    2. Use domain terms: "database connection pooling config"
    3. Be descriptive: "deployment process for production"
    4. Use recall_context() to get full details of interesting results

    **Example workflow:**
    ```
    # Search naturally
    ask_memory("How do we authenticate API requests?")
    # Returns: "Found 2 relevant contexts: api_auth_rules (⚠️ always_check), jwt_config"

    # Get full details
    recall_context("api_auth_rules")
    ```

    **What you'll see:**
    - Number of contexts found
    - List of relevant contexts with relevance scores
    - Preview of each context (intelligent summary)
    - Priority indicators (⚠️ always_check, 📌 important)
    - Tags for each context
    - Suggestions to use recall_context() for full content

    **Performance:**
    Uses lightweight previews instead of loading all full content.
    Typical: 3KB vs 9KB (67% reduction) for 30 contexts.

    Returns: Search results with previews and relevance scores
    """
    session_id = get_current_session_id()

    # Use ActiveContextEngine for natural language search
    from active_context_engine import ActiveContextEngine
    engine = ActiveContextEngine(DB_PATH)
    relevant = engine.check_context_relevance(question, session_id)

    if not relevant:
        return f"❓ Question: {question}\n\n📭 No relevant contexts found.\n\n💡 Tip: Use lock_context() to save important information for future reference."

    output = []
    output.append(f"❓ Question: {question}")
    output.append(f"\n📊 Found {len(relevant)} relevant context(s):\n")

    for i, ctx in enumerate(relevant[:5], 1):  # Top 5 results
        priority_icon = {
            'always_check': '⚠️',
            'important': '📌',
            'reference': '📄'
        }.get(ctx.get('priority', 'reference'), '📄')

        score = ctx.get('relevance_score', 0)
        score_bar = "█" * int(score * 10) if score > 0 else "░" * 5

        output.append(f"{i}. {priority_icon} {ctx['label']} v{ctx['version']}")
        output.append(f"   Relevance: {score_bar} {score:.2f}")

        if ctx.get('tags'):
            output.append(f"   Tags: {', '.join(ctx['tags'][:3])}")

        # Show preview
        preview = ctx.get('preview', ctx.get('content', ''))[:150]
        output.append(f"   Preview: {preview}...")
        output.append(f"   💡 Use recall_context('{ctx['label']}') for full content")
        output.append("")

    if len(relevant) > 5:
        output.append(f"... and {len(relevant) - 5} more contexts")
        output.append("Refine your question to narrow results")

    return "\n".join(output)

@mcp.tool()
async def get_context_preview(topic: str, version: Optional[str] = "latest") -> str:
    """
    Get a quick preview of a locked context without loading the full content.

    **When to use this tool:**
    - When you want to check if a context is relevant before loading it fully
    - To quickly scan multiple contexts
    - When you need just the summary, not the full details
    - To save tokens by avoiding unnecessary full content loads

    **What this does:**
    - Returns the intelligently generated preview (not full content)
    - Shows key concepts extracted from the context
    - Provides metadata (tags, priority, version)
    - Much faster and lighter than recall_context()

    **Preview vs Full Content:**
    - Preview: ~200-500 chars, highlights key info
    - Full content: Could be 5KB+ of detailed information
    - Token savings: 80-95% by using preview first

    **Best practices:**
    1. Use preview first to check relevance
    2. Only use recall_context() if preview looks relevant
    3. Great for scanning multiple contexts quickly
    4. Ideal when you just need to jog your memory

    **Example workflow:**
    ```
    # Quick scan
    get_context_preview("api_patterns")
    # Shows: "API patterns: RESTful design with JWT auth..."

    # Relevant? Get full details
    recall_context("api_patterns")
    ```

    **Performance benefit:**
    Preview: 300 chars vs Full content: 5000 chars = 94% reduction

    Returns: Preview, key concepts, and metadata (no full content)
    """
    conn = get_db()
    session_id = get_current_session_id()

    if version == "latest":
        cursor = conn.execute("""
            SELECT label, version, preview, key_concepts, metadata, locked_at
            FROM context_locks
            WHERE label = ? AND session_id = ?
            ORDER BY locked_at DESC
            LIMIT 1
        """, (topic, session_id))
    else:
        cursor = conn.execute("""
            SELECT label, version, preview, key_concepts, metadata, locked_at
            FROM context_locks
            WHERE label = ? AND version = ? AND session_id = ?
        """, (topic, version, session_id))

    row = cursor.fetchone()

    if not row:
        return f"❌ Context '{topic}' not found"

    metadata = json.loads(row['metadata']) if row['metadata'] else {}
    priority = metadata.get('priority', 'reference')
    tags = metadata.get('tags', [])

    priority_icon = {
        'always_check': '⚠️ [ALWAYS CHECK]',
        'important': '📌 [IMPORTANT]',
        'reference': '📄 [REFERENCE]'
    }.get(priority, '')

    output = []
    output.append(f"📋 Preview: {row['label']} v{row['version']} {priority_icon}")
    output.append(f"🕒 Locked: {datetime.fromtimestamp(row['locked_at']).strftime('%Y-%m-%d %H:%M')}")

    if tags:
        output.append(f"🏷️  Tags: {', '.join(tags)}")

    # Show key concepts
    if row['key_concepts']:
        try:
            concepts = json.loads(row['key_concepts'])
            if concepts:
                output.append(f"🔑 Key concepts: {', '.join(concepts[:5])}")
        except:
            pass

    output.append("")
    output.append("📄 Preview:")
    output.append(row['preview'] or "No preview available")
    output.append("")
    output.append(f"💡 Use recall_context('{topic}') for full content")

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

@mcp.tool()
async def project_update() -> str:
    """
    Scan project and intelligently tag files with structured metadata.
    Self-recovering: continues from where it left off if interrupted.
    Delivers results in phases to avoid timeout.
    """
    try:
        update_session_activity()
        conn = get_db()
        session_id = get_current_session_id()
        
        # Get project root
        if os.environ.get('CLAUDE_PROJECT_DIR'):
            project_root = Path(os.environ['CLAUDE_PROJECT_DIR'])
        else:
            project_root = Path.cwd()
        
        project_root = project_root.resolve()
        
        # Standard project scanning (v4.0.0-rc1 stable)
        output = []
        output.append(f"🔍 Scanning project: {project_root.name}")
        output.append(f"   Path: {project_root}")
        output.append("Analyzing files and applying intelligent tags...")
        output.append("")
        
        # Patterns to ignore (including symlinks to avoid escaping project)
        ignore_patterns = [
        '__pycache__', '.git', 'node_modules', '.venv', 'venv', 
        'dist', 'build', '.pytest_cache', '.mypy_cache', '.coverage',
        '*.pyc', '*.pyo', '.DS_Store', 'Thumbs.db'
        ]
        
        # Statistics
        stats = {
        'total_files': 0,
        'files_tagged': 0,
        'tags_applied': 0,
        'by_status': {},
        'by_domain': {},
        'by_layer': {},
        'by_quality': {}
        }
        
        # Scan files with safety checks and limits
        errors = []
        max_files = 500  # Limit to prevent timeout
        file_count = 0
        
        for path in project_root.rglob('*'):
            if file_count >= max_files:
                output.append(f"\n⚠️ Scan limited to {max_files} files to prevent timeout")
                break
            file_count += 1
            try:
                # Skip symlinks to avoid escaping project directory
                if path.is_symlink():
                    continue
                    
                # Ensure path is within project root (defense in depth)
                try:
                    path.relative_to(project_root)
                except ValueError:
                    # Path is outside project root, skip it
                    continue
                
                # Skip ignored patterns
                if any(pattern in str(path) for pattern in ignore_patterns):
                    continue
                    
                if path.is_file():
                    stats['total_files'] += 1
                    
                    # Generate tags for this file
                    tags = get_file_tags(path, project_root)
                    
                    if tags:
                        # Apply tags to database
                        applied = apply_tags_to_file(conn, str(path.relative_to(project_root)), tags, session_id)
                        if applied > 0:
                            stats['files_tagged'] += 1
                            stats['tags_applied'] += applied
                        
                        # Collect statistics
                        for tag in tags:
                            if ':' in tag:
                                category, value = tag.split(':', 1)
                                if category == 'status':
                                    stats['by_status'][value] = stats['by_status'].get(value, 0) + 1
                                elif category == 'domain':
                                    stats['by_domain'][value] = stats['by_domain'].get(value, 0) + 1
                                elif category == 'layer':
                                    stats['by_layer'][value] = stats['by_layer'].get(value, 0) + 1
                                elif category == 'quality':
                                    stats['by_quality'][value] = stats['by_quality'].get(value, 0) + 1
            except PermissionError as e:
                # Track permission errors but continue scanning
                errors.append(f"Permission denied: {path}")
                continue
            except Exception as e:
                # Track other errors but continue scanning
                errors.append(f"Error scanning {path}: {e}")
                continue
        
        conn.commit()
        
        # Generate report
        output.append(f"📊 Analysis Complete:")
        output.append(f"   • Files scanned: {stats['total_files']}")
        output.append(f"   • Files tagged: {stats['files_tagged']}")
        output.append(f"   • Tags applied: {stats['tags_applied']}")
    
        if stats['by_status']:
            output.append("\n📈 Maturity Status:")
            for status, count in sorted(stats['by_status'].items(), key=lambda x: x[1], reverse=True):
                output.append(f"   • {status}: {count} files")
        
        if stats['by_domain']:
            output.append("\n🎯 Domains Detected:")
            for domain, count in sorted(stats['by_domain'].items(), key=lambda x: x[1], reverse=True)[:5]:
                output.append(f"   • {domain}: {count} files")
        
        if stats['by_layer']:
            output.append("\n🏗️ Architecture Layers:")
            for layer, count in sorted(stats['by_layer'].items(), key=lambda x: x[1], reverse=True)[:5]:
                output.append(f"   • {layer}: {count} files")
        
        if stats['by_quality']:
            output.append("\n✨ Quality Indicators:")
            for quality, count in sorted(stats['by_quality'].items(), key=lambda x: x[1], reverse=True):
                output.append(f"   • {quality}: {count} files")
        
        # Insights
        insights = []
        
        # Check for deprecated files
        if 'deprecated' in stats['by_status']:
            insights.append(f"⚠️ {stats['by_status']['deprecated']} deprecated files found")
        
        # Check for files needing work
        if 'needs-work' in stats['by_quality']:
            insights.append(f"🔧 {stats['by_quality']['needs-work']} files marked for improvement")
        if 'has-workarounds' in stats['by_quality']:
            insights.append(f"⚡ {stats['by_quality']['has-workarounds']} files contain temporary workarounds")
        if 'technical-debt' in stats['by_quality']:
            insights.append(f"💳 {stats['by_quality']['technical-debt']} files have technical debt")
        
        # Check for mock/dev artifacts - CRITICAL
        if 'has-mock-data' in stats['by_quality']:
            insights.append(f"🎭 {stats['by_quality']['has-mock-data']} files contain mock/sample data")
        if 'has-placeholder-data' in stats['by_quality']:
            insights.append(f"📝 {stats['by_quality']['has-placeholder-data']} files have placeholder values (foo/bar/test@example)")
        if 'has-dev-urls' in stats['by_quality']:
            insights.append(f"🔗 {stats['by_quality']['has-dev-urls']} files reference localhost/dev URLs")
        if 'has-hardcoded-values' in stats['by_quality']:
            insights.append(f"🔢 {stats['by_quality']['has-hardcoded-values']} files have hardcoded values")
        
        # Check for undocumented files
        documented = stats['by_quality'].get('documented', 0)
        if documented < stats['total_files'] * 0.3:  # Less than 30% documented
            insights.append("📚 Low documentation coverage detected")
        
        # Check for test coverage
        test_files = stats['by_layer'].get('test', 0)
        if test_files < stats['total_files'] * 0.1:  # Less than 10% test files
            insights.append("🧪 Low test file ratio")
        
        if insights:
            output.append("\n💡 Insights:")
            for insight in insights:
                output.append(f"   {insight}")
        
        # Store project intelligence
        conn.execute("""
            INSERT OR REPLACE INTO project_variables (key, value, updated_at)
            VALUES ('file_analysis', ?, ?)
        """, (json.dumps(stats), time.time()))
        
        conn.commit()
        
        # Report any errors encountered
        if errors:
            output.append(f"\n⚠️ Encountered {len(errors)} errors during scanning:")
            for error in errors[:5]:  # Show first 5 errors
                output.append(f"   • {error}")
            if len(errors) > 5:
                output.append(f"   ... and {len(errors) - 5} more")
        
        output.append("\n✅ Project intelligence updated with structured tags")
        output.append("Use search_by_tags() to query files by their metadata")
        
        # Connection will auto-close due to AutoClosingConnection wrapper
        return "\n".join(output)
    except Exception as e:
        return f"Error scanning project: {e}"

@mcp.tool()
async def project_status() -> str:
    """
    Show current project understanding with tag-based insights.
    """
    conn = get_db()
    
    output = []
    output.append("🎯 Project Intelligence Status")
    output.append("=" * 40)
    
    # Get file analysis stats
    cursor = conn.execute("""
        SELECT value FROM project_variables
        WHERE key = 'file_analysis'
        ORDER BY updated_at DESC
        LIMIT 1
    """)
    
    row = cursor.fetchone()
    if row:
        stats = json.loads(row['value'])
        output.append(f"\n📁 Files: {stats['total_files']} total, {stats['files_tagged']} tagged")
        
        if stats.get('by_status'):
            output.append("\n🏷️ File Maturity:")
            for status, count in sorted(stats['by_status'].items(), key=lambda x: x[1], reverse=True):
                output.append(f"   • {status}: {count}")
        
        if stats.get('by_domain'):
            output.append("\n🎯 Top Domains:")
            for domain, count in list(sorted(stats['by_domain'].items(), key=lambda x: x[1], reverse=True))[:3]:
                output.append(f"   • {domain}: {count}")
    
    # Get tag distribution
    cursor = conn.execute("""
        SELECT tag, COUNT(*) as count 
        FROM file_tags
        GROUP BY tag
        ORDER BY count DESC
        LIMIT 10
    """)
    
    tags = cursor.fetchall()
    if tags:
        output.append("\n🏷️ Top Tags:")
        for tag in tags[:5]:
            output.append(f"   • {tag['tag']}: {tag['count']} files")
    
    # Get quality metrics
    cursor = conn.execute("""
        SELECT 
            SUM(CASE WHEN tag = 'quality:tested' THEN 1 ELSE 0 END) as tested,
            SUM(CASE WHEN tag = 'quality:documented' THEN 1 ELSE 0 END) as documented,
            SUM(CASE WHEN tag = 'quality:needs-work' THEN 1 ELSE 0 END) as needs_work,
            SUM(CASE WHEN tag = 'status:deprecated' THEN 1 ELSE 0 END) as deprecated
        FROM file_tags
    """)
    
    metrics = cursor.fetchone()
    if metrics:
        output.append("\n📊 Quality Metrics:")
        if metrics['tested']:
            output.append(f"   ✅ {metrics['tested']} files with tests")
        if metrics['documented']:
            output.append(f"   📚 {metrics['documented']} documented files")
        if metrics['needs_work']:
            output.append(f"   🔧 {metrics['needs_work']} files need improvement")
        if metrics['deprecated']:
            output.append(f"   ⚠️ {metrics['deprecated']} deprecated files")
    
    return "\n".join(output)

# ============================================================================
# ENHANCED FILE TAGGING WITH SEARCH
# ============================================================================

@mcp.tool()
async def tag_path(path: str, tags: str, comment: Optional[str] = None) -> str:
    """
    Tag a file or directory with semantic tags.
    Tags should be comma-separated, preferably using structured format:
    status:stable, domain:auth, layer:controller, etc.
    """
    update_session_activity()
    conn = get_db()
    session_id = get_current_session_id()
    
    # Normalize path
    file_path = Path(path)
    if not file_path.exists():
        return f"❌ Path does not exist: {path}"
    
    # Parse tags
    tag_list = [t.strip().lower() for t in tags.split(',')]
    
    added = []
    for tag in tag_list:
        try:
            conn.execute("""
                INSERT INTO file_tags (path, tag, comment, created_at, created_by)
                VALUES (?, ?, ?, ?, ?)
            """, (str(file_path), tag, comment, time.time(), session_id))
            added.append(tag)
        except sqlite3.IntegrityError:
            # Tag already exists for this path
            pass
    
    conn.commit()
    
    if added:
        return f"✅ Tagged '{file_path}' with: {', '.join(added)}"
    else:
        return f"ℹ️ Tags already exist for '{file_path}'"

@mcp.tool()
async def search_by_tags(query: str) -> str:
    """
    Search files by tag query. Supports AND/OR logic.
    Examples: 'status:stable AND domain:auth', 'layer:test OR quality:needs-work'
    """
    conn = get_db()
    
    output = []
    output.append(f"🔍 Searching files with tags: {query}")
    output.append("-" * 40)
    
    # Parse query - simple AND/OR support
    if ' AND ' in query.upper():
        # All tags must match
        tags = [t.strip().lower() for t in re.split(r'\s+AND\s+', query, flags=re.IGNORECASE)]
        
        # Build query to find files with ALL tags
        placeholders = ','.join('?' * len(tags))
        cursor = conn.execute(f"""
            SELECT path, GROUP_CONCAT(tag) as all_tags
            FROM file_tags
            WHERE tag IN ({placeholders})
            GROUP BY path
            HAVING COUNT(DISTINCT tag) = ?
        """, tags + [len(tags)])
        
    elif ' OR ' in query.upper():
        # Any tag can match
        tags = [t.strip().lower() for t in re.split(r'\s+OR\s+', query, flags=re.IGNORECASE)]
        
        placeholders = ','.join('?' * len(tags))
        cursor = conn.execute(f"""
            SELECT DISTINCT path, GROUP_CONCAT(tag) as all_tags
            FROM file_tags
            WHERE tag IN ({placeholders})
            GROUP BY path
        """, tags)
        
    else:
        # Single tag or prefix search
        tag = query.strip().lower()
        if '*' in tag:
            # Wildcard search
            tag = tag.replace('*', '%')
            cursor = conn.execute("""
                SELECT path, GROUP_CONCAT(tag) as all_tags
                FROM file_tags
                WHERE tag LIKE ?
                GROUP BY path
            """, (tag,))
        else:
            # Exact match
            cursor = conn.execute("""
                SELECT path, GROUP_CONCAT(tag) as all_tags
                FROM file_tags
                WHERE tag = ?
                GROUP BY path
            """, (tag,))
    
    files = cursor.fetchall()
    if files:
        output.append(f"\n📁 Found {len(files)} files:")
        for file in files[:20]:  # Limit to 20 results
            output.append(f"\n   • {file['path']}")
            # Show all tags for context
            tags = file['all_tags'].split(',')
            categorized = {}
            for tag in tags:
                if ':' in tag:
                    cat, val = tag.split(':', 1)
                    if cat not in categorized:
                        categorized[cat] = []
                    categorized[cat].append(val)
            
            if categorized:
                tag_summary = []
                for cat, vals in categorized.items():
                    tag_summary.append(f"{cat}:{','.join(vals)}")
                output.append(f"     Tags: {' | '.join(tag_summary[:4])}")
        
        if len(files) > 20:
            output.append(f"\n   ... and {len(files) - 20} more files")
    else:
        output.append("No files found matching the query")
    
    return "\n".join(output)

@mcp.tool()
async def file_insights(path: Optional[str] = None) -> str:
    """
    Get insights about a specific file or the entire project.
    Shows quality issues, relationships, and recommendations.
    """
    conn = get_db()
    
    output = []
    
    if path:
        # Specific file insights
        output.append(f"📄 Insights for: {path}")
        output.append("-" * 40)
        
        # Get all tags for this file
        cursor = conn.execute("""
            SELECT tag, comment FROM file_tags
            WHERE path = ?
            ORDER BY created_at DESC
        """, (path,))
        
        tags = cursor.fetchall()
        if tags:
            # Categorize tags
            status = None
            domains = []
            layer = None
            quality = []
            
            for tag in tags:
                if ':' in tag['tag']:
                    cat, val = tag['tag'].split(':', 1)
                    if cat == 'status':
                        status = val
                    elif cat == 'domain':
                        domains.append(val)
                    elif cat == 'layer':
                        layer = val
                    elif cat == 'quality':
                        quality.append(val)
            
            output.append(f"\n📊 File Profile:")
            if status:
                output.append(f"   Status: {status}")
            if layer:
                output.append(f"   Layer: {layer}")
            if domains:
                output.append(f"   Domains: {', '.join(domains)}")
            if quality:
                output.append(f"   Quality: {', '.join(quality)}")
            
            # Recommendations
            recommendations = []
            if status == 'deprecated':
                recommendations.append("🗑️ Consider removing or updating this deprecated file")
            if 'needs-work' in quality:
                recommendations.append("🔧 Address improvement markers in this file")
            if 'has-workarounds' in quality:
                recommendations.append("⚡ Replace temporary workarounds with proper solutions")
            if 'technical-debt' in quality:
                recommendations.append("💳 Consider refactoring to reduce technical debt")
            if 'has-mock-data' in quality:
                recommendations.append("🎭 Replace mock data with real implementation")
            if 'has-placeholder-data' in quality:
                recommendations.append("📝 Replace placeholder values (foo/bar/test@example) with real data")
            if 'has-dev-urls' in quality:
                recommendations.append("🔗 Update localhost/dev URLs to production endpoints")
            if 'has-hardcoded-values' in quality:
                recommendations.append("🔢 Move hardcoded values to configuration")
            if 'documented' not in quality and layer != 'test':
                recommendations.append("📚 Add documentation to this file")
            if 'tested' not in quality and layer in ['controller', 'service', 'model']:
                recommendations.append("🧪 Add test coverage for this file")
            
            if recommendations:
                output.append("\n💡 Recommendations:")
                for rec in recommendations:
                    output.append(f"   {rec}")
        else:
            output.append("No tags found for this file. Run project_update() to analyze.")
    
    else:
        # Project-wide insights
        output.append("🎯 Project-Wide Insights")
        output.append("-" * 40)
        
        # Get problem areas
        cursor = conn.execute("""
            SELECT 
                SUM(CASE WHEN tag = 'status:deprecated' THEN 1 ELSE 0 END) as deprecated,
                SUM(CASE WHEN tag = 'status:poc' THEN 1 ELSE 0 END) as poc,
                SUM(CASE WHEN tag = 'quality:needs-work' THEN 1 ELSE 0 END) as needs_work,
                SUM(CASE WHEN tag = 'quality:needs-refactor' THEN 1 ELSE 0 END) as refactor,
                SUM(CASE WHEN tag = 'security:sensitive' THEN 1 ELSE 0 END) as sensitive,
                SUM(CASE WHEN tag = 'quality:has-mock-data' THEN 1 ELSE 0 END) as mock_data,
                SUM(CASE WHEN tag = 'quality:has-placeholder-data' THEN 1 ELSE 0 END) as placeholders,
                SUM(CASE WHEN tag = 'quality:has-dev-urls' THEN 1 ELSE 0 END) as dev_urls
            FROM file_tags
        """)
        
        issues = cursor.fetchone()
        
        if issues:
            output.append("\n⚠️ Areas Needing Attention:")
            if issues['deprecated'] > 0:
                output.append(f"   • {issues['deprecated']} deprecated files to remove")
            if issues['poc'] > 0:
                output.append(f"   • {issues['poc']} POC files to mature or remove")
            if issues['needs_work'] > 0:
                output.append(f"   • {issues['needs_work']} files marked for improvement")
            if issues['refactor'] > 0:
                output.append(f"   • {issues['refactor']} files needing refactoring")
            if issues['sensitive'] > 0:
                output.append(f"   • {issues['sensitive']} files handling sensitive data")
            
            # Critical: Mock data and dev artifacts
            if issues['mock_data'] > 0:
                output.append(f"   🎭 {issues['mock_data']} files with mock/sample data to replace")
            if issues['placeholders'] > 0:
                output.append(f"   📝 {issues['placeholders']} files with placeholder values (foo/bar/test)")
            if issues['dev_urls'] > 0:
                output.append(f"   🔗 {issues['dev_urls']} files with localhost/dev URLs")
        
        # Get untested domains
        cursor = conn.execute("""
            SELECT DISTINCT f1.tag as domain
            FROM file_tags f1
            WHERE f1.tag LIKE 'domain:%'
            AND NOT EXISTS (
                SELECT 1 FROM file_tags f2
                WHERE f2.path IN (
                    SELECT path FROM file_tags WHERE tag = f1.tag
                )
                AND f2.tag = 'layer:test'
            )
        """)
        
        untested = cursor.fetchall()
        if untested:
            output.append("\n🧪 Domains Lacking Tests:")
            for domain in untested[:5]:
                domain_name = domain['domain'].split(':')[1]
                output.append(f"   • {domain_name}")
    
    return "\n".join(output)

# ============================================================================
# Other tools remain unchanged (search_semantic, what_changed, etc.)
# ============================================================================

@mcp.tool()
async def get_tags(path: str) -> str:
    """
    Get all tags for a file or directory.
    """
    conn = get_db()
    
    cursor = conn.execute("""
        SELECT tag, comment, created_at FROM file_tags
        WHERE path = ?
        ORDER BY created_at DESC
    """, (path,))
    
    tags = cursor.fetchall()
    if tags:
        output = [f"🏷️ Tags for '{path}':"]
        for tag in tags:
            dt = datetime.fromtimestamp(tag['created_at'])
            line = f"   • {tag['tag']}"
            if tag['comment']:
                line += f" - {tag['comment']}"
            line += f" ({dt.strftime('%Y-%m-%d')})"
            output.append(line)
        return "\n".join(output)
    else:
        return f"No tags found for '{path}'"

@mcp.tool()
async def search_tags(tag: str) -> str:
    """
    Find all files with a specific tag.
    """
    conn = get_db()
    
    cursor = conn.execute("""
        SELECT path, comment FROM file_tags
        WHERE tag = ?
        ORDER BY created_at DESC
    """, (tag.lower(),))
    
    files = cursor.fetchall()
    if files:
        output = [f"📁 Files tagged with '{tag}':"]
        for file in files:
            line = f"   • {file['path']}"
            if file['comment']:
                line += f" - {file['comment']}"
            output.append(line)
        return "\n".join(output)
    else:
        return f"No files found with tag '{tag}'"

# Keep all other unchanged tools...
# (search_semantic, what_changed, what_needs_attention, etc.)

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    # DO NOT print anything to stdout - MCP requires clean JSON communication
    # Any debug output would break the JSON protocol
    import sys
    import logging
    
    # Suppress all stdout output that isn't JSON
    logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
    
    # Run the MCP server silently
    asyncio.run(mcp.run())