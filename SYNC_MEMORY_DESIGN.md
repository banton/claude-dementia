# sync_project_memory() Design Specification

## Overview

**Purpose:** Synchronize locked contexts with current project state - make memory match reality.

**Key Behaviors:**
- **Analyzes** project to understand type and structure
- **Removes** stale contexts (features no longer in code)
- **Updates** changed contexts (modified features)
- **Creates** new contexts (new features detected)
- **Organizes** contexts with structured categories

**When to use:**
- First run on new project (bootstrapping)
- After major refactor (REST → GraphQL migration)
- After significant file changes (new modules added)
- When memory feels "out of date"

---

## Tool Signature

```python
@mcp.tool()
async def sync_project_memory(
    path: Optional[str] = None,
    confirm: bool = False,
    dry_run: bool = False,
    priorities: Optional[List[str]] = None
) -> str:
    """
    Synchronize project memory with current codebase state.

    **What this does:**

    This tool creates a complete "understanding" of your project by:
    1. Analyzing project structure to detect type (MCP server, web app, library, CLI)
    2. Generating a high-level overview of what the project does
    3. Extracting critical patterns (schemas, APIs, architecture, rules)
    4. Organizing knowledge into categorized locked contexts
    5. Removing outdated contexts that no longer match code

    After running, Claude can answer "What is this project?" from locked
    contexts without re-reading source files.

    **When to use:**

    - **First run:** Bootstrap memory for new project
    - **Major changes:** After refactoring, migrations, or significant rewrites
    - **Feeling lost:** When Claude seems confused about project structure

    **What gets extracted:**

    ALWAYS_CHECK priority (critical - must be 100% accurate):
    - project_overview: What is this project? Type, purpose, stack, features
    - database_schema: Exact table definitions (if database exists)
    - critical_rules: IMPORTANT/NEVER/ALWAYS rules from code comments
    - session_safety: Session isolation and state management rules

    IMPORTANT priority (frequently needed):
    - architecture: System design, components, data flow
    - api_contracts: All tool/endpoint signatures with descriptions
    - versioning_logic: How versions work (if applicable)
    - configuration: Key settings and environment variables

    REFERENCE priority (occasionally useful):
    - utility_functions: Helper function signatures
    - test_patterns: Testing approach and common fixtures
    - deployment: How to install, configure, run

    **Safety features:**

    - Requires confirmation before deleting stale contexts
    - Archives deleted contexts for recovery
    - Shows detailed change report before applying
    - Preserves version history on updates
    - Never touches user-created contexts (only auto-generated ones)

    **Args:**
        path (str): Project root directory (default: current working directory)
        confirm (bool): Skip confirmation prompt (use with caution)
        dry_run (bool): Show what would change without modifying anything
        priorities (List[str]): Only sync these priorities (default: ["always_check", "important"])
            Options: "always_check", "important", "reference"

    **Returns:**
        Detailed report of changes made:
        - Number of contexts analyzed
        - Stale contexts deleted (with reasons)
        - Contexts updated (with version changes)
        - New contexts created
        - Final memory structure

    **Examples:**

    ```python
    # First run - bootstrap memory (safe, shows preview)
    sync_project_memory(dry_run=True)

    # After seeing dry run, apply changes
    sync_project_memory(confirm=True)

    # After major refactor - sync critical contexts only
    sync_project_memory(confirm=True, priorities=["always_check"])

    # Full sync including reference docs
    sync_project_memory(confirm=True, priorities=["always_check", "important", "reference"])
    ```

    **Warning:**
    This is a destructive operation that may delete contexts. Always run with
    dry_run=True first to preview changes. Deleted contexts are archived and
    can be recovered from context_archives table.

    **Tags:** memory, initialization, sync, cleanup, analysis
    """
```

---

## LLM Prompts for Extraction

### Prompt 1: Project Analysis

