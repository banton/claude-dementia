# Project Context Initialization Plan

## Executive Summary

**Goal:** Automatically extract and lock critical project knowledge as contexts on first run or after major changes.

**Key Insight:** We have two complementary systems:
- **project_update()**: Tags FILES with metadata (status:stable, layer:database)
- **initialize_project_contexts()**: Extracts KNOWLEDGE and locks it (schemas, APIs, patterns)

**Approach:** Hybrid extraction using rule-based candidate identification + LLM-based intelligent summarization.

---

## 1. Problem Statement

### Current Gap
When Claude starts a new session, it must:
1. Read CLAUDE.md (project instructions)
2. Read code files to understand architecture
3. Discover database schema by scanning code
4. Learn API contracts by reading tool definitions
5. Identify critical rules scattered in comments

**This is inefficient and error-prone.** Claude may miss critical patterns or misunderstand context.

### Desired State
On project initialization:
1. System automatically scans project
2. Extracts critical patterns (schemas, APIs, rules)
3. Locks them as contexts with appropriate priorities
4. Claude can recall perfect information via `recall_context("database_schema")`

**Result:** Faster onboarding, perfect recall, no missed patterns.

---

## 2. What to Extract

### Priority 1: ALWAYS_CHECK (Critical Rules)
**Purpose:** Information that MUST be correct 100% of the time

| Context Label | Source | Content |
|--------------|--------|---------|
| `database_schema` | claude_mcp_hybrid.py | All CREATE TABLE statements with exact DDL |
| `critical_rules` | **/*.py comments | All IMPORTANT/WARNING/NEVER/ALWAYS rules |
| `session_isolation` | Code + docs | Rules about session_id, no shared state |

**Why always_check:** Schema corruption or broken isolation = data loss

### Priority 2: IMPORTANT (Frequently Needed)
**Purpose:** Information needed for most development tasks

| Context Label | Source | Content |
|--------------|--------|---------|
| `api_contracts` | @mcp.tool() definitions | Tool signatures, parameters, return types, docstrings |
| `architecture` | README.md, CLAUDE.md | System design, component relationships, data flow |
| `versioning_logic` | Code + docs | Semantic versioning rules (v1.0 → v1.1), history preservation |
| `rlm_optimization` | Code + comments | Token budget, preview generation, key_concepts extraction |

**Why important:** Needed for API changes, architecture discussions, feature additions

### Priority 3: REFERENCE (Occasionally Useful)
**Purpose:** Handy reference information, loaded on-demand

| Context Label | Source | Content |
|--------------|--------|---------|
| `utility_functions` | Code | generate_preview(), extract_key_concepts(), etc. |
| `test_patterns` | test_*.py | TDD workflow, fixture setup, common assertions |
| `deployment` | Docs | How to install, configure, run the MCP server |

**Why reference:** Useful but not critical, can be looked up when needed

---

## 3. Extraction Strategy: Hybrid Approach

### Phase 1: Rule-Based Candidate Identification (Fast)
Use regex/AST parsing to find candidate sections:

```python
# 1. Database schemas
schemas = find_blocks_matching(
    pattern=r'CREATE TABLE.*?;',
    files=['claude_mcp_hybrid.py'],
    flags=re.DOTALL
)

# 2. Tool definitions
tools = find_blocks_matching(
    pattern=r'@mcp\.tool\(\).*?async def.*?(?=\n@mcp\.tool|$)',
    files=['claude_mcp_hybrid.py'],
    flags=re.DOTALL
)

# 3. Critical rules
rules = find_comments_matching(
    pattern=r'(WARNING|IMPORTANT|NEVER|ALWAYS):.*?(?=\n\s*(?:[^#]|$))',
    files=['**/*.py']
)

