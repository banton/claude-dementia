import os
import voyageai

class VoyageEmbeddingService:
    """Service for generating embeddings using VoyageAI API."""
    
    def __init__(self):
        self.api_key = os.getenv('VOYAGEAI_API_KEY')
        if not self.api_key:
            print("Warning: VOYAGEAI_API_KEY not set. Embedding generation will fail if used.")
            self.client = None
        else:
            self.client = voyageai.Client(api_key=self.api_key)
    
    def generate_embedding(self, text: str, model: str = "voyage-3-lite") -> list:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            model: VoyageAI model to use (default: voyage-3-lite)
            
        Returns:
            List of floats representing the embedding vector
            
        Raises:
            ValueError: If client not initialized
            Exception: If API call fails
        """
        if not self.client:
            raise ValueError("VoyageAI client not initialized. Check VOYAGEAI_API_KEY.")
        
        try:
            result = self.client.embed(
                texts=[text],
                model=model,
                input_type="document"
            )
            return result.embeddings[0]
        except Exception as e:
            print(f"VoyageAI embedding generation failed: {e}")
            raise e
    
    def generate_embeddings_batch(self, texts: list, model: str = "voyage-3-lite") -> list:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed
            model: VoyageAI model to use (default: voyage-3-lite)
            
        Returns:
            List of embedding vectors
            
        Raises:
            ValueError: If client not initialized
            Exception: If API call fails
        """
        if not self.client:
            raise ValueError("VoyageAI client not initialized. Check VOYAGEAI_API_KEY.")
        
        try:
            result = self.client.embed(
                texts=texts,
                model=model,
                input_type="document"
            )
            return result.embeddings
        except Exception as e:
            print(f"VoyageAI batch embedding generation failed: {e}")
            raise e
