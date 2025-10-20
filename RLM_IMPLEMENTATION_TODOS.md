# RLM Implementation TODO List
**Project**: claude-dementia v4.1 (RLM Memory Optimization)
**Estimated Timeline**: 2-3 weeks
**Goal**: Implement recursive knowledge deepening with 80% token reduction

---

## Phase 1: Database & Schema (Days 1-2)

### ☐ Task 1.1: Add Database Schema Enhancements
**Files**: `claude_mcp_hybrid.py` (database initialization section)

**Changes**:
```sql
ALTER TABLE context_locks ADD COLUMN preview TEXT;
ALTER TABLE context_locks ADD COLUMN key_concepts TEXT; -- JSON array
ALTER TABLE context_locks ADD COLUMN related_contexts TEXT; -- JSON array
ALTER TABLE context_locks ADD COLUMN last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE context_locks ADD COLUMN access_count INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS context_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    from_label TEXT NOT NULL,
    to_label TEXT NOT NULL,
    relationship_type TEXT,
    strength REAL DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, from_label, to_label)
);

CREATE TABLE IF NOT EXISTS context_access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    label TEXT NOT NULL,
    access_type TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tool_usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    params TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT NOT NULL
);
```

**Test Criteria**:
- [ ] Run migration script on test database
- [ ] Verify all columns exist: `SELECT preview, key_concepts FROM context_locks LIMIT 1`
- [ ] Insert test data into new tables
- [ ] Verify no errors on existing database
- [ ] Test rollback script works

**Success**: Schema upgrade completes without data loss, all new columns queryable

---

### ☐ Task 1.2: Create Migration Script
**Files**: `migrate_v4_1_rlm.py` (new file)

**Implementation**:
```python
#!/usr/bin/env python3
"""
Migration script for RLM enhancements (v4.0 → v4.1)
Adds preview, relationships, and access tracking
"""

def migrate_database(db_path: str):
    """Apply v4.1 schema changes"""
    conn = sqlite3.connect(db_path)

    # Check if already migrated
    cursor = conn.execute("PRAGMA table_info(context_locks)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'preview' in columns:
        print("✅ Already migrated to v4.1")
        return

    # Apply migrations
    conn.executescript("""
        -- Add new columns
        ALTER TABLE context_locks ADD COLUMN preview TEXT;
        ...

        -- Create new tables
        CREATE TABLE IF NOT EXISTS context_relationships (...);
        ...
    """)

    # Generate previews for existing contexts
    cursor = conn.execute("SELECT id, label, content FROM context_locks")
    for row in cursor:
        preview = generate_preview(row[2])
        key_concepts = extract_key_concepts(row[2])
        conn.execute("""
            UPDATE context_locks
            SET preview = ?, key_concepts = ?, last_accessed = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (preview, json.dumps(key_concepts), row[0]))

    conn.commit()
    print(f"✅ Migrated {cursor.rowcount} contexts")

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else ".claude-memory.db"
    migrate_database(db_path)
```

**Test Criteria**:
- [ ] Run on empty database: creates tables
- [ ] Run on v4.0 database: adds columns and populates previews
- [ ] Run twice: detects existing migration, doesn't duplicate
- [ ] Verify preview generation works for 10 test contexts
- [ ] Check key_concepts extraction is valid JSON

**Success**: Migration idempotent, generates previews for all existing contexts

---

## Phase 2: Core Helper Functions (Days 3-4)

### ☐ Task 2.1: Implement Preview Generation
**Files**: `claude_mcp_hybrid.py` or new `preview_generator.py`

**Implementation**:
```python
def generate_preview(content: str, max_length: int = 500) -> str:
    """
    Intelligent preview generation from context content.

    Algorithm:
    1. Extract title/header
    2. Find first substantial paragraph
    3. Find key sentences with MUST/ALWAYS/NEVER
    4. Combine and truncate to max_length
    """
    # See RLM_DETAILED_DESIGN.md for full implementation
```

**Test Cases**:
```python
def test_generate_preview():
    # Test 1: With header
    content = "# API Authentication\n\nUse JWT tokens for all requests..."
    preview = generate_preview(content)
    assert "API Authentication" in preview
    assert len(preview) <= 500

    # Test 2: With MUST rules
    content = "MUST validate tokens. NEVER store passwords..."
    preview = generate_preview(content)
    assert "MUST" in preview or "NEVER" in preview

    # Test 3: Long content truncation
    content = "x" * 2000
    preview = generate_preview(content)
    assert len(preview) <= 503  # 500 + "..."
    assert preview.endswith("...")

    # Test 4: Empty content
    preview = generate_preview("")
    assert preview == ""
```

**Success**: All tests pass, preview extraction captures key information

---

### ☐ Task 2.2: Implement Key Concept Extraction
**Files**: `claude_mcp_hybrid.py` or `preview_generator.py`

**Implementation**:
```python
def extract_key_concepts(content: str, tags: List[str] = None) -> List[str]:
    """
    Extract key technical concepts from content.

    Returns: Up to 10 key concepts as list of strings
    """
    # See RLM_DETAILED_DESIGN.md for full implementation
```

**Test Cases**:
```python
def test_extract_key_concepts():
    # Test 1: Technical terms
    content = "Use JWT tokens with OAuth2 for authentication"
    concepts = extract_key_concepts(content)
    assert "JWT" in concepts or "jwt" in [c.lower() for c in concepts]
    assert "OAuth2" in concepts or "oauth2" in [c.lower() for c in concepts]

    # Test 2: CamelCase detection
    content = "UserAuthenticationService handles LoginRequest"
    concepts = extract_key_concepts(content)
    assert any("User" in c or "Authentication" in c for c in concepts)

    # Test 3: Limit to 10
    content = " ".join([f"concept{i}" for i in range(20)])
    concepts = extract_key_concepts(content)
    assert len(concepts) <= 10

    # Test 4: Include provided tags
    concepts = extract_key_concepts("content", tags=["api", "auth"])
    assert "api" in concepts
    assert "auth" in concepts
```

