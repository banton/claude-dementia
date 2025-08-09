#!/usr/bin/env python3
"""
Claude Session Memory - Persistent memory between Claude sessions
Extends Claude Intelligence with the missing memory features
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import time


class ClaudeMemory:
    """Full session memory system - the missing piece"""
    
    def __init__(self, db_path: str = '.claude-memory.db'):
        """Use same database as Claude Intelligence"""
        self.db_path = db_path
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self._init_memory_tables()
    
    def _init_memory_tables(self):
        """Add memory tables to existing Claude Intelligence database"""
        
        # Session updates (like memory/active/status.md)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS session_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                message TEXT NOT NULL,
                category TEXT,
                metadata TEXT
            )
        """)
        
        # Active context (like memory/active/context.md)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS session_context (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL
            )
        """)
        
        # TODOs tracking
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL,
                completed_at REAL,
                priority INTEGER DEFAULT 0
            )
        """)
        
        # Problems and solutions (like memory/fixes/)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS fixes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                problem TEXT NOT NULL,
                cause TEXT,
                solution TEXT NOT NULL,
                prevention TEXT,
                file_path TEXT
            )
        """)
        
        # Questions and decisions (like memory/questions/)
        self.db.execute("""
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
        """)
        
        self.db.commit()
    
    # Status Updates (memory/active/status.md equivalent)
    def add_update(self, message: str, category: str = None, metadata: Dict = None) -> int:
        """Add a status update to the session log"""
        cursor = self.db.execute(
            "INSERT INTO session_updates (timestamp, message, category, metadata) VALUES (?, ?, ?, ?)",
            (time.time(), message, category, json.dumps(metadata) if metadata else None)
        )
        self.db.commit()
        return cursor.lastrowid
    
    def get_recent_updates(self, limit: int = 20) -> List[Dict]:
        """Get recent status updates"""
        cursor = self.db.execute(
            """SELECT timestamp, message, category, metadata 
               FROM session_updates 
               ORDER BY timestamp DESC 
               LIMIT ?""",
            (limit,)
        )
        
        updates = []
        for row in cursor:
            updates.append({
                'timestamp': datetime.fromtimestamp(row['timestamp']).isoformat(),
                'message': row['message'],
                'category': row['category'],
                'metadata': json.loads(row['metadata']) if row['metadata'] else None
            })
        
        return updates
    
    # Context Management (memory/active/context.md equivalent)
    def set_context(self, key: str, value: str):
        """Set a context value for the session"""
        self.db.execute(
            "INSERT OR REPLACE INTO session_context (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, time.time())
        )
        self.db.commit()
    
    def get_context(self, key: str = None) -> Any:
        """Get context value(s)"""
        if key:
            cursor = self.db.execute(
                "SELECT value FROM session_context WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            return row['value'] if row else None
        else:
            # Get all context
            cursor = self.db.execute(
                "SELECT key, value, updated_at FROM session_context ORDER BY updated_at DESC"
            )
            return {row['key']: row['value'] for row in cursor}
    
    def get_working_context(self) -> str:
        """Get formatted working context like context.md"""
        context = self.get_context()
        if not context:
            return "No active context"
        
        lines = ["# Working Context\n"]
        for key, value in context.items():
            lines.append(f"## {key}")
            lines.append(value)
            lines.append("")
        
        return "\n".join(lines)
    
    # TODO Management
    def add_todo(self, content: str, todo_id: str = None, priority: int = 0) -> str:
        """Add a TODO item"""
        import random
        if not todo_id:
            todo_id = f"todo-{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
        
        self.db.execute(
            "INSERT INTO todos (id, content, status, created_at, priority) VALUES (?, ?, ?, ?, ?)",
            (todo_id, content, 'pending', time.time(), priority)
        )
        self.db.commit()
        return todo_id
    
    def update_todo_status(self, todo_id: str, status: str):
        """Update TODO status (pending, in_progress, completed)"""
        completed_at = time.time() if status == 'completed' else None
        self.db.execute(
            "UPDATE todos SET status = ?, completed_at = ? WHERE id = ?",
            (status, completed_at, todo_id)
        )
        self.db.commit()
    
    def get_todos(self, status: str = None) -> List[Dict]:
        """Get TODOs, optionally filtered by status"""
        if status:
            cursor = self.db.execute(
                "SELECT * FROM todos WHERE status = ? ORDER BY priority DESC, created_at",
                (status,)
            )
        else:
            cursor = self.db.execute(
                "SELECT * FROM todos ORDER BY status, priority DESC, created_at"
            )
        
        todos = []
        for row in cursor:
            todos.append({
                'id': row['id'],
                'content': row['content'],
                'status': row['status'],
                'priority': row['priority'],
                'created_at': datetime.fromtimestamp(row['created_at']).isoformat()
            })
        
        return todos
    
    # Problem/Solution Tracking (memory/fixes/ equivalent)
    def add_fix(self, problem: str, solution: str, cause: str = None, 
                prevention: str = None, file_path: str = None) -> int:
        """Document a problem and its solution"""
        cursor = self.db.execute(
            """INSERT INTO fixes (timestamp, problem, cause, solution, prevention, file_path) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (time.time(), problem, cause, solution, prevention, file_path)
        )
        self.db.commit()
        return cursor.lastrowid
    
    def search_fixes(self, query: str) -> List[Dict]:
        """Search for similar problems/solutions"""
        cursor = self.db.execute(
            """SELECT * FROM fixes 
               WHERE problem LIKE ? OR solution LIKE ? 
               ORDER BY timestamp DESC""",
            (f'%{query}%', f'%{query}%')
        )
        
        fixes = []
        for row in cursor:
            fixes.append({
                'timestamp': datetime.fromtimestamp(row['timestamp']).isoformat(),
                'problem': row['problem'],
                'cause': row['cause'],
                'solution': row['solution'],
                'prevention': row['prevention'],
                'file_path': row['file_path']
            })
        
        return fixes
    
    # Questions/Decisions (memory/questions/ equivalent)
    def add_question(self, question: str, context: str = None, options: List[str] = None) -> int:
        """Record a question that needs answering"""
        cursor = self.db.execute(
            """INSERT INTO decisions (timestamp, question, context, options, status) 
               VALUES (?, ?, ?, ?, 'OPEN')""",
            (time.time(), question, context, json.dumps(options) if options else None)
        )
        self.db.commit()
        return cursor.lastrowid
    
    def answer_question(self, question_id: int, decision: str, rationale: str = None):
        """Record the answer to a question"""
        self.db.execute(
            """UPDATE decisions 
               SET decision = ?, rationale = ?, status = 'ANSWERED' 
               WHERE id = ?""",
            (decision, rationale, question_id)
        )
        self.db.commit()
    
    def get_open_questions(self) -> List[Dict]:
        """Get unanswered questions"""
        cursor = self.db.execute(
            "SELECT * FROM decisions WHERE status = 'OPEN' ORDER BY timestamp DESC"
        )
        
        questions = []
        for row in cursor:
            questions.append({
                'id': row['id'],
                'timestamp': datetime.fromtimestamp(row['timestamp']).isoformat(),
                'question': row['question'],
                'context': row['context'],
                'options': json.loads(row['options']) if row['options'] else None
            })
        
        return questions
    
    # Session Summary
    def get_session_summary(self) -> Dict:
        """Get a comprehensive summary of the current session state"""
        
        # Get counts
        cursor = self.db.execute("SELECT COUNT(*) FROM session_updates")
        update_count = cursor.fetchone()[0]
        
        cursor = self.db.execute("SELECT COUNT(*) FROM todos WHERE status = 'pending'")
        pending_todos = cursor.fetchone()[0]
        
        cursor = self.db.execute("SELECT COUNT(*) FROM todos WHERE status = 'completed'")
        completed_todos = cursor.fetchone()[0]
        
        cursor = self.db.execute("SELECT COUNT(*) FROM decisions WHERE status = 'OPEN'")
        open_questions = cursor.fetchone()[0]
        
        cursor = self.db.execute("SELECT COUNT(*) FROM fixes")
        documented_fixes = cursor.fetchone()[0]
        
        # Get recent items
        recent_updates = self.get_recent_updates(5)
        active_todos = self.get_todos('pending')[:5]
        questions = self.get_open_questions()
        
        return {
            'stats': {
                'updates': update_count,
                'pending_todos': pending_todos,
                'completed_todos': completed_todos,
                'open_questions': open_questions,
                'documented_fixes': documented_fixes
            },
            'recent_updates': recent_updates,
            'active_todos': active_todos,
            'open_questions': questions,
            'context': self.get_context()
        }
    
    def restore_session(self) -> str:
        """Generate a session restoration prompt"""
        summary = self.get_session_summary()
        
        lines = ["# Session Restoration\n"]
        
        # Context
        if summary['context']:
            lines.append("## Current Context")
            for key, value in summary['context'].items():
                lines.append(f"**{key}**: {value}")
            lines.append("")
        
        # Recent updates
        if summary['recent_updates']:
            lines.append("## Recent Updates")
            for update in summary['recent_updates'][:5]:
                lines.append(f"- {update['message']}")
            lines.append("")
        
        # Active TODOs
        if summary['active_todos']:
            lines.append("## Active TODOs")
            for todo in summary['active_todos']:
                lines.append(f"- [{todo['status']}] {todo['content']}")
            lines.append("")
        
        # Open questions
        if summary['open_questions']:
            lines.append("## Open Questions")
            for q in summary['open_questions']:
                lines.append(f"- {q['question']}")
            lines.append("")
        
        return "\n".join(lines)


