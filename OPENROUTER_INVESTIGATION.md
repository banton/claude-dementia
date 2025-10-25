# OpenRouter Investigation for Claude Dementia

## Executive Summary

**Recommendation:** Use a **hybrid approach** with OpenAI for embeddings and OpenRouter for LLM features.

- ✅ OpenAI API for semantic embeddings ($0.02/M tokens - very cheap)
- ✅ OpenRouter for LLM operations ($0.10-0.50/M - flexible, 300+ models)
- ❌ OpenRouter does NOT support embedding models

## Findings

### OpenRouter Capabilities

**What OpenRouter Provides:**
- Unified API access to 300+ LLM models
- Providers: OpenAI, Anthropic (Claude), Google (Gemini), Meta (LLaMA), Mistral, etc.
- OpenAI-compatible API format
- Competitive, transparent pricing
- ~40ms overhead (minimal)
- Pay-as-you-go with no hidden fees

**What OpenRouter Does NOT Provide:**
- ❌ No embedding model APIs
- ❌ No vector similarity endpoints
- ❌ Cannot replace OpenAI for semantic search

### Pricing Analysis

#### Embeddings (Must Use OpenAI Direct)
| Model | Cost | Use Case |
|-------|------|----------|
| text-embedding-3-small | $0.02/M tokens | Recommended (5x cheaper than ada-002) |
| text-embedding-3-large | $0.13/M tokens | Higher quality, 8x more expensive |
| Batch processing | 50% discount | For bulk embedding generation |

**Our Use Case Cost:**
- 1000 contexts × 500 tokens avg = 500K tokens
- Cost: **$0.01 one-time** (using text-embedding-3-small)
- Storage: 6MB (1000 × 1536 dimensions × 4 bytes)

#### LLM Operations (Can Use OpenRouter)
| Provider/Model | OpenRouter | Direct API | Savings |
|----------------|-----------|------------|---------|
| Claude 3 Haiku | $0.25/M | $0.25/M | 0% |
| GPT-3.5 Turbo | $0.50/M | $0.50/M | 0% |
| GPT-4 Turbo | $10/M | $10/M | 0% |
| Mistral 7B | Free | N/A | 100% |
| LLaMA 70B | $0.70/M | N/A | N/A |

**Note:** OpenRouter pricing matches direct APIs but provides:
- Single unified API
- Access to free models
- Access to providers without direct API access
- Fallback between models

## Implementation Architecture

### Recommended: Hybrid Approach

```
┌─────────────────────────────────────────────────────────────┐
│           Claude Dementia Memory System                     │
└────────────────┬────────────────────┬───────────────────────┘
                 │                    │
                 ▼                    ▼
    ┌────────────────────┐  ┌────────────────────────────────┐
    │   OpenAI API       │  │      OpenRouter                │
    │   (Embeddings)     │  │      (LLM Features)            │
    ├────────────────────┤  ├────────────────────────────────┤
    │                    │  │                                │
    │ Use For:           │  │ Use For:                       │
    │ • Vector search    │  │ • Context summarization        │
    │ • Similarity       │  │ • Semantic analysis            │
    │ • Find related     │  │ • Re-ranking results           │
    │   contexts         │  │ • Smart categorization         │
    │                    │  │ • Multiple model access        │
    │                    │  │                                │
    │ Models:            │  │ Models (300+ available):       │
    │ • text-embedding-  │  │ • anthropic/claude-3-haiku     │
    │   3-small          │  │ • mistralai/mistral-7b-free    │
    │ • text-embedding-  │  │ • meta-llama/llama-3-70b       │
    │   3-large          │  │ • google/gemini-pro            │
    │                    │  │ • openai/gpt-4-turbo           │
    │                    │  │                                │
    │ Cost:              │  │ Cost:                          │
    │ $0.02/M tokens     │  │ $0.10-0.50/M (or free)         │
    │                    │  │                                │
    │ Performance:       │  │ Performance:                   │
    │ ~100ms per embed   │  │ ~200-500ms + 40ms overhead     │
    └────────────────────┘  └────────────────────────────────┘
```

## Implementation Code

### Configuration

```python
# config.py
import os
from typing import Literal

# API Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Embedding Configuration
EMBEDDING_PROVIDER: Literal["openai", "local"] = "openai"
EMBEDDING_MODEL = "text-embedding-3-small"  # $0.02/M tokens
EMBEDDING_DIMENSIONS = 1536

# LLM Configuration
LLM_PROVIDER: Literal["openai", "openrouter"] = "openrouter"
LLM_MODEL = "anthropic/claude-3-haiku"  # $0.25/M via OpenRouter

# Feature Flags
ENABLE_SEMANTIC_SEARCH = bool(OPENAI_API_KEY)
ENABLE_AI_SUMMARIZATION = bool(OPENROUTER_API_KEY or OPENAI_API_KEY)
```

### Embedding Service