**Success**: All tests pass, extracts meaningful concepts from real contexts

---

### ☐ Task 2.3: Update lock_context() with Preview Generation
**Files**: `claude_mcp_hybrid.py` (lock_context function)

**Changes**:
```python
@mcp.tool()
async def lock_context(
    content: str,
    topic: str,
    tags: Optional[str] = None,
    priority: Optional[str] = None,
    related: Optional[str] = None  # NEW
) -> str:
    """[Enhanced description - see Task 4]"""

    # Generate preview and concepts
    preview = generate_preview(content)
    key_concepts = extract_key_concepts(content, tag_list)
    related_list = [r.strip() for r in (related or "").split(",")] if related else []

    # Update metadata
    metadata = {
        'tags': tag_list,
        'priority': priority or 'reference',
        'preview': preview,
        'key_concepts': key_concepts,
        'related': related_list
    }

    # Insert with new fields
    conn.execute("""
        INSERT INTO context_locks
        (session_id, label, version, content, content_hash, metadata,
         preview, key_concepts, related_contexts, last_accessed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (...))
```

**Test Criteria**:
- [ ] Lock context without preview: auto-generates
- [ ] Lock with related: stores relationships
- [ ] Verify preview stored in database
- [ ] Verify key_concepts is valid JSON
- [ ] Test with existing contexts (backward compatible)

**Success**: New contexts include preview/concepts, old code still works

---

## Phase 3: RecursiveExplorer Class (Days 5-7)

### ☐ Task 3.1: Create RecursiveExplorer Class
**Files**: `recursive_explorer.py` (new file)

**Implementation**: See RLM_DETAILED_DESIGN.md for complete class

**Key Methods**:
```python
class RecursiveExplorer:
    def search(query, depth=2, max_contexts=10) -> Dict
    def _search_metadata(query) -> List[Dict]
    def _score_previews(query, candidates) -> List[Dict]
    def _load_full_content(label) -> str
    def _explore_related(labels, depth, visited) -> List[Dict]
    def _extract_keywords(query) -> List[str]
    def _explain_match(candidate, keywords, ...) -> str
```

**Test Cases**:
```python
def test_recursive_explorer():
    # Setup test database with 10 contexts
    setup_test_contexts()

    explorer = RecursiveExplorer(test_db, "test_session")

    # Test 1: Basic search
    results = explorer.search("authentication", depth=1)
    assert len(results['matches']) > 0
    assert results['matches'][0]['score'] > 0

    # Test 2: Keyword extraction
    keywords = explorer._extract_keywords("How does JWT authentication work?")
    assert "jwt" in keywords or "JWT" in keywords
    assert "authentication" in keywords
    assert "does" not in keywords  # stop word

    # Test 3: Preview scoring
    candidates = [
        {'label': 'api_auth', 'preview': 'JWT tokens for auth', 'key_concepts': ['JWT']},
        {'label': 'database', 'preview': 'SQL queries', 'key_concepts': ['SQL']}
    ]
    scored = explorer._score_previews("JWT authentication", candidates)
    assert scored[0]['label'] == 'api_auth'  # Better match
    assert scored[0]['score'] > scored[1]['score']

    # Test 4: Recursive exploration
    results = explorer.search("api", depth=2)
    assert 'related_topics' in results
    assert results['depth_reached'] >= 1

    # Test 5: Cycle prevention
    # Create circular reference: A -> B -> C -> A
    results = explorer.search("circular", depth=3)
    # Should not infinite loop, should track visited
    assert results['depth_reached'] <= 3
```

**Success**: All tests pass, no infinite loops, accurate scoring

---

### ☐ Task 3.2: Create KnowledgeDeepener Class
**Files**: `knowledge_deepener.py` (new file)

**Implementation**: See RLM_DETAILED_DESIGN.md for complete class

**Key Methods**:
```python
class KnowledgeDeepener:
    def answer_query(query, max_depth=3) -> Dict
    def _classify_query(query) -> str
    def _extract_relevant_section(content, query) -> str
    def _synthesize_previews(previews, query) -> str
```

**Test Cases**:
```python
def test_knowledge_deepener():
    deepener = KnowledgeDeepener(test_db, "test_session")

    # Test 1: Query classification
    assert deepener._classify_query("How to setup JWT?") == "specific"
    assert deepener._classify_query("Explain authentication") == "exploratory"
    assert deepener._classify_query("List all APIs") == "overview"

    # Test 2: Specific query
    result = deepener.answer_query("What is the JWT secret?", max_depth=2)
    assert result['confidence'] > 0.7
    assert 'JWT' in result['answer']
    assert result['depth_reached'] >= 1

    # Test 3: Exploratory query
    result = deepener.answer_query("Tell me about our APIs", max_depth=3)
    assert result['depth_reached'] >= 2
    assert len(result['contexts_used']) >= 2

    # Test 4: Synthesis
    previews = [
        "API uses JWT tokens",
        "JWT tokens expire in 1 hour",
        "Refresh tokens last 7 days"
    ]
    synthesis = deepener._synthesize_previews(previews, "token expiration")
    assert "JWT" in synthesis
    assert "1 hour" in synthesis or "7 days" in synthesis
```

**Success**: Query classification accurate, synthesis coherent

---

## Phase 4: Enhanced Tool Descriptions (Days 8-9)

### ☐ Task 4.1: Rewrite wake_up() Description
**Files**: `claude_mcp_hybrid.py`

**Current** (7 lines):
```python
"""
Start a development session and load context.
Shows: active todos, recent changes, locked contexts.
"""
```

