# Local Model Setup Guide

## Overview

Use local models (Ollama/LM Studio) instead of cloud APIs for privacy and zero cost.

## Quick Start

### 1. Install Ollama
```bash
# Already installed - verify:
ollama --version
```

### 2. Pull Models
```bash
# For embeddings (274MB)
ollama pull nomic-embed-text

# For LLM features (4.1GB)
ollama pull mistral

# Optional: Better quality LLM (4.7GB)
ollama pull llama3.1:8b
```

### 3. Configure Environment
```bash
# In .env file:
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768

LLM_PROVIDER=ollama
LLM_MODEL=mistral

# Or keep cloud as fallback:
OPENAI_API_KEY=sk-...  # Fallback for embeddings
EMBEDDING_PROVIDER=ollama,openai  # Try Ollama first
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│           Claude Dementia Memory System                     │
└────────────────┬────────────────────┬───────────────────────┘
                 │                    │
                 ▼                    ▼
    ┌────────────────────┐  ┌────────────────────────────────┐
    │   Ollama           │  │      Ollama / LM Studio        │
    │   (Embeddings)     │  │      (LLM Features)            │
    ├────────────────────┤  ├────────────────────────────────┤
    │ • nomic-embed-text │  │ • mistral / llama3.1           │
    │ • 768 dimensions   │  │ • Summarization                │
    │ • ~50ms per embed  │  │ • Classification               │
    │ • 274MB            │  │ • 4.1GB - 4.7GB                │
    │ • FREE             │  │ • FREE                         │
    └────────────────────┘  └────────────────────────────────┘
```

## Implementation

### Updated config.py

```python
import os
from typing import Literal, Optional, List
from pydantic import BaseSettings, Field

class APIConfig(BaseSettings):
    """API configuration with local model support."""

    # API Keys (optional with local models)
    openai_api_key: Optional[str] = Field(default=None, env='OPENAI_API_KEY')
    openrouter_api_key: Optional[str] = Field(default=None, env='OPENROUTER_API_KEY')

    # Embedding Configuration
    embedding_provider: Literal["openai", "ollama", "disabled"] = Field(default="ollama")
    embedding_model: str = Field(default="nomic-embed-text")
    embedding_dimensions: int = Field(default=768)  # nomic-embed-text dimensions
    embedding_fallback: Optional[str] = Field(default=None)  # e.g., "openai"

    # LLM Configuration
    llm_provider: Literal["openai", "openrouter", "ollama", "disabled"] = Field(default="ollama")
    llm_model: str = Field(default="mistral")
    llm_fallback: Optional[str] = Field(default=None)

    # Ollama Configuration
    ollama_base_url: str = Field(default="http://localhost:11434")

    # Feature Flags (auto-enabled based on available providers)
    enable_semantic_search: bool = Field(default=True)
    enable_ai_summarization: bool = Field(default=True)
    enable_auto_classification: bool = Field(default=True)

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

# Global config instance
config = APIConfig()
```

### Ollama Embedding Service

```python
# src/services/ollama_embedding_service.py
import requests
from typing import List, Optional
import numpy as np

class OllamaEmbeddingService:
    """Generate embeddings using Ollama local models."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text"
    ):
        self.base_url = base_url
        self.model = model
        self.dimensions = 768  # nomic-embed-text dimensions
        self.enabled = self._check_ollama_available()

    def _check_ollama_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            if response.status_code != 200:
                return False

            models = response.json().get('models', [])
            return any(m['name'].startswith(self.model) for m in models)
        except Exception:
            return False

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding vector for text.

        Cost: FREE (local)
        Performance: ~50ms per embedding on M1/M2
        """
        if not self.enabled:
            return None

        try:
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text[:8000]  # Reasonable limit
                },
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            return data['embedding']
        except Exception as e:
            print(f"Ollama embedding generation failed: {e}")
            return None

    def batch_generate_embeddings(
        self,
        texts: List[str],
        batch_size: int = 10  # Smaller batches for local models
    ) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts.

        Note: Ollama doesn't have batch API, so we process sequentially.
        Still reasonably fast (~500ms for 10 embeddings).
        """
        if not self.enabled:
            return [None] * len(texts)

        embeddings = []
        for text in texts:
            embedding = self.generate_embedding(text)
            embeddings.append(embedding)

        return embeddings

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two embedding vectors."""
        if not vec1 or not vec2:
            return 0.0

        a = np.array(vec1)
        b = np.array(vec2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
```

### Ollama LLM Service

