#!/usr/bin/env python3
"""
Migration script for RLM enhancements (v4.0 → v4.1)

Adds:
- preview, key_concepts, related_contexts columns to context_locks
- last_accessed, access_count for usage tracking
- New tables: context_relationships, context_access_log, tool_usage_log
- Auto-generates previews for existing contexts

Usage:
    python3 migrate_v4_1_rlm.py [path/to/database.db]

    If no path provided, uses .claude-memory.db in current directory
"""

import sqlite3
import json
import re
import sys
import time
from typing import List, Optional
from pathlib import Path


def generate_preview(content: str, max_length: int = 500) -> str:
    """
    Generate intelligent preview from context content.

    Algorithm:
    1. Extract title/header
    2. Find first substantial lines
    3. Find key sentences with MUST/ALWAYS/NEVER
    4. Combine and truncate to max_length
    """
    if not content or not content.strip():
        return ""

    lines = [line.strip() for line in content.split('\n') if line.strip()]

    if not lines:
        return ""

    preview_parts = []

    # Find title/header (lines starting with #)
    has_header = False
    for line in lines[:5]:
        if line.startswith('#'):
            title = line.lstrip('#').strip()
            preview_parts.append(title)
            has_header = True
            break

    # If no header, use first line as title
    if not has_header and lines:
        preview_parts.append(lines[0])

    # Find substantial content lines (skip headers and very short lines)
    # Also capture key-value pairs like "Host: localhost"
    content_lines = 0
    for line in lines[1:] if has_header else lines[1:]:
        if not line.startswith('#'):
            # Include if substantial (>30 chars) OR key-value pair pattern
            is_substantial = len(line) > 30
            is_key_value = ':' in line and len(line) > 5

            if is_substantial or is_key_value:
                preview_parts.append(line)
                content_lines += 1
                if content_lines >= 3:  # Increased to 3 for config files
                    break

    # Find key sentences with important keywords
    important_patterns = r'\b(MUST|ALWAYS|NEVER|REQUIRED|CRITICAL|WARNING|IMPORTANT)\b'
    key_sentences = []
    for line in lines:
        if re.search(important_patterns, line, re.IGNORECASE):
            key_sentences.append(line)
            if len(key_sentences) >= 2:
                break

    if key_sentences:
        preview_parts.append("Rules: " + "; ".join(key_sentences[:2]))

    # Combine
    preview = "\n".join(preview_parts)

    # Truncate if needed
    if len(preview) > max_length:
        preview = preview[:max_length-3] + "..."

    # Fallback to first max_length chars if preview is empty
    if not preview and content:
        preview = content[:max_length]

    return preview


def extract_key_concepts(content: str, tags: List[str] = None) -> List[str]:
    """
    Extract key technical concepts from content.

    Returns up to 10 key concepts as list of strings.
    """
    concepts = set(tags or [])

    if not content:
        return list(concepts)[:10]

    # Technical terms (CamelCase)
    camel_case = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', content)
    concepts.update(camel_case[:5])

    # snake_case identifiers
    snake_case = re.findall(r'\b[a-z]+_[a-z_]+\b', content)
    concepts.update(snake_case[:5])

    # Common technical terms
    domain_patterns = [
        r'\b(API|REST|GraphQL|JWT|OAuth|OAuth2|SAML)\b',
        r'\b(database|SQL|NoSQL|MongoDB|PostgreSQL|Redis)\b',
        r'\b(authentication|authorization|security|encryption)\b',
        r'\b(deployment|CI/CD|Docker|Kubernetes|container)\b',
        r'\b(React|Vue|Angular|TypeScript|JavaScript|Python|Go|Rust)\b',
    ]

    for pattern in domain_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        concepts.update(matches[:3])

    # Limit to top 10
    return list(concepts)[:10]


def check_migration_status(conn: sqlite3.Connection) -> bool:
    """Check if database is already migrated to v4.1"""
    cursor = conn.execute("PRAGMA table_info(context_locks)")
    columns = [row[1] for row in cursor.fetchall()]

    # Check for key v4.1 columns
    return 'preview' in columns and 'key_concepts' in columns