```python
PROJECT_ANALYSIS_PROMPT = """Analyze this project and provide a structured overview.

Files analyzed:
{file_list}

Key files content:
{key_files_content}

Please provide:

1. **Project Type** (choose one):
   - mcp_server: MCP server using FastMCP or similar
   - web_app: Web application (Flask, FastAPI, Django, Express, etc.)
   - cli_tool: Command-line application
   - library: Reusable library/package
   - other: (specify)

2. **Project Name:** Extract from package.json, setup.py, or main file

3. **Purpose:** One sentence describing what this project does (user value)

4. **Tech Stack:** List primary languages, frameworks, databases, APIs used

5. **Core Features:** 3-5 main capabilities (bullet points)

6. **Architecture Pattern:**
   - How components interact
   - Data flow (if applicable)
   - Key design patterns used

7. **Key Workflows:** Common development/usage patterns

Format your response as structured YAML:
```yaml
project_type: <type>
project_name: <name>
purpose: <one sentence>
tech_stack:
  - <technology 1>
  - <technology 2>
core_features:
  - <feature 1>
  - <feature 2>
architecture:
  pattern: <description>
  data_flow: <description>
workflows:
  - <workflow 1>
```

Be concise but complete. Focus on what makes this project unique."""
```

### Prompt 2: Database Schema Extraction

```python
SCHEMA_EXTRACTION_PROMPT = """Extract database schema from this code.

Code:
{schema_code}

Provide a concise, structured summary:

## Database Schema

### Table: {table_name}
**Purpose:** What this table stores (one sentence)

**Columns:**
- `column_name` (TYPE, constraints) - Purpose
- ...

**Relationships:**
- FOREIGN KEY to other_table(column)
- ...

**Indexes:**
- UNIQUE(col1, col2) - Purpose
- ...

**Key patterns:**
- Any special design patterns (versioning, soft deletes, etc.)

Format for EVERY table found. Be precise with types and constraints.
Omit internal SQLite columns unless significant."""
```

### Prompt 3: API Contracts Extraction

```python
API_CONTRACTS_PROMPT = """Extract API contracts from these tool definitions.

Code:
{tools_code}

For each tool/endpoint, provide:

## Tool: {tool_name}

**Purpose:** What this does (one sentence)

**Signature:**
```python
async def {tool_name}(
    param1: Type,  # Description
    param2: Type = default,  # Description
) -> ReturnType
```

**Parameters:**
- `param1` (Type, required) - What it controls
- `param2` (Type, optional, default: X) - What it controls

**Returns:**
- Type: Description of return value

**Example:**
```python
result = await {tool_name}(param1="example")
# Output: <typical output>
```

**Related tools:** Other tools commonly used with this

Be concise. Focus on contract (signature + behavior), not implementation."""
```

### Prompt 4: Critical Rules Extraction

```python
CRITICAL_RULES_PROMPT = """Extract critical rules from code comments and docstrings.

Code:
{code_with_comments}

Find all statements with these keywords:
- IMPORTANT:
- WARNING:
- NEVER:
- ALWAYS:
- CRITICAL:
- MUST:
- MUST NOT:

Format as categorized bullet points:

## Safety Rules
- NEVER do X because Y
- ALWAYS do Z to ensure W

## Constraints
- MUST X before Y
- Parameter Z MUST be within range [A, B]

## Best Practices
- IMPORTANT: X should be Y for optimal Z

Extract ONLY explicit rules. Include context (why the rule exists) when provided.
Omit generic advice or opinions - focus on hard constraints."""
```

### Prompt 5: Architecture Extraction

```python
ARCHITECTURE_PROMPT = """Describe the software architecture of this project.

Project type: {project_type}

Key files:
{architecture_files}

Provide:

## System Overview
Brief description of how the system works (2-3 sentences)

## Components
- **Component Name:** Role and responsibility
- ...

## Data Flow
1. Step 1: What happens
2. Step 2: What happens
3. ...

## Design Patterns
- Pattern name: Where and why used

## Integration Points
- External API/service: Purpose
- Database: Type and usage
- ...

## Key Decisions
- Why X over Y (if significant architectural choice visible in code)

Be concise. Focus on "what" and "why", not "how" (implementation details).
Assume reader is a developer joining the project."""
```

