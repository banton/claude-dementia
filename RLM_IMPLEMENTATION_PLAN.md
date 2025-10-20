# RLM Memory Optimization Implementation Plan

## Overview
Implement MIT's Recursive Language Model approach to prevent context rot in the memory system. Based on research showing 2x performance improvement by avoiding context overload through recursive exploration with focused, small context windows.

## Background
MIT researchers found that by token 50,000, models start forgetting earlier decisions. By 100,000 tokens, they're rewriting established patterns. Their solution: treat large codebases as external variables and recursively explore them without loading everything at once. This achieved 64.9% vs 30.3% performance on long-context tasks.

## Tasks (8 total)

### HIGH PRIORITY (4 tasks) - Immediate Impact

#### 1. Implement Lazy Loading for wake_up() function
**Files to Modify:**
- `/Users/banton/Sites/claude-dementia/claude_mcp_hybrid.py` (wake_up function)
- `/Users/banton/Sites/claude-dementia/active_context_engine.py` (add metadata-only methods)

**Current Behavior:**
- wake_up() loads all locked contexts into memory
- Returns full content in the response
- Can cause context overload with 30+ contexts

**Intended Result:**
- wake_up() returns only metadata (topic, version, tags, priority, size, last_accessed)
- Content loads on-demand via recall_context()
- Add new wake_up_minimal() option for ultra-light starts

**Implementation Steps:**
1. Create get_context_metadata() method that returns only headers
2. Modify wake_up to use metadata by default
3. Add wake_up(full=True) parameter for backward compatibility
4. Track last_accessed timestamp for each context

**Test Plan:**
1. Count tokens returned by old vs new wake_up
2. Measure response time improvement
3. Verify recall_context still works after minimal wake_up
4. Test with 50+ locked contexts

**Success Metrics:**
- wake_up response < 5000 tokens (vs current ~20000+)
- Response time < 100ms
- Memory usage reduced by 80%+

---

#### 2. Create recursive_explore() function for iterative context discovery
**Files to Create/Modify:**
- `/Users/banton/Sites/claude-dementia/recursive_explorer.py` (new file)
- `/Users/banton/Sites/claude-dementia/claude_mcp_hybrid.py` (add @mcp.tool decorator)

**Intended Result:**
- New function that recursively explores contexts based on query
- Builds understanding iteratively without loading everything
- Returns synthesized findings from multiple small explorations

**Algorithm:**
```python
def explore(query, depth=0, max_depth=3):
    if depth >= max_depth:
        return current_findings
    
    contexts = rank_contexts(query)[:5]  # Top 5 only
    findings = []
    
    for context in contexts:
        chunk = load_chunk(context, size=5000)
        if is_relevant(chunk, query):
            findings.append(extract_info(chunk))
            if needs_deeper_search(chunk):
                sub_query = refine_query(query, chunk)
                findings.extend(explore(sub_query, depth+1))
    
    return synthesize(findings)
```

**Test Plan:**
1. Compare results: recursive_explore vs loading all contexts
2. Measure token usage (should be <20% of full load)
3. Test with nested queries requiring multi-hop reasoning
4. Verify synthesis quality with known test cases

**Success Metrics:**
- Finds relevant info in <3 recursions
- Uses <10000 tokens per exploration
- Accuracy >= 95% compared to full context load
- Response time <2 seconds for typical queries

---

#### 3. Implement Smart check_contexts() with Confidence Scoring
**Files to Modify:**
- `/Users/banton/Sites/claude-dementia/active_context_engine.py` (check_context_relevance method)

**Current Behavior:**
- Returns all potentially relevant contexts
- No prioritization or confidence scores
- Can return 10+ contexts for broad queries

**Intended Result:**
- Returns max 3-5 contexts with confidence scores
- Prioritizes by relevance, recency, and importance
- Provides reasoning for why each context is relevant

**Relevance Scoring Algorithm:**
```python
def calculate_relevance_score(query, context):
    score = 0.0
    
    # Keyword matching (0-40 points)
    keywords = extract_keywords(query)
    matches = count_keyword_matches(context, keywords)
    score += min(40, matches * 10)
    
    # Semantic similarity (0-30 points)
    score += semantic_similarity(query, context.summary) * 30
    
    # Recency bonus (0-15 points)
    days_old = (now - context.last_accessed).days
    score += max(0, 15 - days_old)
    
    # Priority bonus (0-15 points)
    if context.priority == 'always_check': score += 15
    elif context.priority == 'important': score += 10
    elif context.priority == 'reference': score += 5
    
    return score / 100  # Normalize to 0-1
```

**Success Metrics:**
- Precision: 90%+ (returned contexts are relevant)
- Recall: 85%+ (finds most relevant contexts)
- Response time <200ms for typical queries

---

#### 4. Create Context Working Set Manager
**Files to Create/Modify:**
- `/Users/banton/Sites/claude-dementia/working_set_manager.py` (new file)
- `/Users/banton/Sites/claude-dementia/claude_mcp_hybrid.py` (integrate manager)

**Implementation:**
```python
class WorkingSetManager:
    def __init__(self, max_size=10, max_tokens=50000):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.max_tokens = max_tokens
        self.current_tokens = 0
    
    def load_context(self, topic):
        if topic in self.cache:
            # Move to end (most recent)
            self.cache.move_to_end(topic)
            return self.cache[topic]
        
        # Load from database
        context = fetch_from_db(topic)
        tokens = count_tokens(context)
        
        # Evict if necessary
        while len(self.cache) >= self.max_size or 
              self.current_tokens + tokens > self.max_tokens:
            self.evict_lru()
        
        self.cache[topic] = context
        self.current_tokens += tokens
        return context
```

