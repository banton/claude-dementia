# RLM Detailed Design - Recursive Knowledge Deepening

## Philosophy: Iterative Knowledge Discovery

The MIT RLM approach isn't just about lazy loading - it's about **recursive exploration** where understanding deepens iteratively:

```
Query → Metadata → Preview → Full Content → Related Contexts → Deeper → ...
```

Not: "Load nothing" or "Load everything"
But: "Load what you need, when you need it, and explore deeper as required"

---

## Core Architecture: Knowledge Depth Levels

### Level 0: Index (Always in Memory)
```json
{
  "label": "api_authentication",
  "version": "2.1",
  "tags": ["api", "auth", "security"],
  "priority": "important",
  "size": 12500,
  "last_accessed": "2025-01-20T10:30:00Z"
}
```
**Size**: ~200 bytes/context
**Load time**: Already loaded at wake_up()

### Level 1: Preview (On-Demand)
```json
{
  "label": "api_authentication",
  "preview": "API authentication uses JWT tokens. All endpoints require...",
  "summary": "Covers: JWT implementation, token refresh, rate limiting",
  "related": ["api_security_rules", "jwt_config"],
  "key_concepts": ["JWT", "Bearer token", "OAuth2"]
}
```
**Size**: ~500-1000 bytes
**Load time**: <50ms
**When**: User asks "what contexts are relevant to JWT?"

### Level 2: Full Content (On-Demand)
```
Full 10-50KB content of the locked context
```
**Size**: 10-50KB
**Load time**: <100ms
**When**: User explicitly recalls OR system determines high relevance

### Level 3: Related Contexts (Recursive)
```
Automatically loads related contexts based on:
- Explicit links in metadata
- Semantic similarity
- Tag overlap
- Historical co-access patterns
```
**Size**: Variable
**Load time**: <200ms per hop
**When**: User asks follow-up questions OR system detects knowledge gaps

---

## Task 1: Multi-Level Context API (NEW)

### Deliverables

#### 1.1 New Database Schema Enhancements
```sql
-- Add preview and relationships
ALTER TABLE context_locks ADD COLUMN preview TEXT; -- 500 char summary
ALTER TABLE context_locks ADD COLUMN key_concepts TEXT; -- JSON array
ALTER TABLE context_locks ADD COLUMN related_contexts TEXT; -- JSON array of labels

-- Add access tracking for intelligent caching
ALTER TABLE context_locks ADD COLUMN last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE context_locks ADD COLUMN access_count INTEGER DEFAULT 0;

-- Create relationship tracking
CREATE TABLE IF NOT EXISTS context_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    from_label TEXT NOT NULL,
    to_label TEXT NOT NULL,
    relationship_type TEXT, -- 'explicit', 'semantic', 'co-accessed'
    strength REAL DEFAULT 0.5, -- 0.0 to 1.0
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, from_label, to_label)
);

-- Create access history for pattern detection
CREATE TABLE IF NOT EXISTS context_access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    label TEXT NOT NULL,
    access_type TEXT, -- 'preview', 'full', 'related'
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 1.2 New MCP Tools
```python
@mcp.tool()
async def get_context_preview(topic: str) -> str:
    """
    Get a brief preview of a locked context without loading full content.
    Returns: summary, key concepts, related contexts, size estimate.
    """
    # Implementation below

@mcp.tool()
async def explore_context_tree(
    topic: str,
    depth: int = 2,
    max_results: int = 10
) -> str:
    """
    Recursively explore related contexts starting from a topic.
    Returns tree structure showing relationships and relevance.

    Example:
    api_authentication (relevance: 0.95)
    ├─ jwt_config (explicit link, relevance: 0.90)
    │  └─ security_best_practices (related, relevance: 0.75)
    └─ api_rate_limiting (co-accessed, relevance: 0.80)
    """
    # Implementation below

@mcp.tool()
async def search_contexts_semantic(
    query: str,
    depth: Literal["preview", "full"] = "preview",
    max_results: int = 5
) -> str:
    """
    Search contexts using keyword matching and concept extraction.
    Returns results at specified depth level.

    depth='preview': Fast, returns summaries
    depth='full': Slower, returns full content for top matches
    """
    # Implementation below
