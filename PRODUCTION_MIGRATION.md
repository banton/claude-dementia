# Production Code Migration Notice

**Date:** November 23, 2025

## Repository Split

As of this date, the claude-dementia repository has been split into two distinct projects:

### 1. claude-dementia (This Repository - Public OSS)

**Purpose:** Simple, file-based memory system for Claude Code

**Version:** v3.0

**Target Users:**
- Claude Code users
- Local development
- Community contributors

**Features:**
- File-based memory storage
- Simple installation via GitHub
- Works entirely locally
- No cloud dependencies

**Installation:**
```bash
git clone https://github.com/banton/claude-dementia /tmp/claude-memory
cp /tmp/claude-memory/CLAUDE.md ./ && cp -r /tmp/claude-memory/memory ./
chmod +x memory/*.sh && rm -rf /tmp/claude-memory
./memory/compress.sh
```

### 2. dementia-production (Private Repository)

**Purpose:** Full-featured MCP server for hosted/managed service

**Version:** v4.2+

**Target Users:**
- Internal development team
- Hosted API consumers

**Features:**
- PostgreSQL/NeonDB database
- Async architecture (FastMCP)
- VoyageAI embeddings
- OpenRouter LLM integration
- S3 document storage
- Multi-project isolation
- Session management
- Cloud deployment (DigitalOcean)

**Repository:** https://github.com/banton/dementia-production (private)

## Why the Split?

The two versions serve fundamentally different purposes:

1. **OSS (v3.0)** - Simple, accessible memory system for everyone
2. **Production (v4.2+)** - Enterprise-grade hosted service

Maintaining both in a single repository created confusion and complexity. The split allows:

- Clear focus for each version
- Better security (production secrets stay private)
- Simpler contribution workflow for OSS
- Independent versioning and releases

## Migration Impact

### For OSS Contributors

**No change** - Continue using this repository as before. The v3.0 file-based system remains public and actively maintained.

### For Production Developers

**Action Required** - Update your local remotes to point to the new private repository:

```bash
# If you have a local clone of the old repo with production branches
cd ~/your-local-repo

# Add new production remote
git remote add production https://github.com/banton/dementia-production.git

# Fetch production code
git fetch production

# Switch to production main branch
git checkout -b main production/main
```

### For DigitalOcean Deployments

**Action Required** - Update app platform to deploy from new repository:

```bash
# Update DigitalOcean app spec to use new repository
doctl apps spec get <app-id> > app-spec.yaml

# Edit app-spec.yaml:
# Change repo from "banton/claude-dementia" to "banton/dementia-production"
# Change branch from "feature/async-migration" to "main"

doctl apps update <app-id> --spec app-spec.yaml
```

## Branch Cleanup

The following production branches have been removed from claude-dementia (OSS):

- feature/async-migration (moved to production)
- feature/document-ingestion-async (moved to production)
- feature/cloud-* (moved to production)
- All PostgreSQL-related branches (moved to production)

These branches now exist in the private dementia-production repository.

## Pull Requests

### Open PRs in claude-dementia (OSS)

- **PR #2** (document-ingestion) has been closed
- Will be recreated in dementia-production repository

### New PR Workflow

**For OSS contributions:**
- Continue creating PRs against claude-dementia:main

**For production features:**
- Create PRs against dementia-production:main

## Version History

### OSS Timeline (Public)
- **v1.0** - Initial release (basic CLAUDE.md)
- **v2.0** - Memory scripts and compression
- **v3.0** - GitHub installation workflow (current)

### Production Timeline (Private)
- **v4.0** - PostgreSQL migration
- **v4.1** - RLM optimization
- **v4.2** - Async migration (current)
- **v4.3** - Document ingestion (in progress)
- **v5.0** - Redis integration (planned)

## Questions?

- **OSS Issues:** Create an issue in this repository
- **Production Issues:** Contact development team (private repo)

## Related Documentation

- **OSS README:** [README.md](README.md)
- **OSS Installation:** [INSTALL-FOR-CLAUDE.md](INSTALL-FOR-CLAUDE.md)
- **Repository Split Strategy:** See private repo REPO_SPLIT_STRATEGY.md

---

**Summary:** Simple file-based memory stays public (v3.0), production MCP server moved to private repository (v4.2+).
