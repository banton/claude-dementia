# Cost Tracking & Comparison Guide

## Overview

Claude Dementia now tracks **every token used** and compares actual costs (FREE with Ollama) against what you would have paid using commercial APIs:
- **OpenAI** (GPT-3.5, GPT-4, text-embedding-3-small/large)
- **Voyage AI** (voyage-3.5-lite, voyage-3.5, voyage-3-large) - **NEW!**

**See Also**: [VOYAGE_AI_COST_ANALYSIS.md](VOYAGE_AI_COST_ANALYSIS.md) for detailed cost breakdowns and real-world scenarios.

## Quick Start

### 1. Check Current Usage

```
usage_statistics()
```

**Shows:**
- Total operations (embeddings + LLM calls)
- Token counts (input + output)
- Performance metrics (avg duration)
- Model breakdown

### 2. Compare Costs

```
cost_comparison()
```

**Shows:**
- **Actual cost:** $0.00 (Ollama is FREE)
- **OpenAI embedding cost:** What you would have paid
- **OpenAI GPT-3.5 cost:** Alternative pricing
- **OpenAI GPT-4 cost:** Premium alternative pricing
- **Total savings:** 100% (always!)
- **Annual projections:** Extrapolated savings

## Example Output

### Usage Statistics (30 days)

```json
{
  "period_days": 30,
  "stats": [
    {
      "operation_type": "embedding",
      "provider": "ollama",
      "model": "nomic-embed-text",
      "operation_count": 150,
      "total_input_tokens": 75000,
      "avg_duration_ms": 31
    },
    {
      "operation_type": "llm_completion",
      "provider": "ollama",
      "model": "qwen2.5-coder:1.5b",
      "operation_count": 45,
      "total_input_tokens": 22500,
      "total_output_tokens": 11250,
      "avg_duration_ms": 1200
    }
  ],
  "summary": {
    "total_operations": 195,
    "total_input_tokens": 97500,
    "total_output_tokens": 11250,
    "total_tokens": 108750
  }
}
```

### Cost Comparison

```json
{
  "period_days": 30,
  "cost_comparison": {
    "actual": {
      "provider": "ollama",
      "cost_usd": 0.00
    },
    "alternatives": {
      "openai_embedding": {
        "provider": "OpenAI",
        "model": "text-embedding-3-small",
        "cost_usd": 0.00195,
        "savings_usd": 0.00195,
        "savings_percent": 100.0
      },
      "openai_gpt35": {
        "provider": "OpenAI",
        "model": "GPT-3.5 Turbo",
        "cost_usd": 0.028125,
        "savings_usd": 0.028125,
        "savings_percent": 100.0
      },
      "openai_gpt4": {
        "provider": "OpenAI",
        "model": "GPT-4 Turbo",
        "cost_usd": 0.5625,
        "savings_usd": 0.5625,
        "savings_percent": 100.0
      }
    }
  },
  "projections": {
    "openai_embedding": {
      "daily_avg": 0.000065,
      "annual_projected": 0.0237
    },
    "openai_gpt35": {
      "daily_avg": 0.000938,
      "annual_projected": 0.342
    },
    "openai_gpt4": {
      "daily_avg": 0.01875,
      "annual_projected": 6.84
    }
  },
  "pricing_reference": {
    "openai_embeddings": "$0.02/M tokens",
    "openai_gpt35": "$0.50/M input, $1.50/M output",
    "openai_gpt4": "$10.00/M input, $30.00/M output",
    "ollama": "FREE"
  }
}
```

## Real-World Example

**Scenario:** Medium usage over 30 days
- 150 embedding operations
- 45 LLM completions
- ~110K total tokens

**Savings:**
- vs GPT-3.5: $0.028/month → **$0.34/year**
- vs GPT-4: $0.56/month → **$6.84/year**

**For heavy users (10x usage):**
- vs GPT-3.5: **$3.40/year saved**
- vs GPT-4: **$68.40/year saved**

## Time Periods

Check different time ranges:

