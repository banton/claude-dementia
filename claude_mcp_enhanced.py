#!/usr/bin/env python3
"""
Enhanced MCP Tools for Active Context Checking
These functions can be integrated into claude_mcp_hybrid.py
"""

import os
import json
import sqlite3
import time
import hashlib
from typing import Optional
from datetime import datetime

# Import the active engine
from active_context_engine import (
    ActiveContextEngine,
    check_command_context,
    get_relevant_contexts_for_text,
    get_session_start_reminders
)

def enhanced_lock_context(content: str, topic: str, 
                         tags: Optional[str] = None,
                         priority: Optional[str] = None) -> str:
    """
    Enhanced lock_context with priority levels and active checking.
    
    Priority levels:
    - 'always_check': Always checked before relevant actions
    - 'important': Shown at session start
    - 'reference': Standard reference material (default)
    
    Examples:
    - lock_context("ALWAYS use 'output' folder", "output_standard", priority="always_check")
    - lock_context("API spec v2", "api_spec", tags="api,spec", priority="important")
    """
    from claude_mcp_hybrid import get_db, get_current_session_id, update_session_activity
    
    update_session_activity()
    conn = get_db()
    session_id = get_current_session_id()
    
    # Set default priority
    if priority is None:
        # Auto-detect priority based on content
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
    
    # Prepare metadata with priority
    metadata = {
        "tags": tags.split(',') if tags else [],
        "priority": priority,
        "created_at": datetime.now().isoformat(),
        "keywords": extract_keywords(content)  # Auto-extract keywords for matching
    }
    
    # Store lock
    try:
        conn.execute("""
            INSERT INTO context_locks 
            (session_id, label, version, content, content_hash, locked_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session_id, topic, version, content, content_hash, time.time(), json.dumps(metadata)))
        
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

def extract_keywords(content: str) -> list:
    """Extract keywords from content for better matching"""
    import re
    
    # Common programming/config terms to look for
    keywords = []
    patterns = {
        'output': r'\b(output|directory|folder|path)\b',
        'test': r'\b(test|testing|spec)\b',
        'config': r'\b(config|settings|configuration)\b',
        'api': r'\b(api|endpoint|rest|graphql)\b',
        'database': r'\b(database|db|sql|table)\b',
        'security': r'\b(auth|token|password|secret)\b',
        'file': r'\b(file|files|document)\b',
        'build': r'\b(build|compile|deploy)\b',
    }
    
    content_lower = content.lower()
    for key, pattern in patterns.items():
        if re.search(pattern, content_lower):
            keywords.append(key)
    
    return keywords

def enhanced_wake_up() -> str:
    """
    Enhanced wake_up that shows high-priority locked contexts.
    """
    from claude_mcp_hybrid import (
        get_db, get_current_session_id, DB_PATH, DB_LOCATION, 
        PROJECT_ROOT, PROJECT_NAME, initialize_session
    )
    
    # Initialize session
    session_id = initialize_session()
    
    output = []
    output.append("🌅 Good morning! Loading your context...")
    output.append(f"Session: {session_id[:12]}")
    output.append(f"Project: {PROJECT_NAME}")
    output.append(f"Location: {PROJECT_ROOT}")
    output.append(f"Memory: {DB_PATH} ({DB_LOCATION})")
    
    # Get recent updates
    conn = get_db()
    cursor = conn.execute("""
        SELECT category, content, timestamp
        FROM memory_entries
        WHERE session_id != ?
        ORDER BY timestamp DESC
        LIMIT 5
    """, (session_id,))
    
    updates = cursor.fetchall()
    if updates:
        output.append("\n📝 Recent updates:")
        for update in updates:
            dt = datetime.fromtimestamp(update['timestamp'])
            content_preview = update['content'][:200]
            if len(update['content']) > 200:
                content_preview += "..."
            output.append(f"   • {dt.strftime('%m/%d %H:%M')}: {content_preview}")
    
    # Show high-priority locked contexts
    engine = ActiveContextEngine(DB_PATH)
    
    # Get always_check contexts
    always_check = engine.get_session_context_summary(session_id, priority='always_check')
    if "No locked contexts" not in always_check:
        output.append("\n⚠️ High-Priority Rules (Always Checked):")
        output.append(always_check)
    
    # Get important contexts
    important = engine.get_session_context_summary(session_id, priority='important')
    if "No locked contexts" not in important:
        output.append("\n📌 Important Contexts:")
        output.append(important)
    
    # Get active todos
    cursor = conn.execute("""
        SELECT id, content, priority, status
        FROM todos
        WHERE status != 'completed'
        ORDER BY priority DESC, created_at ASC
        LIMIT 10
    """)
    
    todos = cursor.fetchall()
    if todos:
        output.append("\n📋 Active TODOs:")
        for todo in todos:
            priority_marker = {
                2: "[HIGH]",
                1: "[NORMAL]",
                0: "[LOW]"
            }.get(todo['priority'], "")
            
            status_marker = "⏸" if todo['status'] == 'pending' else "▶️"
            output.append(f"   {status_marker} {priority_marker} {todo['content']}")
    
    conn.close()
    
    return "\n".join(output)

def check_before_action(action_type: str, action_details: str) -> Optional[str]:
    """
    Check for relevant contexts before performing an action.
    This should be called before file writes, command execution, etc.
    
    Returns warning message if potential violations found, None otherwise.
    """
    from claude_mcp_hybrid import get_current_session_id, DB_PATH
    
    session_id = get_current_session_id()
    
    # Combine action type and details for checking
    full_action = f"{action_type}: {action_details}"
    
    # Check for violations
    warning = check_command_context(full_action, session_id, DB_PATH)
    
    if warning:
        # Also get relevant contexts for more info
        relevant = get_relevant_contexts_for_text(full_action, session_id, DB_PATH)
        if relevant:
            warning += f"\n\n{relevant}"
    
    return warning

def auto_check_wrapper(original_function):
    """
    Decorator to add automatic context checking to existing functions.
    Can be applied to functions like Write, Edit, Bash, etc.
    """
    from functools import wraps
    
    @wraps(original_function)
    async def wrapper(*args, **kwargs):
        # Extract relevant info based on function
        action_type = original_function.__name__
        action_details = ""
        
        if 'command' in kwargs:
            action_details = kwargs['command']
        elif 'file_path' in kwargs:
            action_details = f"file: {kwargs['file_path']}"
        elif 'content' in kwargs:
            action_details = kwargs['content'][:100]
        elif args:
            action_details = str(args[0])[:100]
        
        # Check for violations
        warning = check_before_action(action_type, action_details)
        
        if warning:
            # Log the warning but don't block
            # In production, you might want to ask for confirmation
            print(f"\n{warning}\n")
        
        # Execute original function
        return await original_function(*args, **kwargs)
    
    return wrapper

# Example: How to integrate into existing MCP server
"""
To integrate this into claude_mcp_hybrid.py:

1. Replace the existing lock_context function with enhanced_lock_context
2. Replace the existing wake_up function with enhanced_wake_up
3. Add auto-checking to critical functions:

@auto_check_wrapper
@mcp.tool()
async def write_file(file_path: str, content: str) -> str:
    # ... existing implementation
    
@auto_check_wrapper  
@mcp.tool()
async def bash(command: str) -> str:
    # ... existing implementation

4. Optionally add a new tool for checking contexts:

@mcp.tool()
async def check_contexts(text: str) -> str:
    '''Check what locked contexts might be relevant to given text'''
    from claude_mcp_hybrid import get_current_session_id, DB_PATH
    
    session_id = get_current_session_id()
    
    # Get relevant contexts
    relevant = get_relevant_contexts_for_text(text, session_id, DB_PATH)
    
    # Check for violations
    violations = check_command_context(text, session_id, DB_PATH)
    
    output = []
    if relevant:
        output.append(relevant)
    if violations:
        output.append(violations)
    
    if not output:
        return "No relevant locked contexts found."
    
    return "\n\n".join(output)
"""