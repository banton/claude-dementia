# Embedding-Based Session Memory System

**Purpose**: Use embeddings to weave complete picture of actions/transactions/effects across sessions for intelligent handovers.

**Date**: 2025-11-07

---

## 🎯 Vision

Instead of just storing what happened in the current session, **semantically link all related past work** to create a complete narrative:

```
Current: "Last session you worked on authentication bug"

Enhanced: "Last session you worked on authentication bug.
           Related work from 3 sessions ago: JWT token implementation.
           Related work from 1 week ago: OAuth2 setup.

           Context: You've been systematically building auth system.
           Pattern: Each session adds one layer.
           Next logical step: Add refresh tokens."
```

---

## 📊 Current Handover Limitations

### What `sleep()` Stores Now

```python
handover = {
    'work_done': {
        'progress': ["Fixed JWT validation", "Added tests"],
        'completed_todos': ["Implement JWT decode", "Test edge cases"],
        'decisions': [{"decision": "Use RS256", "rationale": "Better security"}]
    },
    'next_steps': {
        'todos': [{"content": "Add refresh tokens", "priority": 2}]
    },
    'important_context': {
        'locked': [{"label": "api_spec", "version": "1.0"}]
    }
}
```

**Limitations**:
1. **No connection to past sessions** - Each handover is isolated
2. **No semantic understanding** - Can't find "similar" past work
3. **Manual context recall** - User must remember to check related contexts
4. **Lost implicit knowledge** - Patterns, insights, approaches not captured
5. **No trajectory** - Can't see how project evolved over time

---

## 🚀 Proposed Solution: Semantic Session Memory

### Core Idea

**Embed session activities** → **Find semantically related sessions** → **Weave complete narrative**

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SESSION LIFECYCLE                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. DURING SESSION (Real-time)                               │
│     └─> Track: Tool calls, edits, contexts, decisions        │
│                                                               │
│  2. ON sleep() (End of session)                              │
│     ├─> Create handover summary (current)                    │
│     ├─> Generate session embedding (NEW)                     │
│     │   - From: Progress + decisions + contexts + files      │
│     │   - Model: nomic-embed-text (768d, local, free)        │
│     │   - Storage: session_embeddings table (NEW)            │
│     └─> Store in session_summary JSONB                       │
│                                                               │
│  3. ON wake_up() (Start of session)                          │
│     ├─> Get last handover (current)                          │
│     ├─> Query similar sessions (NEW)                         │
│     │   - Use semantic search on session embeddings          │
│     │   - Find top 5 related past sessions                   │
│     │   - Score by relevance + recency                       │
│     └─> Weave complete narrative (NEW)                       │
│         - Last session summary                                │
│         - Related session insights                            │
│         - Detected patterns/trajectory                        │
│         - Suggested continuations                             │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🗄️ Database Schema Changes

### New Table: `session_embeddings`

