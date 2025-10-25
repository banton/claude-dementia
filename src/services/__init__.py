"""Service initialization and factory."""

from typing import Optional
from src.config import config


def get_embedding_service():
    """Get embedding service based on configuration."""
    from src.services.ollama_embedding_service import OllamaEmbeddingService

    if config.embedding_provider == "ollama":
        service = OllamaEmbeddingService(
            base_url=config.ollama_base_url,
            model=config.embedding_model
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
    from src.services.ollama_llm_service import OllamaLLMService

    if config.llm_provider == "ollama":
        service = OllamaLLMService(
            base_url=config.ollama_base_url,
            default_model=config.llm_model
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
