"""Configuration for Claude Dementia API services."""

import os
from typing import Literal, Optional

class APIConfig:
    """API configuration with local model support."""

    def __init__(self):
        # API Keys (optional with local models)
        self.openai_api_key: Optional[str] = os.getenv('OPENAI_API_KEY')
        self.openrouter_api_key: Optional[str] = os.getenv('OPENROUTER_API_KEY')
        self.voyageai_api_key: Optional[str] = os.getenv('VOYAGEAI_API_KEY')

        # Embedding Configuration
        self.embedding_provider: str = os.getenv('EMBEDDING_PROVIDER', 'ollama')
        self.embedding_model: str = os.getenv('EMBEDDING_MODEL', 'nomic-embed-text')
        self.embedding_dimensions: int = int(os.getenv('EMBEDDING_DIMENSIONS', '768'))
        self.embedding_fallback: Optional[str] = os.getenv('EMBEDDING_FALLBACK')

        # LLM Configuration
        self.llm_provider: str = os.getenv('LLM_PROVIDER', 'ollama')
        self.llm_model: str = os.getenv('LLM_MODEL', 'mistral')
        self.llm_fallback: Optional[str] = os.getenv('LLM_FALLBACK')

        # Ollama Configuration
        self.ollama_base_url: str = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')

        # Feature Flags (auto-enabled based on available providers)
        self.enable_semantic_search: bool = self._check_semantic_search_available()
        self.enable_ai_summarization: bool = self._check_ai_summarization_available()

    def _check_semantic_search_available(self) -> bool:
        """Check if semantic search can be enabled."""
        if self.embedding_provider == 'ollama':
            return True  # Will check Ollama availability at runtime
        elif self.embedding_provider == 'openai':
            return bool(self.openai_api_key)
        elif self.embedding_provider == 'voyage_ai':
            return bool(self.voyageai_api_key)
        return False

    def _check_ai_summarization_available(self) -> bool:
        """Check if AI summarization can be enabled."""
        if self.llm_provider == 'ollama':
            return True  # Will check Ollama availability at runtime
        elif self.llm_provider in ['openrouter', 'openai']:
            return bool(self.openrouter_api_key or self.openai_api_key)
        return False

    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        return {
            'embedding': {
                'provider': self.embedding_provider,
                'model': self.embedding_model,
                'dimensions': self.embedding_dimensions,
                'fallback': self.embedding_fallback
            },
            'llm': {
                'provider': self.llm_provider,
                'model': self.llm_model,
                'fallback': self.llm_fallback
            },
            'ollama': {
                'base_url': self.ollama_base_url
            },
            'voyage_ai': {
                'has_api_key': bool(self.voyageai_api_key)
            },
            'openrouter': {
                'has_api_key': bool(self.openrouter_api_key)
            },
            'features': {
                'semantic_search': self.enable_semantic_search,
                'ai_summarization': self.enable_ai_summarization
            }
        }


# Global config instance
config = APIConfig()