**New** (250+ words):
```python
"""
Start a development session and load your contextual memory.

**When to use this tool:**
- At the very beginning of every session (ALWAYS call this first)
- After returning from a long break
- When you need to understand what work is in progress
- To check for high-priority issues or todos

**What this returns:**
- Session ID and project information
- Last session handover summary with completed work
- High-priority TODOs requiring immediate attention
- Available locked contexts (call recall_context to load specific ones)
- Any errors from the last 24 hours

**Best practices:**
1. Call this BEFORE doing any other work
2. Review the handover to understand previous progress
3. Check for always_check contexts that apply to current task
4. Use recall_context() to load specific contexts as needed (don't load all)

**Example workflow:**
```
1. wake_up() → See that "api_auth" context is important
2. get_context_preview("api_auth") → Quick summary
3. recall_context("api_auth") → Full details if needed
```

**Performance:**
- Response time: <100ms
- Token usage: ~3KB (metadata only, not full contexts)
- Updates: Last session handover and high-priority items

**You should:**
- ALWAYS call this at session start (before any other work)
- Review the handover summary to understand previous progress
- Note which contexts are marked as always_check
- Use progressive loading (preview → full) instead of loading all contexts

Returns: Formatted summary of session state and available contexts (metadata only)
"""
```

**Test Criteria**:
- [ ] Word count: 250-300 words
- [ ] Includes "When to use" section
- [ ] Includes "You should" imperatives
- [ ] Includes example workflow
- [ ] Performance characteristics mentioned
- [ ] Read aloud: sounds instructional, not just descriptive

**Success**: Description guides LLM behavior without ambiguity

---

### ☐ Task 4.2: Write ask_memory() Tool Description
**Files**: `claude_mcp_hybrid.py` (new tool)

**Target**: 400+ words covering:
- When to use / when NOT to use
- Depth parameter explanation with examples
- Performance for each depth level
- Example queries for each query type
- Progressive workflow guidance
- Integration with other tools

**Test Criteria**:
- [ ] Word count: 400-500 words
- [ ] All three depth levels explained with use cases
- [ ] Performance numbers included
- [ ] 3+ example queries
- [ ] Links to related tools (explore_context_tree, recall_context)

**Success**: See RLM_ENGAGEMENT_STRATEGY.md for full template

---

### ☐ Task 4.3: Write explore_context_tree() Tool Description
**Files**: `claude_mcp_hybrid.py` (new tool)

**Target**: 300+ words covering:
- When to use (relationship exploration)
- When NOT to use (simple lookups)
- Depth parameter with visual examples
- Integration workflow
- Relationship type explanations

**Test Criteria**:
- [ ] Word count: 300-400 words
- [ ] Visual tree example in description
- [ ] Clear "when NOT" guidance
- [ ] Relationship types explained (explicit, semantic, co-accessed)

**Success**: See RLM_ENGAGEMENT_STRATEGY.md for full template

---

### ☐ Task 4.4: Rewrite recall_context() Description
**Files**: `claude_mcp_hybrid.py`

**Enhancement**: Add 200+ words with:
- When to use vs other tools
- Progressive loading workflow
- Performance implications
- Anti-patterns

**Test Criteria**:
- [ ] Discourages mass loading
- [ ] Encourages preview-first approach
- [ ] Links to ask_memory as alternative

**Success**: Guides toward progressive loading pattern

---

### ☐ Task 4.5: Rewrite check_contexts() Description
**Files**: `claude_mcp_hybrid.py`

**Enhancement**: 200+ words emphasizing:
- Proactive usage before changes
- Automatic checking scenarios
- Actionable outputs

**Test Criteria**:
- [ ] Lists automatic trigger scenarios
- [ ] Encourages use before major changes
- [ ] Explains violation detection

**Success**: LLM calls proactively before risky operations

---

## Phase 5: New MCP Tools (Days 10-11)

### ☐ Task 5.1: Implement get_context_preview()
**Files**: `claude_mcp_hybrid.py`

**Implementation**:
```python
@mcp.tool()
async def get_context_preview(topic: str) -> str:
    """
    Get a brief preview of a locked context without loading full content.

    [150-200 word description]
    """
    conn = get_db()
    session_id = get_current_session_id()

    cursor = conn.execute("""
        SELECT label, version, preview, key_concepts, related_contexts,
               metadata, last_accessed
        FROM context_locks
        WHERE session_id = ? AND label = ?
        ORDER BY locked_at DESC
        LIMIT 1
    """, (session_id, topic))

    row = cursor.fetchone()
    if not row:
        return f"❌ Context '{topic}' not found"

    metadata = json.loads(row['metadata']) if row['metadata'] else {}
    concepts = json.loads(row['key_concepts']) if row['key_concepts'] else []
    related = json.loads(row['related_contexts']) if row['related_contexts'] else []

    output = []
    output.append(f"📄 {row['label']} v{row['version']}")
    output.append(f"\n📝 Preview:\n{row['preview']}")
    output.append(f"\n🔑 Key Concepts: {', '.join(concepts[:5])}")
    if related:
        output.append(f"\n🔗 Related: {', '.join(related[:3])}")
    output.append(f"\n💡 Use recall_context('{topic}') for full content")

    return "\n".join(output)
```

**Test Cases**:
```python
def test_get_context_preview():
    # Setup: Lock a context with preview
    lock_context("Full content here...", "test_topic", tags="api,auth")

    # Test 1: Get preview
    result = get_context_preview("test_topic")
    assert "📄 test_topic" in result
    assert "📝 Preview:" in result
    assert "🔑 Key Concepts:" in result
    assert "recall_context" in result  # Suggests next action

    # Test 2: Not found
    result = get_context_preview("nonexistent")
    assert "❌" in result
    assert "not found" in result.lower()

    # Test 3: Shows related contexts
    lock_context("Related content", "related_topic", related="test_topic")
    result = get_context_preview("related_topic")
    assert "🔗 Related:" in result
    assert "test_topic" in result
```

**Success**: Returns preview without loading full content, suggests next action

---

### ☐ Task 5.2: Implement ask_memory()
**Files**: `claude_mcp_hybrid.py`

