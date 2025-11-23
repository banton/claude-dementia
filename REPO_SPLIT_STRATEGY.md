# Repository Split Strategy: OSS vs Production

**Date:** November 23, 2025
**Status:** 📋 PROPOSED
**Approach:** Separate repositories for OSS and production

---

## Executive Summary

**Current Problem:**
- Single public repo (`claude-dementia`) contains both OSS v3.0 and production hosted code
- OSS v3.0 (GitHub installation workflow) ≠ Production (PostgreSQL/Neon MCP server)
- Confusion about which version is which
- Can't protect production code/configs in public repo
- OSS contributors see production-specific code

**Proposed Solution:**
Create two separate repositories:

1. **`claude-dementia`** (public) - OSS version for community
2. **`dementia-production`** (private) - Hosted/managed service

**Benefits:**
- ✅ True separation of concerns
- ✅ Production secrets stay private
- ✅ OSS repo is clean and welcoming
- ✅ Independent evolution paths
- ✅ Simpler branching (each repo has main → feature workflow)
- ✅ No accidental production leaks
- ✅ Different access controls

---

## Repository Comparison

### Current State Analysis

**OSS v3.0 (commit ec9368e on `main`):**
- Simple GitHub installation workflow
- File-based memory system
- Bash scripts for compression
- CLAUDE.md instructions
- ~100 lines of code
- Target: Claude Code users (local development)
- Installation: `git clone` + copy files

**Production (current `feature/async-migration`):**
- Full MCP server with FastAPI
- PostgreSQL/Neon database
- Async/await throughout
- Session management
- VoyageAI embeddings
- S3/Spaces storage
- OAuth authentication
- ~11K+ lines of code
- Target: API consumers (hosted service)
- Deployment: DigitalOcean App Platform

**Divergence:**
```bash
290 files changed
+110,101 insertions
-4,935 deletions
```

**Conclusion:** These are fundamentally different products.

---

## Proposed Repository Structure

### Repository 1: `claude-dementia` (Public OSS)

**Purpose:** Community-facing open source memory system

**Branch Structure:**
```
main (v3.0)
  ↑
  │ Community PRs
  │
feature/oss-*
release/v*
```

**Key Files:**
```
claude-dementia/
├── README.md              (OSS installation instructions)
├── CLAUDE.md              (Memory system guide for Claude Code)
├── CONTRIBUTING.md        (Community contribution guidelines)
├── LICENSE                (MIT or similar)
├── memory/
│   ├── compress.sh        (Memory compression script)
│   ├── expand.sh          (Memory expansion script)
│   └── session.md         (Session template)
└── examples/
    └── usage.md           (Example workflows)
```

**README Content:**
```markdown
# Claude Code Memory System

Give Claude Code perfect memory across sessions.

## Quick Install
[Installation instructions for v3.0 approach]

## For Hosted Service
Looking for the managed API? Visit [dementia.ai](https://dementia.ai)
or check the [API documentation](https://docs.dementia.ai).
```

**Version:** v3.0.x (simple, local, file-based)

**Target Users:**
- Claude Code users
- Local development
- Self-hosted deployments
- Learning/experimentation

**Access:** Public

**Deployment:** None (users clone/install locally)

---

### Repository 2: `dementia-production` (Private)

**Purpose:** Hosted/managed MCP service

**Branch Structure:**
```
main (production)
  ↑
  │ Team PRs
  │
staging (optional)
  ↑
  │
feature/*
fix/*
```

**Key Files:**
```
dementia-production/
├── README.md              (Production deployment docs)
├── CLAUDE.md              (Development guide)
├── server_hosted.py       (FastAPI server)
├── claude_mcp_hybrid_sessions.py  (MCP server)
├── postgres_adapter_async.py      (Database layer)
├── mcp_session_store_async.py     (Session management)
├── storage_service.py     (S3/Spaces)
├── voyage_service.py      (VoyageAI embeddings)
├── document_processor.py  (MarkItDown)
├── requirements.txt       (Dependencies)
├── .env.example           (Environment template)
├── .github/
│   └── workflows/
│       └── production-ci.yml      (CI/CD)
├── tests/                 (Comprehensive test suite)
├── docs/
│   ├── API.md             (API documentation)
│   ├── DEPLOYMENT.md      (Deployment guide)
│   └── ARCHITECTURE.md    (System architecture)
└── migrations/            (Database migrations)
```

