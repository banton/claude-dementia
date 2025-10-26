# Multi-Project Isolation Solutions - Research Report

**Date:** 2025-10-26
**Issue:** Claude Desktop MCP server cannot detect current project directory
**Research Focus:** Per-project configuration options and database solutions

---

## Problem Analysis

### Current Broken Assumption

From MULTI_PROJECT_ISOLATION.md line 75:
> `os.getcwd()` **DOES update** when Claude Desktop switches projects, even though the MCP server process doesn't restart.

**Reality:** This assumption is **FALSE**

**Evidence from Innkeeper Project:**
```json
{
  "session": {
    "project_root": "/",           // ← Should be ~/Sites/innkeeper-claude
    "database": "6666cd76.db",     // ← Root database (all 94 mixed contexts)
    "project_name": "Claude Desktop"  // ← Generic fallback
  }
}
```

### Root Cause

1. **MCP servers are long-running processes** that start at system/application launch
2. **Working directory remains fixed** at startup location (typically `/`)
3. **Claude Desktop does not:**
   - Update MCP server working directory when switching projects
   - Set `CLAUDE_PROJECT_DIR` environment variable
   - Send project context through MCP protocol (as of 2025)

### Why Dynamic Detection Failed

Our implementation relies on:
```python
def get_project_root() -> str:
    if os.environ.get('CLAUDE_PROJECT_DIR'):  # Never set
        return os.environ['CLAUDE_PROJECT_DIR']
    return os.getcwd()  # Always returns "/" in Claude Desktop
```

**Result:** All projects use root database (`6666cd76.db`) with 94 mixed contexts.

---

## Solution 1: Multiple MCP Server Instances (RECOMMENDED)

### Overview

Configure separate MCP server instances for each project in `claude_desktop_config.json`, each with its own database configuration.

### Implementation

**File:** `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)

```json
{
  "mcpServers": {
    "dementia-innkeeper": {
      "command": "python3",
      "args": ["/Users/banton/Sites/claude-dementia/claude_mcp_hybrid.py"],
      "env": {
        "DEMENTIA_PROJECT_PATH": "/Users/banton/Sites/innkeeper-claude",
        "DEMENTIA_PROJECT_NAME": "innkeeper-claude",
        "DEMENTIA_DB_PATH": "/Users/banton/.claude-dementia/innkeeper.db"
      }
    },
    "dementia-linkedin": {
      "command": "python3",
      "args": ["/Users/banton/Sites/claude-dementia/claude_mcp_hybrid.py"],
      "env": {
        "DEMENTIA_PROJECT_PATH": "/Users/banton/Sites/linkedin",
        "DEMENTIA_PROJECT_NAME": "linkedin",
        "DEMENTIA_DB_PATH": "/Users/banton/.claude-dementia/linkedin.db"
      }
    },
    "dementia-general": {
      "command": "python3",
      "args": ["/Users/banton/Sites/claude-dementia/claude_mcp_hybrid.py"],
      "env": {
        "DEMENTIA_PROJECT_PATH": "/Users/banton",
        "DEMENTIA_PROJECT_NAME": "general",
        "DEMENTIA_DB_PATH": "/Users/banton/.claude-dementia/general.db"
      }
    }
  }
}
```

### Code Changes Required

**Update `claude_mcp_hybrid.py`:**

```python
def get_project_root() -> str:
    """
    Get project root from explicit environment configuration.
    Falls back to working directory if not set.
    """
    # Priority 1: Explicit project path from MCP config
    if os.environ.get('DEMENTIA_PROJECT_PATH'):
        return os.environ['DEMENTIA_PROJECT_PATH']

    # Priority 2: Claude-provided environment variable
    if os.environ.get('CLAUDE_PROJECT_DIR'):
        return os.environ['CLAUDE_PROJECT_DIR']

    # Priority 3: Current working directory (legacy)
    return os.getcwd()

def get_project_name() -> str:
    """Get project name from explicit environment configuration."""
    # Priority 1: Explicit project name from MCP config
    if os.environ.get('DEMENTIA_PROJECT_NAME'):
        return os.environ['DEMENTIA_PROJECT_NAME']

    # Priority 2: Derive from project path
    return os.path.basename(get_project_root()) or 'unknown'

