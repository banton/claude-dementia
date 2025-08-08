#!/usr/bin/env python3
"""
File System Monitor for Unavoidable Documentation System
Watches for file changes and creates documentation debt entries
"""

import os
import sys
import time
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

class DocumentationDebtCreator:
    """Creates and manages documentation debt in the database"""
    
    def __init__(self, db_config: dict):
        self.db_config = db_config
        self.conn = None
        self.connect()
    
    def connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(
                host=self.db_config.get('host', 'localhost'),
                port=self.db_config.get('port', 5432),
                database=self.db_config.get('database', 'unavoidable_docs'),
                user=self.db_config.get('user', 'unavoidable_docs_user'),
                password=self.db_config.get('password', '')
            )
            self.conn.autocommit = True
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            sys.exit(1)
    
    def get_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file contents"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except:
            return ""
    
    def get_file_stats(self, file_path: str) -> dict:
        """Get file statistics"""
        stats = {
            'file_size': 0,
            'line_count': 0,
            'file_type': Path(file_path).suffix[1:] if Path(file_path).suffix else 'unknown'
        }
        
        try:
            stats['file_size'] = os.path.getsize(file_path)
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                stats['line_count'] = sum(1 for _ in f)
        except:
            pass
        
        return stats
    
    def create_file_entry(self, file_path: str) -> Optional[int]:
        """Create or update file documentation status entry"""
        file_hash = self.get_file_hash(file_path)
        stats = self.get_file_stats(file_path)
        
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check if file already exists
            cur.execute(
                "SELECT id, file_hash, status FROM file_documentation_status WHERE file_path = %s",
                (file_path,)
            )
            existing = cur.fetchone()
            
            if existing:
                # File exists - check if modified
                if existing['file_hash'] != file_hash and file_hash:
                    # File was modified
                    cur.execute("""
                        UPDATE file_documentation_status 
                        SET file_hash = %s, 
                            last_modified = NOW(), 
                            status = CASE 
                                WHEN status = 'documented' THEN 'outdated'
                                ELSE status 
                            END,
                            file_size = %s,
                            line_count = %s,
                            times_skipped = times_skipped + 1
                        WHERE id = %s
                        RETURNING id
                    """, (file_hash, stats['file_size'], stats['line_count'], existing['id']))
                    return existing['id']
                return existing['id']
            else:
                # New file - create entry
                cur.execute("""
                    INSERT INTO file_documentation_status 
                    (file_path, file_hash, status, file_type, file_size, line_count)
                    VALUES (%s, %s, 'undocumented', %s, %s, %s)
                    RETURNING id
                """, (file_path, file_hash, stats['file_type'], 
                      stats['file_size'], stats['line_count']))
                return cur.fetchone()['id']
    
    def create_debt_entry(self, file_id: int, debt_type: str, 
                         description: str, item_name: str = None,
                         line_number: int = None, context: str = None) -> str:
        """Create a documentation debt entry"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check if similar debt already exists
            cur.execute("""
                SELECT id FROM documentation_debt 
                WHERE file_id = %s 
                AND debt_type = %s 
                AND item_name IS NOT DISTINCT FROM %s
                AND resolved_at IS NULL
            """, (file_id, debt_type, item_name))
            
            if cur.fetchone():
                return "EXISTS"
            
            # Determine initial priority based on debt type
            priority_map = {
                'new_file': 'high',
                'new_endpoint': 'high',
                'new_dependency': 'high',
                'schema_change': 'high',
                'new_function': 'medium',
                'new_class': 'medium',
                'new_constant': 'medium',
                'modified_logic': 'medium',
                'new_method': 'low',
                'new_variable': 'low',
                'config_change': 'low'
            }
            priority = priority_map.get(debt_type, 'low')
            
            # Create debt entry
            cur.execute("""
                INSERT INTO documentation_debt
                (file_id, debt_type, item_name, description, priority, 
                 line_number, context, is_blocking)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING debt_id
            """, (file_id, debt_type, item_name, description, priority,
                  line_number, context, priority in ['high', 'critical']))
            
            debt_id = cur.fetchone()['debt_id']
            
            # Update file debt level
            cur.execute("""
                UPDATE file_documentation_status
                SET debt_level = GREATEST(debt_level::text, %s::text)::varchar(10)
                WHERE id = %s
            """, (priority, file_id))
            
            return str(debt_id)
    
    def check_critical_debt(self) -> List[dict]:
        """Check for critical debt that blocks operations"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT dd.*, fds.file_path
                FROM documentation_debt dd
                JOIN file_documentation_status fds ON dd.file_id = fds.id
                WHERE dd.resolved_at IS NULL
                AND (dd.priority = 'critical' 
                     OR dd.hours_old > 24 
                     OR dd.is_blocking = TRUE)
                ORDER BY dd.priority DESC, dd.hours_old DESC
            """)
            return cur.fetchall()

class FileChangeHandler(FileSystemEventHandler):
    """Handles file system events and creates documentation debt"""
    
    def __init__(self, debt_creator: DocumentationDebtCreator, 
                 ignored_patterns: Set[str] = None):
        self.debt_creator = debt_creator
        self.ignored_patterns = ignored_patterns or {
            '.git', '__pycache__', 'node_modules', '.venv', 
            'venv', 'dist', 'build', '.pytest_cache', '.mypy_cache'
        }
        self.file_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go',
            '.rs', '.cpp', '.c', '.h', '.hpp', '.cs', '.rb',
            '.php', '.swift', '.kt', '.scala', '.sql', '.yaml',
            '.yml', '.json', '.xml', '.env', '.config'
        }
    
    def should_track(self, file_path: str) -> bool:
        """Check if file should be tracked for documentation"""
        path = Path(file_path)
        
        # Skip if in ignored directory
        for part in path.parts:
            if part in self.ignored_patterns:
                return False
        
        # Skip if not a tracked file type
        if path.suffix not in self.file_extensions:
            return False
        
        # Skip if file is too small (likely empty or trivial)
        try:
            if os.path.getsize(file_path) < 10:
                return False
        except:
            return False
        
        return True
    
    def detect_file_type_debt(self, file_path: str) -> str:
        """Detect the type of debt based on file path and name"""
        path = Path(file_path)
        name = path.stem.lower()
        
        # API endpoints
        if 'api' in str(path) or 'endpoint' in name or 'route' in name:
            return 'new_endpoint'
        
        # Database/Schema files
        if 'schema' in name or 'migration' in name or path.suffix == '.sql':
            return 'schema_change'
        
        # Configuration files
        if path.suffix in ['.env', '.yaml', '.yml', '.json', '.config']:
            return 'config_change'
        
        # Dependencies
        if name in ['package.json', 'requirements.txt', 'Gemfile', 'go.mod', 'Cargo.toml']:
            return 'new_dependency'
        
        # Class files (heuristic based on naming)
        if name[0].isupper() and path.suffix in ['.py', '.java', '.cs', '.cpp']:
            return 'new_class'
        
        # Default to new file
        return 'new_file'
    
    def on_created(self, event: FileSystemEvent):
        """Handle file creation events"""
        if event.is_directory:
            return
        
        if not self.should_track(event.src_path):
            return
        
        print(f"📄 New file detected: {event.src_path}")
        
        # Create file entry
        file_id = self.debt_creator.create_file_entry(event.src_path)
        if not file_id:
            return
        
        # Detect debt type
        debt_type = self.detect_file_type_debt(event.src_path)
        
        # Create debt entry
        debt_id = self.debt_creator.create_debt_entry(
            file_id=file_id,
            debt_type=debt_type,
            description=f"New {debt_type.replace('_', ' ')} requires documentation",
            item_name=Path(event.src_path).name
        )
        
        if debt_id != "EXISTS":
            print(f"🚨 DOCUMENTATION DEBT CREATED: {debt_type} - {event.src_path}")
            print(f"   Debt ID: {debt_id}")
            
            # Check for critical debt
            critical = self.debt_creator.check_critical_debt()
            if critical:
                print(f"\n⚠️  WARNING: {len(critical)} CRITICAL DEBT ITEMS EXIST!")
                print("   Operations will be blocked until resolved.")
    
    def on_modified(self, event: FileSystemEvent):
        """Handle file modification events"""
        if event.is_directory:
            return
        
        if not self.should_track(event.src_path):
            return
        
        print(f"✏️  File modified: {event.src_path}")
        
        # Update file entry
        file_id = self.debt_creator.create_file_entry(event.src_path)
        if not file_id:
            return
        
        # Create debt for modification
        debt_id = self.debt_creator.create_debt_entry(
            file_id=file_id,
            debt_type='modified_logic',
            description="File modified - documentation may be outdated",
            item_name=Path(event.src_path).name
        )
        
        if debt_id != "EXISTS":
            print(f"🚨 DOCUMENTATION DEBT CREATED: modified_logic - {event.src_path}")

class DocumentationWatcher:
    """Main watcher that monitors the entire project"""
    
    def __init__(self, watch_path: str, db_config: dict):
        self.watch_path = watch_path
        self.db_config = db_config
        self.debt_creator = DocumentationDebtCreator(db_config)
        self.observer = Observer()
        
    def scan_existing_files(self):
        """Scan all existing files and create initial debt"""
        print("🔍 Scanning existing files for documentation debt...")
        
        ignored = {'.git', '__pycache__', 'node_modules', '.venv', 'venv'}
        file_count = 0
        debt_count = 0
        
        for root, dirs, files in os.walk(self.watch_path):
            # Remove ignored directories from traversal
            dirs[:] = [d for d in dirs if d not in ignored]
            
            for file in files:
                file_path = os.path.join(root, file)
                handler = FileChangeHandler(self.debt_creator)
                
                if handler.should_track(file_path):
                    file_count += 1
                    file_id = self.debt_creator.create_file_entry(file_path)
                    
                    if file_id:
                        # Check if file needs documentation
                        debt_type = handler.detect_file_type_debt(file_path)
                        debt_id = self.debt_creator.create_debt_entry(
                            file_id=file_id,
                            debt_type=debt_type,
                            description=f"Existing {debt_type.replace('_', ' ')} needs documentation",
                            item_name=Path(file_path).name
                        )
                        if debt_id != "EXISTS":
                            debt_count += 1
        
        print(f"✅ Scan complete: {file_count} files tracked, {debt_count} debt items created")
    
    def start(self):
        """Start watching for file changes"""
        # Initial scan
        self.scan_existing_files()
        
        # Set up file watcher
        event_handler = FileChangeHandler(self.debt_creator)
        self.observer.schedule(event_handler, self.watch_path, recursive=True)
        self.observer.start()
        
        print(f"\n👁️  Watching for changes in: {self.watch_path}")
        print("   Press Ctrl+C to stop...\n")
        
        try:
            while True:
                time.sleep(1)
                # Periodically escalate debt priority
                if int(time.time()) % 3600 == 0:  # Every hour
                    self.escalate_debt()
        except KeyboardInterrupt:
            self.observer.stop()
            print("\n👋 File watcher stopped.")
        
        self.observer.join()
    
    def escalate_debt(self):
        """Escalate debt priority based on age"""
        with self.debt_creator.conn.cursor() as cur:
            cur.execute("SELECT escalate_debt_priority()")
            print("⏰ Debt priority escalation check completed")

def main():
    """Main entry point"""
    # Configuration
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', 5432),
        'database': os.getenv('DB_NAME', 'unavoidable_docs'),
        'user': os.getenv('DB_USER', 'unavoidable_docs_user'),
        'password': os.getenv('DB_PASSWORD', '')
    }
    
    # Get watch path from argument or use current directory
    watch_path = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    
    # Ensure path exists
    if not os.path.exists(watch_path):
        print(f"❌ Path does not exist: {watch_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("🚨 UNAVOIDABLE DOCUMENTATION SYSTEM - FILE WATCHER")
    print("=" * 60)
    print(f"Monitoring: {watch_path}")
    print(f"Database: {db_config['database']}@{db_config['host']}")
    print("=" * 60)
    
    # Create and start watcher
    watcher = DocumentationWatcher(watch_path, db_config)
    watcher.start()

if __name__ == "__main__":
    main()