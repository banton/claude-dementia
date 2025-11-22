# OAuth PostgreSQL Storage Design

## Problem

Currently OAuth authorization codes and access tokens are stored in-memory:

```python
auth_codes: Dict[str, dict] = {}  # Lost on server restart
access_tokens: Dict[str, dict] = {}  # Lost on server restart
```

**Impact:**
- OAuth flow breaks if server restarts between authorize and token exchange
- Had to add TESTING MODE workaround (lines 197-245) that accepts any code
- Custom Connector sessions break on deployment

## Solution

Store OAuth codes and tokens in PostgreSQL for persistence across restarts.

## Schema Design

### Table: `oauth_authorization_codes`

Stores authorization codes from `/oauth/authorize` until exchange at `/oauth/token`.

```sql
CREATE TABLE oauth_authorization_codes (
    code TEXT PRIMARY KEY,                  -- Authorization code (32-byte urlsafe)
    client_id TEXT NOT NULL,                -- OAuth client ID
    redirect_uri TEXT NOT NULL,             -- Redirect URI from authorize request
    code_challenge TEXT NOT NULL,           -- PKCE code challenge (S256)
    code_challenge_method TEXT NOT NULL,    -- Always 'S256'
    user_id TEXT NOT NULL,                  -- User identifier (demo-user)
    scope TEXT NOT NULL,                    -- OAuth scope (mcp)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,        -- 5 minutes from creation
    used_at TIMESTAMPTZ                     -- When code was exchanged (NULL = unused)
);

-- Index for cleanup of expired codes
CREATE INDEX idx_oauth_codes_expires_at ON oauth_authorization_codes(expires_at);
```

**Lifecycle:**
1. Created by `/oauth/authorize` endpoint
2. Read and validated by `/oauth/token` endpoint
3. Marked as used (set `used_at`) after successful exchange
4. Cleaned up by background job after expiration

### Table: `oauth_access_tokens`

Stores access token metadata for validation.

```sql
CREATE TABLE oauth_access_tokens (
    access_token TEXT PRIMARY KEY,          -- Access token (from DEMENTIA_API_KEY)
    client_id TEXT NOT NULL,                -- OAuth client ID
    user_id TEXT NOT NULL,                  -- User identifier
    scope TEXT NOT NULL,                    -- OAuth scope
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,        -- 24 hours from creation
    last_used_at TIMESTAMPTZ                -- Track activity
);

-- Index for cleanup of expired tokens
CREATE INDEX idx_oauth_tokens_expires_at ON oauth_access_tokens(expires_at);
```

**Lifecycle:**
1. Created by `/oauth/token` endpoint after successful code exchange
2. Read by `validate_oauth_token()` function
3. Updated `last_used_at` on each validation (optional)
4. Cleaned up by background job after expiration

## Implementation Plan

### Phase 1: Schema Creation (TDD)

**Test File:** `tests/test_oauth_postgres.py`

```python
def test_oauth_tables_exist():
    """Test that OAuth tables exist in schema."""
    # Connect to database
    # Query information_schema for tables
    # Assert oauth_authorization_codes exists
    # Assert oauth_access_tokens exists

def test_oauth_code_lifecycle():
    """Test complete authorization code lifecycle."""
    # Insert auth code
    # Read auth code
    # Mark as used
    # Verify cannot be used again
    # Cleanup expired codes

def test_oauth_token_lifecycle():
    """Test access token lifecycle."""
    # Insert token
    # Validate token
    # Update last_used_at
    # Cleanup expired tokens
```

### Phase 2: Migration Script

**File:** `migrate_oauth_storage.py`

```python
#!/usr/bin/env python3
"""
Add OAuth storage tables to PostgreSQL schema.
"""

def migrate_oauth_tables(schema: str):
    """Create OAuth tables in given schema."""
    # CREATE TABLE oauth_authorization_codes
    # CREATE INDEX idx_oauth_codes_expires_at
    # CREATE TABLE oauth_access_tokens
    # CREATE INDEX idx_oauth_tokens_expires_at
```

### Phase 3: Update oauth_mock.py

**Changes:**

1. **Import postgres_adapter:**
```python
from postgres_adapter import PostgreSQLAdapter
```

2. **Replace in-memory dicts with PostgreSQL:**
```python
# OLD:
# auth_codes: Dict[str, dict] = {}
# access_tokens: Dict[str, dict] = {}

# NEW: Use PostgreSQL adapter
_db_adapter = PostgreSQLAdapter()
```

3. **Update `oauth_authorize()` (lines 133-141):**
```python
# OLD: auth_codes[auth_code] = {...}
# NEW:
_db_adapter.execute_update(
    """
    INSERT INTO oauth_authorization_codes
    (code, client_id, redirect_uri, code_challenge, code_challenge_method, user_id, scope, expires_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """,
    params=[
        auth_code,
        client_id,
        redirect_uri,
        code_challenge,
        code_challenge_method,
        'demo-user',
        scope,
        datetime.now(timezone.utc) + timedelta(minutes=5)
    ]
)
```

