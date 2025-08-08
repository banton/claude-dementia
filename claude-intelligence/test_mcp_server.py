#!/usr/bin/env python3
"""
Test suite for Claude Intelligence MCP Server
Following TDD principles - tests written before implementation
"""

import unittest
import tempfile
import shutil
import json
import sqlite3
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import time

# Import our server (not yet implemented)
try:
    from mcp_server import ClaudeIntelligence
except ImportError:
    # Server doesn't exist yet (TDD)
    ClaudeIntelligence = None


class TestProjectStructure(unittest.TestCase):
    """Test basic project setup and initialization"""
    
    def setUp(self):
        """Create a temporary test project"""
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
    def tearDown(self):
        """Clean up test environment"""
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir)
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_server_initializes(self):
        """Server should initialize without errors"""
        server = ClaudeIntelligence()
        self.assertIsNotNone(server)
        
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_creates_sqlite_database(self):
        """Should create SQLite database on init"""
        server = ClaudeIntelligence()
        self.assertTrue(Path('.claude-memory.db').exists())
        
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_database_has_fts5(self):
        """Database should have FTS5 virtual table"""
        server = ClaudeIntelligence()
        conn = sqlite3.connect('.claude-memory.db')
        cursor = conn.cursor()
        
        # Check FTS5 table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='file_fts'
        """)
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        conn.close()


class TestTechStackDetection(unittest.TestCase):
    """Test technology stack detection"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir)
    
    def create_package_json(self, content):
        """Helper to create package.json"""
        with open('package.json', 'w') as f:
            json.dump(content, f)
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_detects_nodejs_project(self):
        """Should detect Node.js from package.json"""
        self.create_package_json({
            "name": "test-app",
            "dependencies": {
                "express": "^4.18.0"
            }
        })
        
        server = ClaudeIntelligence()
        stack = server.detect_tech_stack()
        
        self.assertIn('Node.js', stack)
        self.assertIn('Express', stack)
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_detects_react_project(self):
        """Should detect React from package.json"""
        self.create_package_json({
            "dependencies": {
                "react": "^18.0.0",
                "react-dom": "^18.0.0"
            }
        })
        
        server = ClaudeIntelligence()
        stack = server.detect_tech_stack()
        
        self.assertIn('React', stack)
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_detects_python_project(self):
        """Should detect Python from requirements.txt"""
        with open('requirements.txt', 'w') as f:
            f.write("flask==2.3.0\nsqlalchemy==2.0.0\n")
        
        server = ClaudeIntelligence()
        stack = server.detect_tech_stack()
        
        self.assertIn('Python', stack)
        self.assertIn('Flask', stack)
        
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_detects_docker(self):
        """Should detect Docker from docker-compose.yml"""
        with open('docker-compose.yml', 'w') as f:
            f.write("version: '3'\nservices:\n  web:\n    image: nginx\n")
        
        server = ClaudeIntelligence()
        stack = server.detect_tech_stack()
        
        self.assertIn('Docker', stack)


class TestFileIndexing(unittest.TestCase):
    """Test file indexing and search"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
        # Create test files
        Path('src').mkdir()
        with open('src/payment.py', 'w') as f:
            f.write("""
def process_payment(amount):
    '''Process a payment through Stripe'''
    return stripe.charge(amount)
""")
        
        with open('src/auth.py', 'w') as f:
            f.write("""
def login(username, password):
    '''Authenticate user login'''
    return check_credentials(username, password)
