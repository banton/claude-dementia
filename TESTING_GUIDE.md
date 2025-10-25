# Testing Guide - Local Model Integration

## Quick Start Testing with Claude Desktop

### Prerequisites
✅ Ollama running
✅ nomic-embed-text installed (`ollama pull nomic-embed-text`)
✅ qwen2.5-coder:1.5b installed (`ollama pull qwen2.5-coder:1.5b`)

### Step 1: Restart Claude Desktop

The MCP server needs to reload with the new code:

1. Quit Claude Desktop completely
2. Start Claude Desktop
3. Open your test project

### Step 2: Check Service Status

In Claude Desktop chat:

```
Check embedding_status()
```

**Expected Output:**
```json
{
  "embedding_service": {
    "enabled": true,
    "provider": "ollama",
    "model": "nomic-embed-text",
    "dimensions": 768
  },
  "llm_service": {
    "enabled": true,
    "provider": "ollama",
    "model": "qwen2.5-coder:1.5b"
  }
}
```

### Step 3: Lock Some Test Contexts

```
Lock a few contexts about different topics:

1. Authentication context:
lock_context("JWT authentication with RS256. MUST validate expiration. NEVER store in localStorage.", "auth_system", priority="important")

2. Database context:
lock_context("PostgreSQL connection pooling. Max 20 connections. Timeout 30s.", "db_config", priority="important")

3. API context:
lock_context("REST API endpoints. GET /users, POST /auth/login, DELETE /users/:id", "api_endpoints")
```

### Step 4: Generate Embeddings

```
Run generate_embeddings()
```

**Expected Output:**
```json
{
  "message": "Embedding generation complete",
  "total_processed": 3,
  "success": 3,
  "failed": 0,
  "model": "nomic-embed-text",
  "performance": "~30ms per embedding",
  "cost": "FREE (local)"
}
```

### Step 5: Test Semantic Search

#### Test 1: Find authentication-related contexts
```
semantic_search_contexts("How do we handle user login?")
```

**Expected:** Should return auth_system context with high similarity score (>0.7)

#### Test 2: Find database-related contexts
```
semantic_search_contexts("connection pooling configuration")
```

**Expected:** Should return db_config context

#### Test 3: Cross-domain search (should NOT match)
```
semantic_search_contexts("authentication") should NOT return db_config
```

### Step 6: Test AI Summarization

```
ai_summarize_context("auth_system")
```

**Expected:** AI-generated summary highlighting:
- JWT authentication
- RS256 algorithm
- MUST validate expiration rule
- NEVER store in localStorage rule

### Success Criteria

✅ All 4 new tools available
✅ Embeddings generate successfully
✅ Semantic search finds relevant contexts
✅ AI summaries are coherent and highlight key rules
✅ No errors in Claude Desktop

## Troubleshooting

### "Service not available"

**Check 1: Is Ollama running?**
```bash
curl http://localhost:11434/api/tags
```

**Check 2: Are models installed?**
```bash
ollama list | grep nomic-embed-text
ollama list | grep qwen2.5-coder
```

**Fix:** Start Ollama or pull missing models

### "Import failed"

**Check:** Is src/ directory in the right place?
```bash
ls -la src/services/
```

**Fix:** Ensure all files committed and in project directory

### Embeddings generate but search finds nothing

**Check:** Lower the threshold
```
semantic_search_contexts("your query", threshold=0.5)
```

## Performance Benchmarks

Expected performance on M1/M2 Mac:

- **Embedding generation:** ~30ms per context
- **Semantic search:** ~30-50ms per query
- **AI summarization:** ~1-2s per summary
- **Batch operations:** ~500ms for 10 contexts

## Next Steps After Testing

1. Test with your real project
2. Generate embeddings for existing contexts
3. Try semantic searches for common questions
4. Compare keyword search vs semantic search results
5. Provide feedback on accuracy and usefulness

## Test Project Recommendations

Good projects to test with:
- Projects with authentication code
- Projects with database configuration
- Projects with API documentation
- Any project with 10+ locked contexts

The semantic search really shines when you have contexts on related but not identical topics!
