# Safe Workflow for Claude Desktop

## Context Window Management Guide

**Problem:** Claude Desktop has a 200K token context window that can fill quickly with MCP tools.
**Solution:** Follow this guide to use dementia tools efficiently.

---

## ✅ ALWAYS SAFE (Use Freely)

These tools have minimal token cost (~150-1,000 tokens):

### Session Management
```python
dementia:wake_up()                          # ~300 tokens
dementia:memory_status()                    # ~250 tokens
```

### Context Discovery
```python
dementia:explore_context_tree(flat=True)    # ~1,000 tokens (DEFAULT)
dementia:check_contexts("my query")         # ~350 tokens
```

### Context Preview (RLM Mode)
```python
dementia:recall_context(
    topic="my_topic",
    preview_only=True                        # ~350 tokens ✅
)
```

### Database Queries (with LIMIT)
```python
dementia:query_database(
    query="SELECT * FROM table LIMIT 10"   # ~150-500 tokens
)
```

---

## ⚠️ USE CAREFULLY (Moderate Cost)

These operations accumulate tokens if used repeatedly:

### Full Context Recall
```python
dementia:recall_context(
    topic="my_topic",
    preview_only=False                       # ~900 tokens EACH
)
```

**Best practice:**
1. Start with `preview_only=True` to scan
2. Load full content only for 2-3 most relevant contexts

### Database Schema Inspection
```python
dementia:inspect_database(mode="schema")    # ~1,800 tokens
```

**Best practice:** Run once per session, not repeatedly

### Batch Context Operations
```python
dementia:batch_recall_contexts(
    topics=["api", "database", "security"],
    preview_only=True                        # ✅ Safe
)
```

**Warning:** Never use `preview_only=False` for batch operations!

---

## 🔴 DANGEROUS (Avoid or Confirm)

These operations can overflow your context window:

### Full Context Tree (Old Default)
```python
# ❌ BEFORE (dangerous with 93 contexts)
dementia:explore_context_tree(flat=False)   # ~4,650 tokens

# ✅ FIXED - Now requires confirmation
dementia:explore_context_tree(
    flat=False,
    confirm_full=True                        # Shows warning first
)
```

**What happens:** Returns preview (~100 words) for EVERY context
- 50 contexts = ~2,500 tokens
- 100 contexts = ~5,000 tokens
- 200 contexts = ~10,000 tokens (5% of window!)

### Multiple Full Recalls
```python
# ❌ BAD
for topic in ["api1", "api2", "api3", "api4", "api5"]:
    recall_context(topic, preview_only=False)
# Cost: 5 × 900 = 4,500 tokens

# ✅ GOOD
batch_recall_contexts(
    topics=["api1", "api2", "api3", "api4", "api5"],
    preview_only=True
)
# Cost: ~1,500 tokens
```

### Unlimited Database Queries
```python
# ❌ BAD
SELECT * FROM large_table                    # Could return 10,000+ rows

# ✅ GOOD
SELECT * FROM large_table LIMIT 20          # Controlled size
```

---

## 📊 Token Cost Reference

| Operation | Token Cost | Safe? | Notes |
|-----------|------------|-------|-------|
| `wake_up()` | ~300 | ✅ | Always safe |
| `memory_status()` | ~250 | ✅ | Always safe |
| `explore_context_tree(flat=True)` | ~1,000 | ✅ | Labels only (DEFAULT) |
| `explore_context_tree(flat=False)` | ~50 per context | 🔴 | Now requires `confirm_full=True` |
| `recall_context(..., preview_only=True)` | ~350 | ✅ | RLM preview mode |
| `recall_context(..., preview_only=False)` | ~900 | ⚠️ | Full content - use sparingly |
| `check_contexts(text)` | ~350 | ✅ | Relevance matching only |
| `query_database(simple)` | ~150-500 | ✅ | With LIMIT clause |
| `inspect_database(schema)` | ~1,800 | ⚠️ | Once per session |

---

## 🎯 Recommended Workflows

### 1. Session Start (Safe)
```python
# Step 1: Wake up and check status
dementia:wake_up()

# Step 2: See what contexts exist (labels only)
dementia:explore_context_tree(flat=True)

# Step 3: Check relevant contexts for current task
dementia:check_contexts("I'm working on API authentication")
```

**Total cost:** ~1,650 tokens

---

### 2. Context Discovery (Safe)
```python
# Step 1: Search for relevant contexts
dementia:check_contexts("database migrations")

# Step 2: Preview top matches
dementia:recall_context(
    topic="database_config",
    preview_only=True
)

# Step 3: Load ONLY the most relevant (1-2 contexts)
dementia:recall_context(
    topic="database_config",
    preview_only=False
)
```

**Total cost:** ~1,600 tokens

---

