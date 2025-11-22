import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import os
import sys

sys.path.append(os.getcwd())

from voyage_service import VoyageEmbeddingService

class TestVoyageService(unittest.TestCase):
    @patch.dict(os.environ, {'VOYAGEAI_API_KEY': 'test-key'})
    @patch('voyage_service.voyageai.Client')
    def test_generate_embedding(self, mock_client_class):
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        mock_result = MagicMock()
        mock_result.embeddings = [[0.1, 0.2, 0.3]]
        mock_client.embed.return_value = mock_result
        
        # Test
        service = VoyageEmbeddingService()
        embedding = service.generate_embedding("test text")
        
        # Verify
        self.assertEqual(embedding, [0.1, 0.2, 0.3])
        mock_client.embed.assert_called_once_with(
            texts=["test text"],
            model="voyage-3-lite",
            input_type="document"
        )
    
    @patch.dict(os.environ, {'VOYAGEAI_API_KEY': 'test-key'})
    @patch('voyage_service.voyageai.Client')
    def test_generate_embeddings_batch(self, mock_client_class):
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        mock_result = MagicMock()
        mock_result.embeddings = [[0.1, 0.2], [0.3, 0.4]]
        mock_client.embed.return_value = mock_result
        
        # Test
        service = VoyageEmbeddingService()
        embeddings = service.generate_embeddings_batch(["text1", "text2"])
        
        # Verify
        self.assertEqual(len(embeddings), 2)
        self.assertEqual(embeddings[0], [0.1, 0.2])
        self.assertEqual(embeddings[1], [0.3, 0.4])
    
    @patch.dict(os.environ, {}, clear=True)
    def test_no_api_key(self):
        service = VoyageEmbeddingService()
        self.assertIsNone(service.client)
        
        with self.assertRaises(ValueError):
            service.generate_embedding("test")

if __name__ == '__main__':
    unittest.main()
