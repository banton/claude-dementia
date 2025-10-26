#!/usr/bin/env python3
"""
Initialize and inspect PostgreSQL schema for Claude Dementia projects.

Schema auto-detection:
- Detects project name from git repository or directory name
- No manual configuration needed
- Schema name: {project_name}

Usage:
    python3 init_project_db.py --init           # Initialize schema for current project
    python3 init_project_db.py --status         # Show current schema status
    python3 init_project_db.py --list-schemas   # List all schemas
    python3 init_project_db.py --schema NAME    # Use specific schema (override)
"""

import os
import sys
import argparse
from dotenv import load_dotenv

load_dotenv()

def init_schema(schema_name: str = None):
    """Initialize PostgreSQL schema for a project (auto-detects from directory)."""
    from postgres_adapter import PostgreSQLAdapter
    from src.config import config

    print(f"\n🔧 Initializing PostgreSQL schema...")
    print(f"   Working directory: {os.getcwd()}")

    try:
        if schema_name:
            # Explicit schema override
            adapter = PostgreSQLAdapter(
                database_url=config.database_url,
                schema=schema_name
            )
            print(f"   Schema (explicit): {schema_name}\n")
        else:
            # Auto-detect from directory
            adapter = PostgreSQLAdapter(database_url=config.database_url)
            print(f"   Schema (auto-detected): {adapter.schema}\n")

        adapter.ensure_schema_exists()

        print(f"✅ Schema '{adapter.schema}' initialized successfully!")
        print(f"\n📝 Claude Desktop MCP config:")
        print(f'   {{')
        print(f'     "mcpServers": {{')
        print(f'       "dementia": {{')
        print(f'         "command": "python3",')
        print(f'         "args": ["/path/to/claude_mcp_hybrid.py"]')
        print(f'       }}')
        print(f'     }}')
        print(f'   }}')
        print(f'\n   (Schema will auto-detect based on working directory)')

        adapter.close()
        return True

    except Exception as e:
        print(f"❌ Error initializing schema: {e}")
        import traceback
        traceback.print_exc()
        return False


def show_status(schema_name: str = None):
    """Show status of current PostgreSQL schema (auto-detects from directory)."""
    from postgres_adapter import PostgreSQLAdapter
    from src.config import config

    print(f"\n📊 Schema Status")
    print(f"   Working directory: {os.getcwd()}")

    try:
        if schema_name:
            adapter = PostgreSQLAdapter(
                database_url=config.database_url,
                schema=schema_name
            )
            print(f"   Schema (explicit): {schema_name}\n")
        else:
            adapter = PostgreSQLAdapter(database_url=config.database_url)
            print(f"   Schema (auto-detected): {adapter.schema}\n")

        conn = adapter.get_connection()
        cur = conn.cursor()

        # Check if schema exists
        cur.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name = %s
        """, (adapter.schema,))

        if not cur.fetchone():
            print(f"❌ Schema '{adapter.schema}' does not exist")
            print(f"   Run: python3 init_project_db.py --init")
            return False

        print(f"✅ Schema exists")

        # List tables
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name
        """, (adapter.schema,))

        tables = [row['table_name'] for row in cur.fetchall()]
        print(f"\n📋 Tables ({len(tables)}):")
        for table in tables:
            print(f"   - {table}")

        # Count records in key tables
        print(f"\n📈 Record Counts:")
        for table in ['sessions', 'context_locks', 'memory_entries', 'audit_trail']:
            if table in tables:
                cur.execute(f'SELECT COUNT(*) as count FROM "{adapter.schema}".{table}')
                count = cur.fetchone()['count']
                print(f"   {table}: {count}")

        adapter.release_connection(conn)
        adapter.close()
        return True

    except Exception as e:
        print(f"❌ Error checking status: {e}")
        import traceback
        traceback.print_exc()
        return False


def list_all_schemas():
    """List all Claude Dementia schemas in the database."""
    from postgres_adapter import PostgreSQLAdapter
    from src.config import config

    print(f"\n📚 All Claude Dementia Schemas\n")

    try:
        # Connect without specifying a schema to see all
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(config.database_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # List all user_* schemas
        cur.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name LIKE 'user_%'
            ORDER BY schema_name
        """)

        schemas = [row['schema_name'] for row in cur.fetchall()]

        if not schemas:
            print("   No schemas found")
        else:
            for schema in schemas:
                # Get record counts
                cur.execute(f'SELECT COUNT(*) as count FROM "{schema}".sessions')
                sessions = cur.fetchone()['count']
                cur.execute(f'SELECT COUNT(*) as count FROM "{schema}".context_locks')
                contexts = cur.fetchone()['count']

                print(f"   {schema}")
                print(f"     └─ Sessions: {sessions}, Contexts: {contexts}")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Error listing schemas: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Initialize and manage PostgreSQL schemas for Claude Dementia'
    )

    parser.add_argument('--init', action='store_true',
                       help='Initialize schema for project (auto-detects from directory)')
    parser.add_argument('--status', action='store_true',
                       help='Show schema status (auto-detects from directory)')
    parser.add_argument('--list-schemas', action='store_true',
                       help='List all schemas in database')
    parser.add_argument('--schema', type=str,
                       help='Explicit schema name (optional, overrides auto-detection)')

    args = parser.parse_args()

    # Check if DATABASE_URL is set
    if not os.getenv('DATABASE_URL'):
        print("❌ ERROR: DATABASE_URL not set in .env")
        print("   Please configure PostgreSQL connection in .env file")
        return 1

    if args.list_schemas:
        success = list_all_schemas()
    elif args.init:
        success = init_schema(args.schema)
    elif args.status:
        success = show_status(args.schema)
    else:
        parser.print_help()
        return 0

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
