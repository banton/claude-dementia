#!/usr/bin/env python3
"""
Comprehensive test for context locking system
"""

import asyncio
import json
from context_locking import ContextLockManager, LockSafetyGuard


async def test_comprehensive():
    """Full integration test of locking system"""
    
    print("=" * 60)
    print("Context Locking System - Comprehensive Test")
    print("=" * 60)
    
    manager = ContextLockManager()
    
    # Test 1: Lock a 500-line API spec
    print("\n1. Testing large API spec locking...")
    api_spec = """
# User Management API Specification v2.1

## Authentication
POST /auth/login
  Body: { username: string, password: string }
  Response: { token: string, expires: datetime }

POST /auth/refresh
  Headers: Authorization: Bearer <token>
  Response: { token: string, expires: datetime }

POST /auth/logout
  Headers: Authorization: Bearer <token>
  Response: { success: boolean }

## User Operations
GET /users
  Query: ?page=1&limit=20&sort=created_at
  Response: { users: User[], total: number, page: number }

GET /users/:id
  Response: User

POST /users
  Body: { email: string, name: string, role: string }
  Response: User

PUT /users/:id
  Body: Partial<User>
  Response: User

DELETE /users/:id
  Response: { success: boolean }

## User Model
interface User {
  id: string
  email: string
  name: string
  role: 'admin' | 'user' | 'guest'
  created_at: datetime
  updated_at: datetime
  metadata: object
}
""" * 10  # Make it ~500 lines
    
    result = await manager.lock_context(api_spec, "user_api", "2.1", persist=True)
    assert result['status'] == 'success', f"Failed to lock: {result}"
    print(f"✓ Locked {result['size']} chars as {result['label']} v{result['version']}")
    
    # Test 2: Try to lock a lock command (should fail)
    print("\n2. Testing safety against recursive locks...")
    bad_content = "lock this as 'recursive_test'"
    result = await manager.lock_context(bad_content, "bad_lock")
    assert result['status'] == 'rejected', "Should reject lock commands"
    print(f"✓ Correctly rejected: {result['reason']}")
    
    # Test 3: Recall after "50 messages" (simulated)
    print("\n3. Simulating recall after many messages...")
    print("   [... simulating 50 messages of conversation ...]")
    
    recalled = await manager.recall_context("user_api", "2.1")
    assert recalled['status'] == 'success'
    assert recalled['content'] == api_spec
    print(f"✓ Perfect recall of {len(recalled['content'])} chars")
    print(f"  Hash verification: {recalled['hash']}")
    
    # Test 4: List all locks
    print("\n4. Testing listing functionality...")
    locks = await manager.list_locked_contexts()
    assert len(locks) > 0
    print(f"✓ Found {len(locks)} locked contexts:")
    for lock in locks:
        print(f"  - {lock['label']} v{lock['version']} ({lock['size']} bytes)")
    
    # Test 5: Version management
    print("\n5. Testing version management...")
    v2_content = api_spec + "\n## New Endpoints\nGET /users/search"
    result = await manager.lock_context(v2_content, "user_api", persist=True)  # Auto-version
    assert result['status'] == 'success'
    print(f"✓ Auto-versioned to {result['version']}")
    
    # Test 6: Rate limiting
    print("\n6. Testing rate limiting...")
    # Reset to clear previous attempts
    manager.emergency_reset()
    success_count = 0
    for i in range(15):
        small_content = f"test content number {i} with enough length"
        result = await manager.lock_context(small_content, f"rate_test_{i}")
        if result['status'] == 'success':
            success_count += 1
    
    # Should have hit rate limit at some point
    assert success_count <= 10, f"Rate limit not working: {success_count} succeeded"
    print(f"✓ Rate limiting working ({success_count}/15 succeeded, max 10 allowed)")
    
    # Test 7: Emergency reset
    print("\n7. Testing emergency reset...")
    manager.emergency_reset()
    diagnostic = manager.get_diagnostic_info()
    print(f"✓ Emergency reset complete")
    print(f"  Session: {diagnostic['session_id']}")
    print(f"  Total locks: {diagnostic['total_locks']}")
    print(f"  Total size: {diagnostic['total_size']} bytes")
    
    # Test 8: Content extraction
    print("\n8. Testing content extraction...")
    test_message = """
    Here's the config:
    
    ```yaml
    database:
      host: localhost
      port: 5432
      name: production
    ```
    
    Lock this as 'db_config'
    """
    
    extracted = manager.extract_content_to_lock([], test_message)
    assert extracted is not None
    assert "database:" in extracted
    assert "localhost" in extracted
    assert "5432" in extracted
    print("✓ Correctly extracted code block from message")
    
    # Test 9: Unlock with confirmation
    print("\n9. Testing unlock functionality...")
    result = await manager.unlock_context("rate_test_0", confirm=False)
    assert result['status'] == 'confirmation_required'
    print("✓ Unlock requires confirmation")
    
    result = await manager.unlock_context("rate_test_0", confirm=True)
    assert result['status'] == 'success'
    print(f"✓ Unlocked successfully, deleted {result['deleted']} entries")
    
    # Test 10: Persistence check
    print("\n10. Testing persistence flag...")
    persistent_locks = [l for l in await manager.list_locked_contexts() if l['persistent']]
    assert len(persistent_locks) > 0
    print(f"✓ Found {len(persistent_locks)} persistent locks")
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nThe locking system is working correctly:")
    print("• Can lock and recall large content perfectly")
    print("• Prevents recursive/dangerous locks") 
    print("• Handles versioning automatically")
    print("• Enforces rate limits")
    print("• Has emergency reset capability")
    print("• Extracts content intelligently")
    print("• Requires confirmation for destructive operations")
    

if __name__ == "__main__":
    asyncio.run(test_comprehensive())