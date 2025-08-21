#!/usr/bin/env python3
"""
Test script demonstrating active context checking
Shows how the system would have caught the output folder violation
"""

import os
import sys
import sqlite3
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from active_context_engine import ActiveContextEngine, check_command_context

def setup_test_database():
    """Create a test database with sample locked contexts"""
    db_path = "test_context.db"
    
    # Remove if exists
    if os.path.exists(db_path):
        os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    
    # Create context_locks table
    conn.execute('''
        CREATE TABLE context_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            label TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '1.0',
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            locked_at REAL DEFAULT (strftime('%s', 'now')),
            metadata TEXT
        )
    ''')
    
    # Insert test contexts
    test_contexts = [
        {
            'session_id': 'test_session',
            'label': 'output_folder_standard',
            'version': '1.0',
            'content': '''Output Directory Standard:
            
ALWAYS use 'output' as the default output folder for all patient generation commands unless explicitly specified otherwise.

Rationale:
- Single source of truth for generated data
- Timestamped files prevent overwriting
- Easier to manage and clean up
- Consistent with project conventions

Example correct usage:
python generator.py --count 100 --output output

DO NOT create separate folders like output_test, output_1000, etc.''',
            'content_hash': 'abc123',
            'locked_at': 1692000000,
            'metadata': json.dumps({
                'tags': ['configuration', 'standards', 'workflow'],
                'priority': 'always_check',
                'keywords': ['output', 'folder', 'directory']
            })
        },
        {
            'session_id': 'test_session',
            'label': 'test_organization',
            'version': '1.0',
            'content': '''Test Organization Rules:

NEVER mix test files with source code.
ALWAYS put tests in a dedicated test/ or tests/ directory.
Test files MUST follow naming convention: test_*.py or *_test.py''',
            'content_hash': 'def456',
            'locked_at': 1692000100,
            'metadata': json.dumps({
                'tags': ['testing', 'organization'],
                'priority': 'important',
                'keywords': ['test', 'testing']
            })
        },
        {
            'session_id': 'test_session',
            'label': 'api_design',
            'version': '2.1',
            'content': '''API Design Principles:

Use RESTful conventions for all endpoints.
Version APIs from the start (/api/v1/).
Document with OpenAPI spec.''',
            'content_hash': 'ghi789',
            'locked_at': 1692000200,
            'metadata': json.dumps({
                'tags': ['api', 'design'],
                'priority': 'reference',
                'keywords': ['api', 'rest', 'endpoint']
            })
        }
    ]
    
    for ctx in test_contexts:
        conn.execute("""
            INSERT INTO context_locks 
            (session_id, label, version, content, content_hash, locked_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (ctx['session_id'], ctx['label'], ctx['version'], 
              ctx['content'], ctx['content_hash'], ctx['locked_at'], ctx['metadata']))
    
    conn.commit()
    conn.close()
    
    return db_path

def test_scenarios(db_path):
    """Test various scenarios to show active checking"""
    
    print("=" * 60)
    print("ACTIVE CONTEXT ENGINE - DEMONSTRATION")
    print("=" * 60)
    
    engine = ActiveContextEngine(db_path)
    session_id = 'test_session'
    
    # Test 1: The output folder violation that actually happened
    print("\n📝 Test 1: Output Folder Violation (What Actually Happened)")
    print("-" * 40)
    
    commands = [
        "python test_simulation_statistics.py --output output_test",
        "python generate_patients.py --count 1000 --output output_1000",
        "mkdir output_validation && python validate.py --output output_validation"
    ]
    
    for cmd in commands:
        print(f"\nCommand: {cmd}")
        warning = check_command_context(cmd, session_id, db_path)
        if warning:
            print(warning)
        else:
            print("✅ No violations detected")
    
    # Test 2: Correct usage
    print("\n\n📝 Test 2: Correct Usage")
    print("-" * 40)
    
    correct_commands = [
        "python test_simulation_statistics.py --output output",
        "python generate_patients.py --count 1000 --output output",
    ]
    
    for cmd in correct_commands:
        print(f"\nCommand: {cmd}")
        warning = check_command_context(cmd, session_id, db_path)
        if warning:
            print(warning)
        else:
            print("✅ No violations detected")
    
    # Test 3: Check relevant contexts for different texts
    print("\n\n📝 Test 3: Finding Relevant Contexts")
    print("-" * 40)
    
    texts = [
        "I need to save the generated data somewhere",
        "Let's write some tests for this feature",
        "Creating a new API endpoint for patient data",
        "Setting up the database schema"
    ]
    
    for text in texts:
        print(f"\nText: \"{text}\"")
        contexts = engine.check_context_relevance(text, session_id)
        if contexts:
            print(f"Found {len(contexts)} relevant context(s):")
            for ctx in contexts:
                priority = "⚠️" if ctx['priority'] == 'always_check' else "📌" if ctx['priority'] == 'important' else "📄"
                print(f"  {priority} {ctx['label']} v{ctx['version']} (relevance: {ctx['relevance_score']})")
        else:
            print("  No relevant contexts found")
    
    # Test 4: Session start reminders
    print("\n\n📝 Test 4: Session Start Reminders")
    print("-" * 40)
    
    print("\nHigh-priority contexts (shown at session start):")
    summary = engine.get_session_context_summary(session_id, priority='always_check')
    print(summary)
    
    print("\nAll contexts summary:")
    all_summary = engine.get_session_context_summary(session_id)
    print(all_summary)
    
    # Test 5: Show how the violation would have been prevented
    print("\n\n📝 Test 5: How It Would Have Prevented The Issue")
    print("-" * 40)
    
    print("\nSCENARIO: About to create test script with custom output folder")
    print("\nYour action: Creating file 'test_demo.py' with content:")
    print("  parser.add_argument('--output', default='output_test')")
    
    # Simulate checking before file creation
    file_content = "parser.add_argument('--output', default='output_test', help='Output directory')"
    warning = check_command_context(f"write file with: {file_content}", session_id, db_path)
    
    if warning:
        print("\n⚠️ ACTIVE CONTEXT ENGINE ALERT:")
        print(warning)
        print("\n✅ This would have prevented the violation!")
    
    print("\n" + "=" * 60)
    print("DEMONSTRATION COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    # Setup test database
    db_path = setup_test_database()
    
    try:
        # Run tests
        test_scenarios(db_path)
    finally:
        # Cleanup
        if os.path.exists(db_path):
            os.remove(db_path)
    
    print("\n✨ The active context engine would have caught the output folder violation!")
    print("📚 Key insight: Passive memory (database) → Active enforcement (rule engine)")