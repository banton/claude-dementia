# RLM Engagement Strategy: Making LLMs Actually Use Your Tools

## Analysis of Sequential Thinking MCP Success

### Key Success Factors

#### 1. **Extremely Detailed Tool Description** (The Secret Weapon)

The sequential thinking tool has a **496-word description** that acts as embedded prompting:

```typescript
const SEQUENTIAL_THINKING_TOOL: Tool = {
  name: "sequentialthinking",
  description: `A detailed tool for dynamic and reflective problem-solving through thoughts.
This tool helps analyze problems through a flexible thinking process that can adapt and evolve.
Each thought can build on, question, or revise previous insights as understanding deepens.

When to use this tool:
- Breaking down complex problems into steps
- Planning and design with room for revision
- Analysis that might need course correction
- Problems where the full scope might not be clear initially
- Problems that require a multi-step solution
- Tasks that need to maintain context over multiple steps
- Situations where irrelevant information needs to be filtered out

Key features:
- You can adjust total_thoughts up or down as you progress
- You can question or revise previous thoughts
- You can add more thoughts even after reaching what seemed like the end
...

You should:
1. Start with an initial estimate of needed thoughts, but be ready to adjust
2. Feel free to question or revise previous thoughts
3. Don't hesitate to add more thoughts if needed, even at the "end"
...
11. Only set next_thought_needed to false when truly done and a satisfactory answer is reached`,
```

**Why This Works:**
- Tool descriptions are ALWAYS sent to the LLM with every request
- They become part of the system prompt context
- LLM reads them and understands when/how to use the tool
- The description is **instructional**, not just informational

#### 2. **External Prompting via CLAUDE.md**

Found in wp-devops project:
```markdown
> **You are Claude Code... Use sequential thinking when making plans.**
```

This creates a reinforcement loop:
- System prompt: Tool description tells LLM what it can do
- User context: CLAUDE.md tells LLM when to do it
- Result: LLM naturally uses the tool

#### 3. **Simple, Predictable Interface**

```typescript
{
  thought: string,           // What you're thinking
  nextThoughtNeeded: boolean, // Continue?
  thoughtNumber: number,      // Current step
  totalThoughts: number       // Estimated total
}
```

- Only 4 required parameters
- Boolean flag makes it easy to continue
- LLM can easily track where it is in the process

#### 4. **Server-Side State Management**

```typescript
export class SequentialThinkingServer {
  private thoughtHistory: ThoughtData[] = [];
  private branches: Record<string, ThoughtData[]> = {};
```

- Server maintains state across calls
- LLM doesn't need to track everything
- Each call is lightweight

#### 5. **Visual Feedback (for humans)**

```typescript
console.error(formattedThought);  // Logs to stderr
```

Creates formatted output:
```
┌────────────────────────┐
│ 💭 Thought 1/5         │
├────────────────────────┤
│ I need to check...     │
└────────────────────────┘
```

This helps humans understand what's happening, building trust in the tool.

---

## Applying This to RLM Memory Tools

### Problem: Current Tool Descriptions

Current dementia MCP tools:
```python
@mcp.tool()
async def wake_up() -> str:
    """
    Start a development session and load context.
    Shows: active todos, recent changes, locked contexts.
    """
```

**Issues:**
- Too brief (3 lines)
- Doesn't explain WHEN to use it
- Doesn't provide examples
- No guidance on workflow

### Solution: Enhanced Tool Descriptions

#### Pattern 1: Embedded Usage Instructions

```python
@mcp.tool()
async def wake_up() -> str:
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

    Returns: Formatted summary of session state and available contexts
    """
```

#### Pattern 2: Context-Aware Descriptions

```python
@mcp.tool()
async def ask_memory(
    question: str,
    depth: Literal["preview", "full", "deep"] = "preview"
) -> str:
    """
    Intelligently search locked contexts and answer questions using progressive depth.

    **When to use this tool:**
    - User asks: "What do we have about X?"
    - You need to find relevant context but don't know exact label
    - Planning a feature and need to check existing patterns
    - Debugging and need to recall how something was implemented
    - Before making architectural decisions

    **Depth levels explained:**

    depth="preview" (RECOMMENDED for most queries):
    - Fast: <200ms response time
    - Searches metadata and previews only
    - Returns summaries of 3-5 relevant contexts
    - Uses ~5KB tokens
    - Best for: "What contexts exist about X?" or exploration

    depth="full":
    - Medium: ~500ms response time
    - Loads complete content for top matches
    - Returns detailed information extracted from contexts
    - Uses ~20KB tokens
    - Best for: "Show me the specifics of X" or implementation details

    depth="deep":
    - Slower: ~1000ms response time
    - Recursively explores related contexts
    - Synthesizes information from multiple sources
    - Uses ~40KB tokens
    - Best for: "Explain the complete X system" or architecture questions

    **Usage patterns:**

    Exploratory questions:
    - "What authentication methods do we support?"
      → ask_memory("authentication methods", depth="preview")

    Specific lookups:
    - "Show me the JWT token expiration settings"
      → ask_memory("JWT token expiration", depth="full")

    System understanding:
    - "How does the auth flow work from login to API call?"
      → ask_memory("auth flow login to API", depth="deep")

    **You should:**
    1. Start with preview depth for all queries
    2. Only use full/deep if preview isn't sufficient
    3. Use specific keywords in questions for better matches
    4. If confidence is low, try rephrasing the question
    5. Use explore_context_tree() instead if you want relationship visualization

    **Performance tips:**
    - Preview depth: 5KB tokens, <200ms
    - Full depth: 20KB tokens, <500ms
    - Deep depth: 40KB tokens, <1000ms
    - All much better than loading all contexts (300KB+)

    Returns: Answer with confidence score, sources used, and exploration path
    """
```

