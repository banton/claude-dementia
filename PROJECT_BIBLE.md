# 🧠 Claude Intelligence: Project Bible & Implementation Plan

## Mission Statement
Build a dead-simple MCP server that gives Claude persistent memory of your project - understanding your tech stack, finding files by meaning, and tracking what you've been working on. For solo devs and small teams who want Claude to just remember their project without any operational burden.

## Core Principles
1. **It Just Works** - Zero configuration, 30-second install
2. **Local First** - Everything runs on your machine, no external dependencies
3. **Git Native** - Travels with your repo, respects .gitignore
4. **Small & Fast** - Single file, SQLite, <35MB total
5. **Actually Useful** - Solves real problems from day one

---

## 📋 Proof of Concept Scope

### What We're Building (v0.1.0)

**Three Core Features:**
1. **Tech Stack Detection** - Instantly knows your tools/frameworks
2. **Smart File Search** - Find files by meaning using hybrid FTS5 + optional embeddings
3. **Change Tracking** - Remembers what you worked on between sessions

**Technical Stack:**
- **Language**: Python 3.10+ (better compatibility)
- **Storage**: SQLite with FTS5 (zero setup, fast search)
- **Search**: TF-IDF by default, optional semantic with BAAI/bge-small-en-v1.5 (33MB)
- **Protocol**: MCP (Model Context Protocol)
- **Size**: <5MB without model, <35MB with model

### What We're NOT Building (Yet)
- ❌ Team features
- ❌ Cross-repository intelligence
- ❌ Web dashboard
- ❌ CI/CD integration
- ❌ Cloud sync
- ❌ Deep code analysis
- ❌ Windows native support (WSL only for v0.1)
- ❌ Model selection UI

---

## 🎯 Success Criteria

### Metrics That Matter
1. **Time to First Value**: <60 seconds from git clone to useful result
2. **First Index**: <3s for 300 files, <5s acceptable
3. **Search Latency**: <50ms target, <100ms acceptable
4. **Cold Start**: <500ms target, <1s acceptable
5. **Storage**: <5MB for 1k files (without embeddings)
6. **With Embeddings**: <10MB for 1k files

### User Experience Goals
- "Holy shit, Claude remembers my project!"
- "How did I work without this?"
- "I need to tell my team about this"

---

## 🗺️ Implementation Roadmap

### 3-Day Demo Sprint
**Goal**: Demoable proof that shows the magic

**Day 1: Core Infrastructure**
- [ ] MCP server skeleton + SQLite with FTS5
- [ ] Content hashing with xxhash
- [ ] Smart ignore system (gitignore + defaults)
- [ ] Basic tech stack detection (package.json, requirements.txt)

**Day 2: Search Magic**
- [ ] TF-IDF search (no ML dependencies)
- [ ] FTS5 full-text search setup
- [ ] Progressive indexing with feedback
- [ ] Search result excerpts (show WHY it matched)

**Day 3: Polish & Demo**
- [ ] Git change tracking (recent commits)
- [ ] One-line installer
- [ ] Performance testing
- [ ] Create demo GIF

### Week 1: Foundation (Epics 1-2)
**Goal**: Working MCP server with smart search

**Epic 1: Core MCP Server Infrastructure**
- [ ] Create single-file MCP server skeleton (mcp_server.py)
- [ ] Implement SQLite with FTS5 initialization
- [ ] Add content hashing with xxhash for change detection
- [ ] Implement smart ignore system (gitignore + defaults)
- [ ] Add MCP protocol handling and tool registration
- [ ] Create session lifecycle management

**Epic 2: Tech Stack Detection**
- [ ] Detect Node.js projects (package.json parsing)
- [ ] Detect Python projects (requirements.txt, pyproject.toml)
- [ ] Detect Docker usage (docker-compose.yml, Dockerfile)
- [ ] Detect common frameworks (React, Vue, Django, FastAPI)
- [ ] Detect services and ports from config files
- [ ] Create unified tech stack summary format

**Deliverables:**
- Single-file MCP server that starts with Claude
- SQLite with FTS5 for fast search
- Content hashing for accurate change detection
- Progressive indexing with user feedback

### Week 2: Intelligence (Epics 3-4)
**Goal**: Smart search and change tracking working

