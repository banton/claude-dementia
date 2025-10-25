"""Ollama embedding service for local embeddings."""

import requests
from typing import List, Optional
import numpy as np
import time


class OllamaEmbeddingService:
    """Generate embeddings using Ollama local models."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        token_tracker=None
    ):
        self.base_url = base_url
        self.model = model
        self.dimensions = 768  # nomic-embed-text dimensions
        self.enabled = self._check_ollama_available()
        self.token_tracker = token_tracker

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

    def generate_embedding(self, text: str, context_id: Optional[int] = None) -> Optional[List[float]]:
        """
        Generate embedding vector for text.

        Cost: FREE (local)
        Performance: ~50ms per embedding on M1/M2

        Returns None if service not enabled or on error.
        """
        if not self.enabled:
            import sys
            print(f"Embedding generation skipped: Service not enabled (Ollama not running or {self.model} not installed)", file=sys.stderr)
            return None

        try:
            import sys

            # nomic-embed-text has a 1020 character limit
            MAX_CHARS = 1020
            if len(text) > MAX_CHARS:
                print(f"[ERROR] Text too long: {len(text)} chars (max: {MAX_CHARS})", file=sys.stderr)
                print(f"[ERROR] Text will be truncated to {MAX_CHARS} chars", file=sys.stderr)
                text = text[:MAX_CHARS]

            start_time = time.time()

            request_data = {
                "model": self.model,
                "prompt": text
            }

            print(f"[DEBUG] Ollama embedding request: POST {self.base_url}/api/embeddings", file=sys.stderr)
            print(f"[DEBUG] Model: {self.model}, Text length: {len(text)} chars", file=sys.stderr)

            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json=request_data,
                timeout=30
            )

            print(f"[DEBUG] Response status: {response.status_code}", file=sys.stderr)

            response.raise_for_status()

            duration_ms = int((time.time() - start_time) * 1000)

            data = response.json()
            print(f"[DEBUG] Response keys: {list(data.keys())}", file=sys.stderr)

            if 'embedding' not in data:
                raise ValueError(f"Response missing 'embedding' key. Got keys: {list(data.keys())}, Response: {str(data)[:500]}")

            embedding = data['embedding']
            print(f"[DEBUG] Embedding generated: {len(embedding)} dimensions in {duration_ms}ms", file=sys.stderr)

            # Track usage
            if self.token_tracker:
                self.token_tracker.track_embedding(
                    text=text,
                    model=self.model,
                    provider='ollama',
                    duration_ms=duration_ms,
                    context_id=context_id
                )

            return embedding
        except requests.exceptions.ConnectionError as e:
            import sys
            print(f"[ERROR] Ollama connection failed: Is Ollama running at {self.base_url}?", file=sys.stderr)
            print(f"[ERROR] Exception: {str(e)}", file=sys.stderr)
            return None
        except requests.exceptions.Timeout as e:
            import sys
            print(f"[ERROR] Ollama request timeout (30s): Model may be loading or system overloaded", file=sys.stderr)
            print(f"[ERROR] Exception: {str(e)}", file=sys.stderr)
            return None
        except requests.exceptions.HTTPError as e:
            import sys
            print(f"[ERROR] Ollama HTTP error: {e.response.status_code}", file=sys.stderr)
            print(f"[ERROR] Response body: {e.response.text[:500]}", file=sys.stderr)
            print(f"[ERROR] Request was: POST {self.base_url}/api/embeddings model={self.model}", file=sys.stderr)
            return None
        except ValueError as e:
            import sys
            print(f"[ERROR] Ollama response format error: {str(e)}", file=sys.stderr)
            return None
        except Exception as e:
            import sys
            print(f"[ERROR] Ollama embedding generation failed: {type(e).__name__}: {str(e)}", file=sys.stderr)
            import traceback
            print(f"[ERROR] Traceback: {traceback.format_exc()}", file=sys.stderr)
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