```
# Last week
usage_statistics(days=7)
cost_comparison(days=7)

# Last month (default)
usage_statistics()
cost_comparison()

# Last quarter
usage_statistics(days=90)
cost_comparison(days=90)

# Annual view
usage_statistics(days=365)
cost_comparison(days=365)
```

## What Gets Tracked

### Embeddings
- Input text length
- Token count (using tiktoken)
- Duration in milliseconds
- Model used
- Context ID (if applicable)

### LLM Completions
- Input text (prompt + system prompt)
- Output text (response)
- Token counts (input + output separately)
- Duration
- Model used
- Context ID (if applicable)

## Token Counting

Uses **tiktoken** (OpenAI's official tokenizer) for accurate counts:
- Same encoding as GPT-3.5/GPT-4 (cl100k_base)
- Accurate cost comparisons
- Falls back to char-based estimation if unavailable

## Privacy

All tracking data stays **100% local**:
- Stored in `.claude-memory.db`
- Never sent to any API
- Automatic cleanup after 90 days (configurable)

## Database Schema

```sql
CREATE TABLE token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    operation_type TEXT NOT NULL,      -- 'embedding' or 'llm_completion'
    model TEXT NOT NULL,                -- e.g., 'nomic-embed-text'
    provider TEXT NOT NULL,             -- e.g., 'ollama'
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER DEFAULT 0,
    input_chars INTEGER NOT NULL,
    output_chars INTEGER DEFAULT 0,
    duration_ms INTEGER,
    context_id INTEGER,
    metadata TEXT
);
```

## Use Cases

### 1. Justify Local Models to Team
```
"Look, we've used 500K tokens this month.
With GPT-4, that would cost $75.
With Ollama: $0."
```

### 2. Track Performance
```
"Our embeddings average 31ms,
summaries average 1.2s.
Both well within acceptable limits."
```

### 3. Plan Capacity
```
"At current usage (100K tokens/month),
we'd spend $150/year on GPT-4.
Local models pay for themselves immediately."
```

### 4. Analyze Usage Patterns
```
"We generate 3x more embeddings than summaries.
Embedding speed is critical for user experience."
```

## Advanced: Manual Queries

Access raw data directly:

```python
# Via MCP tool
query_database("SELECT * FROM token_usage ORDER BY timestamp DESC LIMIT 10")

# Check total tokens by model
query_database("""
    SELECT
        model,
        SUM(input_tokens) as total_input,
        SUM(output_tokens) as total_output,
        COUNT(*) as operations
    FROM token_usage
    GROUP BY model
""")
```

## Cleanup

Old records auto-cleanup after 90 days. Manual cleanup:

```python
# Via token tracker (in code)
tracker.clear_old_records(days=30)  # Keep only last 30 days
```

## Pricing Reference (2025)

| Service | Model | Input | Output | Free Tier |
|---------|-------|-------|--------|-----------|
| OpenAI Embeddings | text-embedding-3-small | $0.02/M | - | None |
| OpenAI Embeddings | text-embedding-3-large | $0.13/M | - | None |
| **Voyage AI** | **voyage-3.5-lite** | **$0.02/M** | - | **200M/month** |
| **Voyage AI** | **voyage-3.5** | **$0.06/M** | - | **200M/month** |
| **Voyage AI** | **voyage-3-large** | **$0.18/M** | - | **200M/month** |
| OpenAI LLM | GPT-3.5 Turbo | $0.50/M | $1.50/M | None |
| OpenAI LLM | GPT-4 Turbo | $10.00/M | $30.00/M | None |
| **Ollama** | **All models** | **FREE** | **FREE** | **Unlimited** |

## Benefits Summary

✅ **Zero cost** - No API fees ever
✅ **Full transparency** - See exactly what you're using
✅ **Hard data** - Justify decisions with numbers
✅ **Performance tracking** - Monitor speed/latency
✅ **Annual projections** - Plan long-term savings
✅ **100% private** - All data stays local

---

**Tool Count:** 29 total (+2 cost tracking tools)
- `usage_statistics(days)`
- `cost_comparison(days)`

Ready to track your savings! 🎉
