#!/usr/bin/env python3
"""Migration: Add embedding support to context_locks table."""

import sqlite3
import sys
from pathlib import Path


def migrate(db_path: str, dry_run: bool = False):
    """Add embedding columns to context_locks table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Check if columns already exist
    cursor = conn.execute("PRAGMA table_info(context_locks)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'embedding' in columns:
        print("✓ Embedding columns already exist")
        conn.close()
        return

    print("Adding embedding columns...")

    if dry_run:
        print("[DRY RUN] Would execute:")
        print("  ALTER TABLE context_locks ADD COLUMN embedding BLOB")
        print("  ALTER TABLE context_locks ADD COLUMN embedding_model TEXT")
        conn.close()
        return

    # Add columns
    conn.execute('ALTER TABLE context_locks ADD COLUMN embedding BLOB')
    conn.execute('ALTER TABLE context_locks ADD COLUMN embedding_model TEXT')
    conn.commit()

    print("✓ Migration complete")
    print("  - Added 'embedding' column (BLOB)")
    print("  - Added 'embedding_model' column (TEXT)")

    # Show statistics
    cursor = conn.execute("SELECT COUNT(*) as total FROM context_locks")
    total = cursor.fetchone()['total']
    print(f"\nTotal contexts: {total}")
    print("Note: Use 'generate_embeddings()' MCP tool to populate embeddings")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 migrations/add_embeddings.py <db_path> [--dry-run]")
        sys.exit(1)

    db_path = sys.argv[1]
    dry_run = '--dry-run' in sys.argv

    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}")
        sys.exit(1)

    migrate(db_path, dry_run)