# Integration with Claude Intelligence
def integrate_with_intelligence():
    """Extend Claude Intelligence with full memory capabilities"""
    try:
        from mcp_server import ClaudeIntelligence
        
        # Monkey-patch the class to add memory features
        original_init = ClaudeIntelligence.__init__
        
        def new_init(self, db_path: str = '.claude-memory.db'):
            original_init(self, db_path)
            self.memory = ClaudeMemory(db_path)
        
        ClaudeIntelligence.__init__ = new_init
        
        # Add memory methods to ClaudeIntelligence
        ClaudeIntelligence.add_update = lambda self, *args, **kwargs: self.memory.add_update(*args, **kwargs)
        ClaudeIntelligence.set_context = lambda self, *args, **kwargs: self.memory.set_context(*args, **kwargs)
        ClaudeIntelligence.get_context = lambda self, *args, **kwargs: self.memory.get_context(*args, **kwargs)
        ClaudeIntelligence.add_todo = lambda self, *args, **kwargs: self.memory.add_todo(*args, **kwargs)
        ClaudeIntelligence.get_todos = lambda self, *args, **kwargs: self.memory.get_todos(*args, **kwargs)
        ClaudeIntelligence.add_fix = lambda self, *args, **kwargs: self.memory.add_fix(*args, **kwargs)
        ClaudeIntelligence.add_question = lambda self, *args, **kwargs: self.memory.add_question(*args, **kwargs)
        ClaudeIntelligence.restore_session = lambda self: self.memory.restore_session()
        ClaudeIntelligence.get_session_summary = lambda self: self.memory.get_session_summary()
        
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    # Demo/Test
    print("🧠 Claude Session Memory Demo")
    print("=" * 50)
    
    memory = ClaudeMemory()
    
    # Add some updates
    memory.add_update("Started working on authentication system", category="task")
    memory.add_update("Discovered issue with JWT token expiration", category="finding")
    
    # Set context
    memory.set_context("current_task", "Implementing user authentication")
    memory.set_context("tech_stack", "FastAPI, PostgreSQL, Redis")
    
    # Add TODOs
    memory.add_todo("Fix JWT token expiration logic", priority=1)
    memory.add_todo("Add password reset functionality", priority=2)
    memory.add_todo("Write tests for auth endpoints", priority=1)
    
    # Document a fix
    memory.add_fix(
        problem="JWT tokens expiring too quickly",
        cause="Incorrect timezone handling in token generation",
        solution="Use UTC timestamps consistently",
        prevention="Added unit test for token expiration"
    )
    
    # Add a question
    memory.add_question(
        "Should we use refresh tokens or sliding sessions?",
        context="Need to balance security with user experience",
        options=["Refresh tokens", "Sliding sessions", "Both"]
    )
    
    # Get summary
    print("\n📊 Session Summary:")
    summary = memory.get_session_summary()
    print(f"  Updates: {summary['stats']['updates']}")
    print(f"  Pending TODOs: {summary['stats']['pending_todos']}")
    print(f"  Open Questions: {summary['stats']['open_questions']}")
    print(f"  Documented Fixes: {summary['stats']['documented_fixes']}")
    
    # Show restoration
    print("\n📝 Session Restoration:")
    print(memory.restore_session())
    
    # Try integration
    if integrate_with_intelligence():
        print("\n✅ Successfully integrated with Claude Intelligence!")
    else:
        print("\n⚠️  Claude Intelligence not found, running standalone")