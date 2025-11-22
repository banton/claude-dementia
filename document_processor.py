import os
from pathlib import Path
from typing import Optional, Tuple
from markitdown import MarkItDown

class DocumentProcessor:
    """Handles document text extraction and processing."""
    
    def __init__(self):
        self.markitdown = MarkItDown()
        self.max_tokens = 15000  # Conservative estimate for voyage-3-lite
        
    def extract_text_from_file(self, file_path: str) -> Tuple[str, str]:
        """
        Extract text content from various file types.
        
        Uses markitdown to convert files to LLM-friendly markdown format.
        Supports: txt, md, py, json, csv, pdf, docx, xlsx, pptx, images, etc.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Tuple of (extracted_text, file_type)
            
        Raises:
            FileNotFoundError: If file doesn't exist
            Exception: If extraction fails
        """
        path_obj = Path(file_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Get file extension
        file_type = path_obj.suffix.lower() or "unknown"
        
        try:
            # Use markitdown for all file types
            result = self.markitdown.convert(str(path_obj))
            text = result.text_content
            
            if not text or len(text.strip()) == 0:
                raise ValueError(f"No text content extracted from {file_path}")
            
            return text, file_type
            
        except Exception as e:
            print(f"Failed to extract text from {file_path}: {e}")
            raise e
    
    def chunk_text_if_needed(self, text: str, max_chars: int = 60000) -> Tuple[str, bool]:
        """
        Truncate text if it exceeds max length (Option B: preview only).
        
        Args:
            text: Text to check
            max_chars: Maximum character count (default: ~15K tokens)
            
        Returns:
            Tuple of (text_or_preview, was_truncated)
        """
        if len(text) <= max_chars:
            return text, False
        
        # Truncate and add indicator
        preview = text[:max_chars] + "\n\n[... Content truncated for embedding ...]"
        return preview, True
    
    def get_file_metadata(self, file_path: str) -> dict:
        """
        Get file metadata.
        
        Args:
            file_path: Path to file
            
        Returns:
            Dictionary with file metadata
        """
        path_obj = Path(file_path)
        return {
            "original_name": path_obj.name,
            "file_type": path_obj.suffix.lower() or "unknown",
            "size_bytes": path_obj.stat().st_size
        }