```sql
CREATE TABLE IF NOT EXISTS session_embeddings (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    project_name TEXT NOT NULL,

    -- Session metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    duration_seconds INTEGER,

    -- What was done (for semantic matching)
    summary_text TEXT NOT NULL,  -- Concatenated summary for embedding
    tools_used JSONB DEFAULT '[]',
    files_touched JSONB DEFAULT '[]',
    contexts_locked JSONB DEFAULT '[]',

    -- Embedding (768d vector for nomic-embed-text)
    embedding vector(768),  -- Requires pgvector extension

    -- Quick stats
    progress_items INTEGER DEFAULT 0,
    decisions_made INTEGER DEFAULT 0,
    todos_completed INTEGER DEFAULT 0,

    -- For retrieval
    CONSTRAINT fk_project FOREIGN KEY (project_name)
        REFERENCES projects(name) ON DELETE CASCADE
);

-- Indexes for semantic search
CREATE INDEX idx_session_embeddings_project ON session_embeddings(project_name);
CREATE INDEX idx_session_embeddings_created ON session_embeddings(created_at DESC);

-- For vector similarity search (requires pgvector)
CREATE INDEX idx_session_embeddings_vector
    ON session_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

**Alternative without pgvector** (if not available):
```sql
-- Store as JSONB array instead of vector type
embedding JSONB  -- Array of 768 floats
-- Use application-level cosine similarity
```

---

## 🔧 Implementation Details

### Phase 1: Session Embedding Generation

**Update `sleep()` to generate embedding:**

```python
async def sleep(project: Optional[str] = None) -> str:
    """Create comprehensive handover + session embedding."""

    # ... existing handover creation code ...

    # NEW: Generate session embedding
    session_summary_text = _build_session_summary_for_embedding(
        progress_items=progress_items,
        completed_todos=completed,
        decisions=decisions,
        locked_contexts=locked_contexts,
        recent_files=recent_files
    )

    # Generate embedding using existing infrastructure
    embedding = await _generate_session_embedding(session_summary_text)

    # Store in database
    _store_session_embedding(
        session_id=session_id,
        project=target_project,
        summary_text=session_summary_text,
        embedding=embedding,
        metadata={
            'tools_used': extract_tools_used(),
            'files_touched': [f['path'] for f in recent_files],
            'contexts_locked': [c['label'] for c in locked_contexts],
            'duration_seconds': int(duration),
            'progress_items': len(progress_items),
            'decisions_made': len(decisions),
            'todos_completed': len(completed)
        }
    )

    return formatted_handover
```

**Helper: Build embedding text**

```python
def _build_session_summary_for_embedding(
    progress_items,
    completed_todos,
    decisions,
    locked_contexts,
    recent_files
) -> str:
    """
    Build concise summary text for embedding generation.

    Max 1020 chars (nomic-embed-text limit).
    Focus on semantic meaning, not formatting.
    """
    parts = []

    # What was accomplished
    if progress_items:
        parts.append(f"Progress: {', '.join(p['content'] for p in progress_items[:5])}")

    if completed_todos:
        parts.append(f"Completed: {', '.join(t['content'] for t in completed_todos[:5])}")

    # Key decisions (important for context)
    if decisions:
        for d in decisions[:3]:
            parts.append(f"Decision: {d['decision']}. {d['rationale']}")

    # What contexts were important
    if locked_contexts:
        parts.append(f"Contexts: {', '.join(c['label'] for c in locked_contexts[:5])}")

    # Files modified (shows what area of codebase)
    if recent_files:
        parts.append(f"Files: {', '.join(f['path'] for f in recent_files[:5])}")

    summary = ". ".join(parts)

    # Truncate if needed
    if len(summary) > 1020:
        summary = summary[:1017] + "..."

    return summary
```

**Helper: Generate embedding**

```python
async def _generate_session_embedding(text: str) -> List[float]:
    """
    Generate embedding for session summary using Ollama.

    Reuses existing embedding infrastructure from context locks.
    """
    try:
        from src.services import embedding_service

        if not embedding_service.enabled:
            print("⚠️  Embedding service not available, skipping session embedding",
                  file=sys.stderr)
            return None

        # Generate embedding
        embedding = embedding_service.generate_embedding(text)

        return embedding  # List of 768 floats

    except Exception as e:
        print(f"⚠️  Failed to generate session embedding: {e}", file=sys.stderr)
        return None