**Implementation**:
```python
@mcp.tool()
async def ask_memory(
    question: str,
    depth: Literal["preview", "full", "deep"] = "preview"
) -> str:
    """
    [400+ word description from Task 4.2]
    """
    # Track usage
    track_tool_usage("ask_memory", {"depth": depth, "question_length": len(question)})

    # Use KnowledgeDeepener
    max_depth = {'preview': 1, 'full': 2, 'deep': 3}[depth]
    deepener = KnowledgeDeepener(DB_PATH, get_current_session_id())
    result = deepener.answer_query(question, max_depth=max_depth)

    # Format output
    output = []
    output.append(f"❓ Question: {question}")
    output.append(f"🎯 Confidence: {'█' * int(result['confidence'] * 10)} {result['confidence']:.1%}")
    output.append(f"📊 Explored {len(result['contexts_used'])} contexts at depth {result['depth_reached']}")
    output.append("")
    output.append("💡 Answer:")
    output.append(result['answer'])

    if result['contexts_used']:
        output.append("\n📚 Sources:")
        for ctx in result['contexts_used']:
            output.append(f"   • {ctx['label']} ({ctx['depth']}, relevance: {ctx['relevance']:.2f})")

    output.append(f"\n🔍 Exploration: {' → '.join(result['steps'])}")

    return "\n".join(output)
```

**Test Cases**:
```python
def test_ask_memory():
    # Setup: Create test contexts
    lock_context("JWT tokens expire in 1 hour", "jwt_config", tags="auth,jwt")
    lock_context("OAuth2 flow uses JWT", "oauth_setup", tags="auth,oauth")

    # Test 1: Preview depth
    result = ask_memory("JWT expiration", depth="preview")
    assert "❓ Question:" in result
    assert "🎯 Confidence:" in result
    assert "JWT" in result or "jwt" in result.lower()

    # Test 2: Full depth loads more
    result = ask_memory("JWT token details", depth="full")
    assert "1 hour" in result  # From full content

    # Test 3: Deep explores related
    result = ask_memory("authentication system", depth="deep")
    assert "OAuth" in result or "JWT" in result  # Found related contexts

    # Test 4: Low confidence on miss
    result = ask_memory("blockchain mining", depth="preview")
    assert "confidence" in result.lower()
    # Confidence should be low since no matching contexts
```

**Success**: Progressive depth works, returns synthesized answers

---

### ☐ Task 5.3: Implement explore_context_tree()
**Files**: `claude_mcp_hybrid.py`

**Implementation**:
```python
@mcp.tool()
async def explore_context_tree(
    topic: str,
    depth: int = 2,
    max_results: int = 10
) -> str:
    """
    [300+ word description from Task 4.3]
    """
    explorer = RecursiveExplorer(DB_PATH, get_current_session_id())
    results = explorer.search(topic, depth=depth, max_contexts=max_results)

    output = []
    output.append(f"🔍 Exploring: {topic} (depth={depth})")
    output.append(f"\n📊 Found {len(results['matches'])} matches\n")

    for i, match in enumerate(results['matches'], 1):
        score_bar = "█" * int(match['score'] * 10)
        output.append(f"{i}. {match['label']} v{match['version']}")
        output.append(f"   Relevance: {score_bar} {match['score']:.2f}")
        output.append(f"   {match['match_reason']}")
        output.append(f"   Preview: {match['preview'][:100]}...")

        if match.get('loaded_full'):
            output.append(f"   ✅ Full content loaded")
        else:
            output.append(f"   💡 Use recall_context('{match['label']}') for full content")

        if match.get('related'):
            output.append(f"   🔗 Related: {', '.join(match['related'][:3])}")
        output.append("")

    if results.get('related_topics'):
        output.append(f"\n🌲 Related Topics ({len(results['related_topics'])}):")
        for related in results['related_topics'][:5]:
            output.append(f"   • {related['label']} (via {related['source']})")

    output.append(f"\n📈 Exploration Path:")
    for step in results['exploration_path']:
        output.append(f"   {step}")

    return "\n".join(output)
```

**Test Cases**:
```python
def test_explore_context_tree():
    # Setup: Create linked contexts
    lock_context("Main API docs", "api_main", related="api_auth,api_rate")
    lock_context("Auth docs", "api_auth", related="jwt_config")
    lock_context("JWT config", "jwt_config")
    lock_context("Rate limiting", "api_rate")

    # Test 1: Basic exploration
    result = explore_context_tree("api_main", depth=1)
    assert "🔍 Exploring: api_main" in result
    assert "api_auth" in result or "api_rate" in result

    # Test 2: Deep exploration finds nested
    result = explore_context_tree("api_main", depth=2)
    assert "jwt_config" in result  # Two levels deep

    # Test 3: Tree visualization
    result = explore_context_tree("api_main", depth=2)
    assert "🌲 Related Topics" in result
    assert "Relevance:" in result
    assert "█" in result  # Progress bar

    # Test 4: Respects max_results
    result = explore_context_tree("api", depth=2, max_results=2)
    lines = [l for l in result.split('\n') if l.strip().startswith('1.') or l.strip().startswith('2.')]
    assert len([l for l in result.split('\n') if '. ' in l and 'v' in l]) <= 2
```

**Success**: Tree visualization clear, respects depth limits

---

## Phase 6: Enhanced check_context_relevance() (Day 12)

### ☐ Task 6.1: Implement Two-Stage Relevance Checking
**Files**: `active_context_engine.py`

