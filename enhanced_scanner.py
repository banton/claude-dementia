#!/usr/bin/env python3
"""
Enhanced Project Scanner with Markitdown Integration
Provides multi-stage, resumable scanning with markdown conversion
"""

import os
import sqlite3
import hashlib
import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
from markitdown import MarkItDown

class EnhancedProjectScanner:
    """
    Multi-stage project scanner with:
    1. Fast file discovery and inventory
    2. Content conversion to markdown
    3. Intelligent tagging and analysis
    4. Resumable processing with task queue
    """
    
    # File categories and their processing strategies
    FILE_STRATEGIES = {
        'documents': {
            'extensions': ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.odt'],
            'use_markitdown': True,
            'priority': 1
        },
        'code': {
            'extensions': ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs', '.rb', '.php'],
            'use_markitdown': False,  # Already text
            'priority': 2
        },
        'markdown': {
            'extensions': ['.md', '.markdown', '.rst', '.txt'],
            'use_markitdown': False,  # Already markdown/text
            'priority': 3
        },
        'data': {
            'extensions': ['.json', '.yaml', '.yml', '.xml', '.csv', '.tsv'],
            'use_markitdown': False,  # Structured data
            'priority': 4
        },
        'images': {
            'extensions': ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'],
            'use_markitdown': True,  # Can extract text/OCR
            'priority': 5
        },
        'archives': {
            'extensions': ['.zip', '.tar', '.gz', '.rar', '.7z'],
            'use_markitdown': False,  # Need special handling
            'priority': 6
        }
    }
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.markitdown = MarkItDown()
        self._init_database()
    
    def _init_database(self):
        """Initialize database tables for scan management"""
        conn = sqlite3.connect(self.db_path)
        
        # Scan sessions table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS scan_sessions (
                id TEXT PRIMARY KEY,
                started_at REAL,
                completed_at REAL,
                status TEXT,  -- discovering, processing, completed, paused
                project_root TEXT,
                total_files INTEGER,
                processed_files INTEGER,
                metadata TEXT
            )
        ''')
        
        # File inventory table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS file_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                file_path TEXT UNIQUE,
                file_type TEXT,
                file_size INTEGER,
                modified_time REAL,
                file_hash TEXT,
                status TEXT,  -- pending, processing, completed, failed
                priority INTEGER,
                error_message TEXT,
                FOREIGN KEY (session_id) REFERENCES scan_sessions(id)
            )
        ''')
        
        # Processed content table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS processed_content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER,
                markdown_content TEXT,
                extracted_text TEXT,
                metadata TEXT,
                tags TEXT,
                processed_at REAL,
                processing_time REAL,
                FOREIGN KEY (file_id) REFERENCES file_inventory(id)
            )
        ''')
        
        # Create indexes for performance
        conn.execute('CREATE INDEX IF NOT EXISTS idx_inventory_status ON file_inventory(status)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_inventory_session ON file_inventory(session_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_inventory_priority ON file_inventory(priority)')
        
        conn.commit()
        conn.close()
    
    def start_scan(self, project_root: str) -> str:
        """
        Phase 1: Fast discovery - inventory all files
        Returns session_id for tracking
        """
        session_id = f"scan_{int(time.time())}"
        conn = sqlite3.connect(self.db_path)
        
        # Create scan session
        conn.execute('''
            INSERT INTO scan_sessions (id, started_at, status, project_root, total_files, processed_files)
            VALUES (?, ?, 'discovering', ?, 0, 0)
        ''', (session_id, time.time(), project_root))
        
        # Inventory files
        root_path = Path(project_root)
        file_count = 0
        batch = []
        
        for path in root_path.rglob('*'):
            if path.is_file() and not path.is_symlink():
                try:
                    file_type = self._categorize_file(path)
                    priority = self._get_priority(file_type)
                    
                    batch.append((
                        session_id,
                        str(path),
                        file_type,
                        path.stat().st_size,
                        path.stat().st_mtime,
                        None,  # hash computed later if needed
                        'pending',
                        priority,
                        None  # error_message
                    ))
                    
                    file_count += 1
                    
                    # Insert in batches for performance
                    if len(batch) >= 100:
                        conn.executemany('''
                            INSERT OR IGNORE INTO file_inventory 
                            (session_id, file_path, file_type, file_size, modified_time, 
                             file_hash, status, priority, error_message)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', batch)
                        batch = []
                        
                except Exception as e:
                    # Log error but continue
                    pass
        
        # Insert remaining batch
        if batch:
            conn.executemany('''
                INSERT OR IGNORE INTO file_inventory 
                (session_id, file_path, file_type, file_size, modified_time, 
                 file_hash, status, priority, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', batch)
        
        # Update session
        conn.execute('''
            UPDATE scan_sessions 
            SET total_files = ?, status = 'ready'
            WHERE id = ?
        ''', (file_count, session_id))
        
        conn.commit()
        conn.close()
        
        return session_id
    
    def process_batch(self, session_id: str, batch_size: int = 10) -> Dict:
        """
        Phase 2: Process files in priority order
        Returns progress information
        """
        conn = sqlite3.connect(self.db_path)
        
        # Get next batch of files to process
        cursor = conn.execute('''
            SELECT id, file_path, file_type 
            FROM file_inventory 
            WHERE session_id = ? AND status = 'pending'
            ORDER BY priority, file_size
            LIMIT ?
        ''', (session_id, batch_size))
        
        files = cursor.fetchall()
        processed = 0
        errors = []
        
        for file_id, file_path, file_type in files:
            try:
                # Mark as processing
                conn.execute('''
                    UPDATE file_inventory 
                    SET status = 'processing' 
                    WHERE id = ?
                ''', (file_id,))
                
                # Process file
                start_time = time.time()
                result = self._process_file(file_path, file_type)
                processing_time = time.time() - start_time
                
                # Store result
                conn.execute('''
                    INSERT INTO processed_content 
                    (file_id, markdown_content, extracted_text, metadata, tags, 
                     processed_at, processing_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    file_id,
                    result.get('markdown'),
                    result.get('text'),
                    json.dumps(result.get('metadata', {})),
                    json.dumps(result.get('tags', [])),
                    time.time(),
                    processing_time
                ))
                
                # Mark as completed
                conn.execute('''
                    UPDATE file_inventory 
                    SET status = 'completed' 
                    WHERE id = ?
                ''', (file_id,))
                
                processed += 1
                
            except Exception as e:
                # Mark as failed
                conn.execute('''
                    UPDATE file_inventory 
                    SET status = 'failed', error_message = ? 
                    WHERE id = ?
                ''', (str(e), file_id))
                errors.append((file_path, str(e)))
        
        # Update session progress
        conn.execute('''
            UPDATE scan_sessions 
            SET processed_files = processed_files + ?
            WHERE id = ?
        ''', (processed, session_id))
        
        # Check if complete
        cursor = conn.execute('''
            SELECT COUNT(*) FROM file_inventory 
            WHERE session_id = ? AND status = 'pending'
        ''', (session_id,))
        
        pending = cursor.fetchone()[0]
        if pending == 0:
            conn.execute('''
                UPDATE scan_sessions 
                SET status = 'completed', completed_at = ?
                WHERE id = ?
            ''', (time.time(), session_id))
        
        conn.commit()
        
        # Get progress stats
        cursor = conn.execute('''
            SELECT total_files, processed_files, status 
            FROM scan_sessions 
            WHERE id = ?
        ''', (session_id,))
        
        stats = cursor.fetchone()
        conn.close()
        
        return {
            'processed': processed,
            'errors': errors,
            'total_files': stats[0],
            'processed_files': stats[1],
            'status': stats[2],
            'pending': pending
        }
    
    def _process_file(self, file_path: str, file_type: str) -> Dict:
        """Process a single file based on its type"""
        result = {
            'markdown': None,
            'text': None,
            'metadata': {},
            'tags': []
        }
        
        strategy = self._get_strategy(file_type)
        
        if strategy and strategy.get('use_markitdown'):
            # Use markitdown for conversion
            try:
                converted = self.markitdown.convert(file_path)
                result['markdown'] = converted.text_content
                result['metadata'] = {
                    'title': converted.title or Path(file_path).stem,
                    'conversion': 'markitdown'
                }
            except Exception as e:
                # Fallback to reading raw
                result['text'] = self._read_text_file(file_path)
                result['metadata']['error'] = str(e)
        else:
            # Read as text
            result['text'] = self._read_text_file(file_path)
        
        # Generate tags based on content and metadata
        result['tags'] = self._generate_tags(file_path, result)
        
        return result
    
    def _categorize_file(self, path: Path) -> str:
        """Categorize file based on extension"""
        ext = path.suffix.lower()
        for category, config in self.FILE_STRATEGIES.items():
            if ext in config['extensions']:
                return category
        return 'other'
    
    def _get_priority(self, file_type: str) -> int:
        """Get processing priority for file type"""
        strategy = self.FILE_STRATEGIES.get(file_type)
        return strategy['priority'] if strategy else 99
    
    def _get_strategy(self, file_type: str) -> Optional[Dict]:
        """Get processing strategy for file type"""
        return self.FILE_STRATEGIES.get(file_type)
    
    def _read_text_file(self, file_path: str, max_size: int = 1024 * 1024) -> str:
        """Read text file with size limit"""
        try:
            path = Path(file_path)
            if path.stat().st_size > max_size:
                return f"[File too large: {path.stat().st_size} bytes]"
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            return f"[Error reading file: {e}]"
    
    def _generate_tags(self, file_path: str, content: Dict) -> List[str]:
        """Generate intelligent tags for file"""
        tags = []
        path = Path(file_path)
        
        # Path-based tags
        if 'test' in path.stem.lower() or 'test' in str(path.parent).lower():
            tags.append('type:test')
        if 'doc' in str(path.parent).lower():
            tags.append('type:documentation')
        
        # Content-based tags (if we have text)
        text = content.get('markdown') or content.get('text') or ''
        if 'TODO' in text or 'FIXME' in text:
            tags.append('has:todos')
        if 'import ' in text or 'require(' in text:
            tags.append('type:code')
        
        return tags
    
    def get_summary(self, session_id: str) -> str:
        """Generate a summary of the scan results"""
        conn = sqlite3.connect(self.db_path)
        
        # Get file type distribution
        cursor = conn.execute('''
            SELECT file_type, COUNT(*) 
            FROM file_inventory 
            WHERE session_id = ?
            GROUP BY file_type
        ''', (session_id,))
        
        type_dist = dict(cursor.fetchall())
        
        # Get processing stats
        cursor = conn.execute('''
            SELECT 
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                AVG(processing_time) as avg_time
            FROM file_inventory fi
            LEFT JOIN processed_content pc ON fi.id = pc.file_id
            WHERE session_id = ?
        ''', (session_id,))
        
        stats = cursor.fetchone()
        conn.close()
        
        summary = ["\n📊 Scan Summary:"]
        for file_type, count in type_dist.items():
            summary.append(f"   • {file_type}: {count} files")
        
        if stats[2]:
            summary.append(f"\n⚡ Performance:")
            summary.append(f"   • Avg processing time: {stats[2]:.2f}s")
        
        if stats[1] > 0:
            summary.append(f"\n⚠️ {stats[1]} files failed to process")
        
        return "\n".join(summary)
    
    def get_status(self, session_id: str) -> Dict:
        """Get current status of scan session"""
        conn = sqlite3.connect(self.db_path)
        
        cursor = conn.execute('''
            SELECT * FROM scan_sessions WHERE id = ?
        ''', (session_id,))
        
        session = cursor.fetchone()
        if not session:
            return {'error': 'Session not found'}
        
        # Get file statistics
        cursor = conn.execute('''
            SELECT status, COUNT(*) 
            FROM file_inventory 
            WHERE session_id = ?
            GROUP BY status
        ''', (session_id,))
        
        stats = dict(cursor.fetchall())
        conn.close()
        
        return {
            'session_id': session_id,
            'status': session[3],
            'project_root': session[4],
            'total_files': session[5],
            'processed_files': session[6],
            'file_stats': stats
        }


# Example usage
if __name__ == "__main__":
    scanner = EnhancedProjectScanner('.claude-memory.db')
    
    # Start scan
    session_id = scanner.start_scan('.')
    print(f"Started scan: {session_id}")
    
    # Process in batches
    while True:
        result = scanner.process_batch(session_id, batch_size=5)
        print(f"Processed {result['processed']} files, {result['pending']} remaining")
        
        if result['status'] == 'completed':
            break
        
        if result['errors']:
            print(f"Errors: {result['errors']}")