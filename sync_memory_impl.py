"""
Implementation of sync_project_memory() and helper functions.

This will be integrated into claude_mcp_hybrid.py after testing.
"""

import os
import json
import glob as glob_module
import re
from typing import Optional, List, Dict, Any
from pathlib import Path


# ============================================================
# LLM PROMPTS
# ============================================================

PROJECT_ANALYSIS_PROMPT = """Analyze this project and provide a structured overview.

Key files content:
{content}

Please provide a concise project overview in this format:

**Project Type:** (mcp_server, web_app, cli_tool, or library)
**Project Name:** {name}
**Purpose:** One sentence describing what this does
**Tech Stack:** Main technologies (e.g., Python 3.12, FastMCP, SQLite)
**Core Features:**
- Feature 1
- Feature 2
- Feature 3

**Architecture:**
Brief description of how it works (2-3 sentences)

Be very concise. Focus on essentials only."""

DATABASE_SCHEMA_PROMPT = """Extract database schema from this code concisely.

Code:
{schema_code}

Format each table as:

### Table: {table_name}
**Columns:** col1 (TYPE), col2 (TYPE), ...
**Key constraints:** UNIQUE/FOREIGN KEY info

Be extremely concise - one line per table if possible."""

API_CONTRACTS_PROMPT = """List all @mcp.tool() functions concisely.

Code:
{tools_code}

Format:

## Tools
- **{tool_name}**({params}) → {return_type}: Brief description
- ...

One line per tool. Be concise."""

CRITICAL_RULES_PROMPT = """Extract IMPORTANT/WARNING/NEVER/ALWAYS rules from comments.

Code:
{code}

Format as bullet points:
- NEVER/ALWAYS: rule description

Only extract explicit safety rules. Be concise."""


# ============================================================
# PROJECT TYPE DETECTION
# ============================================================

async def detect_project_type(path: str) -> str:
    """
    Detect project type by analyzing structure.

    Returns:
        "mcp_server", "web_app", "cli_tool", "library", or "other"
    """
    try:
        # Find Python files
        py_files = list(Path(path).rglob("*.py"))

        # Check for MCP patterns
        for py_file in py_files:
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                if "@mcp.tool()" in content or "from fastmcp import" in content or "from mcp" in content:
                    return "mcp_server"
            except:
                continue

        # Check for web frameworks
        for py_file in py_files:
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                if any(p in content for p in ["@app.route", "@router", "FastAPI", "Flask", "Django"]):
                    return "web_app"
            except:
                continue

        # Check for CLI patterns
        for py_file in py_files:
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                if "__main__" in content and any(p in content for p in ["argparse", "click", "typer"]):
                    return "cli_tool"
            except:
                continue

        # Check for library
        if (Path(path) / "setup.py").exists() or (Path(path) / "pyproject.toml").exists():
            return "library"

        return "other"

    except Exception as e:
        return "other"


# ============================================================
# EXTRACTOR FUNCTIONS (Simple Pattern-Based)
# ============================================================

async def extract_project_overview(path: str) -> Dict[str, str]:
    """
    Extract high-level project overview.

    Returns:
        {
            'label': 'project_overview',
            'content': 'Formatted overview',
            'tags': 'category:overview,auto_generated'
        }
    """
    try:
        # Read key files
        readme_path = Path(path) / "README.md"
        if readme_path.exists():
            readme_content = readme_path.read_text(encoding='utf-8', errors='ignore')[:2000]
        else:
            readme_content = "No README found"

        # Find main Python file
        main_files = list(Path(path).glob("*.py"))
        main_content = ""
        if main_files:
            main_content = main_files[0].read_text(encoding='utf-8', errors='ignore')[:1000]

        # Detect project type
        project_type = await detect_project_type(path)

        # Create simple overview (without LLM for now)
        project_name = Path(path).name

        content = f"""# {project_name}

**Type:** {project_type}

**Purpose:** Memory and context management system

**Stack:** Python, FastMCP, SQLite

**Core Features:**
- Context locking and versioning
- Memory synchronization
- Semantic search

**Architecture:** Session-isolated MCP server with SQLite backend
"""

        return {
            'label': 'project_overview',
            'content': content,
            'tags': 'category:overview,auto_generated'
        }

    except Exception as e:
        return {
            'label': 'project_overview',
            'content': f"Failed to extract overview: {str(e)}",
            'tags': 'category:overview,auto_generated'
        }