# 4. Architecture docs
docs = read_files([
    'README.md',
    'CLAUDE.md',
    'ARCHITECTURE.md'
])
```

**Pros:**
- Fast (no LLM calls)
- Deterministic (same results every time)
- Works offline

**Cons:**
- May extract too much (noisy)
- Misses context/relationships
- Hard to maintain regex patterns

### Phase 2: LLM-Based Intelligent Summarization (Quality)
Send candidates to Claude Haiku for intelligent summarization:

```python
async def summarize_for_context(content: str, purpose: str) -> str:
    """
    Use Claude Haiku (cheap, fast) to summarize content for locked context.

    Example prompts:
    - Schema: "Extract database schema. List tables, columns, relationships, constraints."
    - API: "List all tools with signatures and one-line descriptions."
    - Rules: "Extract critical rules as bullet points with 'NEVER/ALWAYS' statements."
    """
    # Use anthropic SDK or HTTP API
    response = await anthropic.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"{purpose}\n\n{content}"
        }]
    )
    return response.content[0].text
```

**Pros:**
- Intelligent (understands context)
- Concise (generates token-optimized summaries)
- Adaptive (works with any project structure)

**Cons:**
- Requires API key
- Costs ~$0.001-0.01 per extraction
- Non-deterministic (summaries may vary slightly)

### Hybrid Workflow
1. **Rules identify** what to extract (fast, offline)
2. **LLM summarizes** how to present it (intelligent, concise)
3. **lock_context()** stores result (versioned, searchable)

---

## 4. Implementation Design

### Tool Signature

```python
@mcp.tool()
async def initialize_project_contexts(
    force_refresh: bool = False,
    priorities: Optional[List[str]] = None,
    path: Optional[str] = None
) -> str:
    """
    Scan project and extract important patterns into locked contexts.

    This creates a knowledge base of critical information that Claude can
    recall perfectly across sessions without re-reading source files.

    **What it extracts:**

    ALWAYS_CHECK priority:
    - database_schema: Exact DDL for all tables
    - critical_rules: IMPORTANT/NEVER/ALWAYS rules from code
    - session_isolation: Rules about session-based safety

    IMPORTANT priority:
    - api_contracts: All MCP tool signatures and descriptions
    - architecture: System design and component relationships
    - versioning_logic: How versions work (v1.0 → v1.1)
    - rlm_optimization: Token budget and RLM patterns

    REFERENCE priority:
    - utility_functions: Helper function signatures
    - test_patterns: TDD workflow and common patterns
    - deployment: How to install and configure

    **Args:**
        force_refresh (bool): Update existing contexts (default: skip if exists)
        priorities (List[str]): Only extract these priorities (default: all)
            Options: ["always_check", "important", "reference"]
        path (str): Project root path (default: current directory)

    **Returns:**
        Summary of contexts created/updated with statistics

    **Example:**
        # First time: Extract everything
        initialize_project_contexts()

        # After schema change: Refresh critical contexts
        initialize_project_contexts(force_refresh=True, priorities=["always_check"])

        # Check what was created
        explore_context_tree()

    **Safety:**
    - Skips existing contexts unless force_refresh=True
    - Resumable if interrupted (uses progress tracking)
    - Phased execution with status updates
    """
