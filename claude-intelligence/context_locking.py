#!/usr/bin/env python3
"""
Context Locking System for Claude Intelligence
Allows locking immutable context snapshots for perfect recall
"""

import re
import json
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import deque, Counter
import time


class LockSafetyGuard:
    """Prevents recursive locking and stuck patterns"""
    
    FORBIDDEN_PATTERNS = [
        # Lock-related commands
        r"lock\s+(this|that|it)\s+as",
        r"✅\s*[Ll]ocked",
        r"\[Locked:",
        r"lock_context|recall_context",
        
        # Repetition patterns
        r"(\[\.{3}\s*\d+\s*messages?\s*later)",
        r"(v\d+\.\d+.*hash:\s*\w+){2,}",  # Repeated version strings
        
        # Claude response patterns
        r"^(Claude|Assistant):\s*✅",
        r"I'll lock this",
        r"I've locked",
        r"Let me lock",
        
        # Meta-locking patterns
        r"locking.*lock",
        r"lock.*locking"
    ]
    
    def __init__(self):
        self.recent_hashes = deque(maxlen=10)
        self.repetition_counter = Counter()
        self.lock_attempts = deque(maxlen=20)  # Track recent lock attempts
        self.last_reset = time.time()
    
    def is_safe_to_lock(self, content: str) -> Tuple[bool, str]:
        """Check if content is safe to lock"""
        
        # Size check
        if len(content) > 51200:  # 50KB max
            return False, "Content too large (max 50KB)"
        
        if len(content) < 10:
            return False, "Content too short (min 10 chars)"
        
        # Check for forbidden patterns
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                return False, f"Content contains forbidden pattern"
        
        # Check for repetition
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        if content_hash in self.recent_hashes:
            self.repetition_counter[content_hash] += 1
            if self.repetition_counter[content_hash] >= 3:
                return False, "Repetitive content detected"
        
        # Rate limiting
        now = time.time()
        recent_attempts = [t for t in self.lock_attempts if now - t < 60]
        if len(recent_attempts) >= 10:
            return False, "Rate limit exceeded (max 10 locks per minute)"
        
        self.recent_hashes.append(content_hash)
        self.lock_attempts.append(now)
        
        # Auto-cleanup old counters
        if now - self.last_reset > 300:  # Reset every 5 minutes
            self.repetition_counter.clear()
            self.last_reset = now
        
        return True, "OK"
    
    def reset(self):
        """Emergency reset"""
        self.recent_hashes.clear()
        self.repetition_counter.clear()
        self.lock_attempts.clear()
        self.last_reset = time.time()


class LockCommandParser:
    """Parse natural language lock commands"""
    
    COMMANDS = {
        'lock': [
            r"^lock this as ['\"]?([a-zA-Z0-9_-]+)['\"]?",
            r"^save this as ['\"]?([a-zA-Z0-9_-]+)['\"]?",
            r"^/lock ([a-zA-Z0-9_-]+)",
        ],
        'recall': [
            r"^show me ([a-zA-Z0-9_-]+)",
            r"^recall ([a-zA-Z0-9_-]+)",
            r"^get ([a-zA-Z0-9_-]+)",
            r"^/recall ([a-zA-Z0-9_-]+)",
        ],
        'unlock': [
            r"^unlock ([a-zA-Z0-9_-]+)",
            r"^delete lock ([a-zA-Z0-9_-]+)",
            r"^/unlock ([a-zA-Z0-9_-]+)",
        ]
    }
    
    def parse(self, message: str) -> Optional[Dict]:
        """Parse message for lock commands"""
        
        # Only process if message starts with command
        message = message.strip()
        
        for cmd_type, patterns in self.COMMANDS.items():
            for pattern in patterns:
                if match := re.match(pattern, message, re.IGNORECASE):
                    return {
                        'command': cmd_type,
                        'label': match.group(1),
                        'raw_message': message
                    }
        
        return None


