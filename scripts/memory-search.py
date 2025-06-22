#!/usr/bin/env python3
"""
Memory search tool - Quickly find relevant information in memory files.
Helps prevent solving the same problem multiple times.
"""
import re
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
import argparse
from collections import defaultdict

class MemorySearcher:
    def __init__(self):
        self.memory_root = Path("memory")
        self.index_file = Path("memory/.search-index.json")
        self.index = {}
        
    def build_index(self):
        """Build a searchable index of all memory files."""
        print("Building search index...")
        self.index = {
            'files': {},
            'keywords': defaultdict(list),
            'patterns': defaultdict(list),
            'fixes': defaultdict(list),
            'questions': defaultdict(list)
        }
        
        for memory_file in self.memory_root.rglob("*.md"):
            if memory_file.name.startswith('.'):
                continue
                
            self._index_file(memory_file)
        
        # Save index
        self._save_index()
        print(f"Indexed {len(self.index['files'])} files")
    
    def _index_file(self, filepath: Path):
        """Index a single file."""
        try:
            content = filepath.read_text().lower()
            rel_path = str(filepath.relative_to(self.memory_root))
            
            # Store file metadata
            self.index['files'][rel_path] = {
                'size': len(content),
                'modified': filepath.stat().st_mtime,
                'type': self._classify_file(rel_path)
            }
            
            # Extract keywords (technical terms)
            technical_terms = re.findall(r'\b(?:api|database|error|bug|fix|pattern|test|auth|cache|async|endpoint)\b', content)
            for term in set(technical_terms):
                self.index['keywords'][term].append(rel_path)
            
            # Special indexing based on file type
            if 'fixes/' in rel_path:
                # Extract error types from fixes
                errors = re.findall(r'(?:error|exception|bug):\s*([^\n]+)', content)
                for error in errors:
                    self.index['fixes'][error.strip()[:50]].append(rel_path)
                    
            elif 'patterns/' in rel_path:
                # Extract pattern names
                patterns = re.findall(r'(?:pattern|approach|solution):\s*([^\n]+)', content)
                for pattern in patterns:
                    self.index['patterns'][pattern.strip()[:50]].append(rel_path)
                    
            elif 'questions/' in rel_path:
                # Extract question topics
                questions = re.findall(r'question:\s*([^\n]+)', content)
                for question in questions:
                    self.index['questions'][question.strip()[:50]].append(rel_path)
                    
        except Exception as e:
            print(f"Error indexing {filepath}: {e}")
    
    def _classify_file(self, rel_path: str) -> str:
        """Classify file type based on path."""
        if 'fixes/' in rel_path:
            return 'fix'
        elif 'patterns/' in rel_path:
            return 'pattern'
        elif 'questions/' in rel_path:
            return 'question'
        elif 'implementations/' in rel_path:
            return 'implementation'
        elif 'architecture/' in rel_path:
            return 'architecture'
        elif 'decisions/' in rel_path:
            return 'decision'
        else:
            return 'other'
    
    def _save_index(self):
        """Save index to file."""
        # Convert defaultdicts to regular dicts for JSON serialization
        index_data = {
            'files': self.index['files'],
            'keywords': dict(self.index['keywords']),
            'patterns': dict(self.index['patterns']),
            'fixes': dict(self.index['fixes']),
            'questions': dict(self.index['questions']),
            'built': datetime.now().isoformat()
        }
        
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_file, 'w') as f:
            json.dump(index_data, f, indent=2)
    
    def _load_index(self) -> bool:
        """Load existing index if available."""
        if not self.index_file.exists():
            return False
            
        try:
            with open(self.index_file, 'r') as f:
                data = json.load(f)
                
            self.index = {
                'files': data['files'],
                'keywords': defaultdict(list, data['keywords']),
                'patterns': defaultdict(list, data['patterns']),
                'fixes': defaultdict(list, data['fixes']),
                'questions': defaultdict(list, data['questions'])
            }
            
            # Check if index is recent (less than 1 day old)
            built_time = datetime.fromisoformat(data['built'])
            if (datetime.now() - built_time).days > 1:
                print("Index is more than 1 day old, rebuilding...")
                return False
                
            return True
            
        except Exception as e:
            print(f"Error loading index: {e}")
            return False
    
    def search(self, query: str, search_type: str = 'all') -> List[Tuple[str, float]]:
        """Search memory for relevant files."""
        # Load or build index
        if not self._load_index():
            self.build_index()
        
        query_lower = query.lower()
        results = defaultdict(float)
        
        # Search in different categories based on type
        if search_type in ['all', 'keyword']:
            for word in query_lower.split():
                if word in self.index['keywords']:
                    for file in self.index['keywords'][word]:
                        results[file] += 1.0
        
        if search_type in ['all', 'fix']:
            for fix_desc, files in self.index['fixes'].items():
                if any(word in fix_desc for word in query_lower.split()):
                    for file in files:
                        results[file] += 2.0  # Higher weight for fixes
        
        if search_type in ['all', 'pattern']:
            for pattern_desc, files in self.index['patterns'].items():
                if any(word in pattern_desc for word in query_lower.split()):
                    for file in files:
                        results[file] += 1.5
        
        if search_type in ['all', 'question']:
            for question_desc, files in self.index['questions'].items():
                if any(word in question_desc for word in query_lower.split()):
                    for file in files:
                        results[file] += 1.0
        
        # Full text search in file paths
        for filepath in self.index['files']:
            if query_lower in filepath.lower():
                results[filepath] += 0.5
        
        # Sort by relevance
        sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
        
        return sorted_results
    
    def show_results(self, results: List[Tuple[str, float]], query: str, limit: int = 10):
        """Display search results."""
        print(f"\n🔍 Search results for: '{query}'")
        print(f"Found {len(results)} relevant files\n")
        
        if not results:
            print("No results found. Try different keywords or rebuild the index.")
            return
        
        for i, (filepath, score) in enumerate(results[:limit], 1):
            file_type = self.index['files'][filepath]['type']
            type_emoji = {
                'fix': '🔧',
                'pattern': '📐',
                'question': '❓',
                'implementation': '🏗️',
                'architecture': '🏛️',
                'decision': '🎯',
                'other': '📄'
            }.get(file_type, '📄')
            
            print(f"{i}. {type_emoji} {filepath} (relevance: {score:.1f})")
            
            # Show preview
            full_path = self.memory_root / filepath
            if full_path.exists():
                try:
                    content = full_path.read_text()
                    # Find first occurrence of query terms
                    preview_line = None
                    for line in content.split('\n'):
                        if any(word in line.lower() for word in query.lower().split()):
                            preview_line = line.strip()
                            break
                    
                    if preview_line:
                        preview = preview_line[:80] + '...' if len(preview_line) > 80 else preview_line
                        print(f"   Preview: {preview}")
                except:
                    pass
            
            print()
        
        if len(results) > limit:
            print(f"... and {len(results) - limit} more results")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Search through Claude memory files')
    parser.add_argument('query', help='Search query')
    parser.add_argument('--type', choices=['all', 'fix', 'pattern', 'question', 'keyword'], 
                       default='all', help='Type of search')
    parser.add_argument('--rebuild', action='store_true', help='Rebuild search index')
    parser.add_argument('--limit', type=int, default=10, help='Maximum results to show')
    
    args = parser.parse_args()
    
    searcher = MemorySearcher()
    
    if args.rebuild:
        searcher.build_index()
    
    # Perform search
    results = searcher.search(args.query, args.type)
    
    # Show results
    searcher.show_results(results, args.query, args.limit)
    
    # Provide copy-paste commands
    if results:
        print("\n📋 Quick commands:")
        print(f"# View top result:")
        print(f"cat memory/{results[0][0]}")
        print(f"\n# Edit top result:")
        print(f"vim memory/{results[0][0]}")

if __name__ == "__main__":
    main()