def get_database_path() -> str:
    """
    Get database path from explicit environment configuration.
    Falls back to hash-based path if not set.
    """
    # Priority 1: Explicit database path from MCP config
    if os.environ.get('DEMENTIA_DB_PATH'):
        return os.environ['DEMENTIA_DB_PATH']

    # Priority 2: Calculate from project root (existing logic)
    cwd = get_project_root()
    context_hash = hashlib.md5(cwd.encode()).hexdigest()[:8]
    cache_dir = os.path.expanduser('~/.claude-dementia')
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f'{context_hash}.db')
```

### User Experience

**In Claude Desktop:**

1. User opens Innkeeper project
2. Sees MCP servers: `dementia-innkeeper`, `dementia-linkedin`, `dementia-general`
3. Uses `dementia-innkeeper:wake_up()` for Innkeeper project
4. Uses `dementia-linkedin:wake_up()` for LinkedIn project

**Pros:**
- ✅ Explicit, predictable behavior
- ✅ No ambiguity about which database is used
- ✅ Works with current Claude Desktop
- ✅ Each project has isolated contexts
- ✅ Easy to add new projects
- ✅ No code changes to MCP protocol needed

**Cons:**
- ⚠️ User must manually select correct server for current project
- ⚠️ More verbose tool names (e.g., `dementia-innkeeper:lock_context`)
- ⚠️ Requires editing global config file per project
- ⚠️ Risk of using wrong server instance

### Known Issue (2025)

**Environment Variables Bug:** There's a reported issue (GitHub #1254) where environment variables from the `env` section may not be passed correctly to MCP servers. This may require testing or workarounds.

---

## Solution 2: Project-Scoped Configuration (Claude Code Only)

### Overview

Use `.mcp.json` files in each project directory for automatic per-project configuration.

### Implementation

**File:** `~/Sites/innkeeper-claude/.mcp.json`

```json
{
  "mcpServers": {
    "dementia": {
      "command": "python3",
      "args": ["/Users/banton/Sites/claude-dementia/claude_mcp_hybrid.py"],
      "env": {
        "DEMENTIA_PROJECT_PATH": "/Users/banton/Sites/innkeeper-claude",
        "DEMENTIA_PROJECT_NAME": "innkeeper-claude",
        "DEMENTIA_DB_PATH": "/Users/banton/.claude-dementia/innkeeper.db"
      }
    }
  }
}
```

**File:** `~/Sites/linkedin/.mcp.json`

```json
{
  "mcpServers": {
    "dementia": {
      "command": "python3",
      "args": ["/Users/banton/Sites/claude-dementia/claude_mcp_hybrid.py"],
      "env": {
        "DEMENTIA_PROJECT_PATH": "/Users/banton/Sites/linkedin",
        "DEMENTIA_PROJECT_NAME": "linkedin",
        "DEMENTIA_DB_PATH": "/Users/banton/.claude-dementia/linkedin.db"
      }
    }
  }
}
```

### User Experience

**In Claude Code (CLI):**

1. User navigates to project: `cd ~/Sites/innkeeper-claude`
2. Runs: `claude code`
3. MCP server automatically configured from `.mcp.json`
4. Tools appear as: `dementia:wake_up()`, `dementia:lock_context()`

**Pros:**
- ✅ Automatic project detection
- ✅ Configuration is version-controlled with project
- ✅ Team can share MCP configuration
- ✅ Simple tool names (no project prefix needed)
- ✅ Scales to many projects

**Cons:**
- ❌ **Only works with Claude Code (CLI), not Claude Desktop**
- ⚠️ Requires `.mcp.json` in every project
- ⚠️ User approval required first time per project

### Compatibility

- ✅ **Claude Code (CLI)**: Full support
- ❌ **Claude Desktop (GUI)**: Not supported (as of 2025)

---

## Solution 3: PostgreSQL Database (EXPLORATORY)

### Overview

Replace SQLite with centralized PostgreSQL database with schema-based isolation.

### Architecture

**Database Structure:**
```sql
-- One database, multiple schemas
CREATE DATABASE claude_dementia;

-- Schema per project
CREATE SCHEMA innkeeper_claude;
CREATE SCHEMA linkedin;
CREATE SCHEMA general;

-- Tables in each schema
CREATE TABLE innkeeper_claude.sessions (...);
CREATE TABLE innkeeper_claude.context_locks (...);

