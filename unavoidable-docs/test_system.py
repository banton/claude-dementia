#!/usr/bin/env python3
"""
Test script for Unavoidable Documentation System
Run this to verify the system is working correctly
"""

import os
import sys
import time
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime

# Colors for output
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
CYAN = '\033[0;36m'
BOLD = '\033[1m'
NC = '\033[0m'  # No Color


def print_header(text):
    """Print a formatted header"""
    print(f"\n{BOLD}{'=' * 60}{NC}")
    print(f"{BOLD}{text}{NC}")
    print(f"{BOLD}{'=' * 60}{NC}")


def print_success(text):
    """Print success message"""
    print(f"{GREEN}✅ {text}{NC}")


def print_error(text):
    """Print error message"""
    print(f"{RED}❌ {text}{NC}")


def print_warning(text):
    """Print warning message"""
    print(f"{YELLOW}⚠️  {text}{NC}")


def print_info(text):
    """Print info message"""
    print(f"{CYAN}ℹ️  {text}{NC}")


def test_database_connection():
    """Test database connectivity"""
    print_header("Testing Database Connection")
    
    try:
        import psycopg2
        from config import DATABASE_CONFIG
        
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        print_success(f"Connected to PostgreSQL")
        print_info(f"Version: {version}")
        
        # Check if schema exists
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('file_documentation_status', 'documentation_debt')
        """)
        table_count = cur.fetchone()[0]
        
        if table_count == 2:
            print_success("Database schema is properly installed")
        else:
            print_error("Database schema is not installed")
            print_info("Run: cd database && ./setup.sh")
            return False
            
        conn.close()
        return True
        
    except ImportError:
        print_error("psycopg2 not installed")
        print_info("Run: pip install -r requirements.txt")
        return False
    except Exception as e:
        print_error(f"Database connection failed: {e}")
        print_info("Check your database configuration in config.py")
        return False


def test_file_monitoring():
    """Test file monitoring system"""
    print_header("Testing File Monitoring")
    
    try:
        from watchers.file_monitor import DocumentationDebtCreator
        from config import DATABASE_CONFIG
        
        # Create a test file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# Test file\nprint('Hello, World!')\n")
            test_file = f.name
        
        # Create debt creator
        debt_creator = DocumentationDebtCreator(DATABASE_CONFIG)
        
        # Process the file
        file_id = debt_creator.create_file_entry(test_file)
        
        if file_id:
            print_success(f"File tracking works - ID: {file_id}")
            
            # Create debt
            debt_id = debt_creator.create_debt_entry(
                file_id, 'new_file', 
                'Test file created', 
                Path(test_file).name
            )
            
            if debt_id != "EXISTS":
                print_success(f"Debt creation works - ID: {debt_id}")
            else:
                print_info("Debt already exists for this file")
        else:
            print_error("Failed to track file")
            return False
            
        # Clean up
        os.unlink(test_file)
        return True
        
    except ImportError as e:
        print_error(f"Import error: {e}")
        print_info("Check if all dependencies are installed")
        return False
    except Exception as e:
        print_error(f"File monitoring test failed: {e}")
        return False


def test_constant_extraction():
    """Test constant extraction"""
    print_header("Testing Constant Extraction")
    
    try:
        from watchers.constant_extractor import ConstantExtractor
        from config import DATABASE_CONFIG
        
        # Create a test file with constants
        test_code = '''
API_KEY = "sk_test_1234567890"
PORT = 3000
DATABASE_URL = "postgresql://user:pass@localhost/db"
TIMEOUT = 5000
API_ENDPOINT = "/api/v1/users"

def connect():
    url = "https://api.example.com"
    return url
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(test_code)
            test_file = f.name
        
        # Extract constants
        extractor = ConstantExtractor(DATABASE_CONFIG)
        constants = extractor.extract_constants_from_file(test_file)
        
        if constants:
            print_success(f"Found {len(constants)} constants:")
            for const in constants[:3]:  # Show first 3
                print_info(f"  - {const['constant_type']}: {const['constant_value'][:30]}...")
        else:
            print_warning("No constants found")
        
        # Clean up
        os.unlink(test_file)
        return len(constants) > 0
        
    except Exception as e:
        print_error(f"Constant extraction test failed: {e}")
        return False


def test_pre_commit_hook():
    """Test pre-commit hook"""
    print_header("Testing Pre-Commit Hook")
    
    hook_path = Path("enforcement/pre_commit_hook.sh")
    
    if not hook_path.exists():
        print_error("Pre-commit hook script not found")
        return False
    
    # Check if script is executable
    if not os.access(hook_path, os.X_OK):
        print_warning("Pre-commit hook is not executable")
        print_info(f"Run: chmod +x {hook_path}")
        os.chmod(hook_path, 0o755)
        print_success("Made hook executable")
    
    # Check if hook is installed
    git_hook = Path(".git/hooks/pre-commit")
    if git_hook.exists():
        print_success("Pre-commit hook is installed")
    else:
        print_warning("Pre-commit hook is not installed")
        print_info(f"Run: {hook_path} --install")
    
    return True


def test_debt_escalation():
    """Test debt escalation logic"""
    print_header("Testing Debt Escalation")
    
    try:
        import psycopg2
        from config import DATABASE_CONFIG
        
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cur = conn.cursor()
        
        # Run escalation function
        cur.execute("SELECT escalate_debt_priority();")
        conn.commit()
        
        print_success("Debt escalation function works")
        
        # Check for critical debt
        cur.execute("""
            SELECT COUNT(*) FROM documentation_debt 
            WHERE priority = 'critical' AND resolved_at IS NULL
        """)
        critical_count = cur.fetchone()[0]
        
        if critical_count > 0:
            print_warning(f"You have {critical_count} critical debt items!")
        else:
            print_info("No critical debt items")
        
        conn.close()
        return True
        
    except Exception as e:
        print_error(f"Debt escalation test failed: {e}")
        return False


def run_all_tests():
    """Run all system tests"""
    print(f"\n{BOLD}🚨 UNAVOIDABLE DOCUMENTATION SYSTEM - TEST SUITE{NC}")
    print(f"{BOLD}{'=' * 60}{NC}")
    print(f"Testing at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{BOLD}{'=' * 60}{NC}")
    
    tests = [
        ("Database Connection", test_database_connection),
        ("File Monitoring", test_file_monitoring),
        ("Constant Extraction", test_constant_extraction),
        ("Pre-Commit Hook", test_pre_commit_hook),
        ("Debt Escalation", test_debt_escalation)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print_error(f"Test '{name}' crashed: {e}")
            results.append((name, False))
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = f"{GREEN}PASS{NC}" if result else f"{RED}FAIL{NC}"
        print(f"  {name}: {status}")
    
    print(f"\n{BOLD}Results: {passed}/{total} tests passed{NC}")
    
    if passed == total:
        print_success("All tests passed! System is ready to use.")
        print_info("\nNext steps:")
        print_info("1. Install pre-commit hook: ./enforcement/pre_commit_hook.sh --install")
        print_info("2. Start file monitor: python watchers/file_monitor.py")
        print_info("3. Scan for constants: python watchers/constant_extractor.py")
    else:
        print_error(f"{total - passed} tests failed. Please fix issues before using the system.")
        return False
    
    return True


if __name__ == "__main__":
    # Change to script directory
    os.chdir(Path(__file__).parent)
    
    # Run tests
    success = run_all_tests()
    sys.exit(0 if success else 1)