```

### Phased Execution (Resumable)

Like `project_update()`, use phases to handle large projects:

```python
# Progress tracking table
CREATE TABLE IF NOT EXISTS initialization_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    phase TEXT NOT NULL,  -- 'schema', 'api', 'architecture', 'rules'
    status TEXT NOT NULL,  -- 'pending', 'in_progress', 'completed', 'failed'
    context_label TEXT,    -- What context was created
    file_path TEXT,        -- Source file
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
)
```

**Execution flow:**

```python
async def initialize_project_contexts(...):
    phases = [
        ('schema', extract_database_schema, 'always_check'),
        ('critical_rules', extract_critical_rules, 'always_check'),
        ('session_isolation', extract_session_rules, 'always_check'),
        ('api_contracts', extract_api_contracts, 'important'),
        ('architecture', extract_architecture, 'important'),
        ('versioning', extract_versioning_logic, 'important'),
        ('rlm', extract_rlm_patterns, 'important'),
        ('utilities', extract_utility_functions, 'reference'),
        ('tests', extract_test_patterns, 'reference'),
        ('deployment', extract_deployment_docs, 'reference'),
    ]

    results = []

    for phase_name, extractor_func, priority in phases:
        # Skip if filtering by priority
        if priorities and priority not in priorities:
            continue

        # Check progress
        progress = get_progress(phase_name)
        if progress['status'] == 'completed' and not force_refresh:
            results.append(f"✅ {phase_name}: Skipped (already exists)")
            continue

        # Mark in progress
        update_progress(phase_name, 'in_progress')

        try:
            # Extract and summarize
            context_data = await extractor_func(path)

            # Check if context already exists
            existing = await recall_context(context_data['label'])

            if existing and not force_refresh:
                results.append(f"⏭️  {phase_name}: Skipped (context exists)")
                update_progress(phase_name, 'completed')
                continue

            # Lock context (create or update)
            if existing and force_refresh:
                await update_context(
                    topic=context_data['label'],
                    content=context_data['content'],
                    tags=context_data['tags'],
                    priority=priority,
                    reason="Auto-refresh from initialize_project_contexts()"
                )
            else:
                await lock_context(
                    content=context_data['content'],
                    topic=context_data['label'],
                    tags=context_data['tags'],
                    priority=priority
                )

            results.append(f"✅ {phase_name}: Created '{context_data['label']}'")
            update_progress(phase_name, 'completed')

        except Exception as e:
            results.append(f"❌ {phase_name}: Failed - {str(e)}")
            update_progress(phase_name, 'failed', error=str(e))

    return "\n".join([
        "🚀 Project Context Initialization Complete",
        "",
        *results,
        "",
        "📚 Use explore_context_tree() to see all locked contexts"
    ])
```

### Example Extractor: Database Schema

```python
async def extract_database_schema(project_path: str) -> dict:
    """
    Extract database schema from initialization code.

    Returns:
        {
            'label': 'database_schema',
            'content': '# Database Schema\n\n## context_locks...',
            'tags': 'schema,database,ddl,sqlite'
        }
    """
    # 1. Find schema file
    schema_file = find_file('**/claude_mcp_hybrid.py', project_path)
    content = read_file(schema_file)

    # 2. Extract CREATE TABLE statements
    schema_blocks = re.findall(
        r"CREATE TABLE.*?(?=\n\s*(?:CREATE TABLE|'''\)|$))",
        content,
        re.DOTALL
    )

    # 3. Combine schemas
    raw_schema = "\n\n".join(schema_blocks)

    # 4. Summarize with LLM
    summary = await summarize_for_context(
        content=raw_schema,
        purpose="""Extract database schema in this format:

## Table: table_name
**Purpose:** Brief description
**Columns:**
- column_name (TYPE) - Description
- ...

**Constraints:**
- UNIQUE(col1, col2)
- ...

Be concise but complete. Include all tables."""
    )

    return {
        'label': 'database_schema',
        'content': summary,
        'tags': 'schema,database,ddl,sqlite'
    }
```

---

## 5. Safety and Conflict Resolution

### Existing Contexts
**Problem:** What if context already exists?

**Options:**
1. **Skip** (default): Preserve manual edits, avoid overwrites
2. **Update** (force_refresh=True): Auto-refresh from current code
3. **Warn**: Flag "stale" contexts where source changed

**Recommendation:** Skip by default, require explicit `force_refresh=True`

```python
existing = await recall_context('database_schema')

if existing and not force_refresh:
    return "⏭️  Skipped: 'database_schema' already exists (use force_refresh=True to update)"

if existing and force_refresh:
    # Create new version
    await update_context(
        topic='database_schema',
        content=new_summary,
        reason="Auto-refresh from initialize_project_contexts()"
    )
```

### Interruption Handling
**Problem:** Extraction fails mid-process (network error, timeout)

**Solution:** Resumable progress tracking

```python
# On next run, check progress
incomplete_phases = get_incomplete_phases()

if incomplete_phases:
    return f"🔄 Resuming from {incomplete_phases[0]}..."