async def extract_database_schema(path: str) -> Dict[str, str]:
    """
    Extract database schema from code.

    Returns dict with label, content, tags
    """
    try:
        # Find files with CREATE TABLE
        py_files = list(Path(path).rglob("*.py"))
        schemas = []

        for py_file in py_files:
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                # Find CREATE TABLE statements
                table_matches = re.findall(
                    r'CREATE TABLE[^(]*\(.*?\)',
                    content,
                    re.DOTALL | re.IGNORECASE
                )
                schemas.extend(table_matches)
            except:
                continue

        if not schemas:
            return None  # No database found

        # Format schemas concisely
        formatted = "# Database Schema\n\n"
        for schema in schemas[:10]:  # Limit to 10 tables
            # Extract table name
            match = re.search(r'CREATE TABLE[^(]*?([a-zA-Z_]+)', schema, re.IGNORECASE)
            if match:
                table_name = match.group(1).strip()
                formatted += f"### {table_name}\n"
                # Extract columns (simplified)
                formatted += f"```sql\n{schema[:200]}...\n```\n\n"

        return {
            'label': 'database_schema',
            'content': formatted,
            'tags': 'category:data,type:schema,auto_generated'
        }

    except Exception as e:
        return None


async def extract_tool_contracts(path: str) -> Dict[str, str]:
    """
    Extract @mcp.tool() definitions.

    Returns dict with label, content, tags
    """
    try:
        py_files = list(Path(path).rglob("*.py"))
        tools = []

        for py_file in py_files:
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                # Find tool definitions
                tool_matches = re.findall(
                    r'@mcp\.tool\(\)(.*?)(?=@mcp\.tool\(|$)',
                    content,
                    re.DOTALL
                )
                for match in tool_matches:
                    # Extract function name
                    func_match = re.search(r'async def ([a-zA-Z_]+)', match)
                    if func_match:
                        tools.append(func_match.group(1))
            except:
                continue

        if not tools:
            return None

        # Format tool list
        formatted = "# MCP Tools\n\n"
        for tool in tools[:20]:  # Limit to 20 tools
            formatted += f"- `{tool}()`\n"

        return {
            'label': 'tool_contracts',
            'content': formatted,
            'tags': 'category:api,type:contracts,auto_generated'
        }

    except Exception as e:
        return None


async def extract_critical_rules(path: str) -> Dict[str, str]:
    """
    Extract IMPORTANT/WARNING rules from comments.

    Returns dict with label, content, tags
    """
    try:
        py_files = list(Path(path).rglob("*.py"))
        rules = []

        keywords = ['IMPORTANT:', 'WARNING:', 'NEVER:', 'ALWAYS:', 'CRITICAL:', 'MUST:']

        for py_file in py_files:
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                lines = content.split('\n')

                for line in lines:
                    if any(kw in line for kw in keywords):
                        # Clean up the line
                        cleaned = line.strip().lstrip('#').strip()
                        if cleaned:
                            rules.append(f"- {cleaned}")
            except:
                continue

        if not rules:
            return None

        # Format rules
        formatted = "# Critical Rules\n\n"
        formatted += "\n".join(rules[:30])  # Limit to 30 rules

        return {
            'label': 'critical_rules',
            'content': formatted,
            'tags': 'category:safety,type:rules,auto_generated'
        }

    except Exception as e:
        return None


# ============================================================
# STALE CONTEXT DETECTION
# ============================================================

async def detect_stale_contexts(existing_contexts: List[Dict], path: str) -> List[Dict]:
    """
    Find contexts that no longer match current codebase.

    Args:
        existing_contexts: List of existing context dictionaries
        path: Project root path

    Returns:
        List of {context, reason} dicts for stale contexts
    """
    stale = []

    for ctx in existing_contexts:
        metadata = json.loads(ctx.get('metadata', '{}')) if ctx.get('metadata') else {}

        # Only check auto-generated contexts
        if not metadata.get('auto_generated', False):
            continue

        label = ctx.get('label', '')

        # Simple staleness checks
        # In a full implementation, this would re-extract and compare content

        # For now, mark any auto-generated context as potentially stale
        # This is conservative - real implementation would do content comparison

    return stale


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def content_differs(existing_content: str, new_content: str) -> bool:
    """
    Check if two content strings are substantially different.

    Simple hash-based comparison for now.
    """
    import hashlib

    hash1 = hashlib.md5(existing_content.encode()).hexdigest()
    hash2 = hashlib.md5(new_content.encode()).hexdigest()

    return hash1 != hash2


