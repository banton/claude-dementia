#!/usr/bin/env python3
"""
Claude Intelligence - MCP Server
A dead-simple project memory for Claude Code
"""

import os
import sys
import json
import sqlite3
import hashlib
import time
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Generator
from dataclasses import dataclass, asdict
import asyncio

# Optional imports
try:
    import xxhash
    HASHER = xxhash.xxh64
except ImportError:
    # Fallback to standard hashlib
    HASHER = lambda: hashlib.md5()

# Default ignore patterns
DEFAULT_IGNORES = [
    'node_modules/', 'dist/', 'build/', '.next/', 'out/',
    'venv/', '.venv/', '__pycache__/', '.pytest_cache/',
    'coverage/', '.git/', '.idea/', '.vscode/',
    '*.pyc', '*.pyo', '*.pyd', '.DS_Store',
    '*.min.js', '*.map', '*.lock', 'package-lock.json',
    'yarn.lock', 'poetry.lock', 'Pipfile.lock'
]


@dataclass
class SearchResult:
    """Search result with metadata"""
    path: str
    score: float
    excerpt: str


class ClaudeIntelligence:
    """Main MCP server class - the entire system"""
    
    def __init__(self, db_path: str = '.claude-memory.db'):
        """Initialize the server and database"""
        self.db_path = db_path
        self.db = None
        self.file_count = 0
        self._init_database()
        self._load_ignore_patterns()
        
    def _init_database(self):
        """Initialize SQLite database with FTS5"""
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        
        # Create main files table
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                hash TEXT NOT NULL,
                indexed_at REAL,
                size_bytes INTEGER,
                metadata TEXT
            )
        """)
        
        # Create FTS5 virtual table for full-text search
        self.db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS file_fts USING fts5(
                path,
                content,
                tokenize='porter unicode61'
            )
        """)
        
        # Create indexes
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_files_hash ON files(hash)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_files_indexed ON files(indexed_at)")
        
        # Create metadata table
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            )
        """)
        
        # Create sessions table for tracking
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                files_indexed INTEGER,
                tech_stack TEXT
            )
        """)
        
        self.db.commit()
    
    def _load_ignore_patterns(self):
        """Load ignore patterns from .gitignore and defaults"""
        self.ignore_patterns = set(DEFAULT_IGNORES)
        
        # Load .gitignore if exists
        if Path('.gitignore').exists():
            with open('.gitignore', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.ignore_patterns.add(line)
        
        # Load .claude-ignore if exists
        if Path('.claude-ignore').exists():
            with open('.claude-ignore', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.ignore_patterns.add(line)
    
    def should_ignore(self, path: str) -> bool:
        """Check if file should be ignored"""
        path_str = str(path)
        
        # Check each ignore pattern
        for pattern in self.ignore_patterns:
            # Simple pattern matching (not full glob)
            if pattern.endswith('/'):
                # Directory pattern
                if pattern[:-1] in path_str.split(os.sep):
                    return True
            elif pattern.startswith('*.'):
                # Extension pattern
                if path_str.endswith(pattern[1:]):
                    return True
            elif pattern in path_str:
                return True
        
        # Skip large files (>200KB)
        try:
            if Path(path).stat().st_size > 200_000:
                return True
        except:
            pass
            
        return False
    
    def get_file_hash(self, file_path: str) -> str:
        """Get content hash of a file"""
        try:
            hasher = HASHER()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
            return hasher.hexdigest() if hasattr(hasher, 'hexdigest') else hasher.digest().hex()
        except Exception:
            return ""
    
    def extract_semantic_content(self, file_path: str, content: str) -> str:
        """Extract semantic content for indexing (max 2KB)"""
        semantic_parts = []
        
        # Extract function/class definitions
        for match in re.finditer(r'(?:def|class|function|const|var|let)\s+(\w+)', content):
            semantic_parts.append(match.group(1))
        
        # Extract comments and docstrings
        for match in re.finditer(r'(?:#|//|/\*|\"\"\"|\'\'\')\s*(.+)', content):
            semantic_parts.append(match.group(1)[:100])  # Limit comment length
        
        # Extract imports
        for match in re.finditer(r'(?:import|from|require|include)\s+([^\s;]+)', content):
            semantic_parts.append(match.group(1))
        
        # Combine and limit to 2KB
        text = ' '.join(semantic_parts)[:2000]
        return text if text else Path(file_path).stem  # Use filename if no content
    
    def index_file(self, file_path: str):
        """Index a single file"""
        if self.should_ignore(file_path):
            return
            
        try:
            file_hash = self.get_file_hash(file_path)
            
            # Check if file needs reindexing
            cursor = self.db.execute(
                "SELECT hash FROM files WHERE path = ?", 
                (file_path,)
            )
            existing = cursor.fetchone()
            
            if existing and existing['hash'] == file_hash:
                return  # File unchanged
            
            # Read and extract content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            semantic_content = self.extract_semantic_content(file_path, content)
            
            # Track if this is a new file
            is_new = existing is None
            
            # Update database
            self.db.execute("""
                INSERT OR REPLACE INTO files (path, hash, indexed_at, size_bytes)
                VALUES (?, ?, ?, ?)
            """, (
                file_path,
                file_hash,
                time.time(),
                Path(file_path).stat().st_size
            ))
            
            # Update FTS index
            self.db.execute("""
                INSERT OR REPLACE INTO file_fts (path, content)
                VALUES (?, ?)
            """, (file_path, semantic_content))
            
            self.db.commit()
            
            # Only increment for new files
            if is_new:
                self.file_count += 1
            
        except Exception as e:
            # Silently skip files we can't read
            pass
    
    def index_progressive(self) -> Generator[str, None, None]:
        """Progressive indexing with feedback"""
        indexed_count = 0
        
        # Phase 1: Current directory (depth 1)
        yield "Indexing current directory..."
        for file in Path('.').iterdir():
            if file.is_file():
                self.index_file(str(file))
                indexed_count += 1
        yield f"Indexed current directory ({indexed_count} files)"
        
        # Phase 2: Source directories
        src_dirs = ['src', 'lib', 'app', 'components', 'pages', 'api']
        for dir_name in src_dirs:
            if Path(dir_name).exists():
                dir_count = 0
                for file in Path(dir_name).rglob('*'):
                    if file.is_file():
                        self.index_file(str(file))
                        dir_count += 1
                if dir_count > 0:
                    indexed_count += dir_count
                    yield f"Indexed {dir_name}/ ({dir_count} files)"
        
        # Phase 3: Everything else
        remaining_count = 0
        for file in Path('.').rglob('*'):
            if file.is_file():
                # Skip if already indexed
                cursor = self.db.execute(
                    "SELECT 1 FROM files WHERE path = ?",
                    (str(file),)
                )
                if not cursor.fetchone():
                    self.index_file(str(file))
                    remaining_count += 1
        
        if remaining_count > 0:
            indexed_count += remaining_count
            yield f"Indexed remaining files ({remaining_count} files)"
        
        # Save session info
        self._save_session()
        
        yield f"Indexing complete: {indexed_count} files"
    
    def is_indexed(self, file_path: str) -> bool:
        """Check if a file is indexed"""
        cursor = self.db.execute(
            "SELECT 1 FROM files WHERE path = ?",
            (file_path,)
        )
        return cursor.fetchone() is not None
    
    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search files using FTS5"""
        results = []
        
        # FTS5 search with BM25 ranking
        cursor = self.db.execute("""
            SELECT path, snippet(file_fts, 1, '...', '...', '...', 20) as excerpt,
                   bm25(file_fts) as score
            FROM file_fts
            WHERE file_fts MATCH ?
            ORDER BY score
            LIMIT ?
        """, (query, limit))
        
        for row in cursor:
            results.append({
                'path': row['path'],
                'score': abs(row['score']),  # BM25 returns negative scores
                'excerpt': row['excerpt']
            })
        
        # If no results, try fuzzy matching
        if not results:
            # Fallback to LIKE search
            cursor = self.db.execute("""
                SELECT path, content as excerpt
                FROM file_fts
                WHERE content LIKE ?
                LIMIT ?
            """, (f'%{query}%', limit))
            
            for row in cursor:
                results.append({
                    'path': row['path'],
                    'score': 0.5,  # Lower score for fuzzy matches
                    'excerpt': row['excerpt'][:100] if row['excerpt'] else ''
                })
        
        return results
    
    def detect_tech_stack(self) -> List[str]:
        """Detect technology stack from project files"""
        stack = []
        
        # Check for Node.js
        if Path('package.json').exists():
            stack.append('Node.js')
            try:
                with open('package.json', 'r') as f:
                    pkg = json.load(f)
                    deps = pkg.get('dependencies', {})
                    
                    # Detect frameworks
                    if 'react' in deps:
                        stack.append('React')
                    if 'vue' in deps:
                        stack.append('Vue')
                    if 'express' in deps:
                        stack.append('Express')
                    if 'next' in deps:
                        stack.append('Next.js')
                    if '@angular/core' in deps:
                        stack.append('Angular')
            except:
                pass
        
        # Check for Python
        if Path('requirements.txt').exists() or Path('pyproject.toml').exists():
            stack.append('Python')
            if Path('requirements.txt').exists():
                try:
                    with open('requirements.txt', 'r') as f:
                        reqs = f.read().lower()
                        if 'flask' in reqs:
                            stack.append('Flask')
                        if 'django' in reqs:
                            stack.append('Django')
                        if 'fastapi' in reqs:
                            stack.append('FastAPI')
                except:
                    pass
        
        # Check for Docker
        if Path('docker-compose.yml').exists() or Path('Dockerfile').exists():
            stack.append('Docker')
        
        # Check for other languages by extension
        extensions = set()
        for file in Path('.').rglob('*'):
            if file.is_file() and not self.should_ignore(str(file)):
                extensions.add(file.suffix)
        
        if '.go' in extensions:
            stack.append('Go')
        if '.rs' in extensions:
            stack.append('Rust')
        if '.java' in extensions:
            stack.append('Java')
        if '.rb' in extensions:
            stack.append('Ruby')
        
        return stack
    
    # MCP Tool Interface
    async def understand_project(self) -> Dict[str, Any]:
        """MCP tool: Get project overview"""
        stack = self.detect_tech_stack()
        
        # Count files
        cursor = self.db.execute("SELECT COUNT(*) as count FROM files")
        file_count = cursor.fetchone()['count']
        
        summary = f"Project with {file_count} indexed files"
        if stack:
            summary = f"{', '.join(stack[:3])} project with {file_count} files"
        
        return {
            'stack': stack,
            'services': [],  # TODO: Detect services
            'summary': summary
        }
    
    async def find_files(self, query: str, k: int = 10) -> List[Dict[str, Any]]:
        """MCP tool: Find files by semantic search"""
        return self.search(query, k)
    
    def is_git_repo(self) -> bool:
        """Check if current directory is a git repository"""
        return Path('.git').exists()
    
    def get_recent_commits(self, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent git commits"""
        if not self.is_git_repo():
            return []
        
        try:
            # Get commit log
            result = subprocess.run(
                ['git', 'log', f'--max-count={limit}', '--pretty=format:%H|%ai|%s|%an'],
                capture_output=True,
                text=True,
                check=True
            )
            
            commits = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    hash_val, date, message, author = line.split('|', 3)
                    commits.append({
                        'hash': hash_val,
                        'date': date,
                        'message': message,
                        'author': author
                    })
            
            return commits
        except subprocess.CalledProcessError:
            return []
    
    def get_last_session_time(self) -> Optional[float]:
        """Get timestamp of last indexing session"""
        cursor = self.db.execute(
            "SELECT timestamp FROM sessions ORDER BY timestamp DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return row['timestamp'] if row else None
    
    def _save_session(self):
        """Save current session info"""
        tech_stack = json.dumps(self.detect_tech_stack())
        self.db.execute(
            "INSERT INTO sessions (timestamp, files_indexed, tech_stack) VALUES (?, ?, ?)",
            (time.time(), self.file_count, tech_stack)
        )
        self.db.commit()
    
    def get_changes_since_last_index(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get files that changed since last index"""
        changes = {'modified': [], 'added': [], 'deleted': []}
        
        # Get all current files
        current_files = {}
        for path in Path('.').rglob('*'):
            if path.is_file() and not self.should_ignore(str(path)):
                current_files[str(path)] = self.get_file_hash(str(path))
        
        # Compare with indexed files
        cursor = self.db.execute("SELECT path, hash FROM files")
        indexed_files = {row['path']: row['hash'] for row in cursor}
        
        # Find changes
        for path, hash_val in current_files.items():
            if path in indexed_files:
                if indexed_files[path] != hash_val:
                    changes['modified'].append({'path': path})
            else:
                changes['added'].append({'path': path})
        
        # Find deleted files
        for path in indexed_files:
            if path not in current_files:
                changes['deleted'].append({'path': path})
        
        return changes
    
    async def recent_changes(self, since: str = 'auto') -> Dict[str, Any]:
        """MCP tool: Get recent changes"""
        changes = self.get_changes_since_last_index()
        commits = self.get_recent_commits(5) if self.is_git_repo() else []
        
        # Count total changes
        total = len(changes['modified']) + len(changes['added']) + len(changes['deleted'])
        
        summary = f"{total} file changes"
        if commits:
            summary += f", {len(commits)} recent commits"
        
        return {
            'changes': changes,
            'commits': commits,
            'summary': summary
        }


def main():
    """Main entry point for MCP server"""
    print("🧠 Claude Intelligence MCP Server")
    print("Starting...")
    
    server = ClaudeIntelligence()
    
    # Index project
    print("Indexing project files...")
    for update in server.index_progressive():
        print(f"  {update}")
    
    print("Ready!")
    
    # In real MCP implementation, would start server here
    # For now, just run a simple REPL for testing
    while True:
        try:
            query = input("\nSearch (or 'quit'): ")
            if query.lower() == 'quit':
                break
            
            results = server.search(query)
            for result in results:
                print(f"  {result['path']} (score: {result['score']:.2f})")
                if result['excerpt']:
                    print(f"    {result['excerpt']}")
        except KeyboardInterrupt:
            break
    
    print("\nGoodbye!")


if __name__ == '__main__':
    main()