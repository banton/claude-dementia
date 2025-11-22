import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import tempfile

sys.path.append(os.getcwd())

from document_processor import DocumentProcessor

class TestDocumentProcessor(unittest.TestCase):
    def setUp(self):
        self.processor = DocumentProcessor()
    
    @patch('document_processor.MarkItDown')
    def test_extract_text_from_file(self, mock_markitdown_class):
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test content")
            temp_path = f.name
        
        try:
            # Setup mock
            mock_md = MagicMock()
            mock_markitdown_class.return_value = mock_md
            
            mock_result = MagicMock()
            mock_result.text_content = "Test content from markitdown"
            mock_md.convert.return_value = mock_result
            
            # Test
            processor = DocumentProcessor()
            text, file_type = processor.extract_text_from_file(temp_path)
            
            # Verify
            self.assertEqual(text, "Test content from markitdown")
            self.assertEqual(file_type, ".txt")
            
        finally:
            os.unlink(temp_path)
    
    def test_chunk_text_if_needed_short(self):
        short_text = "Short text"
        result, truncated = self.processor.chunk_text_if_needed(short_text)
        
        self.assertEqual(result, short_text)
        self.assertFalse(truncated)
    
    def test_chunk_text_if_needed_long(self):
        long_text = "x" * 70000
        result, truncated = self.processor.chunk_text_if_needed(long_text)
        
        self.assertTrue(truncated)
        self.assertLess(len(result), len(long_text))
        self.assertIn("[... Content truncated", result)
    
    def test_get_file_metadata(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test")
            temp_path = f.name
        
        try:
            metadata = self.processor.get_file_metadata(temp_path)
            
            self.assertIn("original_name", metadata)
            self.assertIn("file_type", metadata)
            self.assertIn("size_bytes", metadata)
            self.assertEqual(metadata["file_type"], ".txt")
            self.assertGreater(metadata["size_bytes"], 0)
            
        finally:
            os.unlink(temp_path)

if __name__ == '__main__':
    unittest.main()