### Prompt 6: Configuration Extraction

```python
CONFIGURATION_PROMPT = """Extract important configuration from code and files.

Files:
{config_files}

Identify:

## Environment Variables
- `VAR_NAME`: Purpose, type, default value (if any)
- ...

## Configuration Files
- **File:** path/to/config
  - Setting: Purpose
  - ...

## Key Settings
- **Setting Name:**
  - Purpose: What it controls
  - Type: Expected type
  - Default: Default value
  - Example: Valid example

## Configuration Patterns
- How configuration is loaded (env vars, files, database)
- Validation approach
- Secrets management (if visible)

Focus on settings users/developers need to know about.
Omit internal implementation details."""
```

---

## Project Type Detection Logic

```python
async def detect_project_type(path: str) -> str:
    """
    Analyze project structure to determine type.

    Detection rules (in priority order):
    1. MCP Server: Has @mcp.tool() decorators or fastmcp imports
    2. Web App: Has flask/fastapi/django/express with routes/endpoints
    3. CLI Tool: Has argparse/click/typer with __main__
    4. Library: Has setup.py/pyproject.toml but no main entry point
    5. Other: Default fallback
    """
    files = glob_files("**/*.py", path)

    # Check for MCP patterns
    for file in files:
        content = read_file(file)
        if "@mcp.tool()" in content or "from fastmcp import" in content:
            return "mcp_server"

    # Check for web framework patterns
    web_patterns = ["@app.route", "@router.get", "class.*View", "app.get("]
    for file in files:
        content = read_file(file)
        for pattern in web_patterns:
            if re.search(pattern, content):
                return "web_app"

    # Check for CLI patterns
    for file in files:
        content = read_file(file)
        if "if __name__ == '__main__'" in content:
            if any(p in content for p in ["argparse", "click", "typer"]):
                return "cli_tool"

    # Check for library patterns
    if os.path.exists(os.path.join(path, "setup.py")) or \
       os.path.exists(os.path.join(path, "pyproject.toml")):
        return "library"

    return "other"
```

---

## Stale Context Detection

```python
async def detect_stale_contexts(
    existing_contexts: List[dict],
    current_features: dict
) -> List[dict]:
    """
    Find contexts that no longer match current codebase.

    A context is stale if:
    1. Feature extraction (content-based):
       - Context describes database table that no longer exists
       - Context describes API endpoint that was removed
       - Context describes module/file that was deleted

    2. Content hash (hash-based):
       - Context content hash differs from re-extracted content
       - Indicates source code changed but context wasn't updated

    3. Metadata markers (flag-based):
       - Context metadata has "auto_generated": true
       - AND last_accessed > 90 days ago (unused)

    Returns:
        List of stale contexts with reason for staleness
    """
    stale = []

    for ctx in existing_contexts:
        # Skip user-created contexts (only clean auto-generated)
        metadata = json.loads(ctx['metadata']) if ctx['metadata'] else {}
        if not metadata.get('auto_generated', False):
            continue

        # Feature-based detection
        if ctx['label'] == 'database_schema':
            # Re-extract schema and compare
            current_schema = await extract_database_schema(path)
            if not schemas_match(ctx['content'], current_schema['content']):
                stale.append({
                    'context': ctx,
                    'reason': 'Database schema changed (tables added/removed/modified)'
                })

        elif ctx['label'] == 'api_contracts':
            # Re-extract API and compare
            current_api = await extract_api_contracts(path)
            if not apis_match(ctx['content'], current_api['content']):
                stale.append({
                    'context': ctx,
                    'reason': 'API contracts changed (tools/endpoints modified)'
                })

        elif ctx['label'].startswith('module_'):
            # Check if module still exists
            module_name = ctx['label'].replace('module_', '')
            if not module_exists(module_name, path):
                stale.append({
                    'context': ctx,
                    'reason': f'Module {module_name} no longer exists in codebase'
                })

        # Hash-based detection (for other contexts)
        else:
            # This is more conservative - only flag if very different
            pass

    return stale
```