```

### Stale Detection
**Problem:** Code changed but context not updated

**Solution:** Track content hash, warn on mismatch

```python
async def detect_stale_contexts() -> List[str]:
    """
    Check if locked contexts are stale (source code changed).

    Returns:
        List of context labels that need refresh
    """
    stale = []

    # Check database_schema
    current_schema = extract_raw_schema()
    locked_schema = await recall_context('database_schema')

    if hash(current_schema) != hash(locked_schema):
        stale.append('database_schema')

    return stale

# Usage
stale = await detect_stale_contexts()
if stale:
    print(f"⚠️  Stale contexts detected: {', '.join(stale)}")
    print("   Run initialize_project_contexts(force_refresh=True) to update")
```

---

## 6. User Experience

### First-Time Setup
```bash
$ claude-code

# System auto-detects no contexts exist
⚠️  No project contexts found. Initialize now? [Y/n] y

🚀 Initializing project contexts...

✅ schema: Created 'database_schema' (always_check)
✅ critical_rules: Created 'critical_rules' (always_check)
✅ session_isolation: Created 'session_isolation' (always_check)
✅ api_contracts: Created 'api_contracts' (important)
✅ architecture: Created 'architecture' (important)
✅ versioning: Created 'versioning_logic' (important)
✅ rlm: Created 'rlm_optimization' (important)
⏭️  utilities: Skipped (reference priority, use --all flag)
⏭️  tests: Skipped (reference priority, use --all flag)
⏭️  deployment: Skipped (reference priority, use --all flag)

✨ Initialized 7 contexts in 12s

📚 View with: explore_context_tree()
```

### Manual Refresh
```python
# After changing database schema
initialize_project_contexts(
    force_refresh=True,
    priorities=["always_check"]
)

# Output:
🚀 Project Context Initialization Complete

✅ schema: Updated 'database_schema' v1.0 → v1.1
✅ critical_rules: Skipped (no changes)
✅ session_isolation: Skipped (no changes)
```

### Stale Detection
```python
# Daily check
detect_stale_contexts()

# Output:
⚠️  Stale contexts detected:
  - database_schema: Source changed (3 new tables added)
  - api_contracts: Source changed (2 new tools added)