**Epic 3: Smart File Search**
- [ ] Implement TF-IDF search as default (no dependencies)
- [ ] Build FTS5 full-text search with BM25 ranking
- [ ] Add semantic text extraction (functions, comments, imports)
- [ ] Implement progressive file indexing (current dir first)
- [ ] Add optional embedding support (bge-small-en-v1.5)
- [ ] Build hybrid search (FTS5 first, then vector on top-50)
- [ ] Add search result excerpts showing WHY it matched

**Epic 4: Change Tracking**
- [ ] Implement git integration for change detection
- [ ] Store git HEAD and branch info for accurate tracking
- [ ] Track files modified since last session using git diff
- [ ] Parse recent commit messages for context
- [ ] Create session summary generation

**Deliverables:**
- Hybrid search that's fast AND semantic
- Progressive indexing with instant gratification
- Git-aware change tracking
- Search results that explain themselves

### Week 3: Polish (Epics 5-6-7)
**Goal**: Ready for public release

**Epic 5: Installation & UX**
- [ ] Create one-line install script (curl | bash)
- [ ] Write MCP configuration generator
- [ ] Add progress indicators with time estimates
- [ ] Create .claude-ignore file support
- [ ] Implement 'ci reset' panic command

**Epic 6: Testing & Performance**
- [ ] Create test harness with metrics output
- [ ] Test on small React project (~300 files)
- [ ] Test on Python Flask/FastAPI project (~150 files)
- [ ] Test on mixed tech stack (~1k files)
- [ ] Performance profiling (measure TTFV, search p50/p95)
- [ ] Optimize hot paths and fix bottlenecks

**Epic 7: Documentation & Release**
- [ ] Write simple README with real performance numbers
- [ ] Create 2-minute demo GIF showing the magic
- [ ] Document the MCP tool contract (stable API)
- [ ] Set up GitHub repository and releases
- [ ] Create troubleshooting guide

**Deliverables:**
- One-line installer that just works
- Real performance metrics from test harness
- Search <50ms, startup <500ms, index <3s
- Documentation with actual numbers

---

## 📁 Project Structure

```
claude-intelligence/
├── mcp_server.py           # The entire system (one file!)
├── requirements.txt        # Just: sentence-transformers, gitpython
├── install.sh             # 30-second installer
├── README.md              # Quick start guide
├── LICENSE                # MIT
└── examples/
    ├── .mcp.json          # Example MCP config
    └── .claude-ignore     # Example ignore file
```

**That's it.** No subdirectories, no complex structure.

---

## 🏗️ Technical Architecture

### Database Schema (SQLite)
```sql
-- Optimized schema with FTS5 and hashing
CREATE TABLE files (
    path TEXT PRIMARY KEY,
    hash TEXT NOT NULL,  -- xxhash for change detection
    indexed_at REAL,
    size_bytes INTEGER,
    metadata JSON  -- Everything else goes here
);

-- Full-text search virtual table
CREATE VIRTUAL TABLE file_fts USING fts5(
    path,
    content,  -- Semantic extract: functions, comments, imports
    content=files,
    content_rowid=rowid
);

-- Optional: embeddings table (only if user opts in)
CREATE TABLE embeddings (
    file_path TEXT PRIMARY KEY,
    model TEXT,
    dim INTEGER,
    vector BLOB,  -- Compressed float16 array
    FOREIGN KEY (file_path) REFERENCES files(path)
);

CREATE INDEX idx_files_hash ON files(hash);
CREATE INDEX idx_files_indexed ON files(indexed_at);
```

### Core Classes
```python
class ClaudeIntelligence:
    """The entire system in one class"""
    
    def __init__(self):
        self.db = sqlite3.connect('.claude-memory.db')
        self.init_fts5()  # Enable full-text search
        self.hasher = xxhash.xxh64()
        self.search_engine = TFIDFSearch()  # Start with TF-IDF
        self.project = self._detect_project()
        
    # MCP Tools (stable contract)
    async def understand_project(self) -> dict:
        """Returns: {stack: [...], services: [...], summary: str}"""
        
    async def find_files(self, query: str, k: int = 10) -> list:
        """Returns: [{path: str, score: float, excerpt: str}]"""
        
    async def recent_changes(self, since: str = 'auto') -> dict:
        """Returns: {commits: [...], files: [...]}"""
    
    # Smart indexing
    def index_progressive(self):
        """Index current dir → src dirs → everything else"""
        yield from self._index_hot_paths_first()
    
    # Hybrid search
    def search_hybrid(self, query: str):
        # 1. FTS5 for initial candidates
        candidates = self.fts_search(query, limit=50)
        # 2. Optional: re-rank with vectors if available
        if self.has_embeddings:
            return self.vector_rerank(candidates, query)
        return candidates
```

