# MCP Tools Interoperation Map

## Tool Call Patterns

### Pattern 1: Direct Database Access
**Tools:** Most tools
**Flow:** Tool → get_db(project) → PostgreSQL
**Examples:**
- lock_context() → get_db() → INSERT INTO context_locks
- recall_context() → get_db() → SELECT FROM context_locks
- memory_status() → get_db() → Multiple SELECT queries

### Pattern 2: Service Integration
**Tools:** Embedding-related tools
**Flow:** Tool → get_db(project) → PostgreSQL + embedding_service → Voyage AI
**Examples:**
- lock_context() → get_db() → INSERT → embedding_service.generate_embedding() → UPDATE
- semantic_search_contexts() → get_db() → SELECT → embedding_service.cosine_similarity()

### Pattern 3: Compound Operations
**Tools:** Tools that call other internal functions
**Flow:** Tool → Multiple internal functions → get_db(project) → PostgreSQL
**Examples:**
- check_contexts() → SemanticSearch.search_similar() + get_relevant_contexts_for_text()
- wake_up() → Multiple status queries + session creation
- sleep() → create_handover() + memory_entries aggregation

### Pattern 4: Batch Operations
**Tools:** batch_* tools
**Flow:** Tool → Loop over items → Multiple get_db(project) calls
**Examples:**
- batch_lock_contexts() → [lock_context() for each]
- batch_recall_contexts() → [recall_context() for each]

## Tool Dependencies

### Core Infrastructure
- **get_db(project)** - Used by ALL tools (95%+)
  - Resolves project name
  - Returns PostgreSQL connection
  - Sets search_path to schema

- **embedding_service** - Used by embedding tools (10%)
  - generate_embedding()
  - cosine_similarity()

- **SemanticSearch** - Used by semantic tools (5%)
  - search_similar()
  - add_embedding()

### Session Management
- **get_or_create_session()** - Used by session tools
  - Called by: wake_up, lock_context, memory_status
  - Returns: session_id
  - Creates sessions table entry

### Active Project Tracking
- **_active_projects** (dict) - Global state
  - Set by: switch_project()
  - Read by: get_active_project(), get_db()
  - Enables conversational project switching

## Call Graph by Tool

### wake_up(project)
```
wake_up(project)
├─ get_db(project)
│  ├─ get_active_project() → _active_projects
│  └─ PostgreSQLAdapter(schema)
├─ get_or_create_session()
├─ SELECT FROM context_locks (count)
├─ SELECT FROM memory_entries (count by category)
└─ Returns: status JSON
```

### lock_context(content, topic, project)
```
lock_context(content, topic, project)
├─ get_db(project)
├─ get_or_create_session()
├─ generate_preview() [internal]
├─ extract_key_concepts() [internal]
├─ INSERT INTO context_locks RETURNING id
├─ embedding_service.generate_embedding() [optional]
│  └─ Voyage AI API call
├─ UPDATE context_locks SET embedding [if success]
└─ Returns: success message with [embedded]
```

### semantic_search_contexts(query, project)
```
semantic_search_contexts(query, project)
├─ get_db(project)
├─ SemanticSearch(conn, embedding_service)
│  ├─ embedding_service.generate_embedding(query)
│  │  └─ Voyage AI API call
│  ├─ SELECT FROM context_locks WHERE embedding IS NOT NULL
│  ├─ pickle.loads(embedding) [for each row]
│  ├─ embedding_service.cosine_similarity() [for each]
│  └─ Filter by threshold, sort by similarity
└─ Returns: ranked results JSON
```

### check_contexts(text, project)
```
check_contexts(text, project)
├─ get_db(project)
├─ get_or_create_session()
├─ TRY: Semantic search
│  ├─ SemanticSearch(conn, embedding_service)
│  ├─ search_similar(query=text)
│  └─ Format results with similarity scores
├─ TRY: Keyword fallback
│  ├─ get_relevant_contexts_for_text() [SQLite-based, fails in PG mode]
│  └─ check_command_context() [SQLite-based, fails in PG mode]
└─ Returns: combined results (semantic + keyword if available)
```