**Changes**:
```python
def check_context_relevance(self, text: str, session_id: str) -> List[Dict[str, Any]]:
    """
    Two-stage relevance checking:
    Stage 1: Query metadata + preview only
    Stage 2: Load full content for top 5 matches
    """
    # Stage 1: Metadata search
    cursor = conn.execute("""
        SELECT label, version, preview, key_concepts, metadata, last_accessed
        FROM context_locks
        WHERE session_id = ?
        AND (preview LIKE ? OR key_concepts LIKE ? OR metadata LIKE ?)
    """, (session_id, f'%{keyword}%', ...))

    # Score based on preview only
    candidates = []
    for row in cursor:
        score = self._calculate_relevance_score(text, row)
        candidates.append({
            'label': row['label'],
            'score': score,
            'preview': row['preview'],
            # Don't load content yet
        })

    # Sort and take top 5
    top_candidates = sorted(candidates, key=lambda x: x['score'], reverse=True)[:5]

    # Stage 2: Load full content only for top matches
    for candidate in top_candidates:
        if candidate['score'] > 0.7:  # High confidence threshold
            full_content = self._load_full_content(candidate['label'], session_id)
            candidate['content'] = full_content
        else:
            candidate['content'] = candidate['preview']  # Use preview

    return top_candidates

def _calculate_relevance_score(self, query: str, context_row: dict) -> float:
    """Calculate 0-1 relevance score using metadata + preview only"""
    score = 0.0
    keywords = self._extract_keywords(query)

    # Keyword matching in preview (40 points)
    preview_lower = (context_row['preview'] or '').lower()
    matches = sum(1 for kw in keywords if kw in preview_lower)
    score += min(40, matches * 10)

    # Concept overlap (30 points)
    concepts = json.loads(context_row['key_concepts'] or '[]')
    concept_matches = sum(1 for concept in concepts
                         if any(kw in concept.lower() for kw in keywords))
    score += min(30, concept_matches * 10)

    # Recency (15 points)
    if context_row['last_accessed']:
        days_ago = (time.time() - context_row['last_accessed']) / 86400
        score += max(0, 15 - days_ago)

    # Priority (15 points)
    metadata = json.loads(context_row['metadata'] or '{}')
    priority = metadata.get('priority', 'reference')
    if priority == 'always_check':
        score += 15
    elif priority == 'important':
        score += 10
    elif priority == 'reference':
        score += 5

    return score / 100  # Normalize to 0-1
```

**Test Cases**:
```python
def test_two_stage_relevance():
    engine = ActiveContextEngine(test_db)

    # Setup: 10 contexts with previews
    for i in range(10):
        conn.execute("""
            INSERT INTO context_locks
            (session_id, label, content, preview, key_concepts)
            VALUES (?, ?, ?, ?, ?)
        """, ('test', f'ctx_{i}', f'Full content {i}' * 1000,
              f'Preview mentions keyword {i % 3}',
              json.dumps([f'concept_{i % 3}'])))

    # Test 1: Stage 1 only queries preview
    with mock.patch.object(engine, '_load_full_content') as mock_load:
        results = engine.check_context_relevance("keyword 1", 'test')
        # Should load full content only for high-scoring matches
        assert mock_load.call_count <= 5

    # Test 2: Scoring works on preview
    results = engine.check_context_relevance("keyword 1", 'test')
    assert len(results) <= 5
    assert all('score' in r for r in results)
    assert results[0]['score'] >= results[-1]['score']  # Sorted

    # Test 3: Token reduction
    # Before: Would load all 10 contexts = 10 * 10KB = 100KB
    # After: Loads top 5 = 5 * 10KB = 50KB (50% reduction)
    results = engine.check_context_relevance("keyword", 'test')
    assert len(results) <= 5
```

**Success**: Only top 5 contexts load full content, 50-80% token reduction

---

## Phase 7: Tool Usage Tracking (Day 13)

### ☐ Task 7.1: Add Tool Usage Logging
**Files**: `claude_mcp_hybrid.py`

**Implementation**:
```python
def track_tool_usage(tool_name: str, params: Dict):
    """Log tool usage for analysis"""
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO tool_usage_log
            (tool_name, params, timestamp, session_id)
            VALUES (?, ?, ?, ?)
        """, (tool_name, json.dumps(params), time.time(), get_current_session_id()))
        conn.commit()
    except Exception as e:
        # Don't fail tool execution if logging fails
        print(f"Warning: Failed to log tool usage: {e}", file=sys.stderr)

# Add to all tools
@mcp.tool()
async def wake_up() -> str:
    track_tool_usage("wake_up", {})
    # ... rest of implementation

@mcp.tool()
async def ask_memory(question: str, depth: str = "preview") -> str:
    track_tool_usage("ask_memory", {"depth": depth, "question_len": len(question)})
    # ... rest of implementation
```

**Test Cases**:
```python
def test_tool_usage_tracking():
    # Test 1: Logs are created
    wake_up()
    conn = get_db()
    cursor = conn.execute("SELECT * FROM tool_usage_log WHERE tool_name = 'wake_up'")
    assert cursor.fetchone() is not None

    # Test 2: Params are stored
    ask_memory("test question", depth="full")
    cursor = conn.execute("""
        SELECT params FROM tool_usage_log
        WHERE tool_name = 'ask_memory'
        ORDER BY timestamp DESC LIMIT 1
    """)
    params = json.loads(cursor.fetchone()[0])
    assert params['depth'] == 'full'

    # Test 3: Logging failure doesn't break tool
    with mock.patch('sqlite3.connect', side_effect=Exception("DB error")):
        result = wake_up()  # Should still work
        assert "Good morning" in result
```

**Success**: All tool calls logged, failures don't break tools

---

### ☐ Task 7.2: Create Usage Analysis Queries
**Files**: `analyze_tool_usage.py` (new file)