def migrate_database(db_path: str, verbose: bool = True) -> dict:
    """
    Apply v4.1 RLM schema changes.

    Returns dict with migration statistics.
    """
    if verbose:
        print(f"🔄 Migrating database: {db_path}")

    stats = {
        'already_migrated': False,
        'contexts_updated': 0,
        'previews_generated': 0,
        'tables_created': 0,
        'errors': []
    }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Check if already migrated FIRST, before any changes
        already_migrated = check_migration_status(conn)

        if already_migrated:
            stats['already_migrated'] = True
            if verbose:
                print("✅ Database already migrated to v4.1")
            return stats

        if verbose:
            print("📝 Applying schema changes...")

        # Add new columns to context_locks
        cursor = conn.execute("PRAGMA table_info(context_locks)")
        existing_columns = [row[1] for row in cursor.fetchall()]

        new_columns = [
            ('preview', 'TEXT'),
            ('key_concepts', 'TEXT'),  # JSON array
            ('related_contexts', 'TEXT'),  # JSON array
            ('last_accessed', 'TIMESTAMP'),
            ('access_count', 'INTEGER DEFAULT 0'),
        ]

        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                try:
                    conn.execute(f'ALTER TABLE context_locks ADD COLUMN {col_name} {col_type}')
                    if verbose:
                        print(f"   ✅ Added column: {col_name}")
                except sqlite3.OperationalError as e:
                    stats['errors'].append(f"Failed to add {col_name}: {e}")

        # Create new tables
        tables_sql = [
            ('''
                CREATE TABLE IF NOT EXISTS context_relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    from_label TEXT NOT NULL,
                    to_label TEXT NOT NULL,
                    relationship_type TEXT,
                    strength REAL DEFAULT 0.5,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(session_id, from_label, to_label)
                )
            ''', 'context_relationships'),
            ('''
                CREATE TABLE IF NOT EXISTS context_access_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    access_type TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''', 'context_access_log'),
            ('''
                CREATE TABLE IF NOT EXISTS tool_usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    params TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    session_id TEXT NOT NULL
                )
            ''', 'tool_usage_log'),
        ]

        for sql, table_name in tables_sql:
            try:
                conn.execute(sql)
                stats['tables_created'] += 1
                if verbose:
                    print(f"   ✅ Created table: {table_name}")
            except sqlite3.OperationalError as e:
                stats['errors'].append(f"Failed to create {table_name}: {e}")

        # Create indices for performance
        indices_sql = [
            'CREATE INDEX IF NOT EXISTS idx_context_preview ON context_locks(session_id, label, preview)',
            'CREATE INDEX IF NOT EXISTS idx_context_access ON context_locks(session_id, last_accessed DESC)',
            'CREATE INDEX IF NOT EXISTS idx_relationships ON context_relationships(session_id, from_label)',
            'CREATE INDEX IF NOT EXISTS idx_access_log ON context_access_log(session_id, label, timestamp DESC)',
            'CREATE INDEX IF NOT EXISTS idx_tool_usage ON tool_usage_log(session_id, tool_name, timestamp DESC)',
        ]

        for sql in indices_sql:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                stats['errors'].append(f"Failed to create index: {e}")

        conn.commit()

        # Generate previews for existing contexts
        if verbose:
            print("\n📝 Generating previews for existing contexts...")

        cursor = conn.execute("""
            SELECT id, label, content, metadata
            FROM context_locks
        """)

        contexts = cursor.fetchall()

        for row in contexts:
            try:
                # Parse existing tags from metadata
                tags = []
                if row['metadata']:
                    try:
                        metadata = json.loads(row['metadata'])
                        tags = metadata.get('tags', [])
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Generate preview and concepts
                preview = generate_preview(row['content'])
                key_concepts = extract_key_concepts(row['content'], tags)

                # Update context
                conn.execute("""
                    UPDATE context_locks
                    SET preview = ?,
                        key_concepts = ?,
                        last_accessed = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (preview, json.dumps(key_concepts), row['id']))

                stats['contexts_updated'] += 1
                stats['previews_generated'] += 1

                if verbose and stats['contexts_updated'] % 10 == 0:
                    print(f"   Processed {stats['contexts_updated']} contexts...")

            except Exception as e:
                stats['errors'].append(f"Failed to process context {row['label']}: {e}")

        conn.commit()

        if verbose:
            print(f"\n✅ Migration complete!")
            print(f"   Contexts updated: {stats['contexts_updated']}")
            print(f"   Previews generated: {stats['previews_generated']}")
            print(f"   Tables created: {stats['tables_created']}")
            if stats['errors']:
                print(f"\n⚠️  Errors encountered: {len(stats['errors'])}")
                for error in stats['errors'][:5]:
                    print(f"   - {error}")

    except Exception as e:
        conn.rollback()
        stats['errors'].append(f"Critical error: {e}")
        if verbose:
            print(f"❌ Migration failed: {e}")
        raise

    finally:
        conn.close()

    return stats


def verify_migration(db_path: str) -> bool:
    """Verify that migration was successful"""
    conn = sqlite3.connect(db_path)

    try:
        # Check columns exist
        cursor = conn.execute("PRAGMA table_info(context_locks)")
        columns = [row[1] for row in cursor.fetchall()]

        required_columns = ['preview', 'key_concepts', 'related_contexts', 'last_accessed', 'access_count']
        missing = [col for col in required_columns if col not in columns]

        if missing:
            print(f"❌ Missing columns: {missing}")
            return False

        # Check tables exist
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN (
                'context_relationships',
                'context_access_log',
                'tool_usage_log'
            )
        """)
        tables = [row[0] for row in cursor.fetchall()]

        required_tables = ['context_relationships', 'context_access_log', 'tool_usage_log']
        missing_tables = [t for t in required_tables if t not in tables]

        if missing_tables:
            print(f"❌ Missing tables: {missing_tables}")
            return False

        # Check preview generation worked
        cursor = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN preview IS NOT NULL AND preview != '' THEN 1 ELSE 0 END) as with_preview
            FROM context_locks
        """)
        row = cursor.fetchone()

        if row[0] > 0 and row[1] == 0:
            print(f"⚠️  Warning: No previews generated for {row[0]} contexts")

        print(f"✅ Verification passed: {row[1]}/{row[0]} contexts have previews")
        return True

    finally:
        conn.close()


def main():
    """Main migration entry point"""
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = '.claude-memory.db'

    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        print(f"\nUsage: python3 {sys.argv[0]} [path/to/database.db]")
        sys.exit(1)

    print("=" * 60)
    print("Claude Dementia v4.1 RLM Migration")
    print("=" * 60)
    print()

    # Run migration
    stats = migrate_database(db_path, verbose=True)

    if stats['errors']:
        print(f"\n⚠️  Migration completed with {len(stats['errors'])} errors")
        sys.exit(1)

    # Verify
    print("\n" + "=" * 60)
    print("Verifying migration...")
    print("=" * 60)
    print()

    if verify_migration(db_path):
        print("\n✅ Migration and verification successful!")
        sys.exit(0)
    else:
        print("\n❌ Migration verification failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
