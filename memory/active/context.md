# Working Context

## Current Project: Claude Intelligence
**MCP-based project memory system for Claude Code**

## Architecture Decisions
- Single-file Python MCP server (mcp_server.py)
- SQLite with FTS5 for storage and search
- TF-IDF by default (0MB), optional embeddings (33MB)
- Progressive indexing with user feedback
- Content hashing (xxhash) for change detection
- Hybrid search: FTS5 first, then optional vector re-ranking

## Key Features
1. **Tech Stack Detection** - Auto-detects frameworks/tools
2. **Smart File Search** - Semantic search with excerpts
3. **Change Tracking** - Git-aware session memory

## Implementation Plan
- **3-Day Demo**: Core working with TF-IDF search
- **Week 1**: Foundation + tech detection
- **Week 2**: Smart search + change tracking  
- **Week 3**: Polish + performance + release

## Critical Optimizations
- FTS5 for fast initial search (<10ms)
- Progressive indexing (current → src → rest)
- Smart ignores (node_modules, build, etc.)
- 2KB semantic extraction cap
- Search excerpts show WHY files matched

## Target Metrics
- Startup: <500ms
- Search: <50ms
- Index: <3s for 300 files
- Storage: <5MB without embeddings

## Files Created
- `/PROJECT_BIBLE.md` - Complete implementation plan
- `/unavoidable-docs/` - Original exploration (deprecated)

## Next Steps
1. Create mcp_server.py skeleton
2. Implement SQLite + FTS5
3. Add basic tech stack detection
4. Test with real project
5. Iterate based on performance