**Implementation**:
```python
#!/usr/bin/env python3
"""
Analyze tool usage patterns to measure RLM effectiveness
"""

def analyze_tool_usage(db_path: str):
    conn = sqlite3.connect(db_path)

    print("=== Tool Usage Analysis ===\n")

    # 1. Most used tools
    print("Top 10 tools by usage:")
    cursor = conn.execute("""
        SELECT tool_name, COUNT(*) as uses
        FROM tool_usage_log
        GROUP BY tool_name
        ORDER BY uses DESC
        LIMIT 10
    """)
    for row in cursor:
        print(f"  {row[0]}: {row[1]} uses")

    # 2. Depth distribution for ask_memory
    print("\nask_memory() depth usage:")
    cursor = conn.execute("""
        SELECT json_extract(params, '$.depth') as depth, COUNT(*) as uses
        FROM tool_usage_log
        WHERE tool_name = 'ask_memory'
        GROUP BY depth
    """)
    for row in cursor:
        print(f"  {row[0] or 'preview'}: {row[1]} uses")

    # 3. Session start patterns
    print("\nSession start analysis:")
    cursor = conn.execute("""
        SELECT session_id,
               MIN(timestamp) as start_time,
               (SELECT tool_name FROM tool_usage_log t2
                WHERE t2.session_id = t1.session_id
                ORDER BY timestamp LIMIT 1) as first_tool
        FROM tool_usage_log t1
        GROUP BY session_id
    """)
    wake_up_first = 0
    total_sessions = 0
    for row in cursor:
        total_sessions += 1
        if row[2] == 'wake_up':
            wake_up_first += 1

    percentage = (wake_up_first / total_sessions * 100) if total_sessions > 0 else 0
    print(f"  wake_up() called first: {wake_up_first}/{total_sessions} ({percentage:.1f}%)")
    print(f"  Target: >95%")

    # 4. Progressive loading pattern
    print("\nProgressive loading analysis:")
    cursor = conn.execute("""
        SELECT session_id,
               SUM(CASE WHEN tool_name = 'ask_memory' THEN 1 ELSE 0 END) as ask_count,
               SUM(CASE WHEN tool_name = 'recall_context' THEN 1 ELSE 0 END) as recall_count
        FROM tool_usage_log
        GROUP BY session_id
    """)
    progressive_sessions = 0
    total_sessions = 0
    for row in cursor:
        total_sessions += 1
        if row[1] > row[2]:  # More ask_memory than recall_context
            progressive_sessions += 1

    percentage = (progressive_sessions / total_sessions * 100) if total_sessions > 0 else 0
    print(f"  Sessions using progressive loading: {progressive_sessions}/{total_sessions} ({percentage:.1f}%)")
    print(f"  Target: >60%")

if __name__ == "__main__":
    analyze_tool_usage(".claude-memory.db")
```

**Success**: Analysis script shows usage patterns, identifies problems

---

## Phase 8: Update CLAUDE.md (Day 14)

### ☐ Task 8.1: Add Memory System Usage Section
**Files**: `CLAUDE.md` (in project root)

**Add After**: Memory Loading Protocol section

**Content**:
```markdown
## 🧠 Memory System Usage

### Progressive Loading Protocol

**IMPORTANT**: Never load all contexts at once. Use progressive deepening:

1. **Level 0** (Automatic): `wake_up()` loads metadata only (~3KB)
2. **Level 1** (Explore): `ask_memory(query, depth="preview")` searches previews (~5KB)
3. **Level 2** (Specific): `recall_context(topic)` loads full content when needed (~20KB)
4. **Level 3** (Deep): `ask_memory(query, depth="deep")` recursive exploration (~40KB)

### When to Use Each Tool

**Session Start** (ALWAYS):
```bash
wake_up()
→ Review high-priority contexts
→ Check for locked rules matching current task
```

**Planning Feature**:
```bash
ask_memory("feature domain", depth="preview")
→ See what patterns exist
→ explore_context_tree("domain") for relationships
→ recall_context() only if needed for specifics
```

**Before Making Changes**:
```bash
check_contexts("I'm about to modify authentication")
→ System checks for relevant rules
→ Warns about violations
→ Suggests relevant contexts
```

**Debugging Issues**:
```bash
ask_memory("error symptom", depth="full")
→ Search for similar issues
→ recall_context() if exact match found
→ Apply documented fix
```

**End of Session** (ALWAYS):
```bash
sleep()
→ Creates handover for next session
→ Locks important decisions
```

### Anti-Patterns (Don't Do This)

❌ `recall_context()` for every context at session start
  → Uses 300KB+, causes context overflow

✅ `wake_up()` + progressive loading
  → Uses <30KB average

❌ `recall_context()` for exploration
  → Wastes tokens on irrelevant contexts

✅ `ask_memory(depth="preview")` first
  → Fast, targeted results

❌ Making architectural decisions without checking contexts
  → Might violate existing rules

✅ `check_contexts()` before major changes
  → Catches rule violations early

### Memory System Commands

- `wake_up()` - Start session, load metadata
- `ask_memory(question, depth)` - Intelligent search
- `explore_context_tree(topic, depth)` - Show relationships
- `get_context_preview(topic)` - Quick summary
- `recall_context(topic)` - Full content (use sparingly)
- `lock_context(content, topic)` - Save important patterns
- `check_contexts(text)` - Verify no rule violations
- `sleep()` - End session with handover
```

**Test Criteria**:
- [ ] Added to CLAUDE.md
- [ ] Progressive loading emphasized
- [ ] Anti-patterns clearly called out
- [ ] All new tools documented
- [ ] Examples are concrete and actionable

**Success**: Clear guidance on memory system workflow

---

## Phase 9: Testing & Validation (Days 15-16)

### ☐ Task 9.1: Create Integration Test Suite
**Files**: `tests/test_rlm_integration.py` (new file)