---

## Memory Structure Templates

```python
STRUCTURE_TEMPLATES = {
    "mcp_server": {
        "always_check": [
            {
                "label": "project_overview",
                "extractor": extract_project_overview,
                "description": "High-level understanding of project"
            },
            {
                "label": "database_schema",
                "extractor": extract_database_schema,
                "description": "All database tables and relationships",
                "tags": "category:data, type:schema"
            },
            {
                "label": "critical_rules",
                "extractor": extract_critical_rules,
                "description": "NEVER/ALWAYS safety constraints",
                "tags": "category:safety, type:rules"
            },
            {
                "label": "session_safety",
                "extractor": extract_session_patterns,
                "description": "Session isolation and state management",
                "tags": "category:safety, type:sessions"
            }
        ],
        "important": [
            {
                "label": "architecture",
                "extractor": extract_architecture,
                "description": "System design and component relationships",
                "tags": "category:architecture, type:design"
            },
            {
                "label": "tool_contracts",
                "extractor": extract_api_contracts,
                "description": "All MCP tool signatures and behaviors",
                "tags": "category:api, type:contracts"
            },
            {
                "label": "configuration",
                "extractor": extract_configuration,
                "description": "Environment variables and settings",
                "tags": "category:config, type:settings"
            }
        ],
        "reference": [
            {
                "label": "utility_functions",
                "extractor": extract_utilities,
                "description": "Helper function signatures",
                "tags": "category:code, type:utilities"
            },
            {
                "label": "test_patterns",
                "extractor": extract_test_patterns,
                "description": "Testing approach and fixtures",
                "tags": "category:testing, type:patterns"
            }
        ]
    },

    "web_app": {
        "always_check": [
            {"label": "project_overview", "extractor": extract_project_overview},
            {"label": "database_schema", "extractor": extract_database_schema},
            {"label": "api_endpoints", "extractor": extract_web_api},
            {"label": "auth_system", "extractor": extract_auth_patterns}
        ],
        "important": [
            {"label": "architecture", "extractor": extract_architecture},
            {"label": "frontend_structure", "extractor": extract_frontend},
            {"label": "configuration", "extractor": extract_configuration}
        ],
        "reference": [
            {"label": "deployment", "extractor": extract_deployment}
        ]
    },

    "cli_tool": {
        "always_check": [
            {"label": "project_overview", "extractor": extract_project_overview},
            {"label": "command_structure", "extractor": extract_cli_commands}
        ],
        "important": [
            {"label": "architecture", "extractor": extract_architecture},
            {"label": "configuration", "extractor": extract_configuration}
        ],
        "reference": [
            {"label": "usage_examples", "extractor": extract_usage_docs}
        ]
    },

    "library": {
        "always_check": [
            {"label": "project_overview", "extractor": extract_project_overview},
            {"label": "public_api", "extractor": extract_public_api}
        ],
        "important": [
            {"label": "architecture", "extractor": extract_architecture},
            {"label": "usage_patterns", "extractor": extract_usage_patterns}
        ],
        "reference": [
            {"label": "installation", "extractor": extract_installation_docs}
        ]
    }
}
```

---

## Sync Algorithm