### batch_lock_contexts(contexts, project)
```
batch_lock_contexts(contexts, project)
├─ Parse contexts JSON
├─ FOR EACH context:
│  └─ lock_context(content, topic, ..., project)
│     └─ [See lock_context flow above]
└─ Returns: summary (X succeeded, Y failed)
```

### sleep(project)
```
sleep(project)
├─ get_db(project)
├─ get_or_create_session()
├─ SELECT FROM memory_entries (this session)
├─ SELECT FROM context_locks (recent)
├─ SELECT FROM audit_trail (recent)
├─ Aggregate into handover document
├─ INSERT INTO memory_entries (handover)
└─ Returns: handover JSON
```

### switch_project(name)
```
switch_project(name)
├─ Validate project exists
│  └─ Query information_schema.schemata
├─ Update _active_projects[connection_id] = name
└─ Returns: confirmation message
```

## Interoperation Patterns

### 1. Project Resolution Chain
```
Tool(project=X)
└─ get_db(project=X)
   ├─ If project specified: use X
   ├─ Else: get_active_project() → _active_projects
   ├─ Else: detect_project_name() → git/cwd
   └─ Else: "default"
```

### 2. Embedding Generation Chain
```
lock_context()
└─ INSERT context
   └─ TRY: Auto-embed
      ├─ embedding_service.generate_embedding()
      │  └─ Voyage AI API (voyage-3.5-lite)
      ├─ pickle.dumps(embedding)
      └─ UPDATE context SET embedding
```

### 3. Semantic Search Chain
```
semantic_search_contexts()
└─ Generate query embedding
   └─ FOR EACH context with embedding:
      ├─ pickle.loads(context.embedding)
      ├─ cosine_similarity(query_emb, context_emb)
      └─ Filter by threshold
```

### 4. Session Lifecycle
```
wake_up() → Creates session
├─ Various operations use session
└─ sleep() → Creates handover, archives session
```

## Cross-Tool Dependencies

### Tools That Call Other Tools (Indirectly)

**batch_lock_contexts:**
- Calls: lock_context (logic reused, not MCP call)

**batch_recall_contexts:**
- Calls: recall_context (logic reused)

**check_contexts:**
- Uses: SemanticSearch (shared service)
- Falls back to: get_relevant_contexts_for_text (SQLite-based, deprecated)

### Tools That Share State

**Session-based:**
- wake_up, lock_context, recall_context, memory_status, sleep
- All use: get_or_create_session()
- Share: session_id in queries

**Project-based:**
- switch_project sets → all tools read via get_active_project()
- Share: _active_projects global dict

**Embedding-based:**
- lock_context generates → semantic_search_contexts uses
- check_contexts uses → memory_status shows stats
- Share: embedding column in context_locks

## Performance Characteristics

### Fast (< 50ms)
- recall_context (single SELECT)
- unlock_context (single DELETE)
- get_active_project (dict lookup)
- memory_status (few SELECT COUNT queries)

### Medium (50-200ms)
- lock_context (INSERT + embedding generation + UPDATE)
- search_contexts (SELECT with LIKE queries)
- check_contexts (semantic + keyword)

### Slow (200ms+)
- semantic_search_contexts (embedding generation + similarity for all contexts)
- batch_lock_contexts (N * lock_context time)
- wake_up (multiple aggregation queries)
- sleep (aggregate + create handover)

### External API Calls
- lock_context → Voyage AI (~100-200ms)
- semantic_search_contexts → Voyage AI (~100-200ms)
- generate_embeddings → Voyage AI (batch, ~500ms+)

## Error Propagation

### Graceful Degradation
**Embeddings:**
- lock_context: Context saved even if embedding fails
- check_contexts: Falls back to keyword if semantic fails
- semantic_search_contexts: Returns empty if no embeddings

**Project Resolution:**
- Falls back through: explicit → active → auto-detect → "default"
- Always resolves to valid schema

**Database:**
- Connection pooling handles retries
- Transactions rollback on error
- Schema auto-created if missing

### Hard Failures
**Project not found:**
- delete_project, get_project_info
- Returns error immediately

**Invalid parameters:**
- All tools validate required params
- Return error JSON

**Service unavailable:**
- embedding_service disabled → warnings only
- PostgreSQL unavailable → connection error