### 3. Database Analysis (Safe)
```python
# Step 1: Check schema (once)
dementia:inspect_database(mode="schema")

# Step 2: Run focused queries with LIMIT
dementia:query_database(
    query="SELECT title, status FROM posts
           WHERE status='draft'
           LIMIT 20"
)

# Step 3: Aggregate for summary
dementia:query_database(
    query="SELECT category, COUNT(*) as count
           FROM posts
           GROUP BY category"
)
```

**Total cost:** ~2,500 tokens

---

### 4. Content Production Workflow (Safe)
```python
# Step 1: Load style guide once
dementia:recall_context(
    topic="style_guide",
    preview_only=False
)

# Step 2: Check related content (preview mode)
dementia:check_contexts("writing technical tutorials")

# Step 3: Query database for similar posts
dementia:query_database(
    query="SELECT title, tags FROM posts
           WHERE category='tutorial'
           LIMIT 10"
)

# Step 4: Work on content...

# Step 5: Create handover
dementia:sleep()
```

**Total cost:** ~3,000 tokens

---

## 🚨 Emergency: Context Window Full

If your context window fills up:

1. **Check current usage:**
   - Look for system warning about token count
   - Estimate: 66,962 tokens baseline + your operations

2. **Stop using these immediately:**
   - `explore_context_tree(flat=False)`
   - `recall_context(..., preview_only=False)` in loops
   - Large database queries without LIMIT

3. **Switch to safe mode:**
   - Use `flat=True` for all tree exploration
   - Use `preview_only=True` for all context recalls
   - Add LIMIT 10 to all database queries

4. **Start new session if needed:**
   - Complete current work
   - Run `dementia:sleep()` to save progress
   - Exit and restart Claude Desktop
   - Run `dementia:wake_up()` to resume

---

## 📈 Monitoring Context Usage

### Check Your Budget

**Claude Desktop capacity:** 200,000 tokens total

**Baseline overhead:**
- System instructions: ~40,000 tokens
- MCP tool definitions: ~15,000 tokens
- User memories: ~8,000 tokens
- Conversation history: ~3,000 tokens
- **Total baseline:** ~66,000 tokens (33%)

**Available for work:** ~134,000 tokens

### Safe Operating Limits

- **Conservative:** Keep tool responses under 20,000 tokens (~10%)
- **Moderate:** Up to 40,000 tokens (~20%)
- **Aggressive:** Up to 60,000 tokens (~30%)
- **Danger zone:** Above 60,000 tokens

### Typical Session Budgets

**Light session** (safe):
- wake_up + explore_tree(flat) + 5 previews + 3 full recalls
- Cost: ~6,000 tokens (3% of window)

**Medium session** (moderate):
- wake_up + schema + 10 previews + 5 full recalls + 10 queries
- Cost: ~15,000 tokens (7.5% of window)

**Heavy session** (careful):
- All tools + 20 previews + 10 full recalls + complex queries
- Cost: ~30,000 tokens (15% of window)

---

## 🔧 What Changed (v3.2 Fixes)

### Before (Problematic)
```python
explore_context_tree(flat=False)  # DEFAULT - returned ALL previews
# With 93 contexts: ~4,650 tokens
```

### After (Safe)
```python
explore_context_tree(flat=True)   # DEFAULT - labels only
# With 93 contexts: ~1,000 tokens

explore_context_tree(flat=False, confirm_full=True)  # Requires confirmation
# Shows warning: "This will cost ~4,650 tokens. Proceed?"
```

### New Safety Features

1. **Changed default:** `flat=True` is now default for `explore_context_tree()`
2. **Confirmation required:** `flat=False` with >50 contexts requires `confirm_full=True`
3. **Token estimates:** `wake_up()` now shows token cost estimates
4. **Overflow warnings:** Automatic warnings when context count is high

---

## 📚 Additional Resources

- **Cost Analysis:** See `VOYAGE_AI_COST_ANALYSIS.md` for API costs
- **Full Investigation:** See Claude Desktop test report (from user testing)
- **Token Tracking:** Use `dementia:usage_statistics(days=7)` for actual costs

---

## 🎓 Summary

**Golden Rules:**
1. Always use `flat=True` for context tree exploration (now default)
2. Always start with `preview_only=True` for context recalls
3. Always use LIMIT in database queries
4. Load full context content only when absolutely needed (2-3 per session)
5. Monitor token estimates in `wake_up()` output

**Safe patterns work.** Following these guidelines, you can:
- Manage 100+ locked contexts safely
- Run complex database analyses
- Maintain session continuity across days
- Stay well under context window limits

**The system is designed for this.** The RLM (Retrieval-optimized Language Model) pattern with previews is specifically built to handle large knowledge bases in limited context windows.

---

*Last updated: 2024-10-25 (v3.2 - Context Overflow Prevention)*