**README Content:**
```markdown
# Dementia Production

Hosted MCP server for persistent memory across Claude sessions.

## Deployment
[DigitalOcean deployment instructions]

## Development
[Local development setup]

## API
See [API.md](docs/API.md) for endpoint documentation.
```

**Version:** v4.2.x (hosted, production, PostgreSQL-based)

**Target Users:**
- Internal team
- API consumers
- Production operations

**Access:** Private

**Deployment:** DigitalOcean App Platform

---

## Migration Plan

### Phase 1: Create Production Repository (1 hour)

**Steps:**

1. **Create private repository on GitHub:**
```bash
gh repo create dementia-production --private --description "Production MCP server for dementia hosted service"
```

2. **Clone and prepare production code:**
```bash
# Clone existing repo to new location
cd /tmp
git clone https://github.com/banton/claude-dementia.git dementia-production
cd dementia-production

# Checkout production code (feature/async-migration)
git checkout feature/async-migration

# Remove OSS-specific files
rm -rf memory/ ASK-CLAUDE-CODE.md
rm -rf BUG_*.md  # Clean up bug investigation docs
rm -rf PHASE_*.md  # Clean up migration docs

# Create new README for production
cat > README.md << 'EOF'
# Dementia Production

Production MCP server for persistent memory across Claude sessions.

**Status:** 🚀 Deployed to DigitalOcean

## Environment

- **Database:** NeonDB (PostgreSQL 16 + pgvector)
- **Deployment:** DigitalOcean App Platform
- **API:** FastAPI + FastMCP
- **Auth:** OAuth + Bearer token

## Quick Start

See [DEPLOYMENT.md](DEPLOYMENT.md) for setup instructions.
EOF

# Commit cleanup
git add -A
git commit -m "chore: initialize production repository"

# Create main branch from current state
git checkout -b main
git branch -D feature/async-migration

# Push to new remote
git remote remove origin
git remote add origin https://github.com/banton/dementia-production.git
git push -u origin main
```

3. **Update DigitalOcean to deploy from new repo:**
```bash
# Get current app spec
doctl apps spec get 20c874aa-0ed2-44e3-a433-699f17d88a44 --format yaml > /tmp/app_spec.yaml

# Edit app_spec.yaml:
#   - Change repo: banton/claude-dementia → banton/dementia-production
#   - Change branch: feature/async-migration → main

# Apply updated spec
doctl apps update 20c874aa-0ed2-44e3-a433-699f17d88a44 --spec /tmp/app_spec_updated.yaml
```

4. **Test deployment:**
```bash
# Wait for deployment
doctl apps list-deployments 20c874aa-0ed2-44e3-a433-699f17d88a44

# Test health endpoint
curl https://dementia-mcp-7f4vf.ondigitalocean.app/health
```

**Validation:**
- [ ] New `dementia-production` repo exists (private)
- [ ] Main branch has production code
- [ ] DigitalOcean deploying from new repo
- [ ] Health check passing
- [ ] No OSS-specific files in production repo

---

### Phase 2: Reset OSS Repository (1 hour)

**Steps:**

1. **Backup current state:**
```bash
cd /Users/banton/Sites/claude-dementia
git branch backup-before-reset  # Safety backup
git push origin backup-before-reset
```

2. **Reset main to v3.0:**
```bash
# Checkout main
git checkout main

# Reset to v3.0 commit (ec9368e)
git reset --hard ec9368e

# Force push (destructive - make sure backup exists!)
git push origin main --force
```

3. **Clean up branches:**
```bash
# Delete production-specific branches (they're now in dementia-production)
git push origin --delete feature/async-migration
git push origin --delete feature/document-ingestion-async
git push origin --delete feature/cloud-hosted-mcp
git push origin --delete feature/cloud-api-integration
# (Keep OSS-related branches if any)

# Clean up local branches
git branch -D feature/async-migration
git branch -D feature/document-ingestion-async
git branch -D feature/document-ingestion
```

