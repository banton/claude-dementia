# Hybrid API Implementation Plan

## Overview

Based on the OpenRouter investigation, this document outlines the implementation of a hybrid approach using OpenAI for embeddings and OpenRouter for LLM features in Claude Dementia.

## Architecture Decision

**Selected Approach:** Hybrid (OpenAI + OpenRouter)

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
    │ • Vector search    │  │ • Context summarization        │
    │ • Similarity       │  │ • Semantic analysis            │
    │ • $0.02/M tokens   │  │ • Re-ranking results           │
    └────────────────────┘  │ • $0.10-0.50/M tokens          │
                            └────────────────────────────────┘
```

## Implementation Phases

### Phase 1: Core Infrastructure (2-3 hours)

**Goal:** Set up configuration and base service classes

#### 1.1 Configuration Module

Create `src/config.py`:

```python
import os
from typing import Literal, Optional
from pydantic import BaseSettings, Field

class APIConfig(BaseSettings):
    """API configuration with validation and defaults."""

    # API Keys
    openai_api_key: Optional[str] = Field(default=None, env='OPENAI_API_KEY')
    openrouter_api_key: Optional[str] = Field(default=None, env='OPENROUTER_API_KEY')

    # Embedding Configuration
    embedding_provider: Literal["openai", "disabled"] = Field(default="disabled")
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dimensions: int = Field(default=1536)

    # LLM Configuration
    llm_provider: Literal["openai", "openrouter", "disabled"] = Field(default="disabled")
    llm_model: str = Field(default="anthropic/claude-3-haiku")

    # Feature Flags
    enable_semantic_search: bool = Field(default=False)
    enable_ai_summarization: bool = Field(default=False)
    enable_auto_classification: bool = Field(default=False)

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Auto-enable features based on API key availability
        if self.openai_api_key:
            self.embedding_provider = "openai"
            self.enable_semantic_search = True

        if self.openrouter_api_key or self.openai_api_key:
            self.llm_provider = "openrouter" if self.openrouter_api_key else "openai"
            self.enable_ai_summarization = True
            self.enable_auto_classification = True

# Global config instance
config = APIConfig()
```

**Files to create:**
- `src/config.py` (120 lines)
- `.env.example` (20 lines)

**Testing:**
```bash
# Test configuration loading
python3 -c "from src.config import config; print(config.json(indent=2))"
```

#### 1.2 Embedding Service

Create `src/services/embedding_service.py`:

```python
import openai
from typing import List, Optional
import numpy as np
from src.config import config

