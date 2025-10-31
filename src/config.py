"""Configuration for Claude Dementia API services - PostgreSQL/Neon ONLY."""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class APIConfig:
    """API configuration - PostgreSQL + Voyage AI + OpenRouter (SQLite/Ollama disabled)."""

    def __init__(self):
        # API Keys
        self.openai_api_key: Optional[str] = os.getenv('OPENAI_API_KEY')
        self.openrouter_api_key: Optional[str] = os.getenv('OPENROUTER_API_KEY')
        self.voyageai_api_key: Optional[str] = os.getenv('VOYAGEAI_API_KEY')

        # Database Configuration - PostgreSQL ONLY
        self.database_url: str = os.getenv('DATABASE_URL')
        if not self.database_url:
            # Debug: print all env vars that contain 'DATA' to stderr
            import sys
            data_vars = {k: v[:20] + '...' if len(v) > 20 else v for k, v in os.environ.items() if 'DATA' in k}
            print(f"DEBUG: DATABASE_URL not found. Data-related env vars: {data_vars}", file=sys.stderr)
            raise ValueError("DATABASE_URL must be set in .env (PostgreSQL required)")

        # Embedding Configuration - Voyage AI ONLY
        self.embedding_provider: str = os.getenv('EMBEDDING_PROVIDER', 'voyage_ai')
        self.embedding_model: str = os.getenv('EMBEDDING_MODEL', 'voyage-3.5-lite')
        self.embedding_dimensions: int = int(os.getenv('EMBEDDING_DIMENSIONS', '1024'))

        # LLM Configuration - OpenRouter ONLY
        self.llm_provider: str = os.getenv('LLM_PROVIDER', 'openrouter')
        self.llm_model: str = os.getenv('LLM_MODEL', 'anthropic/claude-3.5-haiku')

        # DISABLED: Ollama Configuration (commented out, preserved for future)
        # self.ollama_base_url: str = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')

        # Feature Flags (auto-enabled based on available providers)
        self.enable_semantic_search: bool = self._check_semantic_search_available()
        self.enable_ai_summarization: bool = self._check_ai_summarization_available()

    def _check_semantic_search_available(self) -> bool:
        """Check if semantic search can be enabled - Voyage AI only."""
        # DISABLED: Ollama support (commented out)
        # if self.embedding_provider == 'ollama':
        #     return True

        if self.embedding_provider == 'voyage_ai':
            return bool(self.voyageai_api_key)

        return False

    def _check_ai_summarization_available(self) -> bool:
        """Check if AI summarization can be enabled - OpenRouter only."""
        # DISABLED: Ollama support (commented out)
        # if self.llm_provider == 'ollama':
        #     return True

        if self.llm_provider == 'openrouter':
            return bool(self.openrouter_api_key)

        return False

    def to_dict(self) -> dict:
        """Convert config to dictionary - PostgreSQL/Neon only."""
        return {
            'database': {
                'type': 'postgresql',
                'provider': 'neon',
                'connected': bool(self.database_url)
            },
            'embedding': {
                'provider': self.embedding_provider,
                'model': self.embedding_model,
                'dimensions': self.embedding_dimensions,
                'has_api_key': bool(self.voyageai_api_key)
            },
            'llm': {
                'provider': self.llm_provider,
                'model': self.llm_model,
                'has_api_key': bool(self.openrouter_api_key)
            },
            'features': {
                'semantic_search': self.enable_semantic_search,
                'ai_summarization': self.enable_ai_summarization
            },
            'disabled': {
                'sqlite': 'Local mode disabled - code preserved',
                'ollama': 'Local models disabled - code preserved'
            }
        }


# Global config instance (lazy initialization for cloud deployment)
_config = None

def get_config() -> APIConfig:
    """Get or create config instance (lazy initialization)."""
    global _config
    if _config is None:
        _config = APIConfig()
    return _config

# For backward compatibility, create a property-based accessor
class _ConfigProxy:
    def __getattr__(self, name):
        return getattr(get_config(), name)

config = _ConfigProxy()