#### Pattern 3: Workflow Integration

```python
@mcp.tool()
async def explore_context_tree(
    topic: str,
    depth: int = 2,
    max_results: int = 10
) -> str:
    """
    Recursively explore related contexts starting from a topic, showing relationships.

    **When to use this tool:**
    - You know a context exists but want to see what's related
    - Understanding dependencies between contexts
    - Discovering related patterns or configurations
    - Mapping out a domain area (e.g., "show me everything about authentication")

    **When NOT to use this tool:**
    - Don't use if you just need content (use recall_context instead)
    - Don't use for simple searches (use ask_memory instead)
    - Don't use at session start (use wake_up instead)

    **Depth parameter:**
    - depth=1: Shows direct relationships only
    - depth=2: Shows relationships of relationships (RECOMMENDED)
    - depth=3: Three levels deep (use sparingly, can be large)

    **Example outputs:**

    explore_context_tree("api_authentication", depth=2)

    Returns:
    ```
    🔍 Exploring: api_authentication (depth=2)

    api_authentication (relevance: 0.95)
    ├─ jwt_config (explicit link, relevance: 0.90)
    │  └─ security_best_practices (related, relevance: 0.75)
    ├─ oauth_setup (related, relevance: 0.82)
    └─ rate_limiting (co-accessed, relevance: 0.80)
    ```

    **Integration with other tools:**
    1. wake_up() → See list of contexts
    2. explore_context_tree("topic") → Understand relationships
    3. get_context_preview() → Quick look at specific contexts
    4. recall_context() → Load full details

    **You should:**
    - Use this when planning work that touches multiple areas
    - Start with depth=2 (good balance of detail vs performance)
    - Look for unexpected relationships that might affect your work
    - Use the relationship visualization to identify dependencies

    Returns: Tree visualization with relevance scores and relationship types
    """
```

---

## Implementation Strategy

### Phase 1: Update Tool Descriptions (Immediate)

Update all MCP tool descriptions in `claude_mcp_hybrid.py`:

```python
TOOL_DESCRIPTIONS = {
    'wake_up': """...""",  # 250+ words
    'sleep': """...""",  # 150+ words
    'memory_update': """...""",  # 200+ words
    'lock_context': """...""",  # 300+ words
    'recall_context': """...""",  # 200+ words
    'explore_context_tree': """...""",  # 300+ words (NEW)
    'ask_memory': """...""",  # 400+ words (NEW)
    'get_context_preview': """...""",  # 150+ words (NEW)
}
```

**Target**: Each description should be 150-400 words

**Include**:
- When to use / when NOT to use
- What it returns
- Parameter explanations
- Example workflows
- Best practices
- Performance characteristics

### Phase 2: Update CLAUDE.md (Project Guidance)

Add memory tool guidance to project CLAUDE.md:

```markdown
## 🧠 Memory System Usage

### Start Every Session
```bash
wake_up  # ALWAYS call first
```

### When Making Decisions
Use the memory system to check for existing patterns:
- **Planning feature**: ask_memory("feature topic", depth="preview")
- **Need specifics**: recall_context("exact_topic")
- **Understanding architecture**: explore_context_tree("domain", depth=2)

### Before Committing Code
Check for relevant rules:
```python
check_contexts("I'm about to modify the authentication flow")
```

### End of Session
```python
sleep()  # Creates handover for next session
```
\```

### Progressive Memory Loading
1. Start light: wake_up() loads only metadata
2. Explore: ask_memory() or explore_context_tree() for discovery
3. Load details: recall_context() only when needed
4. Lock new patterns: lock_context() for important decisions

**Never load all contexts at once** - use progressive deepening instead.
```

### Phase 3: Add Prompting Hooks (System Integration)

