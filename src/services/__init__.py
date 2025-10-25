"""Service initialization and factory."""

from typing import Optional
from src.config import config

# Global token tracker (initialized when get_db is called)
_token_tracker = None


def init_token_tracker(conn):
    """Initialize token tracker with database connection."""
    global _token_tracker
    from src.services.token_tracker import TokenTracker
    _token_tracker = TokenTracker(conn)
    return _token_tracker


def get_embedding_service():
    """Get embedding service based on configuration."""
    if config.embedding_provider == "ollama":
        from src.services.ollama_embedding_service import OllamaEmbeddingService
        service = OllamaEmbeddingService(
            base_url=config.ollama_base_url,
            model=config.embedding_model,
            token_tracker=_token_tracker
        )
        if service.enabled:
            return service

    elif config.embedding_provider == "voyage_ai":
        from src.services.voyage_ai_embedding_service import VoyageAIEmbeddingService
        if config.voyageai_api_key:
            service = VoyageAIEmbeddingService(
                api_key=config.voyageai_api_key,
                model=config.embedding_model,
                dimensions=config.embedding_dimensions,
                token_tracker=_token_tracker
            )
            if service.enabled:
                return service

    # Return disabled service
    class DisabledEmbeddingService:
        enabled = False
        model = None
        dimensions = 0

        def generate_embedding(self, text):
            return None

        def batch_generate_embeddings(self, texts):
            return [None] * len(texts)

        @staticmethod
        def cosine_similarity(vec1, vec2):
            return 0.0

        def get_stats(self):
            return {"enabled": False, "reason": "No embedding provider configured"}

    return DisabledEmbeddingService()


def get_llm_service():
    """Get LLM service based on configuration."""
    if config.llm_provider == "ollama":
        from src.services.ollama_llm_service import OllamaLLMService
        service = OllamaLLMService(
            base_url=config.ollama_base_url,
            default_model=config.llm_model,
            token_tracker=_token_tracker
        )
        if service.enabled:
            return service

    elif config.llm_provider == "openrouter":
        from src.services.openrouter_llm_service import OpenRouterLLMService
        if config.openrouter_api_key:
            service = OpenRouterLLMService(
                api_key=config.openrouter_api_key,
                default_model=config.llm_model,
                token_tracker=_token_tracker
            )
            if service.enabled:
                return service

    # Return disabled service
    class DisabledLLMService:
        enabled = False
        default_model = None

        def chat_completion(self, *args, **kwargs):
            return None

        def summarize_context(self, content):
            return None

        def classify_context_priority(self, content):
            return None

        def get_stats(self):
            return {"enabled": False, "reason": "No LLM provider configured"}

    return DisabledLLMService()


# Global service instances
embedding_service = get_embedding_service()
llm_service = get_llm_service()