```python
# src/services/ollama_llm_service.py
import requests
from typing import Optional

class OllamaLLMService:
    """Generate completions using Ollama local models."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "mistral"
    ):
        self.base_url = base_url
        self.default_model = default_model
        self.enabled = self._check_ollama_available()

    def _check_ollama_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            if response.status_code != 200:
                return False

            models = response.json().get('models', [])
            return any(m['name'].startswith(self.default_model) for m in models)
        except Exception:
            return False

    def chat_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Optional[str]:
        """
        Generate chat completion via Ollama.

        Cost: FREE (local)
        Performance: ~500ms-2s depending on model and length
        """
        if not self.enabled:
            return None

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model or self.default_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens
                    }
                },
                timeout=60
            )
            response.raise_for_status()

            data = response.json()
            return data['message']['content']
        except Exception as e:
            print(f"Ollama completion failed: {e}")
            return None

    def summarize_context(
        self,
        content: str,
        max_length: int = 500
    ) -> Optional[str]:
        """Generate intelligent summary of context content."""
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
        """Classify context priority using AI."""
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
```

### Unified Service Factory

```python
# src/services/__init__.py
from typing import Optional
from src.config import config

def get_embedding_service():
    """Get embedding service based on configuration."""
    from src.services.ollama_embedding_service import OllamaEmbeddingService
    from src.services.openai_embedding_service import OpenAIEmbeddingService

    if config.embedding_provider == "ollama":
        service = OllamaEmbeddingService(
            base_url=config.ollama_base_url,
            model=config.embedding_model
        )
        if service.enabled:
            return service

        # Fallback to OpenAI if configured
        if config.embedding_fallback == "openai" and config.openai_api_key:
            print("Ollama not available, falling back to OpenAI")
            return OpenAIEmbeddingService(api_key=config.openai_api_key)

    elif config.embedding_provider == "openai":
        if config.openai_api_key:
            return OpenAIEmbeddingService(api_key=config.openai_api_key)

    # Return disabled service
    class DisabledService:
        enabled = False
        def generate_embedding(self, text): return None
        def batch_generate_embeddings(self, texts): return [None] * len(texts)

    return DisabledService()

def get_llm_service():
    """Get LLM service based on configuration."""
    from src.services.ollama_llm_service import OllamaLLMService
    from src.services.openrouter_llm_service import OpenRouterLLMService

    if config.llm_provider == "ollama":
        service = OllamaLLMService(
            base_url=config.ollama_base_url,
            default_model=config.llm_model
        )
        if service.enabled:
            return service

        # Fallback to OpenRouter if configured
        if config.llm_fallback == "openrouter" and config.openrouter_api_key:
            print("Ollama not available, falling back to OpenRouter")
            return OpenRouterLLMService(api_key=config.openrouter_api_key)

    elif config.llm_provider == "openrouter":
        if config.openrouter_api_key:
            return OpenRouterLLMService(api_key=config.openrouter_api_key)

    # Return disabled service
    class DisabledService:
        enabled = False
        def chat_completion(self, *args, **kwargs): return None
        def summarize_context(self, content): return None

    return DisabledService()

# Global service instances
embedding_service = get_embedding_service()
llm_service = get_llm_service()
```

## Testing

### 1. Verify Ollama Running
```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Should return JSON with installed models
```

### 2. Test Embeddings
```bash
# Test embedding generation
curl http://localhost:11434/api/embeddings -d '{
  "model": "nomic-embed-text",
  "prompt": "test text"
}'

# Should return JSON with 'embedding' array (768 floats)
```

### 3. Test LLM
```bash
# Test completion
curl http://localhost:11434/api/chat -d '{
  "model": "mistral",
  "messages": [
    {"role": "user", "content": "Say hello"}
  ],
  "stream": false
}'

# Should return JSON with response
```

### 4. Test Integration
```python
# In Python REPL
from src.services import embedding_service, llm_service

# Test embedding
embedding = embedding_service.generate_embedding("test text")
print(f"Embedding dimensions: {len(embedding)}")  # Should be 768

# Test LLM
summary = llm_service.summarize_context("This is test content...")
print(f"Summary: {summary}")
```

## Performance Comparison

| Feature | Cloud (OpenAI) | Local (Ollama) | Difference |
|---------|---------------|----------------|------------|
| **Embeddings** |
| Cost | $0.02/M tokens | FREE | 100% savings |
| Speed | ~100ms | ~50ms | 2x faster |
| Quality | Excellent | Very Good | ~90% |
| Dimensions | 1536 | 768 | Half size |
| **LLM** |
| Cost | $0.25/M tokens | FREE | 100% savings |
| Speed | ~500ms | ~1-2s | 2-4x slower |
| Quality | Excellent | Good | ~80% |
| Privacy | Cloud | Local | 100% private |

## Configuration Examples

### Pure Local (No API Keys)
```bash
# .env
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768

LLM_PROVIDER=ollama
LLM_MODEL=mistral

OLLAMA_BASE_URL=http://localhost:11434
```