**Test Scenarios**:
```python
def test_full_rlm_workflow():
    """Test complete RLM workflow end-to-end"""

    # Setup: Fresh database
    db = create_test_database()

    # Scenario 1: New session
    result = wake_up()
    assert "Good morning" in result
    assert "📋 Active TODOs" in result or "No active TODOs" in result

    # Scenario 2: Lock contexts with preview
    result = lock_context(
        "JWT tokens expire in 1 hour. MUST validate on every request.",
        "jwt_config",
        tags="auth,security",
        priority="always_check",
        related="api_auth,security_rules"
    )
    assert "✅ Locked" in result

    # Verify preview was generated
    conn = sqlite3.connect(db)
    cursor = conn.execute("SELECT preview FROM context_locks WHERE label = 'jwt_config'")
    preview = cursor.fetchone()[0]
    assert preview is not None
    assert len(preview) > 0
    assert "JWT" in preview

    # Scenario 3: Preview lookup (no full load)
    result = get_context_preview("jwt_config")
    assert "📄 jwt_config" in result
    assert "📝 Preview:" in result
    assert "Full content" not in result  # Didn't load full

    # Scenario 4: Ask memory at preview depth
    result = ask_memory("JWT expiration policy", depth="preview")
    assert "❓ Question:" in result
    assert "jwt" in result.lower() or "JWT" in result
    # Should not have loaded full content (fast)

    # Scenario 5: Explore relationships
    result = explore_context_tree("jwt_config", depth=2)
    assert "🔍 Exploring" in result
    assert "api_auth" in result or "security_rules" in result  # Related contexts

    # Scenario 6: Check contexts before change
    result = check_contexts("I'm going to change JWT expiration to 24 hours")
    assert "jwt_config" in result  # Should find relevant context
    assert "MUST validate" in result or "always_check" in result

    # Scenario 7: Full content only when needed
    result = recall_context("jwt_config")
    assert "MUST validate on every request" in result  # Full content

    # Scenario 8: End session
    result = sleep()
    assert "📦 Handover created" in result

def test_token_efficiency():
    """Verify token usage is reduced vs old system"""

    # Setup: 30 contexts @ 10KB each = 300KB total
    for i in range(30):
        lock_context(
            "x" * 10000,  # 10KB content
            f"context_{i}",
            tags=f"tag_{i % 3}"
        )

    # Old behavior: recall_context on all = 300KB
    # New behavior: ask_memory with preview

    result = ask_memory("tag_1", depth="preview")

    # Estimate token usage (rough)
    # Should return ~10 previews @ 500 chars each = 5KB
    # vs loading all 30 contexts = 300KB

    assert len(result) < 50000  # Less than 50KB result
    # vs old system would return 300KB+

def test_progressive_deepening():
    """Verify progressive loading workflow"""

    # Setup
    lock_context("JWT config details...", "jwt", tags="auth")

    # Step 1: Preview
    result1 = ask_memory("JWT", depth="preview")
    assert "JWT" in result1
    size1 = len(result1)

    # Step 2: Full
    result2 = ask_memory("JWT", depth="full")
    assert "JWT" in result2
    size2 = len(result2)

    # Step 3: Deep
    result3 = ask_memory("JWT", depth="deep")
    size3 = len(result3)

    # Verify progressive increase
    assert size1 < size2 < size3
    assert size1 < 10000  # Preview < 10KB
    assert size2 < 50000  # Full < 50KB
    assert size3 < 100000  # Deep < 100KB

def test_two_stage_relevance():
    """Verify two-stage relevance checking reduces DB queries"""

    # Setup: 20 contexts
    for i in range(20):
        lock_context(f"Content {i}", f"ctx_{i}", tags=f"tag_{i % 5}")

    engine = ActiveContextEngine(test_db)

    # Count DB queries
    with mock.patch('sqlite3.connect') as mock_conn:
        engine.check_context_relevance("tag_1", "test_session")

        # Should do:
        # 1. One query for metadata/previews (all 20)
        # 2. Individual queries only for top 5

        # Max 6 queries (1 for all + 5 for top matches)
        assert mock_conn.call_count <= 6
```

**Success**: All integration tests pass, demonstrates token reduction

---

### ☐ Task 9.2: Performance Benchmarking
**Files**: `tests/benchmark_rlm.py` (new file)

**Benchmarks**:
```python
def benchmark_wake_up():
    """Measure wake_up() performance"""
    times = []
    for _ in range(10):
        start = time.time()
        result = wake_up()
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    print(f"wake_up() average: {avg_time*1000:.0f}ms")
    assert avg_time < 0.1, "Target: <100ms"

def benchmark_ask_memory_depths():
    """Compare performance across depths"""

    # Setup: 20 contexts
    for i in range(20):
        lock_context("x" * 10000, f"ctx_{i}", tags="test")

    depths = ["preview", "full", "deep"]
    for depth in depths:
        times = []
        sizes = []
        for _ in range(5):
            start = time.time()
            result = ask_memory("test", depth=depth)
            elapsed = time.time() - start
            times.append(elapsed)
            sizes.append(len(result))

        avg_time = sum(times) / len(times)
        avg_size = sum(sizes) / len(sizes)

        print(f"{depth:8} - {avg_time*1000:5.0f}ms, {avg_size:7.0f} chars")

    # Targets:
    # preview: <200ms, <10KB
    # full:    <500ms, <50KB
    # deep:    <1000ms, <100KB

def benchmark_vs_old_system():
    """Compare token usage: Old vs RLM"""

    # Setup: 30 contexts
    for i in range(30):
        lock_context("x" * 10000, f"ctx_{i}", tags=f"tag_{i % 3}")

    # Old system: Load all contexts
    old_size = 0
    for i in range(30):
        result = recall_context(f"ctx_{i}")
        old_size += len(result)

    print(f"Old system: {old_size} chars total")

    # New system: Progressive loading
    new_size = 0
    result1 = wake_up()
    new_size += len(result1)

    result2 = ask_memory("tag_1", depth="preview")
    new_size += len(result2)

    result3 = recall_context("ctx_1")  # Load just one
    new_size += len(result3)

    print(f"New system: {new_size} chars total")
    print(f"Reduction: {(1 - new_size/old_size)*100:.1f}%")

    assert new_size < old_size * 0.2, "Target: 80% reduction"
```

**Success**: Benchmarks show 80%+ token reduction, <200ms for preview

---

## Phase 10: Documentation (Day 17)

### ☐ Task 10.1: Update README.md
**Files**: `README.md`

