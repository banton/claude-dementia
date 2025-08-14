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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Set, Tuple
import uuid

from mcp.server import FastMCP

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
        # Even if no markers, use project dir if explicitly set
        return os.path.join(project_dir, '.claude-memory.db')
    
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
DB_PATH = get_database_path()

# Use the project directory from environment if available, otherwise current directory
if os.environ.get('CLAUDE_PROJECT_DIR'):
    PROJECT_ROOT = os.environ['CLAUDE_PROJECT_DIR']
else:
    PROJECT_ROOT = os.getcwd()

PROJECT_NAME = os.path.basename(PROJECT_ROOT) or 'Claude Desktop'

# Show where database is stored (for debugging)
if 'claude-dementia' in DB_PATH:
    DB_LOCATION = 'user cache'
else:
    DB_LOCATION = 'project local'

def get_db():
    """Get database connection with row factory"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Initialize database schema if needed
    initialize_database(conn)
    
    return conn

def initialize_database(conn):
    """Create database tables if they don't exist"""
    cursor = conn.cursor()
    
    # Create sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            started_at REAL NOT NULL,
            ended_at REAL,
            last_active REAL,
            summary TEXT
        )
    ''')
    
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
    """Get or create current session ID"""
    conn = get_db()
    
    # Find active session (not ended within last hour)
    cursor = conn.execute("""
        SELECT id FROM sessions 
        WHERE ended_at IS NULL 
           OR ended_at > ?
        ORDER BY started_at DESC
        LIMIT 1
    """, (time.time() - 3600,))
    
    row = cursor.fetchone()
    if row:
        # Update last_active
        conn.execute("""
            UPDATE sessions 
            SET last_active = ?
            WHERE id = ?
        """, (time.time(), row['id']))
        conn.commit()
        return row['id']
    
    # Create new session
    session_id = str(uuid.uuid4())[:8]
    conn.execute("""
        INSERT INTO sessions (id, started_at, last_active)
        VALUES (?, ?, ?)
    """, (session_id, time.time(), time.time()))
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
    output.append("🌅 Good morning! Loading your context...")
    output.append(f"Session: {session_id}")
    output.append(f"Context: {PROJECT_NAME}")
    output.append(f"Location: {PROJECT_ROOT}")
    output.append(f"Memory: {DB_PATH} ({DB_LOCATION})")
    output.append("")
    
    # Get recent updates
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
    
    # Get recent locked contexts  
    cursor = conn.execute("""
        SELECT label, COUNT(*) as count 
        FROM context_locks 
        WHERE session_id = ?
        GROUP BY label 
        ORDER BY MAX(locked_at) DESC 
        LIMIT 3
    """, (session_id,))
    
    topics = cursor.fetchall()
    if topics:
        output.append("\n🔒 Locked contexts:")
        for row in topics:
            output.append(f"   • {row['label']} ({row['count']} versions)")
    
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
    End development session with summary.
    Marks session as ended and provides summary.
    """
    conn = get_db()
    session_id = get_current_session_id()
    
    # Get session stats
    cursor = conn.execute("""
        SELECT started_at FROM sessions WHERE id = ?
    """, (session_id,))
    session = cursor.fetchone()
    
    if not session:
        return "No active session to end"
    
    duration = time.time() - session['started_at']
    hours = int(duration // 3600)
    minutes = int((duration % 3600) // 60)
    
    # Get work done
    cursor = conn.execute("""
        SELECT COUNT(*) as count FROM memory_entries
        WHERE session_id = ? AND category = 'progress'
    """, (session_id,))
    progress = cursor.fetchone()
    
    cursor = conn.execute("""
        SELECT COUNT(*) as count FROM context_locks
        WHERE session_id = ?
    """, (session_id,))
    locks = cursor.fetchone()
    
    cursor = conn.execute("""
        SELECT COUNT(*) as completed FROM todos
        WHERE status = 'completed' 
          AND completed_at > ?
    """, (session['started_at'],))
    todos_done = cursor.fetchone()
    
    # Create summary
    summary_parts = []
    if progress['count'] > 0:
        summary_parts.append(f"{progress['count']} progress updates")
    if locks['count'] > 0:
        summary_parts.append(f"{locks['count']} contexts locked")
    if todos_done['completed'] > 0:
        summary_parts.append(f"{todos_done['completed']} TODOs completed")
    
    summary = f"Session {session_id}: " + ", ".join(summary_parts) if summary_parts else "No specific progress tracked"
    
    # Mark session as ended
    conn.execute("""
        UPDATE sessions 
        SET ended_at = ?, summary = ?
        WHERE id = ?
    """, (time.time(), summary, session_id))
    conn.commit()
    
    output = []
    output.append("💤 Ending session...")
    output.append(f"Duration: {hours}h {minutes}m")
    output.append("")
    output.append("📊 Session Summary:")
    if progress['count'] > 0:
        output.append(f"   • {progress['count']} progress updates")
    if locks['count'] > 0:
        output.append(f"   • {locks['count']} contexts locked")
    if todos_done['completed'] > 0:
        output.append(f"   • {todos_done['completed']} TODOs completed")
    
    # Get pending work
    cursor = conn.execute("""
        SELECT COUNT(*) as pending FROM todos WHERE status = 'pending'
    """)
    pending = cursor.fetchone()
    if pending['pending'] > 0:
        output.append(f"\n📌 {pending['pending']} TODOs remaining for next session")
    
    output.append("\nSee you next time! 👋")
    
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
async def lock_context(content: str, topic: str, tags: Optional[str] = None) -> str:
    """
    Lock context under specific topic with tags.
    Creates immutable snapshot with version tracking.
    """
    update_session_activity()
    conn = get_db()
    session_id = get_current_session_id()
    
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
    
    # Prepare metadata
    metadata = {"tags": tags.split(',') if tags else []}
    
    # Store lock
    try:
        conn.execute("""
            INSERT INTO context_locks 
            (session_id, label, version, content, content_hash, locked_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session_id, topic, version, content, content_hash, time.time(), json.dumps(metadata)))
        
        conn.commit()
        return f"✅ Locked '{topic}' as v{version} ({len(content)} chars, hash: {content_hash[:8]})"
        
    except sqlite3.IntegrityError:
        return f"❌ Version {version} of '{topic}' already exists"
    except Exception as e:
        return f"❌ Failed to lock context: {str(e)}"

@mcp.tool()
async def recall_context(topic: str, version: Optional[str] = "latest") -> str:
    """
    Recall locked context by topic and version.
    Use 'latest' for most recent version.
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
               MAX(locked_at) as latest
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
            output.append(f"\n• {row['label']}")
            output.append(f"  Versions: v{', v'.join(versions)}")
            output.append(f"  Last updated: {dt.strftime('%Y-%m-%d %H:%M')}")
        return "\n".join(output)
    else:
        return "No locked contexts yet. Use lock_context to save important information."

# ============================================================================
# ENHANCED PROJECT INTELLIGENCE WITH AUTO-TAGGING
# ============================================================================

@mcp.tool()
async def project_update() -> str:
    """
    Scan project and intelligently tag files with structured metadata.
    Tags include: status, domain, layer, quality, dependencies, etc.
    """
    update_session_activity()
    conn = get_db()
    session_id = get_current_session_id()
    
    # Get project root - use the environment variable if set, otherwise current directory
    if os.environ.get('CLAUDE_PROJECT_DIR'):
        project_root = Path(os.environ['CLAUDE_PROJECT_DIR'])
    else:
        project_root = Path.cwd()
    
    output = []
    output.append(f"🔍 Scanning project: {project_root.name}")
    output.append("Analyzing files and applying intelligent tags...")
    output.append("")
    
    # Patterns to ignore
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
    
    # Scan files
    for path in project_root.rglob('*'):
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
    
    output.append("\n✅ Project intelligence updated with structured tags")
    output.append("Use search_by_tags() to query files by their metadata")
    
    return "\n".join(output)

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