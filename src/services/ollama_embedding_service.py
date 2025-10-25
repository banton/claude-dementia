"""Ollama embedding service for local embeddings."""

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

        Returns None if service not enabled or on error.
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

    def get_stats(self) -> dict:
        """Get service statistics."""
        return {
            'enabled': self.enabled,
            'model': self.model,
            'dimensions': self.dimensions,
            'base_url': self.base_url,
            'cost': 'FREE (local)',
            'performance': '~50ms per embedding'
        }