```

#### 1.3 Modified lock_context() Function
```python
@mcp.tool()
async def lock_context(
    content: str,
    topic: str,
    tags: Optional[str] = None,
    priority: Optional[str] = None,
    related: Optional[str] = None  # NEW: comma-separated list of related topics
) -> str:
    """
    Enhanced to automatically generate:
    - preview (first 500 chars + key sentences)
    - key_concepts (extracted via regex/simple NLP)
    - relationships (from 'related' parameter)
    """
    # Generate preview
    preview = generate_preview(content)

    # Extract key concepts
    key_concepts = extract_key_concepts(content, tags)

    # Parse related contexts
    related_list = [r.strip() for r in (related or "").split(",")] if related else []

    # Store with metadata
    metadata = {
        'tags': tag_list,
        'priority': priority,
        'preview': preview,
        'key_concepts': key_concepts,
        'related': related_list
    }

    # Insert into database...
```

#### 1.4 Helper Functions
```python
def generate_preview(content: str, max_length: int = 500) -> str:
    """
    Intelligent preview generation:
    1. Extract first paragraph
    2. Find key sentences with important keywords
    3. Compress to max_length while maintaining meaning
    """
    lines = content.split('\n')

    # Find title/header
    title = ""
    for line in lines[:5]:
        if line.strip().startswith('#'):
            title = line.strip('# ').strip()
            break

    # Find first substantial paragraph
    first_para = ""
    for line in lines:
        if len(line.strip()) > 50 and not line.strip().startswith('#'):
            first_para = line.strip()
            break

    # Find key sentences (with MUST, ALWAYS, NEVER, etc.)
    important_patterns = r'\b(MUST|ALWAYS|NEVER|REQUIRED|CRITICAL|WARNING)\b'
    key_sentences = []
    for line in lines:
        if re.search(important_patterns, line, re.IGNORECASE):
            key_sentences.append(line.strip())

    # Combine
    preview_parts = []
    if title:
        preview_parts.append(f"# {title}")
    if first_para:
        preview_parts.append(first_para)
    if key_sentences:
        preview_parts.append("Key rules: " + "; ".join(key_sentences[:2]))

    preview = "\n".join(preview_parts)

    # Truncate if needed
    if len(preview) > max_length:
        preview = preview[:max_length-3] + "..."

    return preview