```python
async def sync_project_memory(
    path: Optional[str] = None,
    confirm: bool = False,
    dry_run: bool = False,
    priorities: Optional[List[str]] = None
) -> str:
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

    # Get structure template
    template = STRUCTURE_TEMPLATES.get(project_type, STRUCTURE_TEMPLATES["library"])

    # ============================================================
    # PHASE 1: Cleanup - Find and remove stale contexts
    # ============================================================
    report.append("\n🧹 PHASE 1: Detecting stale contexts...")

    # Get all existing auto-generated contexts
    existing = await get_all_contexts(filter_auto_generated=True)
    report.append(f"   Found {len(existing)} existing auto-generated contexts")

    # Detect stale contexts
    stale = await detect_stale_contexts(existing, path)

    if stale:
        report.append(f"   Found {len(stale)} stale contexts:")
        for item in stale:
            report.append(f"      ❌ {item['context']['label']}: {item['reason']}")

        if not dry_run and not confirm:
            report.append("\n⚠️  Deletion requires confirmation. Run with confirm=True or dry_run=True")
            return "\n".join(report)

        if not dry_run:
            # Archive and delete stale contexts
            for item in stale:
                await unlock_context(
                    topic=item['context']['label'],
                    version="all",
                    archive=True
                )
            report.append(f"   ✅ Deleted {len(stale)} stale contexts (archived)")
    else:
        report.append("   ✅ No stale contexts found")

    # ============================================================
    # PHASE 2: Extract and Sync - Create/update contexts
    # ============================================================
    report.append("\n📝 PHASE 2: Extracting and syncing contexts...")

    created = []
    updated = []
    skipped = []

    for priority in priorities:
        if priority not in template:
            continue

        for spec in template[priority]:
            label = spec['label']

            # Extract current content using LLM
            try:
                extracted = await spec['extractor'](path)

                # Check if context exists
                existing_ctx = await recall_context(label, version="latest")

                if not existing_ctx or "not found" in existing_ctx.lower():
                    # CREATE new context
                    if not dry_run:
                        await lock_context(
                            content=extracted['content'],
                            topic=label,
                            tags=extracted.get('tags', '') + ',auto_generated',
                            priority=priority
                        )
                    created.append(f"      ✅ Created '{label}' ({priority})")

                elif content_differs(existing_ctx, extracted['content']):
                    # UPDATE existing context
                    if not dry_run:
                        await update_context(
                            topic=label,
                            content=extracted['content'],
                            tags=extracted.get('tags', ''),
                            priority=priority,
                            reason="Auto-sync from sync_project_memory()"
                        )
                    updated.append(f"      ✏️  Updated '{label}' (content changed)")

                else:
                    # SKIP unchanged
                    skipped.append(f"      ⏭️  Skipped '{label}' (unchanged)")

            except Exception as e:
                report.append(f"      ❌ Failed to extract '{label}': {str(e)}")

    # Add results to report
    if created:
        report.append(f"\n   Created {len(created)} new contexts:")
        report.extend(created)

    if updated:
        report.append(f"\n   Updated {len(updated)} contexts:")
        report.extend(updated)

    if skipped:
        report.append(f"\n   Skipped {len(skipped)} unchanged contexts:")
        report.extend(skipped)

    # ============================================================
    # PHASE 3: Validation
    # ============================================================
    report.append("\n✅ PHASE 3: Validation")

    # Count current contexts
    final_contexts = await get_all_contexts(filter_auto_generated=True)
    report.append(f"   Total contexts: {len(final_contexts)}")
    report.append(f"   By priority:")

    for priority in ["always_check", "important", "reference"]:
        count = len([c for c in final_contexts if get_priority(c) == priority])
        report.append(f"      - {priority}: {count}")

    # ============================================================
    # Summary
    # ============================================================
    report.append("\n" + "="*60)
    if dry_run:
        report.append("🔍 DRY RUN - No changes made")
        report.append("   Run with confirm=True to apply these changes")
    else:
        report.append("✨ Memory synchronization complete!")
        report.append(f"   📚 Use explore_context_tree() to view all contexts")
    report.append("="*60)

    return "\n".join(report)
```

---

## Example Output