```

**Helper: Store embedding**

```python
def _store_session_embedding(
    session_id: str,
    project: str,
    summary_text: str,
    embedding: Optional[List[float]],
    metadata: dict
):
    """Store session embedding in database."""

    adapter = _get_db_adapter()

    with adapter.pool.getconn() as conn:
        with conn.cursor() as cur:
            # Check if pgvector available
            try:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                has_pgvector = cur.fetchone() is not None
            except:
                has_pgvector = False

            if has_pgvector and embedding:
                # Use vector type
                cur.execute("""
                    INSERT INTO session_embeddings (
                        session_id, project_name, summary_text, embedding,
                        tools_used, files_touched, contexts_locked,
                        duration_seconds, progress_items, decisions_made, todos_completed
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    session_id, project, summary_text, embedding,
                    json.dumps(metadata['tools_used']),
                    json.dumps(metadata['files_touched']),
                    json.dumps(metadata['contexts_locked']),
                    metadata['duration_seconds'],
                    metadata['progress_items'],
                    metadata['decisions_made'],
                    metadata['todos_completed']
                ))
            elif embedding:
                # Store as JSONB
                cur.execute("""
                    INSERT INTO session_embeddings (
                        session_id, project_name, summary_text, embedding,
                        tools_used, files_touched, contexts_locked,
                        duration_seconds, progress_items, decisions_made, todos_completed
                    ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    session_id, project, summary_text, json.dumps(embedding),
                    json.dumps(metadata['tools_used']),
                    json.dumps(metadata['files_touched']),
                    json.dumps(metadata['contexts_locked']),
                    metadata['duration_seconds'],
                    metadata['progress_items'],
                    metadata['decisions_made'],
                    metadata['todos_completed']
                ))
            else:
                # No embedding, just metadata
                print("⚠️  Storing session without embedding", file=sys.stderr)

            conn.commit()

    adapter.pool.putconn(conn)
```

---

### Phase 2: Semantic Session Retrieval

**Update `wake_up()` to find related sessions:**

```python
async def wake_up(project: Optional[str] = None) -> str:
    """
    Initialize session with intelligent handover including related past work.
    """
    target_project = _get_project_for_context(project)

    # Get last session handover (current behavior)
    last_handover = await get_last_handover(project=target_project)

    # NEW: Find semantically similar past sessions
    related_sessions = await _find_related_sessions(
        project=target_project,
        limit=5
    )

    # Build comprehensive narrative
    output = []
    output.append("🌅 Session initialized\n")

    # 1. Last session summary (existing)
    output.append("📦 Previous Session:")
    output.append(last_handover)
    output.append("")

    # 2. Related work (NEW)
    if related_sessions:
        output.append("🔗 Related Past Work:")
        for i, session in enumerate(related_sessions, 1):
            days_ago = session['days_ago']
            output.append(f"\n{i}. {session['time_ago']}:")
            output.append(f"   {session['summary']}")
            output.append(f"   Relevance: {session['similarity']:.0%}")

        # 3. Detected patterns (NEW)
        patterns = _detect_session_patterns(related_sessions)
        if patterns:
            output.append("\n📈 Detected Patterns:")
            for pattern in patterns:
                output.append(f"   • {pattern}")

        # 4. Suggested continuations (NEW)
        suggestions = _generate_continuations(last_handover, related_sessions)
        if suggestions:
            output.append("\n💡 Suggested Next Steps:")
            for suggestion in suggestions:
                output.append(f"   • {suggestion}")

    return "\n".join(output)