def extract_key_concepts(content: str, tags: List[str] = None) -> List[str]:
    """
    Extract key concepts from content for semantic matching.
    """
    concepts = set(tags or [])

    # Technical terms (CamelCase, snake_case, kebab-case)
    concepts.update(re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', content))  # CamelCase
    concepts.update(re.findall(r'\b[a-z]+_[a-z_]+\b', content))  # snake_case

    # Common domain terms
    domain_patterns = [
        r'\b(API|REST|GraphQL|JWT|OAuth|database|SQL|NoSQL)\b',
        r'\b(authentication|authorization|security|encryption)\b',
        r'\b(deployment|CI/CD|Docker|Kubernetes)\b',
        r'\b(React|Vue|Angular|TypeScript|JavaScript|Python)\b'
    ]

    for pattern in domain_patterns:
        concepts.update(re.findall(pattern, content, re.IGNORECASE))

    # Limit to top 10 most meaningful
    return list(concepts)[:10]
```

---

## Task 2: Recursive Context Explorer (REVISED)

### Why This Matters

Current system:
```python
# User asks: "How does authentication work?"
check_contexts("authentication")
→ Loads ALL 10 contexts with "auth" keyword (100KB+)
→ Returns all to user
→ User overwhelmed
```

RLM approach:
```python
# User asks: "How does authentication work?"
search_contexts_semantic("authentication", depth="preview")
→ Returns 5 preview cards (5KB)
→ Shows: api_authentication (0.95), jwt_config (0.80), oauth_setup (0.75)...

# User: "Tell me more about JWT specifically"
explore_context_tree("jwt_config", depth=2)
→ Shows relationship tree
→ User sees: jwt_config links to api_authentication, security_rules

# User: "Load the full JWT config"
recall_context("jwt_config")
→ Loads full 10KB content
→ Updates access tracking
```

### Deliverables

#### 2.1 RecursiveExplorer Class
```python
# recursive_explorer.py

class RecursiveExplorer:
    """
    Implements iterative deepening search through locked contexts.
    Builds understanding gradually without loading everything.
    """

    def __init__(self, db_path: str, session_id: str):
        self.db_path = db_path
        self.session_id = session_id
        self.exploration_cache = {}  # In-memory cache for this exploration

    def search(
        self,
        query: str,
        depth: int = 2,
        max_contexts: int = 10
    ) -> Dict[str, Any]:
        """
        Multi-level search with iterative deepening.

        Algorithm:
        1. Level 0: Find matching contexts by metadata/tags
        2. Level 1: Load previews, score relevance
        3. Level 2: For top N, load full content
        4. Level 3: Explore related contexts recursively
        """
        results = {
            'query': query,
            'matches': [],
            'exploration_path': [],
            'related_topics': []
        }

        # Phase 1: Metadata search
        candidates = self._search_metadata(query)
        results['exploration_path'].append(
            f"Phase 1: Found {len(candidates)} candidate contexts"
        )

        # Phase 2: Preview scoring
        scored = self._score_previews(query, candidates)
        top_candidates = sorted(scored, key=lambda x: x['score'], reverse=True)[:max_contexts]
        results['exploration_path'].append(
            f"Phase 2: Scored and filtered to top {len(top_candidates)}"
        )

        # Phase 3: Selective full load
        for candidate in top_candidates[:3]:  # Only top 3 get full content
            if candidate['score'] > 0.7:  # High confidence
                full_content = self._load_full_content(candidate['label'])
                candidate['content'] = full_content
                candidate['loaded_full'] = True
            else:
                candidate['content'] = candidate['preview']
                candidate['loaded_full'] = False

        results['matches'] = top_candidates

        # Phase 4: Related contexts (if depth > 1)
        if depth > 1:
            related = self._explore_related(
                [c['label'] for c in top_candidates[:3]],
                depth=depth-1,
                visited=set([c['label'] for c in top_candidates])
            )
            results['related_topics'] = related
            results['exploration_path'].append(
                f"Phase 3: Explored {len(related)} related contexts"
            )

        return results

    def _search_metadata(self, query: str) -> List[Dict]:
        """Phase 1: Fast metadata-only search"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Extract keywords from query
        keywords = self._extract_keywords(query)

        # Search metadata and tags
        cursor = conn.execute("""
            SELECT
                label,
                version,
                preview,
                key_concepts,
                related_contexts,
                metadata,
                last_accessed,
                access_count
            FROM context_locks
            WHERE session_id = ?
            AND (
                label LIKE ? OR
                preview LIKE ? OR
                key_concepts LIKE ? OR
                metadata LIKE ?
            )
        """, (
            self.session_id,
            f'%{keywords[0]}%',
            f'%{keywords[0]}%',
            f'%{keywords[0]}%',
            f'%{keywords[0]}%'
        ))

        candidates = []
        for row in cursor:
            metadata = json.loads(row['metadata']) if row['metadata'] else {}
            candidates.append({
                'label': row['label'],
                'version': row['version'],
                'preview': row['preview'] or "No preview available",
                'key_concepts': json.loads(row['key_concepts'] or '[]'),
                'related': json.loads(row['related_contexts'] or '[]'),
                'priority': metadata.get('priority', 'reference'),
                'last_accessed': row['last_accessed'],
                'access_count': row['access_count']
            })

        conn.close()
        return candidates

    def _score_previews(self, query: str, candidates: List[Dict]) -> List[Dict]:
        """Phase 2: Score relevance using previews only"""
        keywords = self._extract_keywords(query)

        for candidate in candidates:
            score = 0.0

            # Keyword matching in label (40 points)
            label_matches = sum(1 for kw in keywords if kw.lower() in candidate['label'].lower())
            score += min(40, label_matches * 20)

            # Keyword matching in preview (30 points)
            preview_lower = candidate['preview'].lower()
            preview_matches = sum(1 for kw in keywords if kw.lower() in preview_lower)
            score += min(30, preview_matches * 10)

            # Key concept overlap (20 points)
            concept_matches = sum(1 for concept in candidate['key_concepts']
                                 if any(kw.lower() in concept.lower() for kw in keywords))
            score += min(20, concept_matches * 10)

            # Recency bonus (5 points)
            if candidate['last_accessed']:
                days_ago = (time.time() - candidate['last_accessed']) / 86400
                score += max(0, 5 - days_ago)

            # Priority bonus (5 points)
            if candidate['priority'] == 'always_check':
                score += 5
            elif candidate['priority'] == 'important':
                score += 3

            # Normalize to 0-1
            candidate['score'] = score / 100

            # Explanation
            candidate['match_reason'] = self._explain_match(
                candidate, keywords, label_matches, preview_matches, concept_matches
            )

        return candidates

    def _load_full_content(self, label: str) -> str:
        """Phase 3: Load full content for specific context"""
        # Check cache first
        if label in self.exploration_cache:
            return self.exploration_cache[label]

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT content FROM context_locks
            WHERE session_id = ? AND label = ?
            ORDER BY locked_at DESC LIMIT 1
        """, (self.session_id, label))

        row = cursor.fetchone()
        content = row[0] if row else "Content not found"

        # Update access tracking
        conn.execute("""
            UPDATE context_locks
            SET last_accessed = CURRENT_TIMESTAMP,
                access_count = access_count + 1
            WHERE session_id = ? AND label = ?
        """, (self.session_id, label))
        conn.commit()

        # Log access
        conn.execute("""
            INSERT INTO context_access_log (session_id, label, access_type)
            VALUES (?, ?, 'full')
        """, (self.session_id, label))
        conn.commit()
        conn.close()

        # Cache
        self.exploration_cache[label] = content
        return content

    def _explore_related(
        self,
        labels: List[str],
        depth: int,
        visited: Set[str]
    ) -> List[Dict]:
        """Phase 4: Recursively explore related contexts"""
        if depth <= 0:
            return []

        conn = sqlite3.connect(self.db_path)
        related_contexts = []

        for label in labels:
            if label in visited:
                continue

            # Get explicit relationships
            cursor = conn.execute("""
                SELECT related_contexts FROM context_locks
                WHERE session_id = ? AND label = ?
            """, (self.session_id, label))

            row = cursor.fetchone()
            if row and row[0]:
                related_list = json.loads(row[0])
                for related_label in related_list:
                    if related_label not in visited:
                        # Load preview of related context
                        related_info = self._get_context_info(related_label)
                        if related_info:
                            related_info['relationship'] = 'explicit'
                            related_info['source'] = label
                            related_contexts.append(related_info)
                            visited.add(related_label)

        # Recursive exploration
        if depth > 1 and related_contexts:
            deeper = self._explore_related(
                [r['label'] for r in related_contexts],
                depth - 1,
                visited
            )
            related_contexts.extend(deeper)

        conn.close()
        return related_contexts

    def _extract_keywords(self, query: str) -> List[str]:
        """Extract meaningful keywords from query"""
        # Remove common words
        stop_words = {'the', 'a', 'an', 'how', 'what', 'when', 'where', 'why',
                     'is', 'are', 'was', 'were', 'do', 'does', 'did'}

        words = re.findall(r'\b\w+\b', query.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        return keywords[:5]  # Top 5 keywords

    def _explain_match(
        self,
        candidate: Dict,
        keywords: List[str],
        label_matches: int,
        preview_matches: int,
        concept_matches: int
    ) -> str:
        """Generate human-readable explanation of match"""
        reasons = []

        if label_matches > 0:
            reasons.append(f"Label contains {label_matches} keyword(s)")
        if preview_matches > 0:
            reasons.append(f"Preview mentions {preview_matches} keyword(s)")
        if concept_matches > 0:
            reasons.append(f"Key concepts match {concept_matches} keyword(s)")
        if candidate['priority'] in ['always_check', 'important']:
            reasons.append(f"High priority ({candidate['priority']})")

        return "; ".join(reasons) if reasons else "Low relevance match"

    def _get_context_info(self, label: str) -> Optional[Dict]:
        """Get basic info about a context"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT label, version, preview, key_concepts
            FROM context_locks
            WHERE session_id = ? AND label = ?
        """, (self.session_id, label))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            'label': row[0],
            'version': row[1],
            'preview': row[2],
            'key_concepts': json.loads(row[3] or '[]')
        }
