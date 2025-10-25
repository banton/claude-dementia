# Multi-Project Isolation Fix

## Problem

When using Claude Dementia MCP server with Claude Desktop, switching between projects caused memory contamination - contexts from one project would appear in another project.

### Example Bug

1. User opens `~/Sites/innkeeper-claude` (screenplay project)
2. Locks contexts: `act1-ch1-sc1-opening-staff-problems v1.0`, etc.
3. Switches to `~/Sites/linkedin` project in Claude Desktop
4. Runs `explore_context_tree()`
5. **BUG**: Sees screenplay contexts instead of LinkedIn contexts

### Root Cause

MCP servers are **long-running processes** that don't reload when Claude Desktop switches projects.

```python
# Module load time (ONCE when server starts)
PROJECT_ROOT = os.getcwd()  # = ~/Sites/innkeeper-claude
PROJECT_NAME = "innkeeper-claude"

# Later, in get_current_session_id()
def get_current_session_id():
    # Uses STALE values from first project!
    project_fingerprint = md5(f"{PROJECT_ROOT}:{PROJECT_NAME}")
    # fingerprint: "abc123de" (innkeeper-claude)

    # Finds existing session for innkeeper-claude
    # LinkedIn project reuses innkeeper's session!
    return "innk_abc123de"
```

When user switches to LinkedIn project:
- MCP server process keeps running
- `PROJECT_ROOT` still = `~/Sites/innkeeper-claude` (never updated)
- `get_current_session_id()` returns innkeeper session
- LinkedIn project sees innkeeper contexts

---

## Solution

Make project detection **dynamic** - recalculate on every tool call:

```python
def get_project_root() -> str:
    """
    Dynamically get current project root.
    Returns CURRENT os.getcwd(), not cached value.
    """
    if os.environ.get('CLAUDE_PROJECT_DIR'):
        return os.environ['CLAUDE_PROJECT_DIR']
    return os.getcwd()  # ← Always returns CURRENT directory

def get_project_name() -> str:
    """Get current project name from dynamic project root."""
    return os.path.basename(get_project_root())

def get_current_session_id() -> str:
    # Recalculate on EVERY call
    current_project_root = get_project_root()      # ← Dynamic!
    current_project_name = get_project_name()      # ← Dynamic!

    # Fingerprint based on CURRENT project
    project_fingerprint = md5(f"{current_project_root}:{current_project_name}")

    # Finds/creates session for CURRENT project
    return session_for_this_project
```

### Key Insight

`os.getcwd()` **DOES update** when Claude Desktop switches projects, even though the MCP server process doesn't restart. We leverage this to detect project switches.

---

## How It Works

### Database Structure

**Shared database:** `~/.claude-dementia/dementia-{hash}.db`
- Single database shared across all projects (for performance)
- Sessions table has `project_fingerprint` column

**Sessions table:**
```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    started_at REAL,
    last_active REAL,
    project_fingerprint TEXT,  -- ← Isolation key
    project_path TEXT,
    project_name TEXT
);
```

**Context locks table:**
```sql
CREATE TABLE context_locks (
    id INTEGER PRIMARY KEY,
    session_id TEXT,  -- ← FK to sessions
    label TEXT,
    version TEXT,
    content TEXT,
    -- ...
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);
```

### Project Switching Flow

**Initial state (innkeeper-claude):**
```
os.getcwd() = ~/Sites/innkeeper-claude
get_project_root() = ~/Sites/innkeeper-claude
project_fingerprint = md5("~/Sites/innkeeper-claude:innkeeper-claude") = "abc123de"
session_id = "innk_12345678"

contexts: [act1-ch1-sc1, act1-ch2-sc2, ...]
```

**User switches to LinkedIn project:**
```
# MCP server still running, but os.getcwd() updates!
os.getcwd() = ~/Sites/linkedin  # ← Changed!

# Next tool call:
wake_up() calls:
  get_current_session_id() calls:
    current_project_root = get_project_root()  # Returns ~/Sites/linkedin
    current_project_name = get_project_name()  # Returns "linkedin"
    project_fingerprint = md5("~/Sites/linkedin:linkedin") = "def456ab"  # ← Different!

    # Searches for session with fingerprint "def456ab"
    # Not found → creates NEW session
    session_id = "link_87654321"  # ← New session!

# Query contexts:
SELECT * FROM context_locks WHERE session_id = "link_87654321"
# Returns: []  (no contexts yet for LinkedIn project)
```

---

## Testing

### Verify Fix Works

1. **Start with project A:**
   ```bash
   cd ~/Sites/innkeeper-claude
   # Open in Claude Desktop
   ```

2. **Create contexts in project A:**
   ```python
   dementia:lock_context(
       content="Project A specific context",
       topic="project_a_rule",
       priority="important"
   )

   dementia:explore_context_tree(flat=True)
   # Shows: project_a_rule v1.0
   ```

3. **Switch to project B:**
   ```bash
   cd ~/Sites/linkedin
   # Switch project in Claude Desktop
   ```