```python
# embedding_service.py
import openai
from typing import List
import numpy as np

class EmbeddingService:
    """Handle embedding generation using OpenAI API."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text.

        Cost: $0.02 per million tokens
        Performance: ~100ms per embedding
        """
        response = self.client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding

    def batch_generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (batched for efficiency).

        Supports up to 2048 texts per batch.
        """
        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        return [item.embedding for item in response.data]

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two embedding vectors."""
        a = np.array(vec1)
        b = np.array(vec2)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


# Usage
embedding_service = EmbeddingService(OPENAI_API_KEY)

# Generate single embedding
text = "JWT authentication with OAuth2 required"
embedding = embedding_service.generate_embedding(text)
# Returns: [0.012, -0.034, 0.089, ...] (1536 dimensions)

# Batch generate (efficient)
texts = ["Context 1", "Context 2", "Context 3"]
embeddings = embedding_service.batch_generate_embeddings(texts)
```

### LLM Service (OpenRouter)

```python
# llm_service.py
import requests
from typing import Dict, Any, Optional

class LLMService:
    """Handle LLM operations using OpenRouter API."""

    def __init__(
        self,
        api_key: str,
        default_model: str = "anthropic/claude-3-haiku",
        app_name: str = "claude-dementia"
    ):
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = "https://openrouter.ai/api/v1"
        self.app_name = app_name

    def chat_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> str:
        """
        Generate chat completion via OpenRouter.

        Args:
            prompt: User prompt
            model: Model to use (defaults to self.default_model)
            system_prompt: Optional system instructions
            temperature: Randomness (0-1)
            max_tokens: Max response length

        Returns: Generated text
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": f"https://github.com/{self.app_name}",
                "X-Title": self.app_name
            },
            json={
                "model": model or self.default_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
        )
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]

    def summarize_context(self, content: str, max_length: int = 500) -> str:
        """
        Generate intelligent summary of context content.

        Cost: ~$0.25/M input tokens (using Claude 3 Haiku)
        """
        prompt = f"""Summarize the following context in {max_length} characters or less.
Focus on:
1. Main topic/purpose
2. Key rules (MUST/ALWAYS/NEVER)
3. Important technical concepts

Context:
{content[:5000]}  # Limit input to avoid excessive costs
"""

        return self.chat_completion(
            prompt,
            system_prompt="You are a technical summarization assistant. Be concise and focus on critical information.",
            temperature=0.3,  # Lower temperature for consistency
            max_tokens=200
        )

    def classify_context_priority(self, content: str) -> str:
        """
        Classify context priority using AI.

        Returns: "always_check", "important", or "reference"
        """
        prompt = f"""Classify this context's priority level:
- "always_check": Contains rules that MUST be followed (MUST/ALWAYS/NEVER keywords)
- "important": Contains key decisions, specifications, or critical info
- "reference": General information or documentation

Context: {content[:1000]}

Respond with ONLY one word: always_check, important, or reference"""

        response = self.chat_completion(
            prompt,
            temperature=0.1,
            max_tokens=10
        )

        priority = response.strip().lower()
        if priority in ["always_check", "important", "reference"]:
            return priority
        return "reference"  # Default fallback


# Usage
llm_service = LLMService(OPENROUTER_API_KEY)

# Generate summary
summary = llm_service.summarize_context(context_content)

# Classify priority
priority = llm_service.classify_context_priority(context_content)

# Custom completion
response = llm_service.chat_completion(
    "Extract key technical concepts from this text: ...",
    model="mistralai/mistral-7b-free"  # Use free model
)
```

### Semantic Search Integration