```

#### 2.2 MCP Tool Implementation
```python
@mcp.tool()
async def explore_context_tree(
    topic: str,
    depth: int = 2,
    max_results: int = 10
) -> str:
    """
    Recursively explore related contexts starting from a topic.
    """
    explorer = RecursiveExplorer(DB_PATH, get_current_session_id())
    results = explorer.search(topic, depth=depth, max_contexts=max_results)

    # Format output
    output = []
    output.append(f"🔍 Exploring: {topic} (depth={depth})")
    output.append(f"\n📊 Found {len(results['matches'])} matches\n")

    # Show matches with scores
    for i, match in enumerate(results['matches'], 1):
        score_bar = "█" * int(match['score'] * 10)
        output.append(f"{i}. {match['label']} v{match['version']}")
        output.append(f"   Relevance: {score_bar} {match['score']:.2f}")
        output.append(f"   {match['match_reason']}")
        output.append(f"   Preview: {match['preview'][:100]}...")

        if match.get('loaded_full'):
            output.append(f"   ✅ Full content loaded ({len(match['content'])} chars)")
        else:
            output.append(f"   📄 Preview only (use recall_context to load full)")

        if match.get('related'):
            output.append(f"   🔗 Related: {', '.join(match['related'][:3])}")
        output.append("")

    # Show related topics
    if results.get('related_topics'):
        output.append(f"\n🌲 Related Topics ({len(results['related_topics'])}):")
        for related in results['related_topics'][:5]:
            output.append(f"   • {related['label']} (via {related['source']})")

    # Show exploration path
    output.append(f"\n📈 Exploration Path:")
    for step in results['exploration_path']:
        output.append(f"   {step}")

    return "\n".join(output)