#### A. Session Start Reminder
```python
@mcp.tool()
async def wake_up() -> str:
    """..."""

    output = []
    output.append("🌅 Good morning! Loading your context...")

    # ... existing code ...

    # ADD: Prompting hint
    output.append("\n💡 Tip: Use ask_memory(question) to search contexts, " +
                 "or recall_context(topic) to load specific details")

    return "\n".join(output)
```

#### B. Proactive Suggestions
```python
@mcp.tool()
async def check_contexts(text: str) -> str:
    """
    Check if any locked contexts are relevant to given text.
    This tool PROACTIVELY checks for rule violations and relevant contexts.

    **IMPORTANT**: This tool is called AUTOMATICALLY when:
    - You're about to modify code
    - Making architectural decisions
    - Implementing new features
    - User asks "should I..." or "is it ok to..."
    """

    engine = ActiveContextEngine(DB_PATH)
    relevant = engine.check_context_relevance(text, get_current_session_id())

    if not relevant:
        return "✅ No specific rules or contexts apply. Proceed with best practices."

    # Show relevant contexts
    output = []
    output.append(f"⚠️ Found {len(relevant)} relevant contexts:")

    for ctx in relevant[:3]:
        output.append(f"\n📌 {ctx['label']} (relevance: {ctx['score']:.2f})")
        output.append(f"   Preview: {ctx['preview'][:100]}...")
        output.append(f"   💡 Use recall_context('{ctx['label']}') for full details")

    return "\n".join(output)
```

### Phase 4: Create Tool Usage Patterns Resource

Add a new MCP resource that exposes usage patterns:

```python
@mcp.resource("memory://usage-patterns")
def memory_usage_patterns() -> str:
    """
    Common patterns for using the memory system effectively.
    LLM should consult this when unsure how to use memory tools.
    """
    return """
# Memory System Usage Patterns

## Pattern 1: Session Start
```
wake_up()
→ Review high-priority contexts
→ Check for locked rules matching current task
→ Use recall_context() only if needed
```

## Pattern 2: Planning New Feature
```
ask_memory("feature domain", depth="preview")
→ Review relevant existing patterns
→ explore_context_tree() to see dependencies
→ Check if any always_check contexts apply
→ Proceed with implementation
→ lock_context() for new patterns discovered
```

## Pattern 3: Debugging
```
ask_memory("error symptom", depth="full")
→ Check if similar issues documented
→ recall_context("relevant_fix") if match found
→ Apply fix
→ memory_update("Fixed X using pattern Y")
```

## Pattern 4: Architectural Decision
```
explore_context_tree("architecture_area", depth=2)
→ Understand related contexts and constraints
→ ask_memory("should I...", depth="deep")
→ Make decision
→ lock_context(decision, priority="always_check")
```

## Anti-Patterns (Don't Do This)

❌ Loading all contexts at session start
   ✅ Use wake_up() + progressive loading

❌ recall_context() for exploration
   ✅ Use ask_memory() or explore_context_tree()

❌ Forgetting to lock important decisions
   ✅ lock_context() for patterns others should follow

❌ Creating too many always_check contexts
   ✅ Reserve for critical rules only
"""
```

---

## Comparison: Before vs After

### Before (Current State)

**Tool Description:**
```python
async def recall_context(topic: str, version: Optional[str] = "latest") -> str:
    """
    Recall locked context by topic and version.
    Use 'latest' for most recent version.
    """
```

**Problems:**
- LLM doesn't know when to use it
- No workflow guidance
- No performance implications mentioned
- Could easily overuse and load too many contexts

### After (RLM-Enhanced)

**Tool Description:**
```python
async def recall_context(topic: str, version: Optional[str] = "latest") -> str:
    """
    Load the complete content of a specific locked context.

    **When to use this tool:**
    - You need FULL details of a specific context
    - ask_memory() returned a match but you need complete content
    - Implementing something that requires exact specifications
    - User explicitly asks "show me the full X"

    **When NOT to use this tool:**
    - Don't use for exploration (use ask_memory or explore_context_tree)
    - Don't load multiple contexts sequentially (use ask_memory with depth="deep")
    - Don't use at session start (use wake_up, which shows available contexts)

    **Performance:**
    - Loads 10-50KB per context
    - <200ms response time
    - Updates access tracking (affects cache priority)

    **Progressive loading workflow:**
    1. wake_up() → See that "api_auth" context exists
    2. get_context_preview("api_auth") → "This covers JWT tokens and OAuth"
    3. recall_context("api_auth") → Full 25KB specification

    **You should:**
    - Confirm you need the full content before calling
    - Use preview tools first to verify relevance
    - Prefer ask_memory() for synthesis across multiple contexts
    - Only load contexts you'll actually reference

    version parameter:
    - "latest": Most recent version (RECOMMENDED)
    - "1.0", "2.1", etc.: Specific version if needed

    Returns: Complete context content with metadata (size, last modified, relationships)
    """
```

