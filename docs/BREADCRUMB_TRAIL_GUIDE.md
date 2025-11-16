# Breadcrumb Trail Guide - Tool Execution Tracking

## Overview

The breadcrumb trail system provides structured logging for MCP tool execution, making it easy to trace tool flow, debug issues, and monitor production behavior.

## Key Features

- **Visual Markers**: Emoji-based breadcrumbs for easy scanning in logs
- **Structured Data**: JSON-formatted extra data for programmatic parsing
- **Easy Grepping**: Consistent "CRUMB-" prefix for filtering logs
- **Automatic Decorator**: `@breadcrumb` decorator logs entry/exit automatically
- **Stage Tracking**: Log validation, DB queries, cache operations, etc.

## Breadcrumb Types

| Marker | Symbol | Usage |
|--------|--------|-------|
| `CRUMB-ENTRY` | 🔵 | Tool execution started |
| `CRUMB-EXIT` | 🟢 | Tool execution completed |
| `CRUMB-ERROR` | 🔴 | Error occurred |
| `CRUMB-VALIDATE` | 🟡 | Input validation |
| `CRUMB-PROJECT` | 🔷 | Project resolution |
| `CRUMB-SESSION` | 🔶 | Session validation |
| `CRUMB-DB` | 🟣 | Database query |
| `CRUMB-UPDATE` | 🟣 | Database update |
| `CRUMB-CACHE-HIT` | 💚 | Cache hit |
| `CRUMB-CACHE-MISS` | 💔 | Cache miss |
| `CRUMB-SUCCESS` | ✅ | Success operation |
| `CRUMB-WARN` | ⚠️ | Warning/non-fatal issue |

## Quick Start

### 1. Basic Usage with Decorator

```python
from tool_breadcrumbs import breadcrumb, log_validation, log_db_query

@breadcrumb  # Automatically logs ENTRY and EXIT
async def search_contexts(arguments: dict):
    """Search locked contexts."""

    # Validation stage
    log_validation("search_contexts", "Checking query length",
                   query_len=len(arguments.get("query", "")))

    # Database stage
    log_db_query("search_contexts", "SELECT * FROM context_locks WHERE...",
                 limit=arguments.get("limit", 10))

    # Return result (EXIT logged automatically)
    return result
```

### 2. Manual Breadcrumbs

```python
from tool_breadcrumbs import log_breadcrumb, BreadcrumbMarkers

async def complex_tool(arguments: dict):
    # Custom breadcrumb
    log_breadcrumb(
        BreadcrumbMarkers.VALIDATE,
        "Validating complex input",
        tool="complex_tool",
        param_count=len(arguments),
        has_project=bool(arguments.get("project"))
    )

    # Another custom breadcrumb
    log_breadcrumb(
        "CUSTOM_STAGE",  # Custom marker
        "Processing special logic",
        tool="complex_tool",
        batch_size=100
    )
```

### 3. Tool Stage Tracking

```python
from tool_breadcrumbs import log_tool_stage

async def get_last_handover(arguments: dict):
    # Project check
    log_tool_stage("PROJECT_CHECK", "get_last_handover",
                   "Resolving project", project="default")

    # Session check
    log_tool_stage("SESSION_CHECK", "get_last_handover",
                   "Checking session", session_id="abc12345")

    # Database query
    log_tool_stage("DB_QUERY", "get_last_handover",
                   "Fetching handover", query="SELECT session_summary...")

    # Success
    log_tool_stage("SUCCESS", "get_last_handover",
                   "Handover retrieved", status="current", hours_ago=0.5)
```

## Monitoring Production Logs

### Watch All Breadcrumbs

```bash
# Run the breadcrumb monitor
chmod +x /tmp/watch_tool_breadcrumbs.sh
/tmp/watch_tool_breadcrumbs.sh
```

### Filter by Tool

```bash
doctl apps logs APP_ID --type run --follow | grep "CRUMB-" | grep "search_contexts"
```

### Filter by Stage

```bash
# Watch only database queries
doctl apps logs APP_ID --type run --follow | grep "CRUMB-DB"

# Watch only errors
doctl apps logs APP_ID --type run --follow | grep "CRUMB-ERROR"

# Watch validation stages
doctl apps logs APP_ID --type run --follow | grep "CRUMB-VALIDATE"
```

### Track Single Tool Execution

```bash
# Watch a complete tool execution flow
doctl apps logs APP_ID --type run --follow | \
    grep -E "CRUMB-(ENTRY|VALIDATE|DB|SUCCESS|EXIT)" | \
    grep "get_last_handover"
```

## Example Tool Flow

Here's what a complete tool execution looks like in logs:

```
13:45:01 🔵 CRUMB-ENTRY | search_contexts | Starting search_contexts | {"args_count": 1, "kwargs_keys": ["query", "limit"]}
13:45:01 🟡 CRUMB-VALIDATE | search_contexts | Checking query length | {"query_len": 25, "tool": "search_contexts"}
13:45:01 🔷 CRUMB-PROJECT | search_contexts | Resolving project: default | {"project": "default", "source": "session"}
13:45:01 🟣 CRUMB-DB | search_contexts | Executing query | {"query_preview": "SELECT id, label, preview FROM context_locks WHERE...", "limit": 10}
13:45:01 ✅ CRUMB-SUCCESS | search_contexts | Query completed | {"rows": 5, "duration_ms": 12.5}
13:45:01 🟢 CRUMB-EXIT | search_contexts | Completed search_contexts | {"duration_ms": 15.3, "result_size": 5, "status": "success"}
```

## Best Practices

### DO ✅

1. **Use the decorator** for automatic entry/exit logging
2. **Log validation** before processing input
3. **Log database operations** with query previews
4. **Log project/session checks** for context
5. **Include structured data** in extra kwargs
6. **Use consistent tool names** across breadcrumbs

```python
@breadcrumb
async def my_tool(arguments: dict):
    log_validation("my_tool", "Checking params", count=len(arguments))
    log_db_query("my_tool", "SELECT...", table="contexts", limit=10)
    log_tool_stage("SUCCESS", "my_tool", "Completed", rows=5)
    return result
```

### DON'T ❌

1. **Don't log sensitive data** (passwords, API keys, full queries)
2. **Don't log massive objects** (keep extra data small)
3. **Don't skip entry/exit** breadcrumbs
4. **Don't use inconsistent tool names**

```python
# BAD - No decorator, no validation logging
async def my_tool(arguments: dict):
    result = query_db("SELECT * FROM secrets WHERE password = ?", [pw])  # BAD!
    log_breadcrumb("DONE", "finished", huge_result=result)  # BAD!
    return result
```

## Integration with Existing Code

### Minimal Integration

Just add the decorator:

```python
# Before
async def lock_context(arguments: dict):
    # existing code
    return result

# After
@breadcrumb
async def lock_context(arguments: dict):
    # existing code (no changes needed!)
    return result
```

### Full Integration

Add stage logging:

```python
@breadcrumb
async def lock_context(arguments: dict):
    # Validation
    log_validation("lock_context", "Checking arguments",
                   has_content=bool(arguments.get("content")),
                   has_topic=bool(arguments.get("topic")))

    # Project resolution
    project = arguments.get("project", "default")
    log_project_check("lock_context", project, source="argument")

    # Database write
    log_db_update("lock_context", "INSERT context_lock",
                  topic=arguments["topic"], version="1.0")

    # Success
    log_tool_stage("SUCCESS", "lock_context", "Context locked",
                   topic=arguments["topic"], version="1.0")

    return result
```

## Grep Patterns Cheat Sheet

```bash
# All breadcrumbs
grep "CRUMB-"

# Tool execution flow (entry to exit)
grep -E "CRUMB-(ENTRY|EXIT)"

# Errors only
grep "CRUMB-ERROR"

# Database operations
grep -E "CRUMB-(DB|UPDATE)"

# Validation and checks
grep -E "CRUMB-(VALIDATE|PROJECT|SESSION)"

# Successful completions
grep -E "CRUMB-(SUCCESS|EXIT)"

# Specific tool
grep "CRUMB-" | grep "search_contexts"

# Tool execution duration
grep "CRUMB-EXIT" | grep "duration_ms"
```

## Performance Monitoring

Extract timing data from breadcrumbs:

```bash
# Average tool execution time
doctl apps logs APP_ID --type run --tail 1000 | \
    grep "CRUMB-EXIT" | \
    grep -oP "duration_ms\":\s*\K[0-9.]+" | \
    awk '{sum+=$1; count++} END {print "Avg:", sum/count, "ms"}'

# Slowest tool calls
doctl apps logs APP_ID --type run --tail 1000 | \
    grep "CRUMB-EXIT" | \
    grep -oP "duration_ms\":\s*\K[0-9.]+" | \
    sort -rn | \
    head -10
```

## Troubleshooting

### Breadcrumbs Not Showing Up?

1. Check that `tool_breadcrumbs.py` is imported
2. Verify structlog is configured correctly
3. Check log level is set to INFO or DEBUG
4. Ensure grep pattern is correct

### Too Many Breadcrumbs?

Filter by tool or stage:

```bash
# Only errors and warnings
grep -E "CRUMB-(ERROR|WARN)"

# Only one tool
grep "CRUMB-" | grep "specific_tool"

# Only database operations
grep "CRUMB-DB"
```

### Missing Context in Breadcrumbs?

Add more structured data:

```python
log_breadcrumb(
    BreadcrumbMarkers.DB_QUERY,
    "Running complex query",
    tool="my_tool",
    table="contexts",
    filters=["priority=important", "project=linkedin"],
    limit=10,
    offset=0
)
```

## Next Steps

1. **Add `@breadcrumb` decorator** to all MCP tools
2. **Add validation logging** at tool entry
3. **Add DB operation logging** for queries/updates
4. **Run monitor script** during testing
5. **Analyze patterns** to optimize tool performance

## Related Documentation

- `tool_breadcrumbs.py` - Implementation
- `/tmp/watch_tool_breadcrumbs.sh` - Monitoring script
- `src/logging_config.py` - Structlog configuration