```

---

## Task 3: On-Demand Deepening Protocol

### The Problem with Current System

```python
# Current: Binary choice
wake_up()      # Nothing loaded
recall_context()  # Everything loaded

# Missing: Progressive disclosure
```

### The Solution: Progressive Depth Protocol

```python
# Level 0: Index (automatic)
wake_up()
→ Returns: List of locked contexts (metadata only)

# Level 1: Preview (on-demand)
get_context_preview("api_auth")
→ Returns: 500-char summary + key concepts

# Level 2: Full content (explicit)
recall_context("api_auth")
→ Returns: Full 10-50KB content

# Level 3: Related contexts (recursive)
explore_context_tree("api_auth", depth=2)
→ Returns: Tree of related contexts with previews

# Level 4: Deep synthesis (advanced)
synthesize_knowledge("How does auth flow work end-to-end?")
→ Automatically explores multiple contexts and synthesizes answer
```

### Deliverables

#### 3.1 Knowledge Deepening Manager
```python
# knowledge_deepener.py

class KnowledgeDeepener:
    """
    Manages progressive disclosure of context knowledge.
    Automatically determines what depth is needed for a query.
    """

    def __init__(self, db_path: str, session_id: str):
        self.db_path = db_path
        self.session_id = session_id
        self.explorer = RecursiveExplorer(db_path, session_id)
        self.loaded_contexts = {}  # Track what's been loaded this session

    def answer_query(self, query: str, max_depth: int = 3) -> Dict[str, Any]:
        """
        Automatically determine depth needed and explore accordingly.

        Returns:
        - answer: Synthesized response
        - contexts_used: Which contexts were accessed
        - depth_reached: How deep we went
        - confidence: How confident the answer is
        """
        result = {
            'query': query,
            'answer': '',
            'contexts_used': [],
            'depth_reached': 0,
            'confidence': 0.0,
            'steps': []
        }

        # Step 1: Determine query type
        query_type = self._classify_query(query)
        result['steps'].append(f"Query type: {query_type}")

        # Step 2: Initial search (preview level)
        matches = self.explorer.search(query, depth=1, max_contexts=5)
        result['depth_reached'] = 1
        result['steps'].append(f"Found {len(matches['matches'])} relevant contexts")

        # Step 3: Decide if we need deeper exploration
        if query_type == 'specific' and matches['matches']:
            # Need full content
            top_match = matches['matches'][0]
            if top_match['score'] > 0.7:
                full_content = self.explorer._load_full_content(top_match['label'])
                result['contexts_used'].append({
                    'label': top_match['label'],
                    'depth': 'full',
                    'relevance': top_match['score']
                })
                result['answer'] = self._extract_relevant_section(full_content, query)
                result['depth_reached'] = 2
                result['confidence'] = top_match['score']
            else:
                result['answer'] = top_match['preview']
                result['confidence'] = top_match['score'] * 0.8

        elif query_type == 'exploratory':
            # Need related contexts
            if max_depth >= 2:
                related = self.explorer._explore_related(
                    [m['label'] for m in matches['matches'][:2]],
                    depth=2,
                    visited=set()
                )
                result['depth_reached'] = 3
                result['steps'].append(f"Explored {len(related)} related contexts")

                # Synthesize from multiple previews
                all_previews = [m['preview'] for m in matches['matches'][:3]]
                all_previews.extend([r['preview'] for r in related[:3]])
                result['answer'] = self._synthesize_previews(all_previews, query)
                result['confidence'] = 0.7

        elif query_type == 'overview':
            # Just need previews
            previews = [m['preview'] for m in matches['matches'][:5]]
            result['answer'] = self._synthesize_previews(previews, query)
            result['confidence'] = 0.8

        else:
            # Unknown query type, return top matches
            result['answer'] = "Found relevant contexts:\n" + \
                "\n".join([f"- {m['label']}: {m['preview'][:100]}..."
                          for m in matches['matches'][:3]])
            result['confidence'] = 0.6

        return result

    def _classify_query(self, query: str) -> str:
        """
        Classify query to determine search strategy.

        Types:
        - specific: Looking for exact information (how to, what is)
        - exploratory: Broad understanding (explain, describe)
        - overview: High-level summary (list, show all)
        - navigational: Finding a specific context (find, locate)
        """
        query_lower = query.lower()

        if any(word in query_lower for word in ['how to', 'how do', 'what is', 'where is']):
            return 'specific'
        elif any(word in query_lower for word in ['explain', 'describe', 'tell me about']):
            return 'exploratory'
        elif any(word in query_lower for word in ['list', 'show all', 'what are', 'overview']):
            return 'overview'
        elif any(word in query_lower for word in ['find', 'locate', 'show me']):
            return 'navigational'
        else:
            return 'unknown'

    def _extract_relevant_section(self, content: str, query: str) -> str:
        """
        Extract the most relevant section from full content based on query.
        """
        keywords = self.explorer._extract_keywords(query)

        # Split into sections
        sections = []
        current_section = []
        for line in content.split('\n'):
            if line.strip().startswith('#'):
                if current_section:
                    sections.append('\n'.join(current_section))
                current_section = [line]
            else:
                current_section.append(line)
        if current_section:
            sections.append('\n'.join(current_section))

        # Score sections by keyword density
        scored_sections = []
        for section in sections:
            score = sum(1 for kw in keywords if kw in section.lower())
            scored_sections.append((score, section))

        # Return top section(s)
        scored_sections.sort(reverse=True)
        if scored_sections:
            return scored_sections[0][1]  # Top section
        else:
            return content[:1000]  # Fallback to first 1000 chars

    def _synthesize_previews(self, previews: List[str], query: str) -> str:
        """
        Synthesize an answer from multiple preview texts.
        """
        # Combine previews with context indicators
        synthesis = []
        for i, preview in enumerate(previews, 1):
            synthesis.append(f"[Context {i}]: {preview}")

        # Add summary
        synthesis.insert(0, f"Based on {len(previews)} relevant contexts:")
        synthesis.append(f"\nUse recall_context() to load full details of any specific context.")

        return "\n\n".join(synthesis)