4. **Verify isolation:**
   ```python
   dementia:wake_up()
   # Check: project_name should be "linkedin"
   # Check: session_id should be different (link_...)

   dementia:explore_context_tree(flat=True)
   # Should show: No contexts (or only LinkedIn contexts)
   # Should NOT show: project_a_rule ✅
   ```

5. **Create contexts in project B:**
   ```python
   dementia:lock_context(
       content="Project B specific context",
       topic="linkedin_analysis",
       priority="important"
   )

   dementia:explore_context_tree(flat=True)
   # Shows: linkedin_analysis v1.0
   # Does NOT show: project_a_rule ✅
   ```

6. **Switch back to project A:**
   ```bash
   cd ~/Sites/innkeeper-claude
   # Switch back in Claude Desktop
   ```

7. **Verify contexts restored:**
   ```python
   dementia:explore_context_tree(flat=True)
   # Shows: project_a_rule v1.0 ✅
   # Does NOT show: linkedin_analysis ✅
   ```

### Debug Project Detection

If isolation isn't working, check these:

```python
# Add to any tool:
import os
print(f"os.getcwd() = {os.getcwd()}")
print(f"get_project_root() = {get_project_root()}")
print(f"get_project_name() = {get_project_name()}")

# Check session:
dementia:wake_up()
# Look at session.id and session.project_root
```

---

## Technical Details

### Why Dynamic Detection Works

**Key fact:** When Claude Desktop switches projects, it changes the working directory of the MCP server process via the MCP protocol.

Even though the Python process doesn't restart:
- `os.getcwd()` reflects the current project directory
- `os.environ.get('CLAUDE_PROJECT_DIR')` may be updated by Claude Desktop

### Why Not Just Use Separate Databases?

We considered creating separate database files per project:
- `~/Sites/innkeeper-claude/.claude-memory.db`
- `~/Sites/linkedin/.claude-memory.db`

**Problems with separate databases:**
1. No cross-project search capability
2. Duplicate system contexts (style guides, etc.)
3. Harder to manage database upgrades
4. Lost data if project moves
5. Higher disk usage

**Benefits of shared database with isolation:**
1. Single source of truth
2. Can search across projects if needed (future feature)
3. Shared system contexts
4. Survives project renames/moves
5. Easier upgrades

### Session Lifecycle

**First tool call in new project:**
1. `get_project_root()` returns current directory
2. Calculate `project_fingerprint` = md5(path:name)
3. Query: `SELECT * FROM sessions WHERE project_fingerprint = ?`
4. If not found: Create new session
5. If found: Reuse existing session, update last_active

**Subsequent tool calls:**
1. Same fingerprint → same session
2. All contexts filtered by session_id
3. Perfect isolation

---

## Migration Notes

### Backward Compatibility

Old global variables still exist for compatibility:
```python
# DEPRECATED: Don't use directly
PROJECT_ROOT = os.getcwd()  # Set at module load
PROJECT_NAME = os.path.basename(PROJECT_ROOT)

# ALWAYS USE THESE INSTEAD:
get_project_root()   # Dynamic
get_project_name()   # Dynamic
```

### Existing Sessions

Sessions created before this fix:
- May have `project_fingerprint = NULL`
- Will be migrated on first tool call:
  ```sql
  ALTER TABLE sessions ADD COLUMN project_fingerprint TEXT;
  ALTER TABLE sessions ADD COLUMN project_path TEXT;
  ALTER TABLE sessions ADD COLUMN project_name TEXT;
  ```
- Fingerprint calculated from current directory
- Contexts remain accessible

---

## Future Enhancements

### Cross-Project Search

With isolated sessions, we can now add safe cross-project features:

```python
# Search contexts across all projects
dementia:search_all_projects(query="API authentication")
# Returns: [
#   {"project": "innkeeper-claude", "topic": "auth_api", ...},
#   {"project": "linkedin", "topic": "api_design", ...}
# ]
```

### Project Templates

```python
# Copy contexts from one project to another
dementia:copy_contexts(
    from_project="template-api",
    to_project="new-project",
    topics=["api_style", "testing_rules"]
)
```

### Session History

```python
# View all projects with active sessions
dementia:list_projects()
# Returns: [
#   {"name": "innkeeper-claude", "contexts": 15, "last_active": "2h ago"},
#   {"name": "linkedin", "contexts": 8, "last_active": "5m ago"}
# ]
```

---

## Summary

**Before fix:**
- ❌ Single session for all projects
- ❌ Contexts leaked between projects
- ❌ Confusion about which project you're in

**After fix:**
- ✅ Separate session per project (automatic)
- ✅ Perfect context isolation
- ✅ Clear project identification in wake_up()
- ✅ Contexts restore when returning to project

**Implementation:**
- Dynamic `get_project_root()` function
- Session keyed by `project_fingerprint`
- Contexts filtered by `session_id`
- Shared database with isolation

**Testing:**
- Switch between projects in Claude Desktop
- Verify contexts stay separated
- Confirm session IDs are different

---

*Last updated: 2024-10-25 (v3.2 - Multi-Project Isolation)*