**Benefits:**
- Clear when/when-not guidelines
- Workflow integration
- Performance awareness
- Encourages progressive loading

---

## Measurement: How to Know It's Working

### Metrics to Track

1. **Tool Usage Frequency**
   - Goal: `ask_memory()` used 5x more than `recall_context()`
   - Indicates: LLM is using progressive loading

2. **Token Efficiency**
   - Goal: Average tokens/query < 30KB (vs 300KB loading all)
   - Indicates: Smart depth selection

3. **Context Hit Rate**
   - Goal: 80%+ of `ask_memory()` returns useful results
   - Indicates: Good keyword matching and scoring

4. **Session Start Pattern**
   - Goal: 95%+ of sessions start with `wake_up()`
   - Indicates: LLM learned the workflow

5. **Progressive Deepening**
   - Goal: 60%+ queries use preview depth first
   - Indicates: LLM not over-loading

### Logging for Analysis

Add tracking to each tool:

```python
def track_tool_usage(tool_name: str, params: Dict):
    """Log tool usage for analysis"""
    conn = get_db()
    conn.execute("""
        INSERT INTO tool_usage_log
        (tool_name, params, timestamp, session_id)
        VALUES (?, ?, ?, ?)
    """, (tool_name, json.dumps(params), time.time(), get_current_session_id()))
    conn.commit()

@mcp.tool()
async def ask_memory(question: str, depth: str = "preview") -> str:
    track_tool_usage("ask_memory", {"depth": depth, "question_length": len(question)})
    # ... implementation
```

Then analyze:
```sql
-- How often is each depth used?
SELECT depth, COUNT(*)
FROM tool_usage_log
WHERE tool_name = 'ask_memory'
GROUP BY depth;

-- Are sessions starting correctly?
SELECT session_id,
       MIN(timestamp) as first_call,
       (SELECT tool_name FROM tool_usage_log t2
        WHERE t2.session_id = t1.session_id
        ORDER BY timestamp LIMIT 1) as first_tool
FROM tool_usage_log t1
GROUP BY session_id;
```

---

## Implementation Checklist

### Week 1: Descriptions
- [ ] Rewrite all 8 MCP tool descriptions (150-400 words each)
- [ ] Add "when to use" and "when NOT to use" sections
- [ ] Include example workflows
- [ ] Add performance characteristics
- [ ] Test: Read descriptions aloud, verify they're instructional

### Week 2: Project Integration
- [ ] Update CLAUDE.md with memory system workflow
- [ ] Add progressive loading examples
- [ ] Create anti-pattern warnings
- [ ] Test: Does CLAUDE.md clearly guide usage?

### Week 3: Behavioral Hooks
- [ ] Add proactive suggestions to wake_up()
- [ ] Enhance check_contexts() with actionable advice
- [ ] Create usage-patterns resource
- [ ] Test: Do prompts feel natural?

### Week 4: Measurement
- [ ] Add tool usage tracking
- [ ] Create analysis queries
- [ ] Monitor for 1 week
- [ ] Adjust descriptions based on actual usage patterns

---

## Expected Outcomes

### Before RLM Engagement Strategy
- LLM calls `recall_context()` immediately without exploring
- Loads multiple full contexts (300KB+)
- Doesn't use new tools (`ask_memory`, `explore_context_tree`)
- Inconsistent workflow (sometimes skips `wake_up()`)

### After RLM Engagement Strategy
- LLM starts with `wake_up()` (95%+ of sessions)
- Uses `ask_memory(depth="preview")` for exploration
- Progressive deepening: preview → full → deep
- Only loads full contexts when needed
- Averages <30KB per query vs 300KB before
- Proactively checks contexts before major changes

---

## Key Insights from Sequential Thinking

1. **Tool descriptions ARE prompts** - They're included in every LLM request
2. **Be exhaustively detailed** - 400+ words is not too long if it guides usage
3. **Include "You should" instructions** - Direct imperatives work
4. **Show examples and workflows** - Concrete usage patterns
5. **External reinforcement** - CLAUDE.md + tool descriptions = strong signal
6. **Simple state management** - Server tracks state, not LLM
7. **Visual feedback** - Helps humans trust the system

## Final Recommendation

Implement all phases. The tool descriptions are **critical** - they're the primary way the LLM learns to use your tools correctly. The sequential thinking MCP proves that with proper descriptions, LLMs will naturally use tools in sophisticated ways.

Budget: ~1 week to rewrite all descriptions + update documentation.
Impact: Transforms tools from "available but rarely used" to "naturally integrated into workflow"
