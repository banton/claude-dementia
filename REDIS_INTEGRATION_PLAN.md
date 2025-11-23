# Redis Integration Plan for Dementia MCP v4.3.0

**Date:** November 23, 2025
**Current Infrastructure:** DigitalOcean Managed Valkey (Redis-compatible)
**Status:** DESIGN PHASE

---

## Executive Summary

**Goal:** Implement Redis caching layer to reduce database load, improve response times, and enable advanced features like rate limiting and real-time analytics.

**Expected Impact:**
- **Response Time:** Further reduce from <1s → <100ms for cached operations
- **Database Load:** 50-70% reduction in PostgreSQL queries
- **API Costs:** 30-40% reduction via embedding cache
- **Scalability:** Support 10x more concurrent users

**Implementation Timeline:** 3 weeks (3 phases)

**Cost:** Using existing DO Valkey cluster (already provisioned)

---

## Background

### Current Architecture (Post Async Migration)

```
FastMCP (async)
  ↓
MCP Tools (async)
  ↓
PostgreSQLAdapterAsync (asyncpg)
  ↓
NeonDB PostgreSQL
```

**Current Performance:**
- Response time: <1s (improved from 7-12s after async migration)
- Database queries: 5-15 per tool invocation
- Embedding generation: 200-500ms per call (VoyageAI)
- Session lookups: 50-100ms per request

**Pain Points:**
1. Repeated session lookups on every request
2. Context preview regeneration on every search
3. Duplicate embedding generation for same text
4. No query result caching
5. No rate limiting on external APIs

### DigitalOcean Valkey Details

**Service:** Managed Valkey (Redis-compatible, replacing Redis by June 30, 2025)

**Current Cluster:** (User reports: "we already have one redis server running")

**Pricing:**
- Single node (dev): $15/month (1GB RAM)
- HA cluster (prod): $30/month base + $30/month per standby node

**Features:**
- Fully Redis-compatible (drop-in replacement)
- Enhanced multi-threading
- Dual-channel replication
- Per-slot metrics
- Automatic failover (single node)
- SSL/TLS encryption
- Private network only
- No bandwidth charges

**Connection:**
- Private VPC connection (same as PostgreSQL)
- Standard Redis protocol
- Compatible with redis-py, aioredis libraries

---

## Redis Use Cases for Dementia MCP

### Priority 1: Session State Caching (HIGH IMPACT)

**Problem:** Every request queries PostgreSQL for session info
```python
# Current: Every request
session = await session_store.get_session(session_id)  # 50-100ms DB query
```

**Solution:** Cache session state in Redis
```python
# Proposed: First check Redis
session = await redis_cache.get_session(session_id)  # <5ms
if not session:
    session = await session_store.get_session(session_id)  # Fallback to DB
    await redis_cache.set_session(session_id, session, ttl=300)  # Cache 5min
```

**Expected Impact:**
- Response time: -50ms per request
- DB load: -60% session queries
- Cache hit rate: ~90% (sessions active for >5min)

### Priority 2: Context Preview Caching (HIGH IMPACT)

**Problem:** RLM preview generation on every context access
```python
# Current: Generate preview every time
preview = generate_preview(content)  # Expensive text processing
```

**Solution:** Cache previews by content hash
```python
# Proposed: Cache previews
content_hash = hashlib.sha256(content.encode()).hexdigest()
preview = await redis_cache.get(f"preview:{content_hash}")
if not preview:
    preview = generate_preview(content)
    await redis_cache.set(f"preview:{content_hash}", preview, ttl=86400)  # 24h
```