### Smart Content Extraction
```python
def extract_semantic_content(file_path, content):
    """Extract searchable semantic content - max 1-2KB"""
    semantic_parts = []
    
    # Always include (language-aware)
    semantic_parts.extend(extract_definitions(content))  # func/class names
    semantic_parts.extend(extract_comments(content))     # docstrings, comments
    semantic_parts.extend(extract_imports(content))      # dependencies
    semantic_parts.extend(extract_todos(content))        # TODO/FIXME blocks
    
    # Cap at 2KB for FTS and embeddings
    text = " ".join(semantic_parts)[:2000]
    return text

def should_index(file_path):
    """Smart filtering of what to index"""
    # Skip obvious non-semantic files
    if any(skip in file_path for skip in DEFAULT_IGNORES):
        return False
    
    # Skip huge files
    if os.path.getsize(file_path) > 200_000:  # 200KB
        return False
        
    # Skip minified/generated
    if '.min.' in file_path or 'generated' in file_path:
        return False
        
    return True
```

### Default Ignores
```python
DEFAULT_IGNORES = [
    'node_modules/', 'dist/', 'build/', '.next/', 'out/',
    'venv/', '.venv/', '__pycache__/', '.pytest_cache/',
    'coverage/', '.git/', '.idea/', '.vscode/',
    '*.min.js', '*.map', '*.lock', 'package-lock.json'
]
```

---

## 🎨 User Experience Flow

### First Run
```
$ git clone https://github.com/user/project
$ cd project
$ curl -s https://claude.ai/install-intelligence | bash

Installing Claude Intelligence... ✓
Indexing your project...
  ✓ Current directory (23 files) - 0.3s
  ✓ src/ directory (89 files) - 0.8s
  ✓ lib/ directory (45 files) - 0.5s
  ✓ Remaining files (77 files) - 1.1s

Found: React 18, TypeScript, Tailwind, Vercel
Indexed 234 files in 2.7s · Model: TF-IDF (fast mode)

💡 Tip: Install sentence-transformers for semantic search (33MB)

Claude Intelligence active! Claude will now remember your project.
```

### Every Session After
```
[Claude session starts]
🧠 Claude Intelligence loaded

Project: awesome-app
Stack: React, TypeScript, Tailwind
Recent: Working on auth system (2 hours ago)

Claude: "I can see you're working on a React TypeScript project. 
You were working on authentication recently. How can I help?"
```

### Search in Action (with excerpts)
```
Human: "Where do we handle payments?"

Claude: [uses find_files("payment processing")]

"I found your payment handling code:

• /api/stripe/webhook.ts (95% match)
  └─ "async function handleStripeWebhook(event) { ... process payment ..."
  
• /lib/payment.ts (89% match)
  └─ "export class PaymentProcessor { ... charge customer ..."
  
• /components/Checkout.tsx (76% match)
  └─ "// Handle payment form submission ... stripe.confirmPayment ..."
  
• /api/stripe/intent.ts (71% match)
  └─ "createPaymentIntent(amount, currency) { ... }"
```

---

## 🚀 Go-to-Market Strategy

### Phase 1: Proof of Concept (Weeks 1-3)
- Build core functionality
- Test with friendly users
- Iterate based on feedback

### Phase 2: Soft Launch (Week 4)
- Post on Twitter/X with demo video
- Share in Claude Discord
- Submit to HackerNews (Show HN)

### Phase 3: Iterate (Weeks 5-8)
- Incorporate feedback
- Add most-requested features
- Build community

---

## ⚡ Performance Engineering

### Critical Optimizations from Feedback

**1. Model Size Management**
```python
# Problem: all-MiniLM-L6-v2 is 90MB (not 50MB!)
# Solution: Start with TF-IDF, upgrade optional

DEFAULT_MODE = "tfidf"  # 0MB, instant
OPTIONAL_MODEL = "BAAI/bge-small-en-v1.5"  # 33MB if wanted
```

**2. Fast Search via FTS5 + Vectors**
```python
def hybrid_search(query):
    # Step 1: FTS5 for speed (BM25 ranking)
    candidates = fts5_search(query, limit=50)  # <10ms
    
    # Step 2: Vector re-rank only top-50
    if has_embeddings:
        return vector_rerank(candidates, query)  # <50ms
    return candidates
```