4. **Update `oauth_token()` (lines 200-241):**
```python
# OLD: if code in auth_codes:
# NEW:
result = _db_adapter.execute_query(
    """
    SELECT client_id, redirect_uri, code_challenge, scope, expires_at, used_at
    FROM oauth_authorization_codes
    WHERE code = %s
    """,
    params=[code]
)

if result:
    auth_data = result[0]

    # Check if already used
    if auth_data['used_at'] is not None:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Authorization code already used"},
            status_code=400
        )

    # Check expiration
    if datetime.now(timezone.utc) > auth_data['expires_at']:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "Authorization code expired"},
            status_code=400
        )

    # ... validation logic ...

    # Mark code as used
    _db_adapter.execute_update(
        "UPDATE oauth_authorization_codes SET used_at = NOW() WHERE code = %s",
        params=[code]
    )
```

5. **Update `oauth_token()` token storage (lines 252-257):**
```python
# OLD: access_tokens[access_token] = {...}
# NEW:
_db_adapter.execute_update(
    """
    INSERT INTO oauth_access_tokens
    (access_token, client_id, user_id, scope, expires_at)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (access_token) DO UPDATE
    SET last_used_at = NOW()
    """,
    params=[
        access_token,
        client_id,
        'demo-user',
        'mcp',
        datetime.now(timezone.utc) + timedelta(hours=24)
    ]
)
```

6. **Update `validate_oauth_token()` (lines 271-300):**
```python
# OLD: if token in access_tokens:
# NEW:
result = _db_adapter.execute_query(
    """
    SELECT client_id, user_id, scope, expires_at
    FROM oauth_access_tokens
    WHERE access_token = %s
    """,
    params=[token]
)

if result:
    token_data = result[0]

    # Check expiration
    if datetime.now(timezone.utc) > token_data['expires_at']:
        # Cleanup expired token
        _db_adapter.execute_update(
            "DELETE FROM oauth_access_tokens WHERE access_token = %s",
            params=[token]
        )
        return None

    # Update last_used_at
    _db_adapter.execute_update(
        "UPDATE oauth_access_tokens SET last_used_at = NOW() WHERE access_token = %s",
        params=[token]
    )

    return token_data
```

7. **Remove TESTING MODE workaround (lines 197-245):**
```python
# DELETE: Lines 197-245 that accept any code if not in memory
# With PostgreSQL, codes persist across restarts, so this workaround is unnecessary
```

### Phase 4: Background Cleanup Job

**File:** `oauth_cleanup.py`

```python
#!/usr/bin/env python3
"""
Background job to cleanup expired OAuth codes and tokens.
"""

def cleanup_expired_oauth_data():
    """Remove expired authorization codes and access tokens."""
    db = PostgreSQLAdapter()

    # Cleanup expired codes
    db.execute_update(
        "DELETE FROM oauth_authorization_codes WHERE expires_at < NOW()"
    )

    # Cleanup expired tokens
    db.execute_update(
        "DELETE FROM oauth_access_tokens WHERE expires_at < NOW()"
    )
```

Add to `server_hosted.py` startup:
```python
# Schedule cleanup every 1 hour
@app.on_event("startup")
async def schedule_oauth_cleanup():
    asyncio.create_task(periodic_oauth_cleanup())

async def periodic_oauth_cleanup():
    while True:
        try:
            cleanup_expired_oauth_data()
        except Exception as e:
            logger.error(f"OAuth cleanup error: {e}")
        await asyncio.sleep(3600)  # 1 hour
```

## Benefits

1. **✅ Survives restarts:** OAuth flow works across deployments
2. **✅ No TESTING MODE:** Proper validation without workarounds
3. **✅ Audit trail:** Track code usage and token activity
4. **✅ Automatic cleanup:** Background job removes expired data
5. **✅ Better security:** Can detect code reuse attacks

## Testing Checklist

- [ ] Create tables in PostgreSQL
- [ ] Write unit tests for OAuth storage
- [ ] Test authorization code lifecycle
- [ ] Test access token lifecycle
- [ ] Test cleanup of expired data
- [ ] Test OAuth flow survives server restart
- [ ] Deploy to production
- [ ] Verify Custom Connector sessions persist

## Rollback Plan

If issues occur:
1. Revert to in-memory storage (git revert)
2. Keep TESTING MODE enabled
3. Tables remain (no harm, just unused)

## Timeline

- **Phase 1-2:** 30 minutes (schema + migration)
- **Phase 3:** 45 minutes (update oauth_mock.py)
- **Phase 4:** 15 minutes (cleanup job)
- **Testing:** 30 minutes
- **Total:** ~2 hours

## Success Criteria

1. ✅ OAuth flow works normally
2. ✅ OAuth flow works after server restart
3. ✅ No TESTING MODE code remains
4. ✅ Expired codes/tokens are cleaned up
5. ✅ Custom Connector sessions persist