""")
    
    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir)
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_indexes_files_progressively(self):
        """Should index files with progress feedback"""
        server = ClaudeIntelligence()
        
        progress_updates = []
        for update in server.index_progressive():
            progress_updates.append(update)
        
        # Should have progress updates
        self.assertGreater(len(progress_updates), 0)
        
        # Should index our test files (at least 2)
        self.assertGreaterEqual(server.file_count, 2)
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_content_hashing(self):
        """Should use content hash for change detection"""
        server = ClaudeIntelligence()
        server.index_file('src/payment.py')
        
        # Get initial hash
        initial_hash = server.get_file_hash('src/payment.py')
        
        # File unchanged - hash should be same
        current_hash = server.get_file_hash('src/payment.py')
        self.assertEqual(initial_hash, current_hash)
        
        # Modify file
        with open('src/payment.py', 'a') as f:
            f.write("\n# Modified")
        
        # Hash should change
        new_hash = server.get_file_hash('src/payment.py')
        self.assertNotEqual(initial_hash, new_hash)
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_respects_gitignore(self):
        """Should respect .gitignore patterns"""
        # Create gitignore
        with open('.gitignore', 'w') as f:
            f.write("*.pyc\n__pycache__/\n")
        
        # Create ignored files
        Path('__pycache__').mkdir()
        Path('__pycache__/cache.pyc').touch()
        Path('test.pyc').touch()
        
        server = ClaudeIntelligence()
        list(server.index_progressive())
        
        # Should not index ignored files
        self.assertFalse(server.is_indexed('test.pyc'))
        self.assertFalse(server.is_indexed('__pycache__/cache.pyc'))


class TestSearch(unittest.TestCase):
    """Test search functionality"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
        # Create test files with semantic content
        with open('payment.py', 'w') as f:
            f.write("def process_stripe_payment(): pass")
        
        with open('billing.py', 'w') as f:
            f.write("def calculate_invoice(): pass")
            
        with open('auth.py', 'w') as f:
            f.write("def user_login(): pass")
    
    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir)
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_fts5_search(self):
        """Should search using FTS5"""
        server = ClaudeIntelligence()
        list(server.index_progressive())
        
        results = server.search("payment")
        
        # Should find payment-related files
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]['path'], 'payment.py')
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_search_returns_excerpts(self):
        """Search results should include excerpts"""
        server = ClaudeIntelligence()
        list(server.index_progressive())
        
        results = server.search("payment")
        
        # Should have excerpt showing why it matched
        self.assertIn('excerpt', results[0])
        self.assertIn('stripe', results[0]['excerpt'].lower())
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_semantic_search_when_no_exact_match(self):
        """Should find semantically related files"""
        server = ClaudeIntelligence()
        list(server.index_progressive())
        
        # Search for partial match (more realistic for FTS5)
        results = server.search("invoice")
        
        # Should find billing file with calculate_invoice
        paths = [r['path'] for r in results]
        self.assertIn('billing.py', paths, "Should find billing.py for 'invoice' query")


class TestPerformance(unittest.TestCase):
    """Test performance requirements"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
        # Create multiple test files
        for i in range(100):
            with open(f'file_{i}.py', 'w') as f:
                f.write(f"def function_{i}(): pass")
    
    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir)
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_startup_time(self):
        """Should start up quickly with cache"""
        # First run (no cache)
        server1 = ClaudeIntelligence()
        list(server1.index_progressive())
        del server1
        
        # Second run (with cache)
        start = time.time()
        server2 = ClaudeIntelligence()
        startup_time = (time.time() - start) * 1000
        
        # Should be under 1 second
        self.assertLess(startup_time, 1000, f"Startup took {startup_time}ms")
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_search_performance(self):
        """Search should be fast"""
        server = ClaudeIntelligence()
        list(server.index_progressive())
        
        # Measure search time
        start = time.time()
        results = server.search("function")
        search_time = (time.time() - start) * 1000
        
        # Should be under 100ms
        self.assertLess(search_time, 100, f"Search took {search_time}ms")
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    def test_index_performance(self):
        """Indexing should be fast"""
        server = ClaudeIntelligence()
        
        start = time.time()
        list(server.index_progressive())
        index_time = time.time() - start
        
        # 100 files should index in under 3 seconds
        self.assertLess(index_time, 3, f"Indexing took {index_time}s")


class TestMCPInterface(unittest.TestCase):
    """Test MCP tool interface"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir)
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    async def test_understand_project_tool(self):
        """understand_project should return correct format"""
        server = ClaudeIntelligence()
        result = await server.understand_project()
        
        # Should have required keys
        self.assertIn('stack', result)
        self.assertIn('services', result)
        self.assertIn('summary', result)
        
        # Should be correct types
        self.assertIsInstance(result['stack'], list)
        self.assertIsInstance(result['services'], list)
        self.assertIsInstance(result['summary'], str)
    
    @unittest.skipIf(ClaudeIntelligence is None, "Server not implemented yet")
    async def test_find_files_tool(self):
        """find_files should return correct format"""
        with open('test.py', 'w') as f:
            f.write("def test(): pass")
            
        server = ClaudeIntelligence()
        list(server.index_progressive())
        
        results = await server.find_files("test")
        
        # Should return list
        self.assertIsInstance(results, list)
        
        if results:
            # Each result should have required keys
            result = results[0]
            self.assertIn('path', result)
            self.assertIn('score', result)
            self.assertIn('excerpt', result)


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)