**3. Content Hashing (not mtime)**
```python
# mtime lies across OS/filesystems
def needs_reindex(file_path, stored_hash):
    current = xxhash.xxh64_hexdigest(content)
    return current != stored_hash  # Accurate
```

**4. Progressive Indexing**
```python
# Don't make user wait for full scan
for update in index_progressive():
    print(f"  ✓ {update}")  # Instant feedback
```

**5. Storage Optimization**
```python
# Store vectors as compressed float16
vector_f16 = vector.astype(np.float16)
compressed = zlib.compress(vector_f16.tobytes())
# 384*4 bytes → 384*2 → ~400 bytes compressed
```

## 📊 Risk Mitigation

| Risk | Mitigation |
|------|------------|
| MCP protocol changes | Abstract protocol layer, version pinning |
| Slow embeddings | Cache aggressively, embed incrementally |
| Large codebases fail | Set file limits, smart sampling |
| Users don't understand value | Better onboarding, clear demos |
| Anthropic builds this | Move fast, build community, stay agnostic |

---

## 🎯 Definition of Done

The PoC is complete when:

1. ✅ Single file MCP server under 1000 lines
2. ✅ Installs in <30 seconds
3. ✅ Starts in <1 second (with cache)
4. ✅ Finds files semantically with >90% relevance
5. ✅ Uses <20MB storage for 10k file project
6. ✅ Works on Mac, Linux, Windows (WSL)
7. ✅ Zero configuration required
8. ✅ Makes Claude obviously smarter about your project

---

## 💬 Tagline Options

- "Claude, but with memory"
- "Your project's AI memory layer"
- "Make Claude remember everything"
- "Persistent intelligence for Claude"
- **"It just remembers"** ← I like this one

---

## 📝 Next Immediate Actions

1. Create `mcp_server.py` with basic MCP skeleton
2. Add SQLite initialization
3. Implement first tech detection (package.json)
4. Get "Hello World" working with Claude
5. Iterate from there

**The goal**: Have something demoable in 3 days, shippable in 2 weeks.

---

## 🔧 Technical Decisions

### Why Python?
- Most developers have it installed
- Great libraries (sentence-transformers, gitpython)
- MCP has good Python support
- Single file distribution is clean

### Why SQLite?
- Zero configuration needed
- Travels with the repository
- Fast enough for our needs
- Single file (.claude-memory.db)
- Built into Python

### Why Local Embeddings?
- No API keys needed
- No internet required
- No data leaves the machine
- Fast after initial model download
- all-MiniLM-L6-v2 is tiny (80MB) and good enough

### Why MCP?
- Native Claude integration
- Automatic session management
- No daemon needed
- Clean tool interface
- Future-proof as Claude evolves

---

## 📐 Design Decisions

### What Gets Embedded?
```python
EMBED_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx',  # Code
    '.java', '.go', '.rs', '.rb', '.php',  # More code
    '.sql', '.graphql',  # Queries
    '.yml', '.yaml', '.toml',  # Config with logic
}

SKIP_PATTERNS = {
    'node_modules/', 'venv/', '.git/',  # Dependencies
    'dist/', 'build/', 'target/',  # Build outputs
    '*.min.js', '*.map',  # Minified/generated
    'package-lock.json', 'yarn.lock',  # Lock files
}
```

### How Much Context to Keep?
- Last 10 sessions
- Last 30 days of changes
- All file embeddings (until >50MB)
- Automatic cleanup of stale data

### Search Ranking Formula
```python
def rank_results(query_embedding, file_embeddings):
    scores = []
    for file, embedding in file_embeddings:
        # Base similarity
        similarity = cosine_similarity(query_embedding, embedding)
        
        # Boost recent files
        recency_boost = 1.0 + (0.2 if file.recently_modified else 0)
        
        # Boost files in active feature
        relevance_boost = 1.0 + (0.3 if file.in_current_feature else 0)
        
        scores.append(similarity * recency_boost * relevance_boost)
    
    return sorted(scores, reverse=True)
```

---

## 🤝 Community & Support

### Where to Get Help
- GitHub Issues for bugs
- Discord for questions
- Twitter for updates

### How to Contribute
- Test on your projects
- Report what doesn't work
- Suggest what's missing
- Share if it helps you