**Expected Impact:**
- Response time: -100-200ms per context access
- CPU usage: -30% (less text processing)
- Cache hit rate: ~80% (contexts don't change often)

### Priority 3: Embedding Cache (COST SAVINGS)

**Problem:** Duplicate embedding generation costs money
```python
# Current: Generate embedding every time
embedding = voyage.generate_embedding(text)  # $0.00012 per 1K tokens
```

**Solution:** Cache embeddings by text hash
```python
# Proposed: Cache embeddings
text_hash = hashlib.sha256(text.encode()).hexdigest()
cache_key = f"embedding:voyage-3-lite:{text_hash}"
embedding = await redis_cache.get(cache_key)
if not embedding:
    embedding = voyage.generate_embedding(text)
    await redis_cache.set(cache_key, json.dumps(embedding), ttl=604800)  # 7 days
```

**Expected Impact:**
- API cost: -30-40% (avoid duplicate generations)
- Response time: -200-500ms per embedding
- Cache hit rate: ~40% (repeated queries for same contexts)

### Priority 4: Query Result Caching (MEDIUM IMPACT)

**Problem:** Repeated search queries with same parameters
```python
# Current: Execute full search every time
results = await search_contexts("authentication", limit=10)  # 100-300ms
```

**Solution:** Cache search results with TTL
```python
# Proposed: Cache query results
cache_key = f"search:{project}:{query_hash}:{limit}"
results = await redis_cache.get(cache_key)
if not results:
    results = await search_contexts(query, limit)
    await redis_cache.set(cache_key, json.dumps(results), ttl=60)  # 1min TTL
```

**Expected Impact:**
- Response time: -100-300ms for repeated searches
- DB load: -20% search queries
- Cache hit rate: ~30% (users often search multiple times)

### Priority 5: Rate Limiting (OPERATIONAL)

**Problem:** No rate limiting on VoyageAI, OpenRouter APIs
```python
# Current: No limits, potential for API abuse/cost overruns
```

**Solution:** Redis-based rate limiting
```python
# Proposed: Token bucket rate limiting
async def check_rate_limit(user_id: str, api: str, max_per_minute: int):
    key = f"ratelimit:{api}:{user_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)  # Reset after 1 minute
    if count > max_per_minute:
        raise RateLimitExceeded(f"Max {max_per_minute} calls per minute")
```

**Expected Impact:**
- Cost control: Prevent API cost overruns
- Better user experience: Predictable limits
- Security: Prevent abuse

### Priority 6: Session Handover Cache (LOW IMPACT)

**Problem:** Handover packages stored in PostgreSQL, queried on every session start
```python
# Current: Query DB for last handover
handover = await db.fetch("SELECT * FROM session_handovers WHERE...")
```

**Solution:** Cache last handover in Redis
```python
# Proposed: Cache handover packages
handover = await redis_cache.get(f"handover:{project}:latest")
if not handover:
    handover = await db.fetch("SELECT * FROM session_handovers...")
    await redis_cache.set(f"handover:{project}:latest", handover, ttl=3600)
```

**Expected Impact:**
- Response time: -50ms on session start
- DB load: -10% handover queries

---

## Proposed Architecture

### System Architecture

```
FastMCP (async)
  ↓
MCP Tools (async)
  ↓
Redis Adapter (async) ← NEW
  |                   ↓
  |           DigitalOcean Valkey
  |           (Redis-compatible)
  ↓
PostgreSQLAdapterAsync (asyncpg)
  ↓
NeonDB PostgreSQL
```

### Redis Adapter Design

**New File: `redis_adapter_async.py`**

```python
"""
Async Redis adapter for Dementia MCP caching layer.
Uses aioredis for non-blocking operations.
"""

import os
import json
import hashlib
from typing import Optional, Any, Dict
import aioredis
from dotenv import load_dotenv

load_dotenv()


class RedisAdapterAsync:
    """
    Fully async Redis adapter using aioredis.

    Features:
    - Connection pooling
    - Automatic JSON serialization
    - TTL support
    - Graceful degradation (if Redis unavailable)
    - Performance metrics tracking
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        max_connections: int = 10,
        decode_responses: bool = True
    ):
        """
        Initialize async Redis adapter.

        Args:
            redis_url: Redis connection string (default: from REDIS_URL env)
            max_connections: Max connections in pool
            decode_responses: Auto-decode bytes to strings
        """
        self.redis_url = redis_url or os.getenv('REDIS_URL')
        if not self.redis_url:
            raise ValueError("REDIS_URL environment variable not set")

        self.max_connections = max_connections
        self.decode_responses = decode_responses
        self._redis: Optional[aioredis.Redis] = None

        # Metrics tracking
        self.metrics = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "errors": 0
        }

    async def connect(self) -> aioredis.Redis:
        """
        Get or create Redis connection pool.

        Returns:
            aioredis.Redis: Connection pool
        """
        if self._redis is None:
            self._redis = await aioredis.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                decode_responses=self.decode_responses,
                socket_keepalive=True,
                socket_connect_timeout=5,
                retry_on_timeout=True
            )
        return self._redis

    async def get(self, key: str) -> Optional[str]:
        """
        Get value from Redis.

        Args:
            key: Cache key

        Returns:
            Value if exists, None otherwise
        """
        try:
            redis = await self.connect()
            value = await redis.get(key)

            if value is not None:
                self.metrics["hits"] += 1
            else:
                self.metrics["misses"] += 1

            return value
        except Exception as e:
            self.metrics["errors"] += 1
            print(f"Redis GET error: {e}")
            return None  # Graceful degradation

    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in Redis with optional TTL.

        Args:
            key: Cache key
            value: Value to store
            ttl: Time to live in seconds (None = no expiry)

        Returns:
            True if successful, False otherwise
        """
        try:
            redis = await self.connect()

            if ttl:
                await redis.setex(key, ttl, value)
            else:
                await redis.set(key, value)

            self.metrics["sets"] += 1
            return True
        except Exception as e:
            self.metrics["errors"] += 1
            print(f"Redis SET error: {e}")
            return False  # Graceful degradation

    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        try:
            redis = await self.connect()
            await redis.delete(key)
            return True
        except Exception as e:
            print(f"Redis DELETE error: {e}")
            return False

    async def get_json(self, key: str) -> Optional[Dict]:
        """Get JSON value from Redis."""
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None

    async def set_json(
        self,
        key: str,
        value: Dict,
        ttl: Optional[int] = None
    ) -> bool:
        """Set JSON value in Redis."""
        try:
            json_str = json.dumps(value)
            return await self.set(key, json_str, ttl)
        except (TypeError, json.JSONEncodeError) as e:
            print(f"JSON serialization error: {e}")
            return False

    async def incr(self, key: str) -> int:
        """Increment counter (for rate limiting)."""
        try:
            redis = await self.connect()
            return await redis.incr(key)
        except Exception as e:
            print(f"Redis INCR error: {e}")
            return 0

    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiry on existing key."""
        try:
            redis = await self.connect()
            await redis.expire(key, ttl)
            return True
        except Exception as e:
            print(f"Redis EXPIRE error: {e}")
            return False

    async def get_metrics(self) -> Dict[str, int]:
        """Get cache performance metrics."""
        total_requests = self.metrics["hits"] + self.metrics["misses"]
        hit_rate = (
            self.metrics["hits"] / total_requests
            if total_requests > 0
            else 0
        )

        return {
            **self.metrics,
            "total_requests": total_requests,
            "hit_rate": hit_rate
        }

    async def close(self):
        """Close Redis connection pool."""
        if self._redis:
            await self._redis.close()
            await self._redis.connection_pool.disconnect()
```

### Cache Helper Functions

**New File: `cache_helpers.py`**

```python
"""
Helper functions for Redis caching in Dementia MCP.
"""

import hashlib
import json
from typing import Optional, Any, Callable
from functools import wraps

from redis_adapter_async import RedisAdapterAsync


# Global Redis adapter instance
_redis_adapter: Optional[RedisAdapterAsync] = None


async def get_redis() -> RedisAdapterAsync:
    """Get or create Redis adapter instance."""
    global _redis_adapter
    if _redis_adapter is None:
        _redis_adapter = RedisAdapterAsync()
        await _redis_adapter.connect()
    return _redis_adapter


def cache_key(prefix: str, *args, **kwargs) -> str:
    """
    Generate cache key from prefix and arguments.

    Args:
        prefix: Key prefix (e.g., "session", "context")
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        Cache key string

    Example:
        cache_key("session", "abc123") → "session:abc123"
        cache_key("search", "auth", limit=10) → "search:auth:limit=10"
    """
    parts = [prefix]
    parts.extend(str(arg) for arg in args)

    if kwargs:
        sorted_kwargs = sorted(kwargs.items())
        parts.extend(f"{k}={v}" for k, v in sorted_kwargs)

    return ":".join(parts)


def content_hash(text: str) -> str:
    """
    Generate SHA256 hash of content for caching.

    Args:
        text: Content to hash

    Returns:
        Hex digest of SHA256 hash
    """
    return hashlib.sha256(text.encode()).hexdigest()[:16]  # First 16 chars


def cached(
    prefix: str,
    ttl: int = 300,
    key_func: Optional[Callable] = None
):
    """
    Decorator for automatic Redis caching of async functions.

    Args:
        prefix: Cache key prefix
        ttl: Time to live in seconds
        key_func: Optional custom key generation function

    Example:
        @cached("user_profile", ttl=600)
        async def get_user_profile(user_id: str):
            return await db.fetch_user(user_id)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            redis = await get_redis()

            # Generate cache key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = cache_key(prefix, *args, **kwargs)

            # Try cache first
            cached_value = await redis.get_json(key)
            if cached_value is not None:
                return cached_value

            # Cache miss: call function
            result = await func(*args, **kwargs)

            # Store in cache
            await redis.set_json(key, result, ttl)

            return result

        return wrapper
    return decorator
```

---

## Performance Metrics & Logging

### Metrics to Track

**Cache Performance:**
```python
{
    "cache": {
        "hits": 1523,
        "misses": 234,
        "hit_rate": 0.867,
        "total_requests": 1757,
        "errors": 3
    }
}
```

**Response Time Breakdown:**
```python
{
    "timing": {
        "total_ms": 145,
        "cache_lookup_ms": 3,
        "db_query_ms": 0,  # Cached
        "processing_ms": 142
    }
}
```

**API Cost Tracking:**
```python
{
    "api_costs": {
        "voyage_calls_cached": 42,
        "voyage_calls_actual": 18,
        "cache_savings_usd": 0.0029,  # Estimated
        "total_voyage_calls": 60
    }
}
```

**Rate Limiting:**
```python
{
    "rate_limits": {
        "user_123": {
            "voyage_calls_per_min": 15,
            "limit": 30,
            "remaining": 15
        }
    }
}
```

### Structured Logging

**New: Performance Logger**

```python
# src/logging_config.py (UPDATE)

import structlog

# Add cache metrics logger
cache_logger = structlog.get_logger("cache")

def log_cache_operation(
    operation: str,
    key: str,
    hit: bool,
    duration_ms: float
):
    """Log cache operations with metrics."""
    cache_logger.info(
        "cache_operation",
        operation=operation,
        key=key,
        hit=hit,
        duration_ms=duration_ms,
        timestamp=datetime.utcnow().isoformat()
    )


def log_api_call(
    service: str,
    cached: bool,
    duration_ms: float,
    cost_usd: Optional[float] = None
):
    """Log external API calls with cost tracking."""
    api_logger = structlog.get_logger("api_costs")
    api_logger.info(
        "api_call",
        service=service,
        cached=cached,
        duration_ms=duration_ms,
        cost_usd=cost_usd,
        timestamp=datetime.utcnow().isoformat()
    )


def log_performance_breakdown(
    tool: str,
    total_ms: float,
    cache_ms: float,
    db_ms: float,
    processing_ms: float
):
    """Log detailed performance breakdown for tools."""
    perf_logger = structlog.get_logger("performance")
    perf_logger.info(
        "tool_performance",
        tool=tool,
        total_ms=total_ms,
        cache_ms=cache_ms,
        db_ms=db_ms,
        processing_ms=processing_ms,
        timestamp=datetime.utcnow().isoformat()
    )
```

### Performance Monitoring Dashboard (Future)

**Metrics Endpoint:**
```python
# server_hosted.py (ADD)

@app.get("/metrics/cache")
async def get_cache_metrics():
    """Get Redis cache metrics."""
    redis = await get_redis()
    metrics = await redis.get_metrics()

    return JSONResponse({
        "cache_performance": metrics,
        "timestamp": datetime.utcnow().isoformat()
    })
```

---

## Implementation Plan

### Phase 1: Foundation (Week 1)

**Goals:**
- Set up Redis connection
- Implement basic caching adapter
- Add session state caching
- Add performance metrics logging

**Tasks:**

1. **Create Redis Adapter** (Day 1-2)
   - Create `redis_adapter_async.py`
   - Write unit tests with mocked Redis
   - Test connection to existing DO Valkey cluster

2. **Environment Configuration** (Day 2)
   - Add `REDIS_URL` to `.env.example`
   - Document Redis setup in README.md
   - Update requirements.txt:
     ```
     aioredis>=2.0.0
     ```

3. **Session Caching** (Day 3-4)
   - Update `mcp_session_store_async.py`:
     ```python
     async def get_session(self, session_id: str):
         # Try Redis first
         session = await redis.get_json(f"session:{session_id}")
         if session:
             return session

         # Fallback to PostgreSQL
         session = await self._get_session_from_db(session_id)
         if session:
             await redis.set_json(f"session:{session_id}", session, ttl=300)

         return session
     ```
   - Add cache invalidation on session update
   - Test with production session load

4. **Metrics & Logging** (Day 4-5)
   - Add performance logging to key tools
   - Create `/metrics/cache` endpoint
   - Test metrics collection

**Deliverables:**
- ✅ Redis adapter functional
- ✅ Session caching working
- ✅ Metrics logging operational
- ✅ Unit tests passing

**Success Criteria:**
- Session cache hit rate: >80%
- Session lookup time: <5ms (vs 50-100ms before)

### Phase 2: High-Impact Caching (Week 2)

**Goals:**
- Implement context preview caching
- Implement embedding caching
- Add query result caching

**Tasks:**

1. **Preview Caching** (Day 6-7)
   - Update `generate_preview()` function:
     ```python
     async def generate_preview_cached(content: str) -> str:
         content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
         cache_key = f"preview:{content_hash}"

         preview = await redis.get(cache_key)
         if preview:
             return preview

         preview = generate_preview(content)  # Existing function
         await redis.set(cache_key, preview, ttl=86400)  # 24h
         return preview
     ```
   - Update `check_contexts()` to use cached previews
   - Test preview cache hit rate

2. **Embedding Caching** (Day 7-8)
   - Update `voyage_service.py`:
     ```python
     async def generate_embedding_cached(self, text: str, model: str) -> list:
         text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
         cache_key = f"embedding:{model}:{text_hash}"

         embedding = await redis.get_json(cache_key)
         if embedding:
             log_api_call("voyage", cached=True, duration_ms=5)
             return embedding

         # Generate new embedding
         start = time.time()
         embedding = self.generate_embedding(text, model)
         duration = (time.time() - start) * 1000

         log_api_call("voyage", cached=False, duration_ms=duration, cost_usd=0.00012)

         # Cache for 7 days
         await redis.set_json(cache_key, embedding, ttl=604800)
         return embedding
     ```
   - Track API cost savings

3. **Query Result Caching** (Day 9-10)
   - Create cache decorator for search tools:
     ```python
     @cached("search_results", ttl=60)
     async def search_contexts(query: str, limit: int = 10):
         # Existing implementation
         pass
     ```
   - Add cache invalidation on context update
   - Test cache freshness

**Deliverables:**
- ✅ Preview caching operational
- ✅ Embedding caching reducing API costs
- ✅ Query caching improving response times

**Success Criteria:**
- Preview cache hit rate: >70%
- Embedding cache hit rate: >40%
- API cost reduction: >30%
- Query cache hit rate: >30%

### Phase 3: Advanced Features (Week 3)

**Goals:**
- Implement rate limiting
- Add cache warming strategies
- Optimize TTLs based on metrics
- Performance testing & tuning

**Tasks:**

1. **Rate Limiting** (Day 11-12)
   - Create rate limiting helper:
     ```python
     async def check_rate_limit(
         user_id: str,
         api: str,
         max_per_minute: int
     ):
         key = f"ratelimit:{api}:{user_id}:min"
         count = await redis.incr(key)

         if count == 1:
             await redis.expire(key, 60)

         if count > max_per_minute:
             raise RateLimitExceeded(
                 f"Rate limit exceeded: {max_per_minute}/min for {api}"
             )

         return {"remaining": max_per_minute - count}
     ```
   - Add rate limiting to VoyageAI calls
   - Add rate limiting to document ingestion
   - Test rate limit enforcement

2. **Cache Warming** (Day 12-13)
   - Implement session start cache warming:
     ```python
     async def warm_session_cache(project_name: str):
         """Pre-load frequently used contexts into Redis."""
         # Get "always_check" priority contexts
         contexts = await db.fetch("""
             SELECT label, preview
             FROM context_locks
             WHERE project_name = $1 AND priority = 'always_check'
             LIMIT 10
         """, [project_name])

         # Load into Redis
         for ctx in contexts:
             await redis.set(
                 f"preview:{ctx['label']}",
                 ctx['preview'],
                 ttl=3600
             )
     ```
   - Trigger warming on session creation

3. **TTL Optimization** (Day 13-14)
   - Analyze cache metrics
   - Adjust TTLs based on access patterns:
     - Sessions: 300s (5min) - frequently accessed
     - Previews: 86400s (24h) - rarely change
     - Embeddings: 604800s (7d) - expensive, stable
     - Query results: 60s (1min) - need freshness
   - Monitor cache memory usage

4. **Performance Testing** (Day 14-15)
   - Load test with 100 concurrent users
   - Measure response time improvements
   - Validate cache hit rates
   - Document performance gains
   - Create optimization recommendations

**Deliverables:**
- ✅ Rate limiting operational
- ✅ Cache warming improving UX
- ✅ Optimized TTLs
- ✅ Performance test results

**Success Criteria:**
- Overall cache hit rate: >60%
- Response time improvement: >50% for cached operations
- Zero rate limit violations in production
- Cache memory usage: <80% of allocated Redis RAM

---

## Environment Configuration

### Required Environment Variables

```bash
# .env

# Redis/Valkey Configuration (NEW)
REDIS_URL=redis://default:password@host:port/0
# Example: redis://default:abc123@valkey-cluster.db.ondigitalocean.com:25061/0

# Existing Variables
DATABASE_URL=postgresql://...
VOYAGEAI_API_KEY=...
OPENROUTER_API_KEY=...
```

### DigitalOcean Valkey Setup

**Option 1: Use Existing Cluster**
```bash
# Get connection details from DO dashboard
# Databases → [Your Valkey Cluster] → Connection Details
# Copy the "Connection String" → REDIS_URL
```

**Option 2: Create New Cluster** (if needed)
```bash
# Via doctl CLI
doctl databases create valkey-dementia \
  --engine valkey \
  --region nyc3 \
  --size db-s-1vcpu-1gb \
  --num-nodes 1

# Get connection details
doctl databases connection valkey-dementia --format ConnectionString
```

---

## Dependencies

### New Python Packages

```python
# requirements.txt (ADD)

# Redis async client
aioredis>=2.0.0

# Optional: Redis connection pooling
redis[hiredis]>=4.5.0
```

### Install
```bash
pip3 install aioredis redis[hiredis]
```

---

## Testing Strategy

### Unit Tests

**New File: `tests/test_redis_adapter_async.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_redis_adapter_get():
    """Test Redis GET operation."""
    with patch('aioredis.from_url', new_callable=AsyncMock) as mock_redis:
        mock_conn = AsyncMock()
        mock_conn.get.return_value = "test_value"
        mock_redis.return_value = mock_conn

        adapter = RedisAdapterAsync(redis_url="redis://localhost")
        value = await adapter.get("test_key")

        assert value == "test_value"
        mock_conn.get.assert_called_once_with("test_key")

@pytest.mark.asyncio
async def test_redis_adapter_set_with_ttl():
    """Test Redis SET with TTL."""
    with patch('aioredis.from_url', new_callable=AsyncMock) as mock_redis:
        mock_conn = AsyncMock()
        mock_redis.return_value = mock_conn

        adapter = RedisAdapterAsync(redis_url="redis://localhost")
        result = await adapter.set("test_key", "value", ttl=300)

        assert result is True
        mock_conn.setex.assert_called_once_with("test_key", 300, "value")
```

### Integration Tests

**New File: `tests/integration/test_redis_caching.py`**

```python
@pytest.mark.asyncio
async def test_session_caching_integration():
    """Test session caching end-to-end."""
    # Create session in DB
    session_id = await session_store.create_session("test_user", "test_project")

    # First call: should hit DB and cache
    session1 = await session_store.get_session(session_id)
    assert session1["session_id"] == session_id

    # Second call: should hit cache
    session2 = await session_store.get_session(session_id)
    assert session2 == session1

    # Verify cache hit
    redis = await get_redis()
    metrics = await redis.get_metrics()
    assert metrics["hits"] >= 1
```

### Performance Tests

**New File: `tests/performance/test_cache_performance.py`**

```python
@pytest.mark.asyncio
async def test_session_lookup_performance():
    """Measure session lookup performance with caching."""
    import time

    session_id = "test_session_123"

    # Warm cache
    await session_store.get_session(session_id)

    # Measure cached lookup
    start = time.time()
    for _ in range(100):
        await session_store.get_session(session_id)
    cached_duration = time.time() - start

    # Should be <500ms for 100 lookups (avg <5ms each)
    assert cached_duration < 0.5, f"Cached lookups too slow: {cached_duration}s"
```

---

## Rollout Strategy

### Development Environment

1. Install aioredis locally
2. Run Redis via Docker:
   ```bash
   docker run -d -p 6379:6379 redis:7-alpine
   export REDIS_URL="redis://localhost:6379/0"
   ```
3. Run unit tests
4. Test caching manually

### Staging Environment

1. Connect to DO Valkey cluster
2. Deploy with caching enabled
3. Monitor metrics
4. Validate cache hit rates
5. Performance testing

### Production Rollout

**Week 1:** Phase 1 (Session caching only)
- Enable session caching
- Monitor for 3 days
- Validate stability

**Week 2:** Phase 2 (Preview + Embedding caching)
- Enable preview caching
- Enable embedding caching
- Monitor API cost savings
- Validate for 3 days

**Week 3:** Phase 3 (Rate limiting + optimization)
- Enable rate limiting
- Optimize TTLs
- Full performance validation

---

## Monitoring & Alerting

### Key Metrics to Monitor

**Cache Health:**
- Cache hit rate (target: >60%)
- Cache miss rate
- Error rate (target: <0.1%)
- Memory usage (target: <80%)

**Performance:**
- Average response time (cached vs uncached)
- P95 response time
- Database query reduction %

**Cost:**
- VoyageAI API calls avoided
- Estimated cost savings USD/day

### Alerts

**Critical:**
- Cache error rate >1% (5min window)
- Cache memory usage >90%
- Redis connection failures

**Warning:**
- Cache hit rate <40% (1hour window)
- Response time degradation >20%

### Grafana Dashboards (Future)

**Cache Performance Dashboard:**
- Hit/miss rate over time
- Response time comparison (cached vs uncached)
- Memory usage trend
- API cost savings

**Redis Health Dashboard:**
- Connection pool stats
- Command latency
- Memory fragmentation
- Key eviction rate

---

## Risks & Mitigations

### Risk 1: Redis Unavailability

**Impact:** Cache misses, fallback to PostgreSQL
**Probability:** Low (DO managed service has 99.95% SLA)
**Mitigation:**
- Graceful degradation (cache errors don't break tools)
- Automatic reconnection logic
- Health check monitoring

### Risk 2: Cache Invalidation Bugs

**Impact:** Stale data returned to users
**Probability:** Medium (during initial rollout)
**Mitigation:**
- Conservative TTLs (start short, increase based on data)
- Cache version keys (can invalidate all caches by version bump)
- Manual cache clear command for admins

### Risk 3: Memory Exhaustion

**Impact:** Cache evictions, degraded hit rate
**Probability:** Low (current usage ~1GB cluster is oversized)
**Mitigation:**
- Monitor memory usage
- Set eviction policy (allkeys-lru)
- Scale Redis cluster if needed (easy with DO managed)

### Risk 4: Increased Complexity

**Impact:** Harder to debug, more moving parts
**Probability:** Medium
**Mitigation:**
- Comprehensive logging
- Cache metrics dashboard
- Clear documentation
- Training for team

---

## Cost Analysis

### Current Costs (Estimated)

**VoyageAI API:**
- ~$50/month (embeddings)

**PostgreSQL (Neon):**
- Free tier or $19/month

**Total:** ~$50-70/month

### With Redis Caching

**DigitalOcean Valkey:**
- Already provisioned (existing cluster)
- $0/month additional (using existing)

**VoyageAI API:**
- ~$35/month (-30% via embedding cache)

**PostgreSQL:**
- Same ($0-19/month)

**Total:** ~$35-55/month

**Net Savings:** $15/month + improved performance

---

## Success Metrics

### Week 1 (Phase 1)
- ✅ Session cache hit rate >80%
- ✅ Session lookup time <5ms
- ✅ Zero production incidents

### Week 2 (Phase 2)
- ✅ Overall cache hit rate >50%
- ✅ VoyageAI cost reduction >20%
- ✅ Response time improvement >30% for cached operations

### Week 3 (Phase 3)
- ✅ Overall cache hit rate >60%
- ✅ VoyageAI cost reduction >30%
- ✅ Response time improvement >50% for cached operations
- ✅ Zero rate limit violations

---

## Next Steps

1. **Review & Approval:** Review this plan, adjust as needed
2. **Provision Check:** Verify existing DO Valkey cluster details
3. **Phase 1 Start:** Begin redis_adapter_async.py implementation
4. **Testing Setup:** Set up local Redis for development
5. **Metrics Baseline:** Collect current performance baseline before caching

---

## References

**Sources:**
- [DigitalOcean Valkey Pricing](https://docs.digitalocean.com/products/databases/valkey/details/pricing/)
- [DigitalOcean Managed Databases](https://www.digitalocean.com/pricing/managed-databases)
- [Valkey Documentation](https://docs.digitalocean.com/products/databases/redis/)

**Related Documents:**
- `ASYNC_MIGRATION_PLAN.md` - Async architecture foundation
- `PHASE_3_TEST_REPORT.md` - Current performance baseline
- `PR_EVALUATION_ASYNC_MIGRATION.md` - Async migration details

---

**Prepared by:** Claude Code
**Date:** November 23, 2025
**Status:** READY FOR REVIEW