CREATE TABLE linkedin.sessions (...);
CREATE TABLE linkedin.context_locks (...);
```

**Connection Configuration:**

```python
# Per-project MCP server instance
env = {
    "DEMENTIA_DB_URL": "postgresql://user:pass@localhost/claude_dementia",
    "DEMENTIA_SCHEMA": "innkeeper_claude",  # or "linkedin"
    "DEMENTIA_PROJECT_NAME": "innkeeper-claude"
}
```

**Code Changes:**

```python
import psycopg2

def get_db():
    """Get PostgreSQL connection with schema isolation."""
    db_url = os.environ.get('DEMENTIA_DB_URL')
    schema = os.environ.get('DEMENTIA_SCHEMA', 'public')

    conn = psycopg2.connect(db_url)

    # Set search_path for schema isolation
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema}, public")

    return conn
```

### Pros

- ✅ **True multi-user support** - Multiple team members can share contexts
- ✅ **Concurrent access** - PostgreSQL's MVCC handles multiple connections
- ✅ **Network access** - Access contexts from any machine
- ✅ **Better query performance** - For complex queries across many contexts
- ✅ **Schema isolation** - Strong project boundaries
- ✅ **Backup/restore** - Standard PostgreSQL tools
- ✅ **Replication** - Can replicate to other machines
- ✅ **No database lock errors** - PostgreSQL designed for concurrency

### Cons

- ❌ **Requires PostgreSQL installation** - More complex setup
- ❌ **Requires network/server** - Can't work offline without local Postgres
- ❌ **Connection management** - More complex than SQLite
- ❌ **Credentials management** - Need to secure database passwords
- ❌ **Migration complexity** - Need to migrate existing SQLite data
- ❌ **Overkill for single user** - SQLite sufficient for most use cases
- ❌ **Latency** - Network roundtrips vs local file access

### When to Use PostgreSQL

**Good fit if:**
- Multiple team members need shared contexts
- Working across multiple machines
- Need concurrent access from multiple clients
- Building multi-user Claude application
- Need advanced query capabilities
- Have PostgreSQL infrastructure already

**Bad fit if:**
- Single user, single machine
- Want offline-first operation
- Prefer simplicity over features
- Don't want to manage database server

### Managed PostgreSQL Options (2025)

- **Supabase** - Free tier with 500MB, PostgreSQL + REST API
- **Neon** - Serverless PostgreSQL, free tier with 0.5GB
- **Railway** - $5/month for 1GB PostgreSQL
- **DigitalOcean** - Managed PostgreSQL from $15/month
- **AWS RDS** - From $0.017/hour (~$12/month)

---

## Solution 4: Hybrid Approach (FUTURE)

### Overview

Combine local SQLite with optional PostgreSQL sync for teams.

### Architecture

**Local-first:**
- Each project uses local SQLite database
- Fast, offline-capable, no dependencies

**Optional sync:**
- Background sync to PostgreSQL for sharing
- Conflict resolution for concurrent edits
- Selective sync (e.g., only "important" contexts)

**Benefits:**
- ✅ Works offline with SQLite
- ✅ Share contexts when online
- ✅ Team collaboration when needed
- ✅ Performance of local database
- ✅ Flexibility of cloud database

**Complexity:**
- ⚠️ Requires sync logic
- ⚠️ Need conflict resolution
- ⚠️ Two database schemas to maintain

---

## Comparison Matrix

| Solution | Complexity | User Experience | Multi-User | Offline | Current Support |
|----------|-----------|-----------------|------------|---------|----------------|
| **Multiple MCP Instances** | Low | Manual selection | No | Yes | ✅ Works now |
| **Project .mcp.json** | Low | Automatic | No | Yes | ⚠️ CLI only |
| **PostgreSQL** | High | Automatic | Yes | No* | ⚠️ Requires migration |
| **Hybrid SQLite+PG** | Very High | Automatic | Yes | Yes | ❌ Future work |

\* PostgreSQL can work offline with local installation

---

## Recommendations

### Immediate Solution (Now)

**Use Multiple MCP Server Instances (Solution 1)**

**Implementation Steps:**

1. Update `claude_mcp_hybrid.py` to read `DEMENTIA_PROJECT_PATH`, `DEMENTIA_PROJECT_NAME`, `DEMENTIA_DB_PATH` from environment variables

2. Create `claude_desktop_config.json` with instances:
   - `dementia-innkeeper`
   - `dementia-linkedin`
   - `dementia-general`

3. Update validation to check environment variables are set

4. Document usage pattern for users

**Pros:**
- Can implement today
- Works with current Claude Desktop
- Clear, explicit project isolation
- No breaking changes for existing users

**Cons:**
- Manual server selection required
- Verbose tool names

### Medium-Term Solution (When Available)

**Use Project .mcp.json (Solution 2)**

When Claude Desktop adds support for project-scoped configuration (currently only in Claude Code), migrate to `.mcp.json` files in each project.

**Migration Path:**
1. Keep multiple instance configuration
2. Add `.mcp.json` files to projects
3. When Claude Desktop supports it, users can switch
4. Remove multiple instances from global config

### Long-Term Consideration (If Multi-User Needed)

**Evaluate PostgreSQL (Solution 3)**

If team collaboration becomes a priority:
- Test with managed PostgreSQL (Supabase/Neon free tier)
- Build migration tool from SQLite → PostgreSQL
- Implement as optional feature (environment variable flag)
- Keep SQLite as default for single users

---

## Implementation Plan

### Phase 1: Environment Variable Support (Immediate)

**Changes to `claude_mcp_hybrid.py`:**

```python
# Priority-based configuration
def get_project_root() -> str:
    return (
        os.environ.get('DEMENTIA_PROJECT_PATH') or
        os.environ.get('CLAUDE_PROJECT_DIR') or
        os.getcwd()
    )