**Success Metrics:**
- Memory usage never exceeds 50k tokens
- Cache hit rate >70% for typical workflows
- Zero context overflow errors
- Response time <50ms for cached contexts

---

### MEDIUM PRIORITY (2 tasks) - Long-term Scaling

#### 5. Implement Hierarchical Context Organization
**Files to Modify:**
- `/Users/banton/Sites/claude-dementia/claude_mcp_hybrid.py` (lock_context function)
- Database schema: Add parent_context and hierarchy_level columns

**Database Schema Changes:**
```sql
ALTER TABLE context_locks ADD COLUMN parent_context TEXT;
ALTER TABLE context_locks ADD COLUMN hierarchy_level INTEGER DEFAULT 0;
ALTER TABLE context_locks ADD COLUMN child_contexts TEXT; -- JSON array
```

**Implementation:**
- Parent-child relationships between contexts
- Automatic grouping of related contexts
- Navigation from high-level to detailed contexts
- Auto-organize existing contexts by detecting common prefixes

**Success Metrics:**
- Context discovery 50% faster via hierarchy
- Related contexts found in single query
- Auto-organization groups 80%+ of contexts correctly

---

#### 6. Add Context Compression and Archival System
**Files to Create/Modify:**
- `/Users/banton/Sites/claude-dementia/context_compressor.py` (new file)
- `/Users/banton/Sites/claude-dementia/claude_mcp_hybrid.py` (add compression triggers)

**Three-Tier Storage:**
- **HOT:** Full content, accessed <24h
- **WARM:** Compressed summary, accessed <7d
- **COLD:** Title + tags only, accessed >30d

**Compression Logic:**
```python
class ContextCompressor:
    def compress(self, content: str) -> str:
        # Extract key points, remove examples
        # Summarize verbose sections
        # Keep critical rules intact
        return compressed
    
    def should_compress(self, last_accessed, access_count):
        days_old = (now - last_accessed).days
        if days_old > 7 and access_count < 3:
            return True
```

**Success Metrics:**
- 70%+ size reduction for old contexts
- <500ms decompression time
- No loss of critical information
- Database size plateaus instead of growing infinitely

---

### CRITICAL INFRASTRUCTURE (1 task)

#### 7. Build Comprehensive Test Suite for RLM Improvements
**Files to Create:**
- `/Users/banton/Sites/claude-dementia/tests/test_lazy_loading.py`
- `/Users/banton/Sites/claude-dementia/tests/test_recursive_explore.py`
- `/Users/banton/Sites/claude-dementia/tests/test_working_set.py`
- `/Users/banton/Sites/claude-dementia/tests/benchmark_performance.py`

**Test Coverage:**
1. **test_lazy_loading.py** - Verify minimal wake_up, performance
2. **test_recursive_explore.py** - Test iterative discovery, token efficiency
3. **test_working_set.py** - Verify LRU eviction, memory limits
4. **benchmark_performance.py** - Compare old vs new, generate reports

**Success Metrics:**
- All tests passing
- 70%+ performance improvement demonstrated
- Memory usage reduced by 80%+
- No regression in functionality

---

### MIGRATION (1 task)

#### 8. Create Migration Script for Existing Contexts
**Files to Create:**
- `/Users/banton/Sites/claude-dementia/migrate_to_rlm.py`

**Migration Steps:**
1. Add new database columns (parent_context, hierarchy_level, etc.)
2. Auto-organize contexts into hierarchy by common prefixes
3. Initialize access tracking metadata
4. Generate summaries for large contexts (>10k chars)

**Success Metrics:**
- Zero data loss
- 80%+ contexts auto-organized
- Migration completes in <30 seconds
- Backward compatible

---

## Implementation Order
1. **Week 1:** Test suite setup (TDD approach) + Lazy loading
2. **Week 2:** Working set manager + Recursive explore
3. **Week 3:** Smart check_contexts + Hierarchical organization
4. **Week 4:** Compression system + Migration script + Deploy

## Overall Success Criteria
- ✅ Context rot eliminated (no degradation at 50+ contexts)
- ✅ 80% reduction in memory usage
- ✅ 70% performance improvement
- ✅ Maintains all current functionality
- ✅ Backward compatible
- ✅ Scales to 100+ contexts without degradation

## Key Innovation
Following MIT's RLM approach, the memory system transforms from a "load everything" model (causing context rot) to a lightweight orchestrator that:
- Maintains only an index in memory
- Recursively explores contexts on-demand
- Works with small, focused context windows (~10k tokens)
- Synthesizes findings from multiple explorations
- Never exceeds manageable context size

This mirrors how MIT's GPT-5-mini achieved 2x the performance of GPT-5 - not by being smarter, but by changing how it interacts with large amounts of information.

## Next Steps
1. Review and approve plan
2. Set up test environment
3. Begin with test suite creation
4. Implement lazy loading (quick win)
5. Proceed through implementation order

---

*Document created: 2025-01-19*
*Based on: MIT Recursive Language Models research (October 2025)*
*Target completion: 4 weeks*