class ContextLockManager:
    """Manages context locks in the database"""
    
    def __init__(self, db_path: str = '.claude-memory.db'):
        self.db_path = db_path
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.safety_guard = LockSafetyGuard()
        self.parser = LockCommandParser()
        self._init_database()
        self._current_session_id = self._get_or_create_session_id()
    
    def _init_database(self):
        """Initialize context locks table"""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS context_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                label TEXT NOT NULL,
                version TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                locked_by TEXT,
                is_persistent BOOLEAN DEFAULT 0,
                parent_version TEXT,
                metadata TEXT,
                
                -- Prevent duplicates
                UNIQUE(session_id, label, version),
                
                -- Prevent content bombs
                CHECK(length(content) <= 51200)
            )
        """)
        
        # Create index for performance
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_locks_session_label 
            ON context_locks(session_id, label, locked_at DESC)
        """)
        
        self.db.commit()
    
    def _get_or_create_session_id(self) -> str:
        """Get current session ID or create new one"""
        # Simple session ID based on date
        return datetime.now().strftime("%Y%m%d")
    
    def _get_next_version(self, label: str) -> str:
        """Generate next version number for a label"""
        cursor = self.db.execute("""
            SELECT version FROM context_locks 
            WHERE session_id = ? AND label = ?
            ORDER BY CAST(REPLACE(version, '.', '') AS INTEGER) DESC
            LIMIT 1
        """, (self._current_session_id, label))
        
        row = cursor.fetchone()
        if not row:
            return "1.0"
        
        # Increment minor version
        parts = row['version'].split('.')
        if len(parts) == 2:
            return f"{parts[0]}.{int(parts[1]) + 1}"
        else:
            return "1.0"
    
    async def lock_context(
        self, 
        content: str, 
        label: str, 
        version: Optional[str] = None,
        persist: bool = False
    ) -> Dict[str, Any]:
        """Lock a piece of context with a label and version"""
        
        # Safety checks
        is_safe, reason = self.safety_guard.is_safe_to_lock(content)
        if not is_safe:
            return {
                'status': 'rejected',
                'reason': reason
            }
        
        # Large content warning
        if len(content) > 5000 and not persist:
            return {
                'status': 'confirmation_required',
                'message': f'Content is {len(content)} chars. Set persist=True to confirm.'
            }
        
        # Auto-generate version if needed
        if version is None:
            version = self._get_next_version(label)
        
        # Calculate hash
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        try:
            # Store in database
            self.db.execute("""
                INSERT INTO context_locks 
                (session_id, label, version, content, content_hash, 
                 locked_by, is_persistent, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self._current_session_id,
                label,
                version,
                content,
                content_hash,
                'user',
                persist,
                json.dumps({'locked_at': datetime.now().isoformat()})
            ))
            self.db.commit()
            
            return {
                'status': 'success',
                'label': label,
                'version': version,
                'hash': content_hash[:8],
                'size': len(content)
            }
            
        except sqlite3.IntegrityError:
            return {
                'status': 'error',
                'message': f'Lock {label} v{version} already exists'
            }
    
    async def recall_context(
        self, 
        label: str, 
        version: Optional[str] = "latest"
    ) -> Dict[str, Any]:
        """Retrieve locked context exactly as stored"""
        
        if version == "latest":
            cursor = self.db.execute("""
                SELECT * FROM context_locks
                WHERE session_id = ? AND label = ?
                ORDER BY locked_at DESC
                LIMIT 1
            """, (self._current_session_id, label))
        else:
            cursor = self.db.execute("""
                SELECT * FROM context_locks
                WHERE session_id = ? AND label = ? AND version = ?
            """, (self._current_session_id, label, version))
        
        row = cursor.fetchone()
        if not row:
            return {
                'status': 'not_found',
                'message': f'No lock found for {label} v{version}'
            }
        
        return {
            'status': 'success',
            'label': row['label'],
            'version': row['version'],
            'content': row['content'],
            'locked_at': row['locked_at'],
            'hash': row['content_hash'][:8]
        }
    
    async def list_locked_contexts(
        self, 
        session_only: bool = True
    ) -> List[Dict[str, Any]]:
        """List all locked contexts with metadata"""
        
        if session_only:
            cursor = self.db.execute("""
                SELECT label, version, locked_at, length(content) as size, 
                       content_hash, is_persistent
                FROM context_locks
                WHERE session_id = ?
                ORDER BY locked_at DESC
            """, (self._current_session_id,))
        else:
            cursor = self.db.execute("""
                SELECT session_id, label, version, locked_at, 
                       length(content) as size, content_hash, is_persistent
                FROM context_locks
                ORDER BY locked_at DESC
                LIMIT 100
            """)
        
        results = []
        for row in cursor:
            results.append({
                'label': row['label'],
                'version': row['version'],
                'locked_at': row['locked_at'],
                'size': row['size'],
                'hash': row['content_hash'][:8],
                'persistent': bool(row['is_persistent'])
            })
        
        return results
    
    async def unlock_context(
        self,
        label: str,
        version: Optional[str] = None,
        confirm: bool = False
    ) -> Dict[str, Any]:
        """Remove locked context. Requires confirm=True for safety"""
        
        if not confirm:
            return {
                'status': 'confirmation_required',
                'message': 'Set confirm=True to unlock'
            }
        
        if version:
            cursor = self.db.execute("""
                DELETE FROM context_locks
                WHERE session_id = ? AND label = ? AND version = ?
            """, (self._current_session_id, label, version))
        else:
            # Delete all versions
            cursor = self.db.execute("""
                DELETE FROM context_locks
                WHERE session_id = ? AND label = ?
            """, (self._current_session_id, label))
        
        affected = cursor.rowcount
        self.db.commit()
        
        return {
            'status': 'success',
            'deleted': affected
        }
    
    def extract_content_to_lock(
        self, 
        conversation_history: List[Dict], 
        user_message: str
    ) -> Optional[str]:
        """Intelligently extract what should be locked"""
        
        # Look for code blocks in user message
        code_blocks = re.findall(r'```(?:[a-z]*\n)?(.*?)```', user_message, re.DOTALL)
        if code_blocks:
            return code_blocks[-1].strip()  # Most recent code block
        
        # Look for explicit content markers
        if "---START---" in user_message and "---END---" in user_message:
            start = user_message.index("---START---") + 11
            end = user_message.index("---END---")
            return user_message[start:end].strip()
        
        # Check previous message for code/config
        if conversation_history:
            last_msg = conversation_history[-1]
            if last_msg.get('role') == 'assistant':
                code_blocks = re.findall(
                    r'```[a-z]*\n(.*?)\n```', 
                    last_msg['content'], 
                    re.DOTALL
                )
                if code_blocks:
                    return code_blocks[-1]
        
        # If no code found, return None (require explicit content)
        return None
    
    # Emergency commands
    def emergency_reset(self):
        """Emergency reset all safety mechanisms"""
        self.safety_guard.reset()
        return {'status': 'reset', 'message': 'Safety guard reset'}
    
    def get_diagnostic_info(self) -> Dict[str, Any]:
        """Get diagnostic information"""
        cursor = self.db.execute("""
            SELECT COUNT(*) as total_locks,
                   COUNT(DISTINCT label) as unique_labels,
                   SUM(length(content)) as total_size
            FROM context_locks
            WHERE session_id = ?
        """, (self._current_session_id,))
        
        row = cursor.fetchone()
        
        return {
            'session_id': self._current_session_id,
            'total_locks': row['total_locks'],
            'unique_labels': row['unique_labels'],
            'total_size': row['total_size'],
            'recent_hashes': len(self.safety_guard.recent_hashes),
            'lock_attempts': len(self.safety_guard.lock_attempts)
        }
    
    def garbage_collect(self, days_old: int = 30):
        """Remove old non-persistent locks"""
        cutoff = datetime.now().timestamp() - (days_old * 86400)
        
        self.db.execute("""
            DELETE FROM context_locks
            WHERE is_persistent = 0 
            AND CAST(strftime('%s', locked_at) AS INTEGER) < ?
        """, (cutoff,))
        
        affected = self.db.rowcount
        self.db.commit()
        
        return {'deleted': affected}


# Integration with Claude Intelligence
def integrate_locking_with_intelligence():
    """Add locking capabilities to Claude Intelligence"""
    try:
        from mcp_server import ClaudeIntelligence
        
        # Create a shared lock manager
        lock_manager = ContextLockManager()
        
        # Add methods to ClaudeIntelligence
        ClaudeIntelligence.lock_context = lambda self, *args, **kwargs: \
            lock_manager.lock_context(*args, **kwargs)
        ClaudeIntelligence.recall_context = lambda self, *args, **kwargs: \
            lock_manager.recall_context(*args, **kwargs)
        ClaudeIntelligence.list_locked_contexts = lambda self, *args, **kwargs: \
            lock_manager.list_locked_contexts(*args, **kwargs)
        ClaudeIntelligence.unlock_context = lambda self, *args, **kwargs: \
            lock_manager.unlock_context(*args, **kwargs)
        
        return True
    except ImportError:
        return False


# Testing
if __name__ == "__main__":
    import asyncio
    
    async def test_lock_safety():
        """Critical tests to verify safety"""
        
        manager = ContextLockManager(':memory:')  # In-memory for testing
        
        print("Testing lock safety...")
        
        # Test 1: Reject recursive lock attempts
        bad_content = "Lock this as 'api_v1'"
        result = await manager.lock_context(bad_content, 'test1')
        assert result['status'] == 'rejected', "Should reject lock commands"
        print("✓ Rejected recursive lock")
        
        # Test 2: Reject Claude response patterns  
        bad_content = "Claude: ✅ Locked 'api_v1' as version 1.0"
        result = await manager.lock_context(bad_content, 'test2')
        assert result['status'] == 'rejected', "Should reject Claude patterns"
        print("✓ Rejected Claude patterns")
        
        # Test 3: Accept clean content
        good_content = """
class UserAPI:
    def get_user(id: str) -> User:
        return db.find_user(id)
"""
        result = await manager.lock_context(good_content, 'api_spec')
        assert result['status'] == 'success', "Should accept clean content"
        print("✓ Accepted clean content")
        
        # Test 4: Recall works
        recalled = await manager.recall_context('api_spec')
        assert recalled['content'].strip() == good_content.strip()
        print("✓ Recall works correctly")
        
        # Test 5: List works
        locks = await manager.list_locked_contexts()
        assert len(locks) == 1
        assert locks[0]['label'] == 'api_spec'
        print("✓ Listing works")
        
        # Test 6: Unlock requires confirmation
        result = await manager.unlock_context('api_spec', confirm=False)
        assert result['status'] == 'confirmation_required'
        print("✓ Unlock requires confirmation")
        
        result = await manager.unlock_context('api_spec', confirm=True)
        assert result['status'] == 'success'
        print("✓ Unlock with confirmation works")
        
        print("\n✅ All safety tests passed!")
    
    # Run tests
    asyncio.run(test_lock_safety())