### Code of Conduct
- Be helpful
- Be patient with bugs (it's v0.1!)
- Share feedback constructively
- Remember: solo devs and small teams are our focus

---

## 📈 Future Vision (Post-PoC)

**v0.2.0** - Quality of Life
- Configuration file support
- Better progress indicators
- Faster embeddings with caching

**v0.3.0** - Deeper Intelligence
- Understand function relationships
- Track error patterns
- Learn from test files

**v0.4.0** - Team Features (Maybe)
- Shareable intelligence via git
- Team knowledge aggregation
- Who-knows-what mapping

**v1.0.0** - Production Ready
- Plugin system
- Multiple LLM support
- Performance guarantees

---

## 📋 Testing Harness & Metrics

### Test Projects
```python
TEST_REPOS = {
    'tiny_react': {
        'url': 'github.com/example/tiny-react',
        'files': 300,
        'expect_stack': ['React', 'TypeScript', 'Tailwind'],
        'expect_index_time': '<3s'
    },
    'flask_api': {
        'url': 'github.com/example/flask-api', 
        'files': 150,
        'expect_stack': ['Python', 'Flask', 'SQLAlchemy'],
        'expect_index_time': '<2s'
    },
    'mixed_stack': {
        'url': 'github.com/example/fullstack',
        'files': 1000,
        'expect_stack': ['React', 'Express', 'PostgreSQL'],
        'expect_index_time': '<5s'
    }
}
```

### Performance Metrics Script
```python
def measure_performance():
    metrics = {}
    
    # Time to First Value
    start = time.time()
    ci = ClaudeIntelligence()
    metrics['startup_ms'] = (time.time() - start) * 1000
    
    # Index time
    start = time.time()
    for _ in ci.index_progressive():
        pass
    metrics['index_time_s'] = time.time() - start
    
    # Search performance
    queries = ["payment", "authentication", "database"]
    times = []
    for q in queries:
        start = time.time()
        ci.find_files(q)
        times.append((time.time() - start) * 1000)
    
    metrics['search_p50_ms'] = percentile(times, 50)
    metrics['search_p95_ms'] = percentile(times, 95)
    
    # Storage
    metrics['db_size_mb'] = os.path.getsize('.claude-memory.db') / 1024 / 1024
    
    print(f"""
    === Performance Report ===
    Startup: {metrics['startup_ms']:.0f}ms
    Index: {metrics['index_time_s']:.1f}s  
    Search P50: {metrics['search_p50_ms']:.0f}ms
    Search P95: {metrics['search_p95_ms']:.0f}ms
    Storage: {metrics['db_size_mb']:.1f}MB
    """)
    
    return metrics
```

### Functionality Tests
- [ ] Detects Node.js project correctly
- [ ] Detects Python project correctly  
- [ ] FTS5 search returns relevant results
- [ ] Shows recent changes via git
- [ ] Respects .gitignore + default ignores
- [ ] Content hash detects real changes
- [ ] Progressive indexing shows feedback

### Performance Requirements
- [ ] Startup <500ms with cache, <1s acceptable
- [ ] Search <50ms for 1000 files, <100ms acceptable
- [ ] Initial scan <3s for 300 files, <5s acceptable
- [ ] Storage <5MB for 1k files without embeddings
- [ ] Memory usage <100MB during operation

### User Experience Tests
- [ ] Installs in one command
- [ ] No configuration needed
- [ ] Shows WHY files matched
- [ ] Progressive feedback during indexing
- [ ] Graceful handling of missing git

---

## 🎬 Demo Script

```markdown
# The 2-Minute Demo

## Setup (30 seconds)
"Here's a React project I just cloned. Let me install Claude Intelligence..."
$ curl -s https://claude.ai/install | bash
"Done! That's it for setup."

## First Magic (30 seconds)
"Now when I start Claude..."
[Claude automatically says: "I see this is a React TypeScript project with Tailwind"]
"Claude already knows my tech stack!"

## Second Magic (30 seconds)
"Now watch this - I'll ask about payments without mentioning file names..."
Human: "Where do we handle Stripe payments?"
Claude: "I found your payment code in:
- /api/stripe/webhook.ts
- /components/CheckoutForm.tsx
- /lib/stripe-client.ts"
"It found files by MEANING, not names!"

## Third Magic (30 seconds)
"And it remembers what I was working on..."
Claude: "I see you were working on the auth system 2 hours ago. 
You modified the login flow and added JWT refresh tokens."
"It remembers between sessions!"

## Conclusion
"Claude Intelligence - it just remembers. 
Install in 30 seconds, zero config, works everywhere."
```

---

*This is our north star. Everything else is noise until we have a working PoC that makes people say "Holy shit, I need this!"*