**Add Section**:
```markdown
## RLM Memory Optimization (v4.1+)

Claude Dementia v4.1 implements Recursive Language Model (RLM) optimizations for efficient memory usage:

### Progressive Loading
- **Level 0**: Metadata only (~3KB)
- **Level 1**: Previews (~5KB)
- **Level 2**: Full content (~20KB)
- **Level 3**: Deep recursive exploration (~40KB)

### New Tools
- `ask_memory(question, depth)` - Intelligent context search
- `explore_context_tree(topic, depth)` - Relationship visualization
- `get_context_preview(topic)` - Quick summaries

### Performance
- **80% token reduction** vs loading all contexts
- **<200ms** for preview-level queries
- **<500ms** for full-depth queries
- **Smart caching** reduces redundant loads

See [RLM_DETAILED_DESIGN.md](RLM_DETAILED_DESIGN.md) for implementation details.
```

**Success**: README includes RLM overview and benefits

---

### ☐ Task 10.2: Create User Guide
**Files**: `docs/RLM_USER_GUIDE.md` (new file)

**Content**:
```markdown
# RLM Memory System User Guide

## Quick Start

### First Session
```bash
wake_up()  # ALWAYS start here
```

### Finding Information
```bash
# Quick search
ask_memory("what patterns exist for authentication?", depth="preview")

# Detailed lookup
ask_memory("show JWT configuration", depth="full")

# Deep exploration
ask_memory("explain the complete auth system", depth="deep")
```

### Exploring Relationships
```bash
explore_context_tree("api_authentication", depth=2)
# Shows:
# api_authentication
# ├─ jwt_config
# │  └─ security_rules
# └─ oauth_setup
```

### Loading Specific Content
```bash
# Preview first
get_context_preview("jwt_config")

# Full content if needed
recall_context("jwt_config")
```

## Best Practices

1. **Always start with wake_up()** - Loads metadata only
2. **Use ask_memory() for exploration** - Don't recall_context() blindly
3. **Check contexts before changes** - Use check_contexts()
4. **Lock important decisions** - So others can find them
5. **End with sleep()** - Creates handover for next session

## Common Workflows

[See RLM_ENGAGEMENT_STRATEGY.md for full examples]
```

**Success**: User guide covers common tasks with examples

---

## Validation Checklist

### ☐ Functional Tests
- [ ] All unit tests pass (Tasks 2.1-2.2, 3.1-3.2, 5.1-5.3)
- [ ] Integration tests pass (Task 9.1)
- [ ] Edge cases handled (empty DB, missing contexts, etc.)

### ☐ Performance Tests
- [ ] wake_up() <100ms (Task 9.2)
- [ ] ask_memory(preview) <200ms
- [ ] ask_memory(full) <500ms
- [ ] ask_memory(deep) <1000ms
- [ ] 80%+ token reduction vs old system

### ☐ Behavioral Tests
- [ ] Tool descriptions guide usage correctly
- [ ] LLM uses progressive loading naturally
- [ ] LLM calls wake_up() first (95%+ of sessions)
- [ ] LLM prefers preview over full depth
- [ ] LLM uses check_contexts() proactively

### ☐ Migration Tests
- [ ] Migration works on v4.0 database
- [ ] Migration is idempotent (safe to run twice)
- [ ] Previews generated for existing contexts
- [ ] No data loss during migration
- [ ] Rollback script works

### ☐ Documentation
- [ ] All tool descriptions 150+ words
- [ ] CLAUDE.md includes memory workflow
- [ ] README updated with RLM features
- [ ] User guide created
- [ ] Code comments explain key algorithms

---

## Success Metrics (Measure After 1 Week)

Track these metrics using `analyze_tool_usage.py`:

1. **Session Start Pattern**
   - Target: >95% start with wake_up()
   - Query: "SELECT first_tool FROM session_analysis"

2. **Progressive Loading Adoption**
   - Target: >60% use ask_memory before recall_context
   - Query: "SELECT progressive_ratio FROM loading_patterns"

3. **Depth Distribution**
   - Target: preview:full:deep ratio of 70:25:5
   - Query: "SELECT depth, COUNT(*) FROM ask_memory_usage"

4. **Token Efficiency**
   - Target: <30KB average per query session
   - Measure: Sum of result lengths per session

5. **Cache Hit Rate**
   - Target: >70% of contexts cached after first load
   - Query: "SELECT cache_hits / total_loads FROM access_log"

---

## Rollback Plan

If RLM causes issues:

1. **Disable new tools** (quick):
   ```python
   # Comment out in claude_mcp_hybrid.py
   # @mcp.tool()
   # async def ask_memory(...):
   ```

2. **Revert to v4.0 descriptions**:
   - Restore short tool descriptions
   - Remove progressive loading guidance from CLAUDE.md

3. **Keep schema changes** (safe):
   - preview, key_concepts columns are backward compatible
   - Old tools still work without using new columns

4. **Database rollback** (if needed):
   ```bash
   python3 rollback_v4_1.py .claude-memory.db
   ```

---

## Timeline Summary

- **Days 1-2**: Database schema & migration
- **Days 3-4**: Helper functions & preview generation
- **Days 5-7**: RecursiveExplorer & KnowledgeDeepener
- **Days 8-9**: Enhanced tool descriptions
- **Days 10-11**: New MCP tools (ask_memory, explore_tree, preview)
- **Day 12**: Two-stage relevance checking
- **Day 13**: Usage tracking & analytics
- **Day 14**: CLAUDE.md updates
- **Days 15-16**: Testing & benchmarking
- **Day 17**: Documentation

**Total: 17 days (2.5 weeks)**

---

## Priority Levels

**P0 (Must Have)**:
- Database schema (Task 1.1-1.2)
- Preview generation (Task 2.1-2.2)
- Two-stage relevance (Task 6.1)
- Tool descriptions (Task 4.1-4.5)
- ask_memory() (Task 5.2)

**P1 (Should Have)**:
- RecursiveExplorer (Task 3.1)
- explore_context_tree() (Task 5.3)
- Usage tracking (Task 7.1-7.2)
- Integration tests (Task 9.1)

**P2 (Nice to Have)**:
- KnowledgeDeepener (Task 3.2)
- get_context_preview() (Task 5.1)
- Performance benchmarks (Task 9.2)
- User guide (Task 10.2)

**MVP: P0 tasks only = 1 week**