### Hybrid (Local Primary, Cloud Fallback)
```bash
# .env
EMBEDDING_PROVIDER=ollama
EMBEDDING_FALLBACK=openai
OPENAI_API_KEY=sk-...

LLM_PROVIDER=ollama
LLM_FALLBACK=openrouter
OPENROUTER_API_KEY=sk-or-...

# Uses Ollama if available, falls back to cloud if Ollama down
```

### Cloud Only (Original Plan)
```bash
# .env
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...

LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
```

## Model Recommendations

### For Embeddings

| Model | Size | Quality | Speed | Dimensions | Use Case |
|-------|------|---------|-------|------------|----------|
| nomic-embed-text | 274MB | ⭐⭐⭐⭐⭐ | Fast | 768 | **Recommended** |
| all-minilm | 45MB | ⭐⭐⭐ | Very Fast | 384 | Quick testing |

### For LLM Features

| Model | Size | Quality | Speed | Use Case |
|-------|------|---------|-------|----------|
| mistral | 4.1GB | ⭐⭐⭐⭐ | Fast | **Recommended** for summarization |
| llama3.1:8b | 4.7GB | ⭐⭐⭐⭐⭐ | Moderate | Better quality, slower |
| phi3:mini | 2.3GB | ⭐⭐⭐ | Very Fast | Quick testing |
| codellama | 3.8GB | ⭐⭐⭐⭐ | Fast | Code-focused tasks |

## LM Studio Alternative

If using LM Studio instead of Ollama:

1. **Start LM Studio Server**
   - Open LM Studio
   - Go to "Local Server" tab
   - Click "Start Server"
   - Note the port (usually 1234)

2. **Configure**
   ```bash
   # .env
   OLLAMA_BASE_URL=http://localhost:1234/v1
   ```

3. **LM Studio uses OpenAI-compatible API**
   - Same endpoints as OpenAI
   - Use `OpenAIEmbeddingService` with custom base_url
   - Works with existing code

## Migration from Cloud

### 1. Current Setup (Cloud)
```bash
# Using OpenAI + OpenRouter
# Cost: ~$0.27/M tokens
# Privacy: Cloud-based
```

### 2. Transition to Local
```bash
# Pull models
ollama pull nomic-embed-text  # 5 seconds
ollama pull mistral           # 30 seconds

# Update .env
# Set EMBEDDING_PROVIDER=ollama
# Set LLM_PROVIDER=ollama
```

### 3. Verify
```bash
# Restart MCP server
# Run: embedding_status()
# Should show: "provider": "ollama"
```

### 4. Re-generate Embeddings
```bash
# Embeddings are provider-specific
# Need to regenerate for Ollama (different dimensions)
generate_embeddings(regenerate=True)

# Takes ~1 minute for 1000 contexts
# One-time operation
```

## Troubleshooting

### "Ollama not available"
```bash
# Check if running
curl http://localhost:11434/api/tags

# If not running:
ollama serve  # Or restart Ollama app
```

### "Model not found"
```bash
# List installed models
ollama list

# Pull missing model
ollama pull nomic-embed-text
ollama pull mistral
```

### "Dimension mismatch"
```bash
# Ollama embeddings are 768-dim
# OpenAI embeddings are 1536-dim
# Cannot mix - must regenerate all embeddings

# Solution:
generate_embeddings(regenerate=True)
```

### Slow Performance
```bash
# Check system resources
# Ollama uses GPU if available (Metal on Mac)

# Monitor Ollama:
ollama ps

# For faster results:
# 1. Use smaller model (phi3:mini)
# 2. Reduce max_tokens
# 3. Increase temperature (faster, less precise)
```

## Best Practices

1. **Start Local**: Use Ollama by default for privacy and zero cost
2. **Cloud Fallback**: Configure fallback for reliability
3. **Model Selection**: Start with recommended models, experiment later
4. **Batch Operations**: Generate embeddings in batches for efficiency
5. **Monitor Performance**: Check response times, adjust models if needed
6. **Keep Models Updated**: `ollama pull <model>` periodically for updates

## Cost Savings

### Scenario: 1000 contexts, 100 queries/month

**Cloud Only:**
- Initial embeddings: $0.01
- Monthly queries: $0.02
- AI summaries: $0.01
- **Total: $0.04/month**

**Local Only:**
- Initial embeddings: FREE
- Monthly queries: FREE
- AI summaries: FREE
- **Total: $0.00/month** ✨

**Savings: 100%** + Complete privacy

---

**Status:** Ready to implement
**Next Step:** Pull Ollama models and test integration
**Time Estimate:** 30 minutes setup + testing