def get_project_name() -> str:
    return (
        os.environ.get('DEMENTIA_PROJECT_NAME') or
        os.path.basename(get_project_root()) or
        'unknown'
    )

def get_database_path() -> str:
    # Explicit path takes priority
    if os.environ.get('DEMENTIA_DB_PATH'):
        return os.environ['DEMENTIA_DB_PATH']

    # Fall back to hash-based path
    cwd = get_project_root()
    context_hash = hashlib.md5(cwd.encode()).hexdigest()[:8]
    cache_dir = os.path.expanduser('~/.claude-dementia')
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f'{context_hash}.db')
```

**New validation checks:**

```python
def validate_database_isolation(conn):
    # ... existing checks ...

    # Check environment configuration
    validation_report["checks"]["env_configuration"] = {
        "passed": all([
            os.environ.get('DEMENTIA_PROJECT_PATH'),
            os.environ.get('DEMENTIA_PROJECT_NAME'),
            os.environ.get('DEMENTIA_DB_PATH')
        ]),
        "project_path_set": bool(os.environ.get('DEMENTIA_PROJECT_PATH')),
        "project_name_set": bool(os.environ.get('DEMENTIA_PROJECT_NAME')),
        "db_path_set": bool(os.environ.get('DEMENTIA_DB_PATH')),
        "level": "important"
    }
```

### Phase 2: User Configuration (Immediate)

**Create setup script:** `setup_multi_project.sh`

```bash
#!/bin/bash
# Generate claude_desktop_config.json entries for user's projects

echo "Setting up Claude Desktop MCP instances..."
echo ""
echo "Enter project details:"
read -p "Project name (e.g., innkeeper-claude): " name
read -p "Project path (e.g., ~/Sites/innkeeper-claude): " path

# Expand tilde
path="${path/#\~/$HOME}"