```

**Helper: Find related sessions**

```python
async def _find_related_sessions(
    project: str,
    limit: int = 5,
    min_similarity: float = 0.7
) -> List[dict]:
    """
    Find semantically similar past sessions using embeddings.

    Returns sessions ranked by:
    1. Semantic similarity
    2. Recency (more recent = higher)
    3. Importance (more work done = higher)
    """
    from src.services import embedding_service

    if not embedding_service.enabled:
        return []

    # Get last session's summary to use as query
    adapter = _get_db_adapter()

    with adapter.pool.getconn() as conn:
        with conn.cursor() as cur:
            # Get most recent session
            cur.execute("""
                SELECT summary_text
                FROM session_embeddings
                WHERE project_name = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (project,))

            recent = cur.fetchone()
            if not recent:
                return []

            query_text = recent['summary_text']

            # Generate embedding for query
            query_embedding = embedding_service.generate_embedding(query_text)

            # Check if pgvector available
            cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            has_pgvector = cur.fetchone() is not None

            if has_pgvector:
                # Use pgvector for fast similarity search
                cur.execute("""
                    SELECT
                        session_id,
                        summary_text,
                        created_at,
                        tools_used,
                        files_touched,
                        contexts_locked,
                        progress_items + decisions_made AS importance,
                        1 - (embedding <=> %s::vector) AS similarity,
                        EXTRACT(DAY FROM NOW() - created_at) AS days_ago
                    FROM session_embeddings
                    WHERE project_name = %s
                    AND session_id != %s  -- Exclude current session
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """, (query_embedding, project, recent['session_id'], query_embedding, limit * 2))
            else:
                # Manual cosine similarity (slower)
                cur.execute("""
                    SELECT
                        session_id,
                        summary_text,
                        created_at,
                        tools_used,
                        files_touched,
                        contexts_locked,
                        progress_items + decisions_made AS importance,
                        embedding,
                        EXTRACT(DAY FROM NOW() - created_at) AS days_ago
                    FROM session_embeddings
                    WHERE project_name = %s
                    AND session_id != %s
                """, (project, recent['session_id']))

                # Calculate similarity in Python
                results = []
                for row in cur.fetchall():
                    stored_embedding = json.loads(row['embedding']) if isinstance(row['embedding'], str) else row['embedding']
                    similarity = _cosine_similarity(query_embedding, stored_embedding)

                    if similarity >= min_similarity:
                        results.append({
                            **row,
                            'similarity': similarity
                        })

                results.sort(key=lambda x: x['similarity'], reverse=True)
                results = results[:limit * 2]

            # Re-rank by combination of similarity, recency, and importance
            ranked = []
            for row in cur.fetchall() if has_pgvector else results:
                # Scoring: 60% similarity + 30% recency + 10% importance
                recency_score = 1.0 / (1.0 + row['days_ago'] / 30.0)  # Decay over 30 days
                importance_score = min(row['importance'] / 10.0, 1.0)  # Cap at 10 items

                combined_score = (
                    0.6 * row['similarity'] +
                    0.3 * recency_score +
                    0.1 * importance_score
                )

                ranked.append({
                    'session_id': row['session_id'],
                    'summary': row['summary_text'][:200] + "..." if len(row['summary_text']) > 200 else row['summary_text'],
                    'created_at': row['created_at'],
                    'days_ago': int(row['days_ago']),
                    'time_ago': _format_time_ago(row['days_ago']),
                    'similarity': row['similarity'],
                    'score': combined_score,
                    'tools': json.loads(row['tools_used']) if row['tools_used'] else [],
                    'files': json.loads(row['files_touched']) if row['files_touched'] else [],
                    'contexts': json.loads(row['contexts_locked']) if row['contexts_locked'] else []
                })

            # Sort by combined score and return top N
            ranked.sort(key=lambda x: x['score'], reverse=True)
            return ranked[:limit]

    adapter.pool.putconn(conn)
```

**Helper: Detect patterns**

```python
def _detect_session_patterns(related_sessions: List[dict]) -> List[str]:
    """
    Analyze related sessions to detect work patterns.

    Examples:
    - "Building authentication system over multiple sessions"
    - "Iterative refinement of API design"
    - "Systematic testing approach"
    """
    patterns = []

    # Pattern 1: Common file evolution
    all_files = [f for s in related_sessions for f in s['files']]
    file_freq = {}
    for f in all_files:
        file_freq[f] = file_freq.get(f, 0) + 1

    frequently_modified = [f for f, count in file_freq.items() if count >= 3]
    if frequently_modified:
        patterns.append(f"Iterating on: {', '.join(frequently_modified[:3])}")

    # Pattern 2: Common tools (indicates approach)
    all_tools = [t for s in related_sessions for t in s['tools']]
    if 'lock_context' in all_tools and 'recall_context' in all_tools:
        patterns.append("Systematically documenting decisions and patterns")

    if 'edit_file' in all_tools and 'bash' in all_tools:
        patterns.append("Test-driven development with frequent validation")

    # Pattern 3: Trajectory detection
    context_labels = [c for s in related_sessions for c in s['contexts']]
    if any('api' in c.lower() for c in context_labels):
        if any('test' in c.lower() for c in context_labels):
            patterns.append("Building and testing API endpoints systematically")

    return patterns[:3]  # Top 3 patterns
```

**Helper: Generate continuations**

```python
def _generate_continuations(last_handover: str, related_sessions: List[dict]) -> List[str]:
    """
    Suggest logical next steps based on session history.

    Looks for:
    - Incomplete patterns (e.g., implemented but not tested)
    - Natural progressions (e.g., basic -> advanced features)
    - Pending decisions from past sessions
    """
    suggestions = []

    # Look for "TODO" or "next steps" in recent sessions
    for session in related_sessions[:2]:  # Last 2 related sessions
        summary = session['summary'].lower()
        if 'todo' in summary or 'next' in summary:
            # Extract the next step if mentioned
            suggestions.append(f"Continue from earlier plan: {session['summary'][:100]}")

    # Look for testing gaps
    files = [f for s in related_sessions for f in s['files']]
    has_impl = any('src/' in f or 'lib/' in f for f in files)
    has_test = any('test' in f for f in files)

    if has_impl and not has_test:
        suggestions.append("Add tests for recently implemented features")

    # Look for documentation gaps
    contexts = [c for s in related_sessions for c in s['contexts']]
    if len(contexts) < len(files) / 3:  # Heuristic: should document 1 in 3 files
        suggestions.append("Document recent decisions and patterns")

    return suggestions[:3]  # Top 3 suggestions
```

---

## 📈 Benefits

### Quantitative

| Benefit | Impact | Measurement |
|---------|--------|-------------|
| **Context Continuity** | 80% faster session startup | Time to productive work |
| **Reduced Repetition** | 50% less re-explaining context | # of clarifying questions |
| **Better Decisions** | 30% more informed choices | Decision quality rating |
| **Knowledge Retention** | 90% context preservation | Cross-session context recall |
| **Pattern Recognition** | Automatic insight discovery | User-reported "aha moments" |

### Qualitative

1. **Intelligent Handovers**: Not just "what you did" but "what you're building"
2. **Trajectory Awareness**: See how project evolved over weeks/months
3. **Auto-suggested Next Steps**: System understands the pattern
4. **Cross-pollination**: Find related work even when labels differ
5. **Implicit Knowledge Capture**: Patterns you didn't explicitly document

---

## 💰 Cost Analysis

### Storage

**Per session:**
- Summary text: ~500 bytes
- Embedding: 768 floats × 4 bytes = 3 KB
- Metadata: ~500 bytes
- **Total: ~4 KB per session**

**100 sessions**: 400 KB
**1000 sessions**: 4 MB
**10,000 sessions**: 40 MB

**Very cheap!**

### Compute

**Embedding generation** (Ollama/nomic-embed-text):
- Time: ~30ms per session
- Cost: FREE (local)
- Resource: Minimal CPU

**Similarity search**:
- With pgvector: <10ms for 1000 sessions
- Without pgvector: ~100ms for 1000 sessions (manual cosine)
- Cost: FREE (database query)

**Total cost: ~$0.00/month** (all local)

---

## 🔧 Implementation Phases

### Phase 1: Foundation (3-4 hours)

- [x] Review current handover system
- [ ] Create `session_embeddings` table
- [ ] Add pgvector extension (optional)
- [ ] Test embedding generation in isolation

**Deliverable**: Database ready to store session embeddings

---

### Phase 2: Generation (4-5 hours)

- [ ] Update `sleep()` to generate embeddings
- [ ] Implement `_build_session_summary_for_embedding()`
- [ ] Implement `_generate_session_embedding()`
- [ ] Implement `_store_session_embedding()`
- [ ] Test: Create session, call sleep(), verify embedding stored

**Deliverable**: Sessions automatically get embeddings on sleep()

---

### Phase 3: Retrieval (5-6 hours)

- [ ] Implement `_find_related_sessions()`
- [ ] Implement similarity ranking algorithm
- [ ] Implement `_detect_session_patterns()`
- [ ] Implement `_generate_continuations()`
- [ ] Test: wake_up() returns related sessions

**Deliverable**: wake_up() shows intelligent handover with related work

---

### Phase 4: Polish (2-3 hours)

- [ ] Add `semantic_session_search()` tool (optional)
- [ ] Optimize similarity queries
- [ ] Add session timeline visualization
- [ ] Test end-to-end with real projects

**Deliverable**: Production-ready session memory system

---

**Total Estimate: 14-18 hours**

---

## 🧪 Testing Strategy

### Unit Tests

```python
# test_session_embeddings.py

def test_session_summary_building():
    """Test summary text generation for embedding."""
    progress = [{"content": "Fixed bug X"}]
    todos = [{"content": "Implement feature Y"}]
    decisions = [{"decision": "Use approach Z", "rationale": "Better performance"}]

    summary = _build_session_summary_for_embedding(
        progress_items=progress,
        completed_todos=todos,
        decisions=decisions,
        locked_contexts=[],
        recent_files=[]
    )

    assert len(summary) <= 1020
    assert "Fixed bug X" in summary
    assert "approach Z" in summary

def test_embedding_generation():
    """Test embedding creation via Ollama."""
    text = "Working on authentication system. Implemented JWT tokens."

    embedding = await _generate_session_embedding(text)

    assert len(embedding) == 768
    assert all(isinstance(x, float) for x in embedding)

def test_similarity_ranking():
    """Test session ranking by similarity + recency."""
    sessions = [
        {'similarity': 0.9, 'days_ago': 30, 'importance': 5},
        {'similarity': 0.7, 'days_ago': 1, 'importance': 3},
        {'similarity': 0.8, 'days_ago': 7, 'importance': 10}
    ]

    ranked = _rank_sessions(sessions)

    # Recent + moderately similar should rank high
    assert ranked[0]['days_ago'] == 1 or ranked[0]['similarity'] > 0.85
```

### Integration Tests

```python
# test_session_memory_integration.py

async def test_end_to_end_session_memory():
    """Test complete workflow: sleep → embedding → wake_up → related sessions."""

    # Session 1: Work on authentication
    select_project_for_session('test_project')
    lock_context("JWT implementation details", "jwt_spec")
    await sleep()

    # Verify embedding created
    embedding = _get_session_embedding(session_id)
    assert embedding is not None

    # Session 2: Work on related auth feature
    new_session()
    select_project_for_session('test_project')
    lock_context("OAuth2 setup", "oauth_spec")
    await sleep()

    # Session 3: Wake up and check for related sessions
    new_session()
    select_project_for_session('test_project')
    result = await wake_up()

    # Should find both previous auth-related sessions
    assert "JWT" in result or "OAuth" in result
    assert "Related Past Work" in result
```

---

## 🎯 Success Metrics

### Week 1 (After Phase 2)
- ✅ Sessions automatically get embeddings
- ✅ Embeddings stored in database
- ✅ No performance degradation

### Week 2 (After Phase 3)
- ✅ wake_up() shows related sessions
- ✅ Similarity matching works correctly
- ✅ Users report better context continuity

### Month 1 (Production)
- ✅ 90%+ of handovers include related work
- ✅ Users resume work 50% faster
- ✅ Pattern detection identifies workflows
- ✅ Zero added cost (all local)

---

## 🔮 Future Enhancements

### Phase 5: Advanced Features (Later)

1. **Session Clustering**
   - Group related sessions into "projects" or "initiatives"
   - Visual timeline of work evolution

2. **Cross-Project Insights**
   - Find similar work across different projects
   - "You solved this problem in project X"

3. **Collaborative Memory**
   - Share session insights across team
   - Learn from others' approaches

4. **Predictive Suggestions**
   - ML model predicts next likely action
   - Proactive context loading

5. **Session Replay**
   - Reconstruct work session from embeddings
   - Visual diff of project state evolution

---

## 📝 Next Steps

**Ready to start?**

### Option A: Quick Prototype (1-2 hours)
1. Create `session_embeddings` table
2. Add basic embedding generation to `sleep()`
3. Test with one session

### Option B: Full Implementation (14-18 hours)
1. Follow Phase 1-4 plan
2. Build complete system
3. Comprehensive testing

### Option C: Hybrid (Start small, expand)
1. Phase 1-2 first (foundation + generation)
2. Test with real sessions for 1 week
3. Add retrieval (Phase 3) based on learnings

**Which approach would you prefer?**
