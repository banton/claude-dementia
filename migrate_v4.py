#!/usr/bin/env python3
"""
Migration script for Claude Dementia v4.0 Active Context Engine
Adds priority levels to existing locked contexts
"""

import sqlite3
import json
import sys
import os
from pathlib import Path

def migrate_context_locks(db_path):
    """Add priority field to existing locked contexts"""
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    print(f"🔄 Migrating database: {db_path}")
    
    # Get all locked contexts
    cursor = conn.execute("""
        SELECT id, label, content, metadata 
        FROM context_locks
    """)
    
    contexts = cursor.fetchall()
    migrated = 0
    
    for ctx in contexts:
        metadata = json.loads(ctx['metadata']) if ctx['metadata'] else {}
        
        # Skip if already has priority
        if 'priority' in metadata:
            continue
        
        # Auto-detect priority based on content
        content_lower = ctx['content'].lower() if ctx['content'] else ""
        
        if any(word in content_lower for word in ['always', 'never', 'must']):
            priority = 'always_check'
        elif any(word in content_lower for word in ['important', 'critical', 'required']):
            priority = 'important'
        else:
            priority = 'reference'
        
        # Extract keywords for better matching
        keywords = []
        keyword_patterns = {
            'output': ['output', 'directory', 'folder', 'path'],
            'test': ['test', 'testing', 'spec'],
            'config': ['config', 'settings', 'configuration'],
            'api': ['api', 'endpoint', 'rest', 'graphql'],
            'database': ['database', 'db', 'sql', 'table'],
            'security': ['auth', 'token', 'password', 'secret'],
        }
        
        for key, terms in keyword_patterns.items():
            if any(term in content_lower for term in terms):
                keywords.append(key)
        
        # Update metadata
        metadata['priority'] = priority
        metadata['keywords'] = keywords
        if 'created_at' not in metadata:
            metadata['created_at'] = '2024-01-01T00:00:00'  # Default for old entries
        
        # Update database
        conn.execute("""
            UPDATE context_locks 
            SET metadata = ?
            WHERE id = ?
        """, (json.dumps(metadata), ctx['id']))
        
        migrated += 1
        print(f"  ✓ {ctx['label']}: {priority} priority")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Migrated {migrated} locked contexts")
    return True

def check_migration_needed(db_path):
    """Check if migration is needed"""
    
    if not os.path.exists(db_path):
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("""
        SELECT COUNT(*) as count
        FROM context_locks
        WHERE metadata IS NULL 
           OR metadata NOT LIKE '%priority%'
    """)
    
    result = cursor.fetchone()
    conn.close()
    
    return result[0] > 0

def main():
    """Run migration for all known databases"""
    
    print("=" * 60)
    print("Claude Dementia v4.0 Migration")
    print("Adding Active Context Engine support")
    print("=" * 60)
    
    databases_to_check = []
    
    # Check current project database
    if os.path.exists('.claude-memory.db'):
        databases_to_check.append('.claude-memory.db')
    
    # Check user cache directory
    cache_dir = os.path.expanduser('~/.claude-dementia')
    if os.path.exists(cache_dir):
        for file in Path(cache_dir).glob('*.db'):
            databases_to_check.append(str(file))
    
    if not databases_to_check:
        print("No databases found to migrate")
        return
    
    print(f"\nFound {len(databases_to_check)} database(s) to check\n")
    
    for db_path in databases_to_check:
        if check_migration_needed(db_path):
            migrate_context_locks(db_path)
        else:
            print(f"✓ {db_path}: Already migrated")
    
    print("\n" + "=" * 60)
    print("Migration complete!")
    print("\nNew features available:")
    print("  • Priority levels: always_check, important, reference")
    print("  • check_contexts() tool for violation detection")
    print("  • High-priority contexts shown at wake_up()")
    print("=" * 60)

if __name__ == "__main__":
    main()