```

#### 3.2 MCP Tool Implementation
```python
@mcp.tool()
async def ask_memory(
    question: str,
    depth: Literal["preview", "full", "deep"] = "preview"
) -> str:
    """
    Ask a question and automatically explore locked contexts to answer it.

    depth='preview': Fast, uses previews only
    depth='full': Loads full content for top matches
    depth='deep': Recursively explores related contexts
    """
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
    output.append("")

    if result['contexts_used']:
        output.append("📚 Sources:")
        for ctx in result['contexts_used']:
            output.append(f"   • {ctx['label']} ({ctx['depth']}, relevance: {ctx['relevance']:.2f})")

    output.append(f"\n🔍 Exploration: {' → '.join(result['steps'])}")

    return "\n".join(output)
```

---

## Integration & Data Flow

### Scenario 1: User starts session
```
1. wake_up() called
   → Returns Level 0 (index): List of all contexts (metadata only)
   → ~2-3KB total

2. User sees: "You have 30 locked contexts: api_auth, database_schema, ..."
```

### Scenario 2: User asks broad question
```
1. User: "What do we have about authentication?"

2. ask_memory("authentication", depth="preview")
   → KnowledgeDeepener classifies as "exploratory"
   → RecursiveExplorer searches metadata
   → Loads Level 1 (previews) for top 5 matches
   → Returns synthesized summary from previews
   → ~5KB total

