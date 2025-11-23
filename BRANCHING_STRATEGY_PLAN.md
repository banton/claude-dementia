# GitHub Branching Strategy for OSS + Hosted Solution

**Date:** November 23, 2025
**Status:** 📋 PROPOSED
**Repository:** `banton/claude-dementia` (public)

---

## Executive Summary

**Problem:** Current repository mixes OSS (open source) and hosted/managed solution code, causing confusion about which branch is the "source of truth" for deployments.

**Solution:** Implement dual-track branching strategy:
- **OSS Track:** `main` branch (locked, public-facing)
- **Hosted Track:** `production` branch (deployment target, managed solution)

This enables:
- Clean separation of OSS vs hosted code
- Proper PR workflow for hosted solution
- Automated DO deployments
- Community contributions to OSS without affecting production

---

## Current State Analysis

### Repository Status
```yaml
default_branch: main
visibility: public (OSS)
branch_protection: none
github_actions: none
deployed_branch: feature/async-migration (on DigitalOcean)
```

### Branch Inventory
**OSS Branches:**
- `main` - OSS v3.0 (GitHub installation workflow)
- `release/v4.0.0-rc1` - OSS release candidate

**Hosted Solution Branches:**
- `feature/async-migration` ← **Currently deployed to DO**
- `feature/document-ingestion-async` ← PR #2 (awaiting merge)
- `feature/cloud-hosted-mcp`
- `feature/cloud-api-integration`

### Deployment Configuration
```yaml
# DigitalOcean App: dementia-mcp-7f4vf
github:
  branch: feature/async-migration  # ← Should be production branch
  deploy_on_push: true
  repo: banton/claude-dementia
```

**Issues:**
1. Deploying from feature branch (not sustainable)
2. No clear "production" branch
3. No branch protection (anyone can force-push)
4. OSS `main` is outdated vs production code
5. No CI/CD automation

---

## Proposed Branching Strategy

### Dual-Track Model

