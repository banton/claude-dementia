# Project Management Guide

## Overview

Claude Dementia supports multi-project isolation using PostgreSQL schemas. Each project gets its own isolated schema with complete data separation.

**No filesystem required** - works conversationally in Claude Desktop!

## MCP Tools Available

### 1. `create_project(name)`
Create a new project with isolated PostgreSQL schema.

**Conversational Usage:**
```
User: "Create a project called innkeeper"
Claude: [calls create_project(name="innkeeper")]
Claude: "✅ Project 'innkeeper' created successfully!"
```

**Returns:**
- Success message
- Schema name (sanitized version of project name)
- Usage instructions

### 2. `list_projects()`
List all available projects with statistics.

**Conversational Usage:**
```
User: "What projects do I have?"
Claude: [calls list_projects()]
Claude: Shows list with sessions/contexts/memories counts
```

**Returns:**
- List of all projects
- Stats for each: sessions, contexts, memories
- Total project count

### 3. `get_project_info(name)`
Get detailed information about a specific project.

**Conversational Usage:**
```
User: "Show me details about my innkeeper project"
Claude: [calls get_project_info(name="innkeeper")]
Claude: Shows stats, recent sessions, recent contexts
```

**Returns:**
- Project stats (sessions, contexts, memories)
- Recent sessions (last 5)
- Recent contexts (last 10)

### 4. `delete_project(name, confirm=False)`
Delete a project and all its data (DESTRUCTIVE).

**Conversational Usage:**
```
User: "Delete my test project"
Claude: [calls delete_project(name="test", confirm=False)]
Claude: "⚠️ This will permanently delete ALL data. Confirm?"
User: "Yes, delete it"
Claude: [calls delete_project(name="test", confirm=True)]
Claude: "✅ Project deleted"
```

**Security:**
- Requires explicit `confirm=True` to prevent accidents
- Shows warning message first
- Permanently deletes ALL data in that project

## Typical Workflows

### First Time Setup
```
User: "I want to track context for my innkeeper project"
Claude: [calls create_project(name="innkeeper")]
Claude: "✅ Project created! Use 'innkeeper' when working on that project"
```

### Daily Usage
```
User: "Let's work on innkeeper"
Claude: [will call wake_up(project="innkeeper") in future]

User: "Lock this API spec"
Claude: [will call lock_context(..., project="innkeeper") in future]
```

### Switching Projects
```
User: "Switch to my linkedin project"
Claude: [calls list_projects() to check if it exists]
Claude: "Project 'linkedin' doesn't exist yet. Should I create it?"
User: "Yes"
Claude: [calls create_project(name="linkedin")]
```

### Cleanup
```
User: "I'm done with the test project, delete it"
Claude: [calls delete_project(name="test")]
Claude: Shows warning and asks for confirmation
```

## Schema Naming

Project names are automatically sanitized for PostgreSQL:
- Converted to lowercase
- Special characters replaced with underscores
- Limited to 32 characters

Examples:
- `"innkeeper"` → schema: `innkeeper`
- `"LinkedIn Posts"` → schema: `linkedin_posts`
- `"My-Cool-Project_2024"` → schema: `my_cool_project_2024`

## Current State

**Implemented:**
- ✅ Create, List, Info, Delete projects
- ✅ Isolated PostgreSQL schemas per project
- ✅ Conversational interface (no filesystem needed)
- ✅ Safety confirmations for destructive operations

**TODO (future iteration):**
- Add `project` parameter to all existing MCP tools (wake_up, lock_context, etc.)
- Holistic review of entire toolset
- Project switching/context management
- Migration tools for moving data between projects

## Technical Details

**PostgreSQL Schema Isolation:**
- Each project = one PostgreSQL schema
- Schema contains all tables: sessions, context_locks, memory_entries, etc.
- Complete data isolation between projects
- No cross-project queries possible

**Connection Pooling:**
- One connection pool per schema
- Automatic cleanup
- Thread-safe operations

**Database:**
- Managed PostgreSQL (Neon)
- DATABASE_URL configured in .env
- Multi-tenant architecture

## For Developers

**Testing:**
```bash
# Test project management tools
python3 -c "
import asyncio
import claude_mcp_hybrid

async def test():
    result = await claude_mcp_hybrid.list_projects()
    print(result)

asyncio.run(test())
"
```

**Existing Projects:**
You may see old test schemas with prefixes like:
- `user_*` - Old multi-user architecture (deprecated)
- `local_*` - Old hash-based naming (deprecated)

These can be safely deleted using `delete_project()`.
