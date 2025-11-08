# Continuous Context Gathering with Embeddings

**Purpose**: Replace `wake_up()`/`sleep()` with continuous, automatic context gathering using embeddings.

**Date**: 2025-11-07
**Revision**: Based on plan to deprecate explicit session lifecycle tools

---

## 🎯 Core Philosophy

**Old Approach** (Deprecated):
```
Session Start → wake_up() → Work → sleep() → Session End
                ↓                     ↓
         Load handover         Create handover
```

**New Approach** (Continuous):
```
Work → Work → Work → Work → Work...
  ↓      ↓      ↓      ↓      ↓
Embed  Embed  Embed  Embed  Embed
  ↓      ↓      ↓      ↓      ↓
Build context automatically, retrieve on-demand
```

**Users don't think in "sessions" - they just work.**

---

## 🏗️ Architecture

### Continuous Context Capture

```
┌─────────────────────────────────────────────────────────────┐
│                    EVERY TOOL CALL                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  User: lock_context("API spec", "api_v1")                    │
│    ↓                                                          │
│  1. Execute tool (current behavior)                          │
│  2. Extract action semantics (NEW)                           │
│     - What: "Locked API specification"                       │
│     - Why: Implicit from content                             │
│     - Context: Current file, current task                    │
│  3. Generate embedding (NEW)                                 │
│     - From: Action + content preview                         │
│     - Model: nomic-embed-text (local, free)                  │
│  4. Store activity record (NEW)                              │
│     - Table: session_activities                              │
│     - Includes: tool, action, embedding, timestamp           │
│  5. Return result (current behavior)                         │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│                    CONTEXT RETRIEVAL                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Automatic triggers:                                          │
│  • New session detected → Load relevant past work            │
│  • Project switched → Load project-specific context          │
│  • Similar work detected → Show related activities           │
│  • User asks → Semantic search through history               │
│                                                               │
│  Manual triggers (optional):                                  │
│  • show_context() - Show current work narrative              │
│  • search_history("authentication") - Find past work         │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🗄️ Database Schema

### New Table: `session_activities`

Track every significant action with semantic embedding:

```sql
CREATE TABLE IF NOT EXISTS session_activities (
    id SERIAL PRIMARY KEY,

    -- Session & Project
    session_id TEXT NOT NULL,
    project_name TEXT NOT NULL,

    -- What happened
    tool_name TEXT NOT NULL,              -- lock_context, edit_file, etc.
    action_type TEXT NOT NULL,            -- create, update, delete, read
    action_summary TEXT NOT NULL,         -- "Locked API spec for authentication"

    -- Details
    resource_type TEXT,                   -- context, file, decision, etc.
    resource_id TEXT,                     -- api_v1, src/auth.py, etc.
    metadata JSONB DEFAULT '{}',          -- Tool-specific details

    -- Semantic embedding (768d for nomic-embed-text)
    embedding vector(768),                -- Requires pgvector

    -- Context
    current_files JSONB DEFAULT '[]',     -- Files being worked on
    current_contexts JSONB DEFAULT '[]',  -- Contexts in use

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    duration_ms INTEGER,                  -- How long tool took

    CONSTRAINT fk_session FOREIGN KEY (session_id)
        REFERENCES mcp_sessions(session_id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX idx_activities_session ON session_activities(session_id);
CREATE INDEX idx_activities_project ON session_activities(project_name);
CREATE INDEX idx_activities_tool ON session_activities(tool_name);
CREATE INDEX idx_activities_time ON session_activities(created_at DESC);

-- Vector similarity search (requires pgvector)
CREATE INDEX idx_activities_embedding
    ON session_activities
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

**Alternative without pgvector:**
```sql
embedding JSONB  -- Store as array of 768 floats
```

---

## 🔧 Implementation Strategy

### Phase 1: Activity Tracking Decorator

**Wrap all tools with activity tracker:**

```python
def track_activity(tool_name: str, action_type: str):
    """
    Decorator to automatically track and embed tool usage.

    Replaces explicit wake_up/sleep with continuous tracking.
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()

            # Execute the tool (original behavior)
            result = await func(*args, **kwargs)

            duration_ms = int((time.time() - start_time) * 1000)

            # Extract semantic information for embedding
            action_summary = _extract_action_summary(
                tool_name=tool_name,
                action_type=action_type,
                args=args,
                kwargs=kwargs,
                result=result
            )

            # Generate embedding (async, non-blocking)
            asyncio.create_task(_store_activity(
                tool_name=tool_name,
                action_type=action_type,
                action_summary=action_summary,
                metadata=_extract_metadata(kwargs),
                duration_ms=duration_ms
            ))

            return result

        return wrapper
    return decorator
```

**Apply to all tools:**

```python
@mcp.tool()
@track_activity("lock_context", "create")
async def lock_context(content: str, topic: str, ...) -> str:
    """Lock context..."""
    # ... existing implementation ...

@mcp.tool()
@track_activity("edit_file", "update")
async def edit_file(file_path: str, ...) -> str:
    """Edit file..."""
    # ... existing implementation ...

@mcp.tool()
@track_activity("recall_context", "read")
async def recall_context(topic: str, ...) -> str:
    """Recall context..."""
    # ... existing implementation ...
```

---

### Phase 2: Activity Storage

```python
async def _store_activity(
    tool_name: str,
    action_type: str,
    action_summary: str,
    metadata: dict,
    duration_ms: int
):
    """
    Store activity with embedding in background.

    Non-blocking - doesn't slow down tool execution.
    """
    from src.services import embedding_service

    # Get session context
    session_id = getattr(config, '_current_session_id', None)
    if not session_id:
        return  # No active session

    project = _get_project_for_context()

    # Get current context (what files/contexts are active)
    current_files = _get_current_files()
    current_contexts = _get_current_contexts()

    # Generate embedding (if service available)
    embedding = None
    if embedding_service.enabled:
        try:
            # Build embedding text from action summary + context
            embed_text = f"{action_summary}. Context: {', '.join(current_contexts[:3])}. Files: {', '.join(current_files[:3])}"

            # Truncate to 1020 chars (nomic-embed-text limit)
            if len(embed_text) > 1020:
                embed_text = embed_text[:1017] + "..."

            embedding = embedding_service.generate_embedding(embed_text)
        except Exception as e:
            print(f"⚠️  Failed to generate activity embedding: {e}", file=sys.stderr)

    # Store in database
    adapter = _get_db_adapter()

    with adapter.pool.getconn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO session_activities (
                    session_id, project_name, tool_name, action_type,
                    action_summary, resource_type, resource_id,
                    metadata, embedding, current_files, current_contexts,
                    duration_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session_id, project, tool_name, action_type,
                action_summary,
                metadata.get('resource_type'),
                metadata.get('resource_id'),
                json.dumps(metadata),
                embedding,  # vector type or JSONB
                json.dumps(current_files),
                json.dumps(current_contexts),
                duration_ms
            ))
            conn.commit()

    adapter.pool.putconn(conn)
```

---

### Phase 3: Helper Functions

**Extract action summary:**

```python
def _extract_action_summary(
    tool_name: str,
    action_type: str,
    args: tuple,
    kwargs: dict,
    result: str
) -> str:
    """
    Extract semantic summary from tool call.

    Examples:
    - lock_context(...) → "Locked API specification for authentication"
    - edit_file(...) → "Updated auth.py to fix JWT validation"
    - bash(...) → "Ran tests for authentication module"
    """

    if tool_name == "lock_context":
        topic = kwargs.get('topic', args[1] if len(args) > 1 else 'unknown')
        priority = kwargs.get('priority', 'reference')
        return f"Locked context '{topic}' (priority: {priority})"

    elif tool_name == "recall_context":
        topic = kwargs.get('topic', args[0] if args else 'unknown')
        return f"Recalled context '{topic}'"

    elif tool_name == "edit_file":
        path = kwargs.get('file_path', args[0] if args else 'unknown')
        filename = path.split('/')[-1]
        return f"Edited {filename}"

    elif tool_name == "bash":
        command = kwargs.get('command', args[0] if args else 'unknown')
        # Extract intent from command
        if 'test' in command.lower():
            return f"Ran tests"
        elif 'git' in command.lower():
            return f"Git operation: {command[:50]}"
        else:
            return f"Executed: {command[:50]}"

    elif tool_name == "select_project_for_session":
        project = kwargs.get('project_name', args[0] if args else 'unknown')
        return f"Selected project '{project}'"

    else:
        # Generic fallback
        return f"Used {tool_name}"
```

**Extract metadata:**

```python
def _extract_metadata(kwargs: dict) -> dict:
    """Extract relevant metadata from tool call."""

    metadata = {}

    # Common fields
    if 'topic' in kwargs:
        metadata['resource_type'] = 'context'
        metadata['resource_id'] = kwargs['topic']

    if 'file_path' in kwargs:
        metadata['resource_type'] = 'file'
        metadata['resource_id'] = kwargs['file_path']

    if 'project' in kwargs:
        metadata['target_project'] = kwargs['project']

    if 'priority' in kwargs:
        metadata['priority'] = kwargs['priority']

    if 'tags' in kwargs:
        metadata['tags'] = kwargs['tags']

    return metadata
```

**Get current context:**

```python
def _get_current_files() -> List[str]:
    """Get list of files currently being worked on."""
    session_id = getattr(config, '_current_session_id', None)
    if not session_id:
        return []

    adapter = _get_db_adapter()

    with adapter.pool.getconn() as conn:
        with conn.cursor() as cur:
            # Get files touched in last 5 minutes
            cur.execute("""
                SELECT DISTINCT resource_id
                FROM session_activities
                WHERE session_id = %s
                AND resource_type = 'file'
                AND created_at > NOW() - INTERVAL '5 minutes'
                ORDER BY created_at DESC
                LIMIT 5
            """, (session_id,))

            return [row['resource_id'] for row in cur.fetchall()]

    adapter.pool.putconn(conn)

def _get_current_contexts() -> List[str]:
    """Get list of contexts currently relevant."""
    session_id = getattr(config, '_current_session_id', None)
    if not session_id:
        return []

    adapter = _get_db_adapter()

    with adapter.pool.getconn() as conn:
        with conn.cursor() as cur:
            # Get contexts used in last 10 minutes
            cur.execute("""
                SELECT DISTINCT resource_id
                FROM session_activities
                WHERE session_id = %s
                AND resource_type = 'context'
                AND created_at > NOW() - INTERVAL '10 minutes'
                ORDER BY created_at DESC
                LIMIT 5
            """, (session_id,))

            return [row['resource_id'] for row in cur.fetchall()]

    adapter.pool.putconn(conn)
```

---

### Phase 4: Context Retrieval (Replace wake_up)

**New tool: `show_context()`**

```python
@mcp.tool()
async def show_context(project: Optional[str] = None) -> str:
    """
    Show complete work context for this project.

    Automatically called on new session start.
    Replaces wake_up() with continuous context gathering.

    Returns:
        Complete narrative of past work, current state, and suggestions
    """
    target_project = _get_project_for_context(project)
    session_id = getattr(config, '_current_session_id', None)

    # Find semantically related past activities
    related_activities = await _find_related_activities(
        project=target_project,
        limit=20  # Top 20 related activities
    )

    # Build narrative
    output = []
    output.append("🎯 Work Context\n")

    # 1. Current session (if any activities)
    current = [a for a in related_activities if a['session_id'] == session_id]
    if current:
        output.append("📍 This Session:")
        for activity in current[-5:]:  # Last 5 activities
            output.append(f"   • {activity['action_summary']}")
        output.append("")

    # 2. Related past work
    past = [a for a in related_activities if a['session_id'] != session_id]
    if past:
        output.append("🔗 Related Past Work:")

        # Group by time
        recent = [a for a in past if a['days_ago'] < 1]
        this_week = [a for a in past if 1 <= a['days_ago'] < 7]
        older = [a for a in past if a['days_ago'] >= 7]

        if recent:
            output.append("\n  Yesterday:")
            for a in recent[:3]:
                output.append(f"   • {a['action_summary']} ({a['similarity']:.0%} relevant)")

        if this_week:
            output.append("\n  This Week:")
            for a in this_week[:3]:
                output.append(f"   • {a['action_summary']} ({a['time_ago']}, {a['similarity']:.0%} relevant)")

        if older:
            output.append("\n  Earlier:")
            for a in older[:2]:
                output.append(f"   • {a['action_summary']} ({a['time_ago']}, {a['similarity']:.0%} relevant)")

    # 3. Detected patterns
    patterns = _detect_activity_patterns(related_activities)
    if patterns:
        output.append("\n📈 Detected Patterns:")
        for pattern in patterns[:3]:
            output.append(f"   • {pattern}")

    # 4. Suggested next actions
    suggestions = _suggest_next_actions(related_activities)
    if suggestions:
        output.append("\n💡 Suggested Next:")
        for suggestion in suggestions[:3]:
            output.append(f"   • {suggestion}")

    return "\n".join(output)
```

**Find related activities:**

```python
async def _find_related_activities(
    project: str,
    current_activity: Optional[str] = None,
    limit: int = 20
) -> List[dict]:
    """
    Find semantically similar past activities.

    If current_activity provided: Find similar to it
    Otherwise: Find similar to recent work in this session
    """
    from src.services import embedding_service

    if not embedding_service.enabled:
        # Fallback: Just return recent activities
        return _get_recent_activities(project, limit)

    adapter = _get_db_adapter()
    session_id = getattr(config, '_current_session_id', None)

    # Build query embedding
    if current_activity:
        query_embedding = embedding_service.generate_embedding(current_activity)
    else:
        # Use recent activities from this session
        recent = _get_recent_activities(project, limit=5, session_id=session_id)
        if not recent:
            return []

        # Combine recent activity summaries
        combined = ". ".join(a['action_summary'] for a in recent)
        query_embedding = embedding_service.generate_embedding(combined)

    # Semantic search
    with adapter.pool.getconn() as conn:
        with conn.cursor() as cur:
            # Check if pgvector available
            cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            has_pgvector = cur.fetchone() is not None

            if has_pgvector:
                # Fast vector search
                cur.execute("""
                    SELECT
                        session_id,
                        tool_name,
                        action_summary,
                        resource_id,
                        created_at,
                        metadata,
                        current_files,
                        current_contexts,
                        1 - (embedding <=> %s::vector) AS similarity,
                        EXTRACT(DAY FROM NOW() - created_at) AS days_ago
                    FROM session_activities
                    WHERE project_name = %s
                    AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """, (query_embedding, project, query_embedding, limit))
            else:
                # Manual cosine similarity
                cur.execute("""
                    SELECT
                        session_id, tool_name, action_summary,
                        resource_id, created_at, metadata,
                        current_files, current_contexts, embedding,
                        EXTRACT(DAY FROM NOW() - created_at) AS days_ago
                    FROM session_activities
                    WHERE project_name = %s
                    AND embedding IS NOT NULL
                """, (project,))

                # Calculate similarity in Python
                results = []
                for row in cur.fetchall():
                    stored_emb = json.loads(row['embedding']) if isinstance(row['embedding'], str) else row['embedding']
                    similarity = _cosine_similarity(query_embedding, stored_emb)

                    results.append({
                        'session_id': row['session_id'],
                        'tool_name': row['tool_name'],
                        'action_summary': row['action_summary'],
                        'resource_id': row['resource_id'],
                        'created_at': row['created_at'],
                        'metadata': row['metadata'],
                        'current_files': row['current_files'],
                        'current_contexts': row['current_contexts'],
                        'similarity': similarity,
                        'days_ago': row['days_ago']
                    })

                results.sort(key=lambda x: x['similarity'], reverse=True)
                results = results[:limit]

                return results

            # Format results
            activities = []
            for row in cur.fetchall():
                activities.append({
                    'session_id': row['session_id'],
                    'tool_name': row['tool_name'],
                    'action_summary': row['action_summary'],
                    'resource_id': row['resource_id'],
                    'created_at': row['created_at'],
                    'days_ago': int(row['days_ago']),
                    'time_ago': _format_time_ago(row['days_ago']),
                    'similarity': row['similarity'],
                    'metadata': json.loads(row['metadata']) if row['metadata'] else {},
                    'current_files': json.loads(row['current_files']) if row['current_files'] else [],
                    'current_contexts': json.loads(row['current_contexts']) if row['current_contexts'] else []
                })

            return activities

    adapter.pool.putconn(conn)
```

---

## 🎯 Automatic Context Loading

**On new session:**

```python
# In session initialization (middleware or local fork)
def _init_session(...):
    """Initialize session and auto-load context."""

    # ... existing session creation ...

    # Automatically show context (replaces wake_up)
    if session_is_new:
        context = await show_context()
        # Store in session summary for reference
        _update_session_summary(session_id, {'initial_context': context})

    return session_id
```

**On project switch:**

```python
@mcp.tool()
@track_activity("switch_project", "update")
async def switch_project(name: str) -> str:
    """Switch active project."""

    # ... existing project switching ...

    # Auto-load context for new project
    context = await show_context(project=name)

    return f"✅ Switched to '{name}'\n\n{context}"
```

---

## 📊 Benefits Over wake_up/sleep

| Old Approach | New Approach | Benefit |
|--------------|--------------|---------|
| Manual `wake_up()` | Automatic on session start | Zero cognitive load |
| Manual `sleep()` | Continuous tracking | Never forget to save |
| Session boundaries | Continuous stream | More natural workflow |
| Explicit handovers | Semantic search | Better continuity |
| Limited to sessions | All-time history | Complete narrative |
| Text summaries | Embedded activities | Semantic understanding |

---

## 💰 Cost & Performance

**Storage:**
- Per activity: ~4 KB (summary + embedding + metadata)
- 100 activities/day × 30 days = 3,000 activities = 12 MB/month
- **Very cheap!**

**Compute:**
- Embedding generation: ~30ms per activity (background, non-blocking)
- Similarity search: <10ms with pgvector, ~100ms without
- **No user-visible latency**

**Cost:**
- Ollama (local): **$0.00**
- Database storage: **~$0.01/month** (12 MB)
- **Total: Essentially free**

---

## 🔧 Implementation Phases

### Phase 1: Activity Tracking (3-4 hours)

- [ ] Create `session_activities` table
- [ ] Implement `track_activity` decorator
- [ ] Implement `_store_activity()` background task
- [ ] Apply decorator to 5-10 key tools
- [ ] Test: Activities stored with embeddings

**Deliverable**: Tools automatically track activities

---

### Phase 2: Context Retrieval (4-5 hours)

- [ ] Implement `_find_related_activities()`
- [ ] Implement `show_context()` tool
- [ ] Implement pattern detection
- [ ] Implement next action suggestions
- [ ] Test: show_context() returns intelligent narrative

**Deliverable**: Context retrieval working

---

### Phase 3: Automatic Loading (2-3 hours)

- [ ] Auto-call `show_context()` on new session
- [ ] Auto-call on project switch
- [ ] Optimize queries for performance
- [ ] Test end-to-end workflow

**Deliverable**: Fully automatic context

---

### Phase 4: Deprecate wake_up/sleep (1 hour)

- [ ] Mark `wake_up()` as deprecated
- [ ] Mark `sleep()` as deprecated
- [ ] Update documentation
- [ ] Migration guide for users

**Deliverable**: Clean transition

---

**Total Estimate: 10-13 hours**

---

## 🧪 Testing Plan

```python
# test_continuous_context.py

async def test_activity_tracking():
    """Test that tool calls generate activities."""

    # Call a tool
    await lock_context("Test spec", "test_topic")

    # Verify activity stored
    activity = _get_last_activity()
    assert activity['tool_name'] == 'lock_context'
    assert activity['action_summary'] == "Locked context 'test_topic'"
    assert activity['embedding'] is not None

async def test_semantic_search():
    """Test finding related activities."""

    # Create several activities
    await lock_context("JWT spec", "jwt")
    await lock_context("OAuth spec", "oauth")
    await lock_context("Database schema", "db")

    # Search for auth-related
    related = await _find_related_activities(
        project='test',
        current_activity="Working on authentication"
    )

    # Should find JWT and OAuth, not database
    summaries = [a['action_summary'] for a in related]
    assert any('jwt' in s.lower() for s in summaries)
    assert any('oauth' in s.lower() for s in summaries)

async def test_automatic_context_loading():
    """Test context loads automatically."""

    # Simulate new session
    session_id = _create_new_session()

    # Should automatically call show_context()
    # (verify via session summary or logs)
    summary = _get_session_summary(session_id)
    assert 'initial_context' in summary
```

---

## 🎯 Success Metrics

**Week 1:**
- ✅ Activities tracked automatically
- ✅ Embeddings generated for 80%+ activities
- ✅ No performance degradation

**Week 2:**
- ✅ Context retrieval works
- ✅ Related activities found correctly
- ✅ Users stop using wake_up/sleep

**Month 1:**
- ✅ 100% automatic context loading
- ✅ wake_up/sleep deprecated
- ✅ Users report better continuity
- ✅ Zero added cost

---

## 💡 Next Steps

**Recommended: Start with Phase 1 (Quick Prototype)**

1. **Create table** - 30 min
2. **Add decorator to 3 tools** - 1 hour
3. **Test storage** - 30 min
4. **Evaluate** - Does it work?

Then decide if full implementation is worth it.

**Ready to start?**