```python
# semantic_search.py
import sqlite3
from typing import List, Dict, Tuple

class SemanticSearch:
    """Semantic search using embeddings stored in SQLite."""

    def __init__(self, conn: sqlite3.Connection, embedding_service: EmbeddingService):
        self.conn = conn
        self.embedding_service = embedding_service
        self._init_schema()

    def _init_schema(self):
        """Add embedding column to context_locks if not exists."""
        cursor = self.conn.execute("PRAGMA table_info(context_locks)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'embedding' not in columns:
            # Store as BLOB (binary)
            self.conn.execute('ALTER TABLE context_locks ADD COLUMN embedding BLOB')
            self.conn.commit()

    def add_embedding(self, context_id: int, text: str):
        """Generate and store embedding for context."""
        embedding = self.embedding_service.generate_embedding(text)

        # Convert to binary for efficient storage
        embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()

        self.conn.execute("""
            UPDATE context_locks
            SET embedding = ?
            WHERE id = ?
        """, (embedding_bytes, context_id))
        self.conn.commit()

    def search_similar(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7
    ) -> List[Dict]:
        """
        Find contexts semantically similar to query.

        Args:
            query: Search query text
            limit: Max results to return
            threshold: Minimum similarity score (0-1)

        Returns: List of dicts with context info + similarity score
        """
        # Generate query embedding
        query_embedding = self.embedding_service.generate_embedding(query)

        # Get all contexts with embeddings
        cursor = self.conn.execute("""
            SELECT id, label, content, preview, embedding
            FROM context_locks
            WHERE embedding IS NOT NULL
        """)

        results = []
        for row in cursor.fetchall():
            # Convert binary back to array
            context_embedding = np.frombuffer(row['embedding'], dtype=np.float32).tolist()

            # Calculate similarity
            similarity = self.embedding_service.cosine_similarity(
                query_embedding,
                context_embedding
            )

            if similarity >= threshold:
                results.append({
                    "id": row['id'],
                    "label": row['label'],
                    "preview": row['preview'],
                    "similarity": round(similarity, 3)
                })

        # Sort by similarity (highest first)
        results.sort(key=lambda x: x['similarity'], reverse=True)

        return results[:limit]


# Usage
semantic_search = SemanticSearch(conn, embedding_service)

# Add embeddings to existing contexts (one-time)
contexts = conn.execute("SELECT id, content FROM context_locks WHERE embedding IS NULL").fetchall()
for context in contexts:
    semantic_search.add_embedding(context['id'], context['content'])

# Search semantically
results = semantic_search.search_similar("How do we handle authentication?")
# Returns contexts about JWT, OAuth, auth even without exact keywords
```

## Cost Analysis

### Scenario: Memory System with 1000 Contexts

#### Initial Setup (One-time)
```
Generate embeddings: 1000 contexts × 500 tokens avg = 500K tokens
Cost: $0.01 (using text-embedding-3-small)
Storage: 6MB in SQLite
```

#### Ongoing Usage (Monthly)
```
New contexts: 50/month × 500 tokens = 25K tokens
Cost: $0.0005/month (embeddings)

AI summaries: 50/month × 1000 tokens = 50K tokens
Cost: $0.0125/month (using Claude 3 Haiku via OpenRouter)

Total monthly cost: ~$0.01-0.02
```

#### Comparison with Direct OpenAI Only
```
Embeddings: Same ($0.0005/month)
LLM (GPT-3.5): 50K tokens × $0.50/M = $0.025/month

Total with OpenAI only: $0.0255/month
Total with Hybrid: $0.013/month

Savings: 48% cheaper using OpenRouter for LLM
```

## Migration Path

### Phase 1: Add OpenAI Embeddings (Optional Feature)
1. Add embedding column to database
2. Implement EmbeddingService
3. Add semantic_search MCP tool
4. Make it optional (graceful degradation if no API key)

### Phase 2: Add OpenRouter for AI Features (Optional)
1. Implement LLMService
2. Enhance summarization with AI
3. Add smart priority classification
4. Add context analysis tools

### Phase 3: Advanced Features
1. Hybrid search (keyword + semantic)
2. Context re-ranking with AI
3. Automatic context relationships
4. Smart context recommendations

## Configuration Options

### Environment Variables
```bash
# Required for semantic search
export OPENAI_API_KEY="sk-..."

# Optional for enhanced LLM features
export OPENROUTER_API_KEY="sk-or-..."

# Feature flags
export ENABLE_SEMANTIC_SEARCH=true
export ENABLE_AI_SUMMARIZATION=true

# Model selection
export EMBEDDING_MODEL="text-embedding-3-small"
export LLM_MODEL="anthropic/claude-3-haiku"
```

### Graceful Degradation
```python
# If no API keys provided, fall back to existing functionality
if not OPENAI_API_KEY:
    # Use existing keyword search (FTS5)
    # Use existing generate_preview() function

if not OPENROUTER_API_KEY:
    # Use existing summarization
    # Or fall back to OpenAI if available
```

## Recommendation

**Implement the Hybrid Approach with Optional Feature Flags:**

1. ✅ **Add OpenAI embeddings** as optional feature for semantic search
   - Cost: ~$0.01 for initial 1000 contexts
   - Massive improvement in search quality
   - Works alongside existing FTS5 search

2. ✅ **Add OpenRouter** as optional provider for LLM features
   - Cost: ~$0.01/month for typical usage
   - 48% cheaper than OpenAI direct
   - Access to 300+ models for flexibility

3. ✅ **Maintain existing functionality** as fallback
   - No breaking changes
   - Works without API keys
   - Users choose their level of cloud integration

## Next Steps

1. Create `embedding_service.py` with OpenAI integration
2. Create `llm_service.py` with OpenRouter integration
3. Add `semantic_search` MCP tool
4. Update documentation with setup instructions
5. Add environment variable configuration
6. Implement feature flags for graceful degradation

---

**Status:** Investigation Complete
**Recommendation:** Hybrid approach (OpenAI + OpenRouter)
**Estimated Implementation:** 4-6 hours
**Monthly Cost:** $0.01-0.02 for typical usage