3. User sees: Preview summaries of 5 auth-related contexts
```

### Scenario 3: User needs specific details
```
1. User: "Show me the full JWT configuration"

2. ask_memory("JWT configuration", depth="full")
   → KnowledgeDeepener classifies as "specific"
   → RecursiveExplorer finds jwt_config (score: 0.95)
   → Loads Level 2 (full content) for jwt_config
   → Extracts relevant section about configuration
   → ~15KB total

3. User sees: Full JWT config details
```

### Scenario 4: User explores relationships
```
1. User: "What's related to API authentication?"

2. explore_context_tree("api_authentication", depth=2)
   → RecursiveExplorer starts with api_authentication
   → Loads preview (Level 1)
   → Finds related: jwt_config, oauth_setup, rate_limiting
   → Recursively loads previews of related contexts
   → Builds relationship tree
   → ~10KB total

3. User sees:
   api_authentication (0.95)
   ├─ jwt_config (explicit, 0.90)
   │  └─ security_best_practices (related, 0.75)
   └─ rate_limiting (co-accessed, 0.80)
```

### Scenario 5: Automatic deepening
```
1. User: "How does the complete auth flow work from login to API call?"

2. ask_memory("complete auth flow", depth="deep")
   → Classifies as "exploratory" + "specific"
   → Searches: login_process, jwt_generation, api_authentication
   → Loads full content for top 2 (Level 2)
   → Explores related contexts (Level 3)
   → Synthesizes multi-context answer
   → ~30KB total (still 70% less than loading all 30 contexts)

3. User sees: Comprehensive explanation synthesized from 4 contexts
```

---

## Success Metrics

### Token Efficiency
| Scenario | Old System | New System | Improvement |
|----------|------------|------------|-------------|
| Session start | 20KB | 3KB | 85% |
| Broad search | 300KB (all) | 5KB (previews) | 98% |
| Specific lookup | 50KB | 15KB (targeted) | 70% |
| Deep exploration | 300KB (all) | 30KB (selective) | 90% |

### Response Time
| Operation | Target | How |
|-----------|--------|-----|
| Metadata search | <50ms | In-memory index |
| Preview load | <100ms | Small DB query |
| Full content | <200ms | Single context load |
| Tree exploration | <500ms | Iterative, cached |

### Accuracy
| Metric | Target |
|--------|--------|
| Relevant result in top 3 | >90% |
| False positives | <10% |
| Synthesis coherence | >80% user satisfaction |

---

## Next Steps

1. Review this design
2. Approve changes to schema and API
3. Implement in order:
   - Day 1-2: Database schema + preview generation
   - Day 3-4: RecursiveExplorer class
   - Day 5-6: KnowledgeDeepener + ask_memory tool
   - Day 7: Integration testing
   - Week 2: Optimization and deployment

Questions to discuss:
- Is preview auto-generation algorithm sufficient?
- Should we add semantic similarity (requires embeddings)?
- How to handle context updates (invalidation)?
- User experience: When to auto-deepen vs ask user?