# Generate database path
db_name=$(echo "$name" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
db_path="$HOME/.claude-dementia/${db_name}.db"

cat <<EOF

Add this to ~/Library/Application Support/Claude/claude_desktop_config.json:

  "dementia-${name}": {
    "command": "python3",
    "args": ["$(pwd)/claude_mcp_hybrid.py"],
    "env": {
      "DEMENTIA_PROJECT_PATH": "${path}",
      "DEMENTIA_PROJECT_NAME": "${name}",
      "DEMENTIA_DB_PATH": "${db_path}"
    }
  }

EOF
```

### Phase 3: Documentation (Immediate)

**Update MULTI_PROJECT_ISOLATION.md:**

1. Add "Configuration Required" section
2. Explain environment variable approach
3. Provide setup script
4. Document validation checks
5. Add troubleshooting section

**Create PER_PROJECT_SETUP.md:**

1. Step-by-step guide for users
2. Example configurations
3. Common pitfalls
4. Migration from hash-based to explicit configuration

### Phase 4: Migration Tool (Optional)

**Create migration script for existing users:**

```python
# migrate_to_explicit_config.py
# Scans ~/.claude-dementia/ for existing databases
# Identifies which projects they belong to
# Generates config entries
```

---

## Testing Strategy

### Test 1: Environment Variable Configuration

```bash
# Test explicit configuration
export DEMENTIA_PROJECT_PATH="/Users/banton/Sites/innkeeper-claude"
export DEMENTIA_PROJECT_NAME="innkeeper-claude"
export DEMENTIA_DB_PATH="/Users/banton/.claude-dementia/innkeeper.db"

python3 -c "
from claude_mcp_hybrid import get_project_root, get_project_name, get_database_path
print('Project Root:', get_project_root())
print('Project Name:', get_project_name())
print('Database Path:', get_database_path())
"
```

**Expected:**
```
Project Root: /Users/banton/Sites/innkeeper-claude
Project Name: innkeeper-claude
Database Path: /Users/banton/.claude-dementia/innkeeper.db
```

### Test 2: Multiple Instance Isolation

1. Configure two MCP instances in Claude Desktop
2. Lock context with `dementia-innkeeper:lock_context()`
3. Verify it doesn't appear in `dementia-linkedin:explore_context_tree()`
4. Confirm database validation passes for both instances

### Test 3: Fallback Behavior

```bash
# Test fallback to hash-based path
unset DEMENTIA_PROJECT_PATH
unset DEMENTIA_PROJECT_NAME
unset DEMENTIA_DB_PATH

cd /Users/banton/Sites/linkedin
python3 -c "
from claude_mcp_hybrid import get_database_path
print('Database Path:', get_database_path())
"
```

**Expected:**
```
Database Path: /Users/banton/.claude-dementia/832c1a38.db
```

---

## Risk Assessment

### Risk 1: Environment Variable Bug

**Issue:** GitHub #1254 reports environment variables may not be passed correctly to MCP servers (May 2025).

**Mitigation:**
- Test thoroughly in Claude Desktop
- Provide diagnostic tool to verify environment variables
- Document workarounds if bug persists
- Consider command-line argument alternative:
  ```json
  "args": [
    "claude_mcp_hybrid.py",
    "--project-path", "/Users/banton/Sites/innkeeper-claude",
    "--project-name", "innkeeper-claude",
    "--db-path", "/Users/banton/.claude-dementia/innkeeper.db"
  ]
  ```

### Risk 2: User Configuration Complexity

**Issue:** Users need to manually edit JSON configuration file.

**Mitigation:**
- Provide setup script
- Create configuration generator tool
- Clear documentation with examples
- Video tutorial

### Risk 3: Tool Selection Confusion

**Issue:** User might use wrong MCP instance for current project.

**Mitigation:**
- Tool names include project identifier
- wake_up() output shows project details prominently
- Validation errors if using wrong instance
- Consider naming convention: `dementia-{PROJECT}:tool()`

---

## Open Questions

1. **Has Anthropic announced plans for automatic project detection in MCP?**
   - Need to check roadmap/GitHub issues

2. **Is there a way to detect current Claude Desktop project via MCP protocol?**
   - May need to file feature request

3. **Should we support PostgreSQL as an option?**
   - Depends on user needs (single vs multi-user)

4. **Should tool names include project prefix automatically?**
   - e.g., `dementia-innkeeper:lock_context` vs `lock_context`

5. **How to handle legacy databases (6666cd76.db with 94 mixed contexts)?**
   - Migration script to split into per-project databases?
   - Archive and start fresh?

---

## Conclusion

**Recommended Solution:** Multiple MCP Server Instances (Solution 1)

**Rationale:**
- Works with current Claude Desktop
- Explicit and predictable
- No breaking changes
- Can migrate to project-scoped config when available

**Implementation Effort:** Low (2-4 hours)
- Update environment variable priority
- Create setup script
- Update documentation
- Test with multiple projects

**Next Steps:**
1. Implement environment variable support
2. Test with Innkeeper and LinkedIn projects
3. Document configuration process
4. Gather user feedback
5. Consider PostgreSQL if multi-user needs arise

---

*Research completed: 2025-10-26*
*Implementation status: Ready to proceed*