4. **Update README for OSS:**
```bash
cat > README.md << 'EOF'
# Claude Code Memory System v3.0

**Give Claude Code perfect memory across sessions. Install from GitHub in 30 seconds.**

## 🚀 Quick Start

```bash
git clone https://github.com/banton/claude-dementia /tmp/claude-memory
cp /tmp/claude-memory/CLAUDE.md ./ && cp -r /tmp/claude-memory/memory ./
chmod +x memory/*.sh && rm -rf /tmp/claude-memory
```

## 📚 Documentation

See [CLAUDE.md](CLAUDE.md) for complete usage guide.

## 🌐 Hosted Service

Looking for the managed API?
**→ [dementia.ai](https://dementia.ai)** (coming soon)

This repo is the OSS version for local/self-hosted use.

## 📝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

## 📄 License

MIT License - see [LICENSE](LICENSE)
EOF

git add README.md
git commit -m "docs: update README for OSS v3.0"
git push origin main
```

5. **Protect main branch:**
```bash
gh api repos/banton/claude-dementia/branches/main/protection \
  --method PUT \
  --field required_status_checks[strict]=true \
  --field required_pull_request_reviews[required_approving_review_count]=1 \
  --field enforce_admins=false \
  --field required_linear_history=true \
  --field allow_force_pushes=false
```

**Validation:**
- [ ] Main branch is at v3.0 (ec9368e)
- [ ] README explains OSS version
- [ ] Link to hosted service (when ready)
- [ ] Production branches deleted
- [ ] Branch protection enabled

---

### Phase 3: Update Pending PRs (30 min)

**Current State:**
- PR #2: `feature/document-ingestion-async` → `feature/async-migration` (in `claude-dementia`)

**Actions:**

1. **Close PR #2 in OSS repo:**
```bash
gh pr close 2 -c "Closing - this feature belongs in production repo (dementia-production)"
```

2. **Recreate PR in production repo:**
```bash
cd /tmp/dementia-production

# Fetch the document-ingestion branch
git remote add oss https://github.com/banton/claude-dementia.git
git fetch oss feature/document-ingestion-async
git checkout -b feature/document-ingestion FETCH_HEAD

# Push to production repo
git push origin feature/document-ingestion

# Create PR
gh pr create --base main \
  --title "feat(document-ingestion): Add S3 storage and VoyageAI document ingestion" \
  --body "See original PR in OSS repo (closed)"

# Merge after review
gh pr merge --squash --delete-branch
```

**Validation:**
- [ ] PR #2 closed in OSS repo
- [ ] New PR created in production repo
- [ ] Document ingestion merged to production
- [ ] Production deployed with new feature

---

### Phase 4: Repository Configuration (1 hour)

**Production Repo (`dementia-production`):**

1. **Settings:**
   - Visibility: Private
   - Default branch: `main`
   - Branch protection on `main`: Required PRs, status checks
   - Disable: Wiki, Projects, Discussions (use Linear instead)

2. **Secrets (GitHub Actions):**
   ```
   DATABASE_URL
   VOYAGEAI_API_KEY
   OPENROUTER_API_KEY
   S3_ACCESS_KEY_ID
   S3_SECRET_ACCESS_KEY
   DIGITALOCEAN_ACCESS_TOKEN
   ```

3. **Topics:**
   ```
   mcp, fastapi, postgresql, neon, production
   ```

4. **Description:**
   ```
   Production MCP server for persistent memory (private)
   ```

**OSS Repo (`claude-dementia`):**

1. **Settings:**
   - Visibility: Public
   - Default branch: `main`
   - Branch protection on `main`: Required PRs
   - Enable: Discussions, Wiki

2. **Topics:**
   ```
   claude-code, memory-system, oss, developer-tools
   ```

3. **Description:**
   ```
   Give Claude Code perfect memory across sessions (OSS)
   ```

4. **About:**
   - Website: `https://dementia.ai` (when ready)
   - Check: Issues, Discussions

**Validation:**
- [ ] Production repo configured (private)
- [ ] OSS repo configured (public)
- [ ] Branch protections enabled
- [ ] Topics set correctly
- [ ] Descriptions clear

---

### Phase 5: Documentation Updates (2 hours)

**Production Repo:**

1. **Create production docs:**
```bash
cd /tmp/dementia-production

# DEPLOYMENT.md
cat > DEPLOYMENT.md << 'EOF'
# Deployment Guide

## DigitalOcean App Platform

[Deployment instructions]
EOF

# API.md
cat > docs/API.md << 'EOF'
# API Documentation

[MCP tools, endpoints, authentication]
EOF

# ARCHITECTURE.md
cat > docs/ARCHITECTURE.md << 'EOF'
# System Architecture

[Database schema, services, async flow]
EOF

# Update CLAUDE.md for production development
# [Production-specific development guide]

git add -A
git commit -m "docs: add production documentation"
git push origin main
```

2. **Create CONTRIBUTING.md:**
```markdown
# Contributing to Dementia Production

This is the private production repository.

## Development Workflow

1. Create feature branch from `main`
2. Develop and test locally
3. Create PR to `main`
4. After review and CI passing, merge
5. Auto-deploys to DigitalOcean

## Testing

[Local testing setup with PostgreSQL]

## Code Style

[Python conventions, async patterns]
```

**OSS Repo:**

1. **Create OSS CONTRIBUTING.md:**
```markdown
# Contributing to Claude Code Memory System

This is the OSS version for local/self-hosted use.

## How to Contribute

1. Fork the repo
2. Create feature branch
3. Test your changes
4. Submit PR to `main`

## Guidelines

- Keep it simple (file-based memory)
- Avoid external dependencies
- Document in CLAUDE.md
```

2. **Update CLAUDE.md for OSS:**
```markdown
# Claude Memory System Guide

[OSS-specific instructions for v3.0]
```

**Validation:**
- [ ] Production docs complete (DEPLOYMENT, API, ARCHITECTURE)
- [ ] Production CONTRIBUTING.md
- [ ] OSS CONTRIBUTING.md
- [ ] OSS CLAUDE.md updated

---

## Code Sharing Strategy

### Option 1: No Sharing (Recommended)

**Approach:** Accept that OSS and production are different products.

**Pros:**
- Simple - no coordination needed
- Each repo evolves independently
- No shared code complexity

**Cons:**
- Some duplication if features overlap

**Recommendation:** Start with this. If significant code overlap emerges later, revisit.

---

### Option 2: Shared Library (Future)

**Approach:** Extract common logic to separate package.

**Example:**
```
dementia-core (PyPI package)
  ├── memory/          (Core memory logic)
  └── utils/           (Shared utilities)

claude-dementia (OSS)
  └── uses: dementia-core

dementia-production (Private)
  └── uses: dementia-core
```

**When to use:**
- If >30% code overlap emerges
- If OSS gains significant traction
- If multiple products share logic

**Recommendation:** Defer until needed.

---

## Migration Checklist

### Pre-Migration
- [ ] Backup current repository state
- [ ] Document current DigitalOcean deployment
- [ ] Export current environment variables
- [ ] Notify team of repository split

### Phase 1: Create Production Repo
- [ ] Create `dementia-production` private repo
- [ ] Push production code to new repo
- [ ] Clean up production-specific files
- [ ] Create production README
- [ ] Update DigitalOcean to deploy from new repo
- [ ] Test deployment from new repo
- [ ] Verify app health

### Phase 2: Reset OSS Repo
- [ ] Create backup branch in OSS repo
- [ ] Reset main to v3.0 (ec9368e)
- [ ] Update README for OSS
- [ ] Delete production branches
- [ ] Enable branch protection on main
- [ ] Clean up issues/PRs

### Phase 3: Update PRs
- [ ] Close PR #2 in OSS repo
- [ ] Recreate PR in production repo
- [ ] Merge document ingestion to production
- [ ] Delete feature branches in OSS

### Phase 4: Configure Repos
- [ ] Set production repo as private
- [ ] Configure branch protections (both repos)
- [ ] Add GitHub secrets (production)
- [ ] Set repository topics (both)
- [ ] Update descriptions (both)

### Phase 5: Documentation
- [ ] Create production DEPLOYMENT.md
- [ ] Create production API.md
- [ ] Create production ARCHITECTURE.md
- [ ] Update production CLAUDE.md
- [ ] Create CONTRIBUTING.md (both repos)
- [ ] Update OSS CLAUDE.md

### Post-Migration
- [ ] Test OSS installation workflow
- [ ] Test production deployment
- [ ] Update Linear tasks with new repo links
- [ ] Announce split to team
- [ ] Archive old branches

---

## Timeline

| Phase | Duration | Parallelizable? |
|-------|----------|-----------------|
| Phase 1: Create Production Repo | 1 hour | No |
| Phase 2: Reset OSS Repo | 1 hour | No (after Phase 1) |
| Phase 3: Update PRs | 30 min | Yes (after Phase 1) |
| Phase 4: Configure Repos | 1 hour | Yes (after Phase 1) |
| Phase 5: Documentation | 2 hours | Yes (after Phase 1) |

**Sequential:** 5.5 hours
**With Parallelization:** 3 hours

---

## Risks and Mitigation

### Risk 1: Breaking Production During Migration
**Mitigation:**
- Create backup branch before any changes
- Test new repo deployment before switching
- Keep old repo deployment until new one confirmed working
- Rollback procedure documented

### Risk 2: Losing Git History
**Mitigation:**
- Production repo gets full history from feature/async-migration
- OSS repo keeps full history (just resets main branch)
- Backup branch preserved in both repos
- Can always recover from backups

### Risk 3: Confusion About Which Repo
**Mitigation:**
- Clear descriptions on both repos
- README.md prominently explains difference
- Link between repos (OSS → hosted, production → OSS)
- Update Linear/docs with correct repo links

### Risk 4: Accidental Public Code in Production
**Mitigation:**
- Production repo is private
- GitHub secrets for sensitive configs
- Code review before merges
- Automated security scanning

---

## Post-Split Workflow

### Adding Feature to OSS
```bash
cd claude-dementia
git checkout -b feature/oss-better-compression
# ... develop ...
git push origin feature/oss-better-compression
gh pr create --base main
```

### Adding Feature to Production
```bash
cd dementia-production
git checkout -b feature/redis-caching
# ... develop ...
git push origin feature/redis-caching
gh pr create --base main
# After merge, auto-deploys to DO
```

### Porting OSS Feature to Production
```bash
# If an OSS improvement is useful for production
cd dementia-production
git remote add oss https://github.com/banton/claude-dementia.git
git fetch oss
git cherry-pick <commit-hash>
# Or manually port the code
```

---

## Recommended Next Steps

### Immediate (Today)
1. **Approve this approach** (vs dual-track branching)
2. **Create `dementia-production` private repo**
3. **Push production code** to new repo
4. **Test deployment** from new repo

### This Week
1. **Update DigitalOcean** to deploy from production repo
2. **Reset OSS repo** to v3.0
3. **Update PRs** (close in OSS, recreate in production)
4. **Configure repos** (settings, protections)

### Next Week
1. **Write documentation** (DEPLOYMENT, API, etc.)
2. **Update CLAUDE.md** in both repos
3. **Clean up branches** in OSS repo
4. **Announce split** to team/community

---

## Success Criteria

After migration:

✅ **Two Separate Repos:**
- `claude-dementia` (public) = OSS v3.0
- `dementia-production` (private) = Hosted v4.2+

✅ **Clear Ownership:**
- OSS: Community contributions, simple file-based system
- Production: Team-only, full MCP server, database-backed

✅ **Proper Workflows:**
- OSS: Fork → feature → PR → main
- Production: Feature → PR → main → auto-deploy

✅ **Security:**
- Production secrets in private repo
- No accidental leaks
- Proper access controls

✅ **Documentation:**
- Each repo has clear README
- CONTRIBUTING guides specific to each
- Cross-links between repos

---

## Comparison: Dual-Track vs Separate Repos

| Aspect | Dual-Track (Single Repo) | Separate Repos |
|--------|--------------------------|----------------|
| **Complexity** | Medium (two main branches) | Low (each repo simple) |
| **Security** | ⚠️ Production code public | ✅ Production private |
| **Confusion** | ⚠️ Which branch for what? | ✅ Clear repo = purpose |
| **Access Control** | ❌ Same for both | ✅ Different per repo |
| **Code Sharing** | ✅ Easy (same repo) | ⚠️ Needs coordination |
| **Community** | ⚠️ See production code | ✅ Clean OSS focus |
| **Maintenance** | ⚠️ Complex branch rules | ✅ Simple per repo |
| **Secrets** | ❌ Can't use GitHub secrets | ✅ Private repo secrets |

**Recommendation:** **Separate Repos** is cleaner for OSS + production split.

---

## Conclusion

Splitting into two repositories provides:

1. **True Separation:** OSS (public, simple) vs Production (private, full-featured)
2. **Better Security:** Production code/configs stay private
3. **Clearer Purpose:** Each repo has single, clear identity
4. **Simpler Workflow:** Each repo uses standard main → feature flow
5. **Community-Friendly:** OSS repo is clean, welcoming, focused

**Recommended Approach:** Proceed with repository split.

---

**Prepared by:** Claude Code
**Date:** November 23, 2025
**Status:** 📋 PROPOSED - Awaiting approval to create production repo