```
🔍 PHASE 0: Analyzing project structure...
   Project type detected: mcp_server

🧹 PHASE 1: Detecting stale contexts...
   Found 8 existing auto-generated contexts
   Found 2 stale contexts:
      ❌ rest_api_endpoints: API endpoints changed (tools/endpoints modified)
      ❌ old_memory_system: Module old_memory_system no longer exists in codebase
   ✅ Deleted 2 stale contexts (archived)

📝 PHASE 2: Extracting and syncing contexts...
   Created 1 new contexts:
      ✅ Created 'project_overview' (always_check)

   Updated 3 contexts:
      ✏️  Updated 'database_schema' (content changed)
      ✏️  Updated 'tool_contracts' (content changed)
      ✏️  Updated 'critical_rules' (content changed)

   Skipped 4 unchanged contexts:
      ⏭️  Skipped 'architecture' (unchanged)
      ⏭️  Skipped 'session_safety' (unchanged)
      ⏭️  Skipped 'configuration' (unchanged)
      ⏭️  Skipped 'utility_functions' (unchanged)

✅ PHASE 3: Validation
   Total contexts: 8
   By priority:
      - always_check: 4
      - important: 3
      - reference: 1

============================================================
✨ Memory synchronization complete!
   📚 Use explore_context_tree() to view all contexts
============================================================
```

---

## Testing Strategy

### Test 1: First Run (Bootstrap)
```python
def test_first_run_creates_all_contexts():
    # Empty database
    assert len(list_all_contexts()) == 0

    # Run sync
    result = sync_project_memory(confirm=True)

    # Verify contexts created
    contexts = list_all_contexts()
    assert "project_overview" in [c.label for c in contexts]
    assert "database_schema" in [c.label for c in contexts]
    assert "tool_contracts" in [c.label for c in contexts]
```

### Test 2: Stale Detection
```python
def test_detects_stale_contexts():
    # Create context for feature that will be removed
    lock_context(topic="old_feature", content="...", tags="auto_generated")

    # Remove feature from code
    delete_file("old_feature.py")

    # Run sync
    result = sync_project_memory(confirm=True)

    # Verify stale context deleted
    assert "old_feature" not in [c.label for c in list_all_contexts()]

    # Verify archived
    archived = query_archives("old_feature")
    assert len(archived) > 0
```

### Test 3: Update Detection
```python
def test_updates_changed_contexts():
    # Create context
    lock_context(topic="database_schema", content="Old schema", tags="auto_generated")

    # Modify code (add new table)
    add_table_to_code("new_table")

    # Run sync
    result = sync_project_memory(confirm=True)

    # Verify context updated
    schema = recall_context("database_schema")
    assert "new_table" in schema
    assert "v1.1" in schema  # Version incremented
```

---

## Implementation Checklist

- [ ] Create `sync_project_memory()` tool with full docstring
- [ ] Implement `detect_project_type()` function
- [ ] Create LLM extraction prompts (6 prompts)
- [ ] Implement extractor functions:
  - [ ] `extract_project_overview()`
  - [ ] `extract_database_schema()`
  - [ ] `extract_api_contracts()`
  - [ ] `extract_critical_rules()`
  - [ ] `extract_architecture()`
  - [ ] `extract_configuration()`
- [ ] Implement `detect_stale_contexts()`
- [ ] Implement sync algorithm (3 phases)
- [ ] Add metadata marker `auto_generated: true` to all created contexts
- [ ] Create memory structure templates for each project type
- [ ] Write test suite (12 tests minimum)
- [ ] Add dry_run and confirm flags
- [ ] Add progress tracking table
- [ ] Test on claude-dementia project
- [ ] Document in README

---

## Next Steps

1. Create `test_sync_memory.py` with TDD approach
2. Implement core sync algorithm
3. Implement LLM extractors with prompts
4. Test on real project (claude-dementia)
5. Refine prompts based on quality of extracted contexts
6. Add progress tracking for large projects
7. Add resumability if interrupted
