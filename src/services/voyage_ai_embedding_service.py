"""Voyage AI embedding service for cloud embeddings."""

import requests
from typing import List, Optional
import numpy as np


class VoyageAIEmbeddingService:
    """Generate embeddings using Voyage AI cloud API."""

    def __init__(
        self,
        api_key: str,
        model: str = "voyage-3.5-lite",
        dimensions: int = 1024,
        token_tracker=None
    ):
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.token_tracker = token_tracker
        self.base_url = "https://api.voyageai.com/v1/embeddings"
        self.rerank_url = "https://api.voyageai.com/v1/rerank"
        self.enabled = self._check_api_available()

    def _check_api_available(self) -> bool:
        """Check if Voyage AI API is accessible."""
        if not self.api_key:
            return False

        try:
            # Test with minimal request
            response = requests.post(
                self.base_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "input": ["test"],
                    "model": self.model
                },
                timeout=10
            )
            return response.status_code in [200, 201]
        except Exception:
            return False

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding vector for text.

        Cost: $0.02/M tokens (voyage-3.5-lite)
        Performance: ~100-300ms depending on text length
        Free tier: 200M tokens/month
        """
        if not self.enabled:
            return None

        try:
            import time
            start_time = time.time()

            response = requests.post(
                self.base_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "input": [text[:8000]],  # Reasonable limit
                    "model": self.model,
                    "input_type": "document"
                },
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            embedding = data['data'][0]['embedding']

            # Track usage if tracker available
            if self.token_tracker:
                duration_ms = int((time.time() - start_time) * 1000)
                self.token_tracker.track_embedding(
                    text=text,
                    model=self.model,
                    provider="voyage_ai",
                    duration_ms=duration_ms
                )

            return embedding

        except Exception as e:
            print(f"Voyage AI embedding generation failed: {e}")
            return None

    def batch_generate_embeddings(
        self,
        texts: List[str],
        batch_size: int = 128  # Voyage AI supports up to 128 texts per request
    ) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts efficiently.

        Voyage AI supports batch requests (up to 128 texts),
        which is much faster than sequential requests.
        """
        if not self.enabled:
            return [None] * len(texts)

        embeddings = []

        try:
            import time

            # Process in batches
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                start_time = time.time()

                response = requests.post(
                    self.base_url,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    json={
                        "input": [t[:8000] for t in batch],
                        "model": self.model,
                        "input_type": "document"
                    },
                    timeout=60
                )
                response.raise_for_status()

                data = response.json()
                batch_embeddings = [item['embedding'] for item in data['data']]
                embeddings.extend(batch_embeddings)

                # Track usage for batch if tracker available
                if self.token_tracker:
                    duration_ms = int((time.time() - start_time) * 1000)
                    for text in batch:
                        self.token_tracker.track_embedding(
                            text=text,
                            model=self.model,
                            provider="voyage_ai",
                            duration_ms=duration_ms // len(batch)  # Approximate per-text duration
                        )

            return embeddings

        except Exception as e:
            print(f"Voyage AI batch embedding failed: {e}")
            return [None] * len(texts)

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two embedding vectors."""
        if not vec1 or not vec2:
            return 0.0

        a = np.array(vec1)
        b = np.array(vec2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def rerank(
        self,
        query: str,
        documents: List[dict],
        top_k: int = 10,
        model: str = "rerank-2.5-lite"
    ) -> List[dict]:
        """
        Rerank documents using Voyage AI reranker for improved relevance.

        Two-stage retrieval:
        1. Initial vector search returns top-N candidates (e.g., 50)
        2. Reranker uses cross-attention to score query-document pairs
        3. Returns top-K most relevant documents with rerank scores

        Args:
            query: Search query string
            documents: List of candidate documents with 'id' and 'content' keys
            top_k: Number of top results to return (default: 10)
            model: Reranker model - "rerank-2.5" or "rerank-2.5-lite" (default)

        Returns:
            List of reranked documents with added 'rerank_score' field,
            sorted by relevance (highest first)

        Cost:
            - rerank-2.5-lite: $0.02/M tokens
            - rerank-2.5: $0.05/M tokens
            Typical query: ~$0.0003 (50 docs × 1000 chars)

        Performance: ~200-500ms for 50 documents

        Example:
            # Get 50 candidates from vector search
            candidates = semantic_search(query, limit=50)

            # Rerank to get best 10
            results = service.rerank(
                query="FastAPI authentication",
                documents=candidates,
                top_k=10
            )
        """
        if not self.enabled:
            return documents[:top_k]

        if not documents:
            return []

        try:
            import time
            start_time = time.time()

            # Extract content from documents
            # Support both dict-like objects and objects with attributes
            doc_contents = []
            for doc in documents:
                if isinstance(doc, dict):
                    content = doc.get('content') or doc.get('preview') or doc.get('text', '')
                else:
                    content = getattr(doc, 'content', '') or getattr(doc, 'preview', '') or getattr(doc, 'text', '')
                doc_contents.append(str(content)[:8000])  # Limit content length

            response = requests.post(
                self.rerank_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "query": query[:2000],  # Limit query length
                    "documents": doc_contents,
                    "model": model,
                    "top_k": min(top_k, len(documents)),
                    "return_documents": False  # We already have the documents
                },
                timeout=30
            )
            response.raise_for_status()

            data = response.json()

            # Reorder documents by reranker scores
            # Voyage AI returns: {"data": [{"index": 3, "relevance_score": 0.95}, ...]}
            reranked_docs = []
            for result in data['data']:
                doc_index = result['index']
                relevance_score = result['relevance_score']

                # Get original document and add rerank score
                doc = documents[doc_index]
                if isinstance(doc, dict):
                    doc_copy = doc.copy()
                    doc_copy['rerank_score'] = relevance_score
                    reranked_docs.append(doc_copy)
                else:
                    # Handle object with attributes
                    doc_dict = {'rerank_score': relevance_score}
                    for key in ['id', 'content', 'preview', 'label', 'version', 'similarity_score']:
                        if hasattr(doc, key):
                            doc_dict[key] = getattr(doc, key)
                    reranked_docs.append(doc_dict)

            # Track usage if tracker available
            if self.token_tracker:
                duration_ms = int((time.time() - start_time) * 1000)
                # Approximate token count: query + all documents
                total_text = query + ' '.join(doc_contents)
                self.token_tracker.track_embedding(
                    text=total_text,
                    model=model,
                    provider="voyage_ai",
                    duration_ms=duration_ms
                )

            return reranked_docs

        except Exception as e:
            print(f"Voyage AI reranking failed: {e}")
            # Fallback: return original order
            return documents[:top_k]

    def get_stats(self) -> dict:
        """Get service statistics and configuration."""
        return {
            "enabled": self.enabled,
            "provider": "voyage_ai",
            "model": self.model,
            "dimensions": self.dimensions,
            "base_url": self.base_url,
            "has_api_key": bool(self.api_key),
            "features": {
                "batch_support": True,
                "max_batch_size": 128,
                "max_text_length": 8000,
                "free_tier": "200M tokens/month",
                "reranking": True,
                "rerank_models": ["rerank-2.5", "rerank-2.5-lite"]
            }
        }