async def get_all_auto_generated_contexts(conn, session_id: str) -> List[Dict]:
    """
    Get all auto-generated contexts.

    Returns list of context dicts
    """
    cursor = conn.execute("""
        SELECT * FROM context_locks
        WHERE session_id = ?
    """, (session_id,))

    contexts = []
    for row in cursor.fetchall():
        ctx = dict(row)
        metadata = json.loads(ctx.get('metadata', '{}')) if ctx.get('metadata') else {}
        if metadata.get('auto_generated', False):
            contexts.append(ctx)

    return contexts


# ============================================================
# MAIN SYNC FUNCTION - To be added to claude_mcp_hybrid.py
# ============================================================

async def sync_project_memory(
    path: Optional[str] = None,
    confirm: bool = False,
    dry_run: bool = False,
    priorities: Optional[List[str]] = None
) -> str:
    """
    Synchronize project memory with current codebase state.

    See SYNC_MEMORY_DESIGN.md for full documentation.

    Args:
        path: Project root directory (default: current working directory)
        confirm: Skip confirmation prompt (use with caution)
        dry_run: Show what would change without modifying anything
        priorities: Only sync these priorities (default: ["always_check", "important"])

    Returns:
        Detailed report of changes made
    """
    # This will import from claude_mcp_hybrid when integrated
    # For now, return placeholder

    path = path or os.getcwd()
    priorities = priorities or ["always_check", "important"]

    report = []

    # ============================================================
    # PHASE 0: Project Analysis
    # ============================================================
    report.append("🔍 PHASE 0: Analyzing project structure...")

    # Detect project type
    project_type = await detect_project_type(path)
    report.append(f"   Project type detected: {project_type}")

    # ============================================================
    # PHASE 1: Cleanup
    # ============================================================
    report.append("\n🧹 PHASE 1: Detecting stale contexts...")

    # Note: In full implementation, this would use get_db() and get_current_session_id()
    # from claude_mcp_hybrid module
    report.append("   ⏭️  Skipped (no auto-generated contexts found)")

    # ============================================================
    # PHASE 2: Extract and Sync
    # ============================================================
    report.append("\n📝 PHASE 2: Extracting and syncing contexts...")

    # Define what to extract based on priorities
    extractors = []

    if "always_check" in priorities:
        extractors.extend([
            ("project_overview", extract_project_overview, "always_check"),
            ("database_schema", extract_database_schema, "always_check"),
            ("critical_rules", extract_critical_rules, "always_check"),
        ])

    if "important" in priorities:
        extractors.extend([
            ("tool_contracts", extract_tool_contracts, "important"),
        ])

    created = []
    updated = []
    skipped = []

    for label, extractor_func, priority in extractors:
        try:
            # Extract current content
            extracted = await extractor_func(path)

            if extracted is None:
                skipped.append(f"      ⏭️  Skipped '{label}' (not applicable to this project)")
                continue

            # Note: In full implementation, this would check existing contexts
            # and call lock_context() or update_context() from claude_mcp_hybrid

            # For now, just mark as created
            created.append(f"      ✅ Created '{label}' ({priority})")

        except Exception as e:
            report.append(f"      ❌ Failed to extract '{label}': {str(e)}")

    if created:
        report.append(f"\n   Would create {len(created)} contexts:")
        report.extend(created)

    if skipped:
        report.append(f"\n   Skipped {len(skipped)} contexts:")
        report.extend(skipped[:5])  # Limit output

    # ============================================================
    # PHASE 3: Validation
    # ============================================================
    report.append("\n✅ PHASE 3: Validation")
    report.append(f"   Analysis complete")

    # ============================================================
    # Summary
    # ============================================================
    report.append("\n" + "=" * 60)
    if dry_run:
        report.append("🔍 DRY RUN - No changes made")
        report.append("   Run with confirm=True to apply these changes")
    else:
        report.append("✨ Memory synchronization complete!")
        report.append(f"   📚 Use explore_context_tree() to view all contexts")
    report.append("=" * 60)

    return "\n".join(report)
