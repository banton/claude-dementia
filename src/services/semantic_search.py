"""Semantic search using embeddings stored in SQLite."""

import sqlite3
from typing import List, Dict, Optional
import numpy as np


class SemanticSearch:
    """Semantic search using embeddings stored in SQLite."""

    def __init__(self, conn: sqlite3.Connection, embedding_service):
        self.conn = conn
        self.embedding_service = embedding_service
        self.enabled = embedding_service.enabled

    def add_embedding(self, context_id: int, text: str) -> bool:
        """
        Generate and store embedding for context.

        Returns True if successful, False otherwise.
        """
        if not self.enabled:
            return False

        embedding = self.embedding_service.generate_embedding(text)
        if not embedding:
            return False

        # Convert to binary for efficient storage
        embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()

        self.conn.execute("""
            UPDATE context_locks
            SET embedding = ?, embedding_model = ?
            WHERE id = ?
        """, (embedding_bytes, self.embedding_service.model, context_id))
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
        embeddings = self.embedding_service.batch_generate_embeddings(texts)

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
                    """, (embedding_bytes, self.embedding_service.model, ctx['id']))
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
        query_embedding = self.embedding_service.generate_embedding(query)
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
            similarity = self.embedding_service.cosine_similarity(
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

    def get_embedding_stats(self) -> Dict:
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
            "statistics": [dict(row) for row in stats] if stats else []
        }