class EmbeddingService:
    """Handle embedding generation using OpenAI API."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.enabled = bool(api_key or config.openai_api_key)
        if not self.enabled:
            return

        self.client = openai.OpenAI(api_key=api_key or config.openai_api_key)
        self.model = model or config.embedding_model

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding vector for text.

        Cost: $0.02 per million tokens (~$0.00002 per 1000 tokens)
        Performance: ~100ms per embedding

        Returns None if service not enabled.
        """
        if not self.enabled:
            return None

        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text[:8000]  # Truncate to token limit
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Embedding generation failed: {e}")
            return None

    def batch_generate_embeddings(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts (batched for efficiency).

        Supports up to 2048 texts per batch (uses smaller batches for safety).
        """
        if not self.enabled:
            return [None] * len(texts)

        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            truncated = [text[:8000] for text in batch]

            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=truncated
                )
                embeddings.extend([item.embedding for item in response.data])
            except Exception as e:
                print(f"Batch embedding failed for batch {i//batch_size}: {e}")
                embeddings.extend([None] * len(batch))

        return embeddings

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two embedding vectors."""
        if not vec1 or not vec2:
            return 0.0

        a = np.array(vec1)
        b = np.array(vec2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

# Global service instance
embedding_service = EmbeddingService()
```

**Files to create:**
- `src/services/__init__.py` (empty)
- `src/services/embedding_service.py` (100 lines)

**Testing:**
```python
# Test embedding generation
from src.services.embedding_service import embedding_service

if embedding_service.enabled:
    text = "JWT authentication with OAuth2 required"
    embedding = embedding_service.generate_embedding(text)
    print(f"Generated embedding with {len(embedding)} dimensions")
else:
    print("Embedding service not enabled (no API key)")
```

#### 1.3 LLM Service

Create `src/services/llm_service.py`:

```python
import requests
from typing import Dict, Any, Optional, Literal
from src.config import config

class LLMService:
    """Handle LLM operations using OpenRouter API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        app_name: str = "claude-dementia"
    ):
        self.enabled = bool(api_key or config.openrouter_api_key)
        if not self.enabled:
            return

        self.api_key = api_key or config.openrouter_api_key
        self.default_model = default_model or config.llm_model
        self.base_url = "https://openrouter.ai/api/v1"
        self.app_name = app_name

    def chat_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Optional[str]:
        """
        Generate chat completion via OpenRouter.

        Cost: $0.10-0.50/M tokens (model dependent)
        Performance: ~200-500ms + 40ms OpenRouter overhead

        Returns None if service not enabled or on error.
        """
        if not self.enabled:
            return None

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
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
                },
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"LLM completion failed: {e}")
            return None

    def summarize_context(
        self,
        content: str,
        max_length: int = 500
    ) -> Optional[str]:
        """
        Generate intelligent summary of context content.

        Cost: ~$0.25/M input tokens (using Claude 3 Haiku)
        Falls back to extract-based summary if service unavailable.
        """
        if not self.enabled:
            return None

        prompt = f"""Summarize the following context in {max_length} characters or less.
Focus on:
1. Main topic/purpose
2. Key rules (MUST/ALWAYS/NEVER)
3. Important technical concepts

Context:
{content[:5000]}"""

        return self.chat_completion(
            prompt,
            system_prompt="You are a technical summarization assistant. Be concise and focus on critical information.",
            temperature=0.3,
            max_tokens=200
        )

    def classify_context_priority(self, content: str) -> Optional[str]:
        """
        Classify context priority using AI.

        Returns: "always_check", "important", "reference", or None
        """
        if not self.enabled:
            return None

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

        if response:
            priority = response.strip().lower()
            if priority in ["always_check", "important", "reference"]:
                return priority

        return None

# Global service instance
llm_service = LLMService()
```

**Files to create:**
- `src/services/llm_service.py` (150 lines)

**Testing:**
```python
# Test LLM service
from src.services.llm_service import llm_service

if llm_service.enabled:
    summary = llm_service.summarize_context("Test context content...")
    print(f"Generated summary: {summary}")
else:
    print("LLM service not enabled (no API key)")
```

### Phase 2: Database Integration (2-3 hours)

**Goal:** Add embedding storage and semantic search capabilities

#### 2.1 Database Schema Changes

Update `claude_mcp_hybrid.py` schema initialization:

```python
def init_schema(conn):
    """Initialize database schema with embedding support."""

    # ... existing tables ...

    # Add embedding column to context_locks (if not exists)
    cursor = conn.execute("PRAGMA table_info(context_locks)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'embedding' not in columns:
        conn.execute('ALTER TABLE context_locks ADD COLUMN embedding BLOB')
        conn.commit()

    if 'embedding_model' not in columns:
        conn.execute('ALTER TABLE context_locks ADD COLUMN embedding_model TEXT')
        conn.commit()
```

**Migration Script:**

Create `migrations/add_embeddings.py`:

```python
"""Migration: Add embedding support to context_locks table."""

import sqlite3
import sys
from pathlib import Path

def migrate(db_path: str):
    """Add embedding columns to context_locks table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Check if columns already exist
    cursor = conn.execute("PRAGMA table_info(context_locks)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'embedding' in columns:
        print("✓ Embedding columns already exist")
        return

    # Add columns
    print("Adding embedding columns...")
    conn.execute('ALTER TABLE context_locks ADD COLUMN embedding BLOB')
    conn.execute('ALTER TABLE context_locks ADD COLUMN embedding_model TEXT')
    conn.commit()

    print("✓ Migration complete")
    print("  - Added 'embedding' column (BLOB)")
    print("  - Added 'embedding_model' column (TEXT)")

    # Show statistics
    cursor = conn.execute("SELECT COUNT(*) as total FROM context_locks")
    total = cursor.fetchone()['total']
    print(f"\nTotal contexts: {total}")
    print(f"Note: Run 'generate_embeddings' tool to populate embeddings for existing contexts")

    conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 migrations/add_embeddings.py <db_path>")
        sys.exit(1)

    migrate(sys.argv[1])
```

**Files to create:**
- `migrations/__init__.py` (empty)
- `migrations/add_embeddings.py` (60 lines)

**Testing:**
```bash
# Run migration on test database
python3 migrations/add_embeddings.py .claude-memory.db
```

#### 2.2 Semantic Search Service

Create `src/services/semantic_search.py`:

```python
import sqlite3
from typing import List, Dict, Optional
import numpy as np
from src.services.embedding_service import embedding_service

class SemanticSearch:
    """Semantic search using embeddings stored in SQLite."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.enabled = embedding_service.enabled

    def add_embedding(self, context_id: int, text: str) -> bool:
        """
        Generate and store embedding for context.

        Returns True if successful, False otherwise.
        """
        if not self.enabled:
            return False

        embedding = embedding_service.generate_embedding(text)
        if not embedding:
            return False

        # Convert to binary for efficient storage
        embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()

        self.conn.execute("""
            UPDATE context_locks
            SET embedding = ?, embedding_model = ?
            WHERE id = ?
        """, (embedding_bytes, embedding_service.model, context_id))
        self.conn.commit()

        return True

    def batch_add_embeddings(self, contexts: List[Dict]) -> Dict[str, int]:
        """
        Generate and store embeddings for multiple contexts.

        Args:
            contexts: List of dicts with 'id' and 'content' keys

        Returns: Dict with 'success', 'failed', 'skipped' counts
        """
        if not self.enabled:
            return {"success": 0, "failed": 0, "skipped": len(contexts)}

        # Generate all embeddings in batch
        texts = [ctx['content'] for ctx in contexts]
        embeddings = embedding_service.batch_generate_embeddings(texts)

        success = 0
        failed = 0

        for ctx, embedding in zip(contexts, embeddings):
            if embedding:
                embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()
                try:
                    self.conn.execute("""
                        UPDATE context_locks
                        SET embedding = ?, embedding_model = ?
                        WHERE id = ?
                    """, (embedding_bytes, embedding_service.model, ctx['id']))
                    success += 1
                except Exception as e:
                    print(f"Failed to store embedding for context {ctx['id']}: {e}")
                    failed += 1
            else:
                failed += 1

        self.conn.commit()

        return {"success": success, "failed": failed, "skipped": 0}

    def search_similar(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        priority_filter: Optional[str] = None,
        tags_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        Find contexts semantically similar to query.

        Args:
            query: Search query text
            limit: Max results to return
            threshold: Minimum similarity score (0-1)
            priority_filter: Filter by priority level
            tags_filter: Comma-separated tags to filter by

        Returns: List of dicts with context info + similarity score
        """
        if not self.enabled:
            return []

        # Generate query embedding
        query_embedding = embedding_service.generate_embedding(query)
        if not query_embedding:
            return []

        # Build SQL query with filters
        sql = """
            SELECT id, label, content, preview, embedding, metadata
            FROM context_locks
            WHERE embedding IS NOT NULL
        """
        params = []

        if priority_filter:
            sql += " AND json_extract(metadata, '$.priority') = ?"
            params.append(priority_filter)

        if tags_filter:
            tags = [t.strip() for t in tags_filter.split(',')]
            tag_conditions = " OR ".join(["json_extract(metadata, '$.tags') LIKE ?" for _ in tags])
            sql += f" AND ({tag_conditions})"
            params.extend([f'%{tag}%' for tag in tags])

        cursor = self.conn.execute(sql, params)

        results = []
        for row in cursor.fetchall():
            # Convert binary back to array
            context_embedding = np.frombuffer(row['embedding'], dtype=np.float32).tolist()

            # Calculate similarity
            similarity = embedding_service.cosine_similarity(
                query_embedding,
                context_embedding
            )

            if similarity >= threshold:
                results.append({
                    "id": row['id'],
                    "label": row['label'],
                    "preview": row['preview'],
                    "similarity": round(similarity, 3),
                    "metadata": row['metadata']
                })

        # Sort by similarity (highest first)
        results.sort(key=lambda x: x['similarity'], reverse=True)

        return results[:limit]

    def get_embedding_stats(self) -> Dict[str, Any]:
        """Get statistics about embeddings in database."""
        cursor = self.conn.execute("""
            SELECT
                COUNT(*) as total_contexts,
                COUNT(embedding) as contexts_with_embeddings,
                embedding_model
            FROM context_locks
            GROUP BY embedding_model
        """)

        stats = cursor.fetchall()

        return {
            "enabled": self.enabled,
            "statistics": [dict(row) for row in stats]
        }
```

**Files to create:**
- `src/services/semantic_search.py` (200 lines)

### Phase 3: MCP Tool Integration (2-3 hours)

**Goal:** Add new MCP tools for semantic search and AI features

#### 3.1 New MCP Tools

Add to `claude_mcp_hybrid.py`:

```python
@mcp.tool()
async def generate_embeddings(
    context_ids: Optional[str] = None,
    regenerate: bool = False
) -> str:
    """
    Generate embeddings for contexts to enable semantic search.

    **Token Efficiency: MINIMAL** (~500 tokens)

    Args:
        context_ids: Comma-separated IDs to generate embeddings for (default: all without embeddings)
        regenerate: If True, regenerate embeddings even if they exist

    Returns: Statistics about embedding generation

    **Cost:** ~$0.02 per 1M tokens (OpenAI text-embedding-3-small)
    **Requirement:** OPENAI_API_KEY environment variable

    Example:
        generate_embeddings()  # Generate for all contexts without embeddings
        generate_embeddings(context_ids="1,2,3")  # Specific contexts
        generate_embeddings(regenerate=True)  # Regenerate all
    """
    from src.services.semantic_search import SemanticSearch
    from src.services.embedding_service import embedding_service

    if not embedding_service.enabled:
        return json.dumps({
            "error": "Embedding service not available",
            "reason": "OPENAI_API_KEY not configured",
            "setup": "Set OPENAI_API_KEY environment variable to enable semantic search"
        }, indent=2)

    conn = get_db()
    semantic_search = SemanticSearch(conn)

    # Determine which contexts to process
    if context_ids:
        ids = [int(id.strip()) for id in context_ids.split(',')]
        sql = f"SELECT id, content FROM context_locks WHERE id IN ({','.join(['?']*len(ids))})"
        cursor = conn.execute(sql, ids)
    elif regenerate:
        cursor = conn.execute("SELECT id, content FROM context_locks")
    else:
        cursor = conn.execute("SELECT id, content FROM context_locks WHERE embedding IS NULL")

    contexts = [{"id": row['id'], "content": row['content']} for row in cursor.fetchall()]

    if not contexts:
        return json.dumps({
            "message": "No contexts to process",
            "total_contexts": 0
        }, indent=2)

    # Generate embeddings in batch
    result = semantic_search.batch_add_embeddings(contexts)

    return json.dumps({
        "message": "Embedding generation complete",
        "total_processed": len(contexts),
        "success": result['success'],
        "failed": result['failed'],
        "model": embedding_service.model,
        "cost_estimate_usd": len(contexts) * 0.00002  # Rough estimate
    }, indent=2)


@mcp.tool()
async def semantic_search_contexts(
    query: str,
    limit: int = 10,
    threshold: float = 0.7,
    priority: Optional[str] = None,
    tags: Optional[str] = None
) -> str:
    """
    Search contexts using semantic similarity (embeddings).

    **Token Efficiency: PREVIEW** (~2-5KB depending on limit)

    Args:
        query: Natural language search query
        limit: Maximum number of results (default: 10)
        threshold: Minimum similarity score 0-1 (default: 0.7)
        priority: Filter by priority ("always_check", "important", "reference")
        tags: Comma-separated tags to filter by

    Returns: Contexts ranked by semantic similarity with scores

    **Requirement:** Must run generate_embeddings() first
    **Cost:** $0.02 per 1M tokens for query embedding

    Example:
        semantic_search_contexts("How do we handle authentication?")
        # Returns contexts about JWT, OAuth, auth flows even without exact keywords

        semantic_search_contexts("database connection pooling", priority="important")
    """
    from src.services.semantic_search import SemanticSearch
    from src.services.embedding_service import embedding_service

    if not embedding_service.enabled:
        return json.dumps({
            "error": "Semantic search not available",
            "reason": "OPENAI_API_KEY not configured",
            "fallback": "Use search_contexts() for keyword-based search"
        }, indent=2)

    conn = get_db()
    semantic_search = SemanticSearch(conn)

    # Perform semantic search
    results = semantic_search.search_similar(
        query=query,
        limit=limit,
        threshold=threshold,
        priority_filter=priority,
        tags_filter=tags
    )

    if not results:
        return json.dumps({
            "query": query,
            "total_results": 0,
            "message": "No similar contexts found",
            "suggestions": [
                "Lower threshold value (current: {})".format(threshold),
                "Run generate_embeddings() if not done yet",
                "Try broader query terms"
            ]
        }, indent=2)

    return json.dumps({
        "query": query,
        "total_results": len(results),
        "threshold": threshold,
        "results": results,
        "note": "Similarity scores range from 0-1, higher is more similar"
    }, indent=2)


@mcp.tool()
async def ai_summarize_context(topic: str) -> str:
    """
    Generate AI-powered summary of a context using LLM.

    **Token Efficiency: SUMMARY** (~1-2KB)

    Args:
        topic: Context topic/label to summarize

    Returns: AI-generated summary focusing on key concepts and rules

    **Requirement:** OPENROUTER_API_KEY or OPENAI_API_KEY
    **Cost:** ~$0.25/M tokens (Claude 3 Haiku via OpenRouter)

    Example:
        ai_summarize_context("api_specification")
        # Returns: Intelligent summary highlighting:
        #   - Main purpose
        #   - Key rules (MUST/ALWAYS/NEVER)
        #   - Technical concepts
    """
    from src.services.llm_service import llm_service

    if not llm_service.enabled:
        return json.dumps({
            "error": "AI summarization not available",
            "reason": "No API key configured",
            "setup": "Set OPENROUTER_API_KEY or OPENAI_API_KEY",
            "fallback": "Use recall_context(topic, preview_only=True) for extract-based summary"
        }, indent=2)

    conn = get_db()

    # Get context content
    cursor = conn.execute("""
        SELECT content, preview FROM context_locks
        WHERE label = ?
        ORDER BY version DESC LIMIT 1
    """, (topic,))

    row = cursor.fetchone()
    if not row:
        return json.dumps({
            "error": "Context not found",
            "topic": topic
        }, indent=2)

    # Generate AI summary
    summary = llm_service.summarize_context(row['content'])

    if not summary:
        return json.dumps({
            "error": "Summary generation failed",
            "fallback_preview": row['preview']
        }, indent=2)

    return json.dumps({
        "topic": topic,
        "ai_summary": summary,
        "model": llm_service.default_model,
        "note": "AI-generated summary may differ from extract-based preview"
    }, indent=2)


@mcp.tool()
async def embedding_status() -> str:
    """
    Check status of embedding and AI features.

    **Token Efficiency: MINIMAL** (~500 tokens)

    Returns: Configuration status, statistics, and setup instructions
    """
    from src.services.embedding_service import embedding_service
    from src.services.llm_service import llm_service
    from src.services.semantic_search import SemanticSearch
    from src.config import config

    conn = get_db()
    semantic_search = SemanticSearch(conn)

    status = {
        "embedding_service": {
            "enabled": embedding_service.enabled,
            "provider": config.embedding_provider,
            "model": config.embedding_model if embedding_service.enabled else None,
            "features": ["semantic_search"] if embedding_service.enabled else []
        },
        "llm_service": {
            "enabled": llm_service.enabled,
            "provider": config.llm_provider,
            "model": config.llm_model if llm_service.enabled else None,
            "features": ["ai_summarization", "priority_classification"] if llm_service.enabled else []
        },
        "statistics": semantic_search.get_embedding_stats(),
        "setup_instructions": {}
    }

    # Add setup instructions if services disabled
    if not embedding_service.enabled:
        status["setup_instructions"]["embeddings"] = {
            "step1": "Set OPENAI_API_KEY environment variable",
            "step2": "Restart MCP server",
            "step3": "Run generate_embeddings() to populate existing contexts",
            "cost": "~$0.02 per 1M tokens (~$0.01 for 1000 contexts)"
        }

    if not llm_service.enabled:
        status["setup_instructions"]["llm"] = {
            "step1": "Set OPENROUTER_API_KEY or OPENAI_API_KEY",
            "step2": "Restart MCP server",
            "step3": "Use ai_summarize_context() for AI-powered summaries",
            "cost": "~$0.25/M tokens (Claude 3 Haiku)"
        }

    return json.dumps(status, indent=2)
```

**Changes to make:**
- Add 4 new tools to `claude_mcp_hybrid.py`
- Import new service modules
- Update tool count in README.md (23 → 27)

### Phase 4: Documentation & Testing (1-2 hours)

#### 4.1 Update Documentation

**Files to update:**
1. `README.md` - Add new tools section
2. `CLAUDE.md` - Add usage instructions
3. `RLM_IMPLEMENTATION_PLAN.md` - Mark semantic search complete (10/12 RAG compliance)

#### 4.2 Create Usage Guide

Create `docs/SEMANTIC_SEARCH_GUIDE.md`:

```markdown
# Semantic Search Guide

## Overview

Claude Dementia now supports semantic search using OpenAI embeddings and optional AI summarization via OpenRouter.

## Setup

### 1. Configure API Keys

```bash
# For semantic search (required)
export OPENAI_API_KEY="sk-..."

# For AI summarization (optional)
export OPENROUTER_API_KEY="sk-or-..."
```

### 2. Restart MCP Server

```bash
# Stop Claude Desktop/Code
# Start Claude Desktop/Code (will reload MCP server)
```

### 3. Generate Embeddings

```python
# Check status
embedding_status()

# Generate embeddings for all contexts
generate_embeddings()
# Output: {success: 100, failed: 0, cost_estimate_usd: 0.01}
```

## Usage

### Semantic Search

Find contexts by meaning, not just keywords:

```python
# Find authentication-related contexts
semantic_search_contexts("How do we handle user authentication?")

# Results include contexts about:
# - JWT tokens
# - OAuth flows
# - Session management
# Even if those exact words weren't in the query

# Filter by priority
semantic_search_contexts("database queries", priority="important")

# Adjust similarity threshold
semantic_search_contexts("API endpoints", threshold=0.6, limit=20)
```

### AI Summarization

Generate intelligent summaries:

```python
# Get AI-powered summary
ai_summarize_context("api_specification")

# Returns:
# - Main purpose
# - Key rules (MUST/ALWAYS/NEVER)
# - Technical concepts
# - Dependencies
```

### Hybrid Search Strategy

Combine keyword and semantic search:

```python
# 1. Start with keyword search (fast, free)
search_contexts("authentication")

# 2. Use semantic search for better results
semantic_search_contexts("authentication")

# 3. Compare results - semantic often finds more relevant contexts
```

## Cost Analysis

### Initial Setup (1000 contexts)
- Embedding generation: $0.01 one-time
- Storage: 6MB in SQLite

### Ongoing Usage
- New context embedding: $0.00002 per context
- Semantic search query: $0.00002 per query
- AI summarization: $0.00025 per summary

### Monthly Estimate (50 new contexts, 100 searches, 20 summaries)
- Embeddings: $0.001
- Searches: $0.002
- Summaries: $0.005
- **Total: ~$0.01/month**

## Troubleshooting

### "Semantic search not available"
- Check: `embedding_status()`
- Verify: OPENAI_API_KEY is set
- Run: `generate_embeddings()`

### "No similar contexts found"
- Lower threshold: `threshold=0.6` (default 0.7)
- Check: Do contexts have embeddings? Run `embedding_status()`
- Try: Broader query terms

### Performance Issues
- Batch operations: Generate embeddings in batches of 100
- First search slow: Subsequent searches are cached
- Large databases: Consider PostgreSQL migration (future)

## Best Practices

1. **Generate embeddings incrementally**: Run after locking new contexts
2. **Use keyword search first**: Faster for exact matches
3. **Use semantic search for exploration**: Better for fuzzy queries
4. **Combine both**: Keyword OR semantic for comprehensive results
5. **Monitor costs**: Check `embedding_status()` for statistics
```

#### 4.3 Testing Plan

Create `tests/test_semantic_search.py`:

```python
"""Tests for semantic search functionality."""

import pytest
import sqlite3
from src.services.embedding_service import EmbeddingService
from src.services.semantic_search import SemanticSearch

def test_embedding_generation():
    """Test embedding generation for text."""
    service = EmbeddingService(api_key="test-key")

    # Skip if no API key
    if not service.enabled:
        pytest.skip("OpenAI API key not configured")

    text = "JWT authentication with OAuth2 required"
    embedding = service.generate_embedding(text)

    assert embedding is not None
    assert len(embedding) == 1536  # text-embedding-3-small dimensions
    assert all(isinstance(x, float) for x in embedding)

def test_cosine_similarity():
    """Test cosine similarity calculation."""
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [1.0, 0.0, 0.0]
    vec3 = [0.0, 1.0, 0.0]

    # Identical vectors should have similarity 1.0
    assert EmbeddingService.cosine_similarity(vec1, vec2) == pytest.approx(1.0)

    # Orthogonal vectors should have similarity 0.0
    assert EmbeddingService.cosine_similarity(vec1, vec3) == pytest.approx(0.0)

def test_semantic_search_similarity():
    """Test semantic search finds similar contexts."""
    # This test requires actual OpenAI API access
    # Could be mocked or run as integration test
    pass

def test_batch_embedding_generation():
    """Test batch embedding generation."""
    service = EmbeddingService(api_key="test-key")

    if not service.enabled:
        pytest.skip("OpenAI API key not configured")

    texts = ["First text", "Second text", "Third text"]
    embeddings = service.batch_generate_embeddings(texts)

    assert len(embeddings) == 3
    assert all(e is not None for e in embeddings)
```

## Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Create `src/config.py` with APIConfig class
- [ ] Create `src/services/embedding_service.py`
- [ ] Create `src/services/llm_service.py`
- [ ] Create `.env.example` with API key templates
- [ ] Test configuration loading
- [ ] Test embedding generation (if API key available)
- [ ] Test LLM completion (if API key available)

### Phase 2: Database Integration
- [ ] Create `migrations/add_embeddings.py`
- [ ] Run migration on development database
- [ ] Create `src/services/semantic_search.py`
- [ ] Test embedding storage and retrieval
- [ ] Test semantic similarity search
- [ ] Verify embedding statistics

### Phase 3: MCP Tool Integration
- [ ] Add `generate_embeddings()` tool
- [ ] Add `semantic_search_contexts()` tool
- [ ] Add `ai_summarize_context()` tool
- [ ] Add `embedding_status()` tool
- [ ] Update tool count in README.md (23 → 27)
- [ ] Test each tool with and without API keys

### Phase 4: Documentation & Testing
- [ ] Create `docs/SEMANTIC_SEARCH_GUIDE.md`
- [ ] Update README.md with new tools section
- [ ] Update CLAUDE.md with usage instructions
- [ ] Update RLM_IMPLEMENTATION_PLAN.md (10/12 RAG)
- [ ] Create `tests/test_semantic_search.py`
- [ ] Run all tests
- [ ] Validate syntax: `python3 -m py_compile claude_mcp_hybrid.py`

## Success Criteria

- [ ] All services gracefully degrade without API keys
- [ ] Embedding generation works in batches
- [ ] Semantic search returns relevant results
- [ ] AI summarization produces quality summaries
- [ ] Tool count updated: 23 → 27
- [ ] RAG compliance: 9/12 → 10/12 (83%)
- [ ] Documentation complete and accurate
- [ ] All tests pass

## Rollback Plan

If issues arise:

1. **Revert commits:**
   ```bash
   git log --oneline  # Find commit before implementation
   git revert <commit-hash>
   ```

2. **Remove API dependencies:**
   - Delete `src/` directory
   - Remove new tools from `claude_mcp_hybrid.py`
   - Restore README.md from git

3. **Database rollback:**
   - Embedding columns are optional, no data loss
   - Can drop columns if needed: `ALTER TABLE context_locks DROP COLUMN embedding`

## Timeline Estimate

- **Phase 1:** 2-3 hours (core infrastructure)
- **Phase 2:** 2-3 hours (database integration)
- **Phase 3:** 2-3 hours (MCP tools)
- **Phase 4:** 1-2 hours (documentation & testing)

**Total:** 7-11 hours for complete implementation

## Next Steps

This implementation plan is ready for execution. To begin:

1. Create `.env` file with API keys
2. Start with Phase 1 (core infrastructure)
3. Test each phase before proceeding
4. Commit incrementally with descriptive messages

---

**Status:** Ready for implementation
**Dependencies:** OpenAI API key (required), OpenRouter API key (optional)
**Impact:** +4 tools, +10% RAG compliance, +6MB per 1000 contexts