```
┌─────────────────────────────────────────────────────────┐
│                    OSS TRACK (Public)                    │
│                                                          │
│  main (OSS)                                             │
│    ↑                                                     │
│    │ Community PRs                                      │
│    │                                                     │
│  feature/oss-*                                          │
│                                                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                 HOSTED TRACK (Managed)                   │
│                                                          │
│  production (Hosted) ← DigitalOcean Deploy              │
│    ↑                                                     │
│    │ Team PRs                                           │
│    │                                                     │
│  staging (Optional)                                      │
│    ↑                                                     │
│    │                                                     │
│  feature/*                                               │
│  fix/*                                                   │
│  test/*                                                  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Branch Definitions

#### **`main` (OSS Track)**
- **Purpose:** Open source version, community-facing
- **Protection:** Protected, requires PR + review
- **Deployment:** None (users clone/fork for local use)
- **Merge From:** `feature/oss-*` branches only
- **Version:** Independent OSS versioning (v3.0, v4.0, etc.)
- **README:** Installation instructions for local/self-hosted use

#### **`production` (Hosted Track)**
- **Purpose:** Managed/hosted solution (production)
- **Protection:** Protected, requires PR + review + CI passing
- **Deployment:** Auto-deploy to DigitalOcean on push
- **Merge From:** `staging` (if used) or `feature/*` branches
- **Version:** Hosted service versioning (v4.2.0, v4.3.0, etc.)
- **README:** API documentation, hosted service info

#### **`staging` (Optional)**
- **Purpose:** Pre-production testing environment
- **Protection:** Protected, requires PR
- **Deployment:** Auto-deploy to DO staging app
- **Merge From:** `feature/*` branches
- **Merge To:** `production` (after validation)

#### **`feature/*` (Hosted Track)**
- **Purpose:** New features for hosted solution
- **Examples:** `feature/document-ingestion-async`, `feature/redis-caching`
- **Protection:** None
- **Merge To:** `staging` or `production` (via PR)
- **Lifetime:** Delete after merge

#### **`feature/oss-*` (OSS Track)**
- **Purpose:** New features for OSS version
- **Examples:** `feature/oss-local-sqlite`, `feature/oss-cli-improvements`
- **Protection:** None
- **Merge To:** `main` (via PR)
- **Lifetime:** Delete after merge

---

## Implementation Plan

### Phase 1: Create Production Branch (Immediate)

**Steps:**
```bash
# 1. Checkout current deployed branch
git checkout feature/async-migration
git pull origin feature/async-migration

# 2. Create production branch from it
git checkout -b production
git push origin production

# 3. Update DigitalOcean app to deploy from production
doctl apps spec get 20c874aa-0ed2-44e3-a433-699f17d88a44 --format yaml > /tmp/app_spec.yaml
# Edit: change branch from feature/async-migration to production
doctl apps update 20c874aa-0ed2-44e3-a433-699f17d88a44 --spec /tmp/app_spec_updated.yaml

# 4. Set production as protected branch on GitHub
gh api repos/banton/claude-dementia/branches/production/protection \
  --method PUT \
  --field required_status_checks[strict]=true \
  --field required_pull_request_reviews[required_approving_review_count]=1 \
  --field enforce_admins=true \
  --field required_linear_history=true
```

**Timeline:** 1 hour

**Validation:**
- [ ] Production branch exists on GitHub
- [ ] DO app deploying from production branch
- [ ] Branch protection enabled
- [ ] Test PR workflow: feature → production

---

### Phase 2: Protect Main Branch (Immediate)

**Steps:**
```bash
# 1. Enable branch protection on main
gh api repos/banton/claude-dementia/branches/main/protection \
  --method PUT \
  --field required_status_checks[strict]=true \
  --field required_pull_request_reviews[required_approving_review_count]=1 \
  --field enforce_admins=false \  # Allow maintainer to push
  --field required_linear_history=true

# 2. Add protection for force-push
gh api repos/banton/claude-dementia/branches/main/protection \
  --method PUT \
  --field restrictions=null \  # No specific users/teams
  --field allow_force_pushes=false \
  --field allow_deletions=false
```

**Timeline:** 30 minutes

**Validation:**
- [ ] Main branch protected
- [ ] Cannot force-push to main
- [ ] PRs required for merges

---

### Phase 3: Update Repository Settings (Immediate)

**Steps:**
```bash
# 1. Change default branch to production (for hosted development)
gh api repos/banton/claude-dementia \
  --method PATCH \
  --field default_branch=production

# 2. Add branch protection to production
# (Same as Phase 1 step 4)

# 3. Update README.md on production branch
# - Add deployment status badge
# - Link to hosted API docs
# - Differentiate from OSS README

# 4. Update README.md on main branch
# - Keep OSS installation instructions
# - Add link to hosted service
# - Add "This is the OSS version" notice
```

**Timeline:** 1 hour

**Validation:**
- [ ] Default branch is production
- [ ] README.md differentiated on each branch
- [ ] Clear documentation of branch purposes

---

### Phase 4: Merge Pending PRs (Next)

**Current PR:**
- PR #2: `feature/document-ingestion-async` → `feature/async-migration`

**Actions:**
1. Update PR #2 base branch from `feature/async-migration` → `production`
2. Review and merge PR #2
3. Verify DO deployment from production branch
4. Delete `feature/async-migration` branch (now superseded by production)

**Steps:**
```bash
# 1. Update PR base branch
gh pr edit 2 --base production

# 2. After review, merge
gh pr merge 2 --squash --delete-branch

# 3. Verify deployment
doctl apps list-deployments 20c874aa-0ed2-44e3-a433-699f17d88a44

# 4. Clean up old feature branch
git push origin --delete feature/async-migration
```

**Timeline:** 1 hour (including review)

---

### Phase 5: Set Up GitHub Actions (Recommended)

**CI/CD Pipeline for `production` branch:**

**.github/workflows/production-ci.yml**
```yaml
name: Production CI/CD

on:
  pull_request:
    branches: [production]
  push:
    branches: [production]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov

      - name: Run tests
        run: |
          pytest tests/ -v --cov=. --cov-report=term-missing

      - name: Lint code
        run: |
          pip install flake8 black
          flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
          black --check .

  deploy:
    needs: test
    if: github.ref == 'refs/heads/production' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - name: Trigger DigitalOcean Deploy
        run: echo "DO auto-deploys on push to production"
```

**CI Pipeline for `main` branch:**

**.github/workflows/oss-ci.yml**
```yaml
name: OSS CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest

      - name: Run OSS tests
        run: |
          pytest tests/unit/ -v
```

**Timeline:** 2-3 hours

**Validation:**
- [ ] GitHub Actions running on PRs
- [ ] Tests passing before merge
- [ ] Automated deployment notification

---

### Phase 6: Create Staging Environment (Optional)

**Benefits:**
- Test features before production
- Catch issues early
- Parallel development (staging + production)

**Steps:**
1. Create `staging` branch from `production`
2. Create new DigitalOcean app for staging
3. Configure auto-deploy: staging branch → DO staging app
4. Update workflow: feature → staging → production

**Timeline:** 4 hours

**Cost:** ~$12/month for additional DO app

**Decision:** Recommend only if team size > 2 or deployment frequency > 5/week

---

## Workflow Examples

### Adding Feature to Hosted Solution

```bash
# 1. Create feature branch from production
git checkout production
git pull origin production
git checkout -b feature/redis-caching

# 2. Develop feature
# ... make changes ...

# 3. Commit and push
git add .
git commit -m "feat(cache): implement Redis caching layer"
git push origin feature/redis-caching

# 4. Create PR
gh pr create --base production --title "feat(cache): Implement Redis caching layer"

# 5. After CI passes and review approved, merge
gh pr merge --squash --delete-branch

# 6. Production auto-deploys to DO
```

### Adding Feature to OSS Version

```bash
# 1. Create feature branch from main
git checkout main
git pull origin main
git checkout -b feature/oss-improved-cli

# 2. Develop feature
# ... make changes ...

# 3. Commit and push
git add .
git commit -m "feat(cli): improve CLI error messages"
git push origin feature/oss-improved-cli

# 4. Create PR
gh pr create --base main --title "feat(cli): Improve CLI error messages"

# 5. After review, merge
gh pr merge --squash --delete-branch
```

### Hotfix to Production

```bash
# 1. Create fix branch from production
git checkout production
git pull origin production
git checkout -b fix/session-leak

# 2. Fix issue
# ... make changes ...

# 3. Commit and push
git add .
git commit -m "fix(session): prevent session ID leak in logs"
git push origin fix/session-leak

# 4. Create PR with urgency label
gh pr create --base production --title "fix(session): Prevent session ID leak" --label "urgent"

# 5. Fast-track review and merge
gh pr merge --squash --delete-branch
```

---

## Branch Protection Rules

### `production` Branch
```yaml
protection:
  required_status_checks:
    strict: true
    contexts:
      - "test (production-ci)"
  required_pull_request_reviews:
    required_approving_review_count: 1
    dismiss_stale_reviews: true
    require_code_owner_reviews: false
  enforce_admins: true
  required_linear_history: true
  allow_force_pushes: false
  allow_deletions: false
```

### `main` Branch
```yaml
protection:
  required_status_checks:
    strict: true
    contexts:
      - "test (oss-ci)"
  required_pull_request_reviews:
    required_approving_review_count: 1
    dismiss_stale_reviews: true
  enforce_admins: false  # Allow maintainer to manage releases
  required_linear_history: true
  allow_force_pushes: false
  allow_deletions: false
```

---

## DigitalOcean Configuration Updates

### Current Configuration
```yaml
# dementia-mcp-7f4vf
github:
  branch: feature/async-migration  # ← NEEDS UPDATE
  deploy_on_push: true
  repo: banton/claude-dementia
```

### Proposed Configuration
```yaml
# dementia-mcp-7f4vf (Production)
github:
  branch: production  # ← UPDATED
  deploy_on_push: true
  repo: banton/claude-dementia
environment:
  - key: DEPLOYMENT_ENV
    value: "production"
```

### Optional: Staging App
```yaml
# dementia-mcp-staging (New)
github:
  branch: staging
  deploy_on_push: true
  repo: banton/claude-dementia
environment:
  - key: DEPLOYMENT_ENV
    value: "staging"
```

---

## Migration Checklist

### Pre-Migration
- [ ] Backup current DigitalOcean configuration
- [ ] Document current deployed commit SHA
- [ ] Notify team of branching strategy change
- [ ] Review all open PRs and update base branches

### Phase 1: Create Production Branch
- [ ] Create production branch from feature/async-migration
- [ ] Push production branch to GitHub
- [ ] Update DO app to deploy from production
- [ ] Enable branch protection on production
- [ ] Test deployment from production branch
- [ ] Verify app health after deployment

### Phase 2: Protect Main Branch
- [ ] Enable branch protection on main
- [ ] Test PR workflow to main
- [ ] Update CONTRIBUTING.md with OSS contribution guidelines

### Phase 3: Update Repository Settings
- [ ] Change default branch to production
- [ ] Update README.md on production (hosted docs)
- [ ] Update README.md on main (OSS docs)
- [ ] Add branch badges to README files
- [ ] Update CLAUDE.md with new branching strategy

### Phase 4: Merge Pending PRs
- [ ] Update PR #2 base to production
- [ ] Review and merge PR #2
- [ ] Verify deployment after merge
- [ ] Delete feature/async-migration branch
- [ ] Delete feature/document-ingestion-async branch (after merge)

### Phase 5: Set Up CI/CD (Optional)
- [ ] Create .github/workflows/production-ci.yml
- [ ] Create .github/workflows/oss-ci.yml
- [ ] Test GitHub Actions on test PR
- [ ] Configure required status checks in branch protection

### Phase 6: Communication
- [ ] Update repository description
- [ ] Pin README explaining dual tracks
- [ ] Update GitHub topics/tags
- [ ] Announce branching strategy to team

---

## Timeline Summary

| Phase | Duration | Can Parallelize? |
|-------|----------|------------------|
| Phase 1: Create Production Branch | 1 hour | No (prerequisite for others) |
| Phase 2: Protect Main Branch | 30 min | Yes (after Phase 1) |
| Phase 3: Update Repository Settings | 1 hour | Yes (after Phase 1) |
| Phase 4: Merge Pending PRs | 1 hour | Yes (after Phase 1) |
| Phase 5: Set Up GitHub Actions | 2-3 hours | Yes (after Phase 1) |
| Phase 6: Create Staging Env (Optional) | 4 hours | Yes (after Phase 1) |

**Minimum Time (Sequential):** 3.5 hours
**With Parallelization:** 2 hours
**With GitHub Actions:** 4-5 hours
**With Staging:** 6-9 hours

---

## Risks and Mitigation

### Risk 1: Breaking Production During Migration
**Mitigation:**
- Create production branch before updating DO configuration
- Test production branch deploy before switching
- Keep feature/async-migration as backup until confirmed working
- Document rollback procedure

### Risk 2: Confusion About Which Branch to Use
**Mitigation:**
- Clear documentation in README on both branches
- Update CLAUDE.md with branching strategy
- Pin issue explaining dual tracks
- Use branch descriptions on GitHub

### Risk 3: Accidental Commits to Wrong Branch
**Mitigation:**
- Set production as default branch (hosted development)
- Branch protection prevents direct pushes
- PR reviews catch mistakes
- Clear commit message conventions

### Risk 4: OSS `main` Becoming Outdated
**Mitigation:**
- Periodic syncs from production → main (for portable features)
- Maintain separate roadmap for OSS vs hosted
- Active community engagement on main branch
- Tag releases on both branches

---

## Recommended Next Steps

### Immediate (Today)
1. **Create production branch** from feature/async-migration
2. **Update PR #2** base to production (instead of feature/async-migration)
3. **Protect production branch** (enable branch protection)
4. **Update DigitalOcean** app to deploy from production

### This Week
1. **Merge PR #2** (document ingestion)
2. **Test deployment** from production branch
3. **Protect main branch**
4. **Update README files** on both branches

### Next Week
1. **Set up GitHub Actions** CI/CD
2. **Clean up old feature branches**
3. **Update CLAUDE.md** with new workflow
4. **Create CONTRIBUTING.md** for OSS vs hosted

### Optional (Next Month)
1. **Create staging environment** (if needed)
2. **Implement automated tests** in CI
3. **Set up deployment notifications**
4. **Create branch strategy documentation**

---

## Success Criteria

After implementation, you should have:

✅ **Clear Separation:**
- `main` = OSS version (public, community)
- `production` = Hosted version (managed, deployed)

✅ **Proper Workflow:**
- All changes via PRs
- Branch protection prevents accidents
- CI tests before merge (if Actions enabled)
- Auto-deploy to DO on production push

✅ **Documentation:**
- README explains dual tracks
- CLAUDE.md has updated workflow
- CONTRIBUTING.md for each track
- Clear branch descriptions

✅ **Deployment:**
- DigitalOcean deploys from production
- Auto-deploy on push
- No manual intervention needed
- Rollback capability

---

## Conclusion

This dual-track branching strategy provides:

1. **OSS Independence:** Community can contribute to `main` without affecting production
2. **Production Stability:** Protected `production` branch with PR workflow
3. **Development Velocity:** Feature branches → PR → auto-deploy
4. **Clear Ownership:** Each branch has single purpose
5. **Scalability:** Can add staging, testing branches as needed

**Recommended Approach:** Start with Phases 1-4 (minimum viable branching), then add GitHub Actions and staging as team/deployment frequency grows.

---

**Prepared by:** Claude Code
**Date:** November 23, 2025
**Status:** 📋 PROPOSED - Awaiting approval to proceed with Phase 1