💡 Run initialize_project_contexts(force_refresh=True) to update
```

---

## 7. Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
- [ ] Create `initialization_progress` table
- [ ] Implement `initialize_project_contexts()` skeleton
- [ ] Add progress tracking (start/complete/resume)
- [ ] Write tests for resumable execution

### Phase 2: Rule-Based Extractors (Week 1)
- [ ] Implement `extract_database_schema()` (regex-based)
- [ ] Implement `extract_api_contracts()` (AST-based)
- [ ] Implement `extract_critical_rules()` (comment-based)
- [ ] Write tests for each extractor

### Phase 3: LLM Integration (Week 2)
- [ ] Integrate Anthropic API (Haiku)
- [ ] Implement `summarize_for_context()` with prompts
- [ ] Add token counting and cost estimation
- [ ] Handle API errors gracefully

### Phase 4: Advanced Extractors (Week 2)
- [ ] Implement `extract_architecture()` (docs + code)
- [ ] Implement `extract_versioning_logic()` (pattern detection)
- [ ] Implement `extract_rlm_patterns()` (comment + code)
- [ ] Implement utility/test/deployment extractors

### Phase 5: Safety Features (Week 3)
- [ ] Implement conflict resolution (skip vs update)
- [ ] Implement stale detection with content hashing
- [ ] Add `detect_stale_contexts()` tool
- [ ] Auto-suggest refresh when stale detected

### Phase 6: UX Improvements (Week 3)
- [ ] Add auto-initialization on first run
- [ ] Implement progress bars for long extractions
- [ ] Add cost estimation before LLM calls
- [ ] Create summary dashboard of all contexts

### Phase 7: Testing & Documentation (Week 4)
- [ ] Integration tests for full workflow
- [ ] Test resumable execution after failures
- [ ] Test force_refresh with version history
- [ ] Document extraction patterns and prompts
- [ ] Create user guide with examples

---

## 8. Cost Analysis

### LLM Costs (Claude Haiku)
- Input: $0.80 / 1M tokens
- Output: $4.00 / 1M tokens

**Typical extraction:**
- Schema: 2K input → 500 output = $0.004
- API contracts: 5K input → 1K output = $0.008
- Architecture: 3K input → 800 output = $0.007
- Rules: 1K input → 300 output = $0.002

**Total per initialization: ~$0.02-0.05** (negligible)

### Performance
- Rule-based extraction: <1s per phase
- LLM summarization: ~2s per phase (parallel possible)
- Total initialization: 10-20s for full project

---

## 9. Alternative Approaches Considered

### Alternative 1: Pure Rule-Based (No LLM)
**Pros:** Fast, free, deterministic
**Cons:** Brittle regex, verbose output, misses context
**Verdict:** ❌ Too rigid, poor quality summaries

### Alternative 2: Pure LLM (No Rules)
**Pros:** Intelligent, adaptive
**Cons:** Expensive, slow, may miss edge cases
**Verdict:** ❌ Too slow and costly for large projects

### Alternative 3: Manual Curation
**Pros:** Perfect control
**Cons:** High maintenance, error-prone, tedious
**Verdict:** ❌ Doesn't scale, defeats automation purpose

### Hybrid (Recommended)
**Pros:** Fast rules + intelligent summaries, resumable
**Cons:** Slightly complex, requires API key
**Verdict:** ✅ Best balance of speed, quality, cost

---

## 10. Success Metrics

### Quantitative
- ✅ Initialization completes in <30s
- ✅ Creates 7-10 contexts (always_check + important)
- ✅ Costs <$0.10 per full initialization
- ✅ 95%+ accuracy in schema extraction
- ✅ Resumable after interruption (0 data loss)

### Qualitative
- ✅ Claude can answer "what's the database schema?" instantly
- ✅ Claude never forgets API contracts
- ✅ Critical rules enforced consistently
- ✅ New developers onboard faster (read locked contexts)
- ✅ Stale contexts detected automatically

---

## 11. Future Enhancements

### v2: Incremental Updates
Instead of full re-initialization, detect changed files and update only affected contexts.

```python
# Watch mode
initialize_project_contexts(watch=True)

# On file change:
File changed: claude_mcp_hybrid.py
  → Detected new table: user_preferences
  → Updating 'database_schema' v1.2 → v1.3
  ✅ Updated in 3s
```

### v3: Cross-Project Knowledge
Share common patterns across projects.

```python
# Global context library
~/.claude-contexts/
  patterns/rest-api.md
  patterns/tdd-workflow.md
  patterns/sqlite-schema.md

# Reference in new project
initialize_project_contexts(
    import_patterns=["rest-api", "tdd-workflow"]
)
```

### v4: Visual Context Map
Generate relationship diagrams between contexts.

```
database_schema
    ↓ (used by)
api_contracts
    ↓ (implements)
architecture
    ↓ (follows)
critical_rules
```

---

## 12. Recommendation

### ✅ Implement This Feature

**Why:**
1. **Solves real problem:** Claude forgets schemas, APIs, rules across sessions
2. **High ROI:** 20 hours dev time → saves 2-5 min/session forever
3. **Extensible:** Foundation for advanced features (stale detection, incremental updates)
4. **Low cost:** ~$0.02/init, runs once per project or on major changes

**Priorities:**
1. **Must have:** Schema + API + critical rules extraction (Phases 1-3)
2. **Should have:** Stale detection + force_refresh (Phase 5)
3. **Nice to have:** Advanced extractors + UX improvements (Phases 4-6)

**Timeline:**
- Week 1: Core + extractors (Phases 1-2)
- Week 2: LLM integration (Phase 3)
- Week 3: Polish + testing (Phases 5-7)

**Next Step:**
Create `test_initialize_contexts.py` with TDD approach, then implement phase by phase.
