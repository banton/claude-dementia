# DigitalOcean Deployment Update Required

**Status:** ⚠️ BLOCKED - Manual Action Required
**Priority:** 🔴 CRITICAL (Deployment will fail until resolved)
**Date:** November 23, 2025

## Issue

DigitalOcean App Platform cannot access the new private `dementia-production` repository.

**Error:**
```
Error: GitHub user does not have access to banton/dementia-production
```

## Root Cause

The `dementia-production` repository is **private**, and DigitalOcean's GitHub integration has not been granted access yet.

The current deployment configuration has been prepared but cannot be applied until GitHub access is granted.

## Required Actions

### Option 1: Grant Access via DigitalOcean UI (Recommended)

1. **Go to DigitalOcean App Platform:**
   - https://cloud.digitalocean.com/apps/20c874aa-0ed2-44e3-a433-699f17d88a44

2. **Navigate to Settings → Source:**
   - Click "Edit Source"

3. **Reconnect GitHub:**
   - Click "Reconnect" or "Authorize GitHub"
   - In the GitHub authorization screen, ensure `dementia-production` is selected
   - If not visible, click "Configure" next to DigitalOcean
   - Grant repository access to `banton/dementia-production`

4. **Update Repository and Branch:**
   - Repository: `banton/dementia-production`
   - Branch: `main`
   - Click "Save"

5. **Trigger Deployment:**
   - DigitalOcean should automatically deploy from the new repository
   - Monitor logs for successful deployment

### Option 2: Grant Access via GitHub UI

1. **Go to GitHub App Settings:**
   - https://github.com/settings/installations
   - Find "DigitalOcean" in the list
   - Click "Configure"

2. **Grant Repository Access:**
   - Under "Repository access"
   - Select "Only select repositories"
   - Add `banton/dementia-production` to the list
   - Click "Save"

3. **Update App via doctl (CLI):**
   ```bash
   # The spec is already prepared at /tmp/app-spec.yaml
   APP_ID="20c874aa-0ed2-44e3-a433-699f17d88a44"
   doctl apps update $APP_ID --spec /tmp/app-spec.yaml
   ```

## Prepared Configuration

The app spec has been prepared with the following changes:

**Before:**
```yaml
github:
  repo: banton/claude-dementia
  branch: feature/async-migration
  deploy_on_push: true
```

**After:**
```yaml
github:
  repo: banton/dementia-production
  branch: main
  deploy_on_push: true
```

**File:** `/tmp/app-spec.yaml` (ready to apply after GitHub access is granted)

## Verification Steps

After granting access and updating the app:

1. **Check Deployment Status:**
   ```bash
   APP_ID="20c874aa-0ed2-44e3-a433-699f17d88a44"
   doctl apps list-deployments $APP_ID --format ID,Phase,Progress
   ```

2. **Monitor Build Logs:**
   ```bash
   doctl apps logs $APP_ID --type build --tail 100
   ```

3. **Check Runtime Logs:**
   ```bash
   doctl apps logs $APP_ID --type run --tail 100
   ```

4. **Test Health Endpoint:**
   ```bash
   curl https://dementia-mcp-7f4vf.ondigitalocean.app/health
   ```

## Why This Happened

During the repository split:
- Created new private repository `dementia-production`
- GitHub apps (including DigitalOcean) don't automatically get access to new private repos
- Manual authorization required for security reasons
- This is expected behavior for private repositories

## Impact

**Current State:**
- ✅ Production code migrated to `dementia-production`
- ✅ OSS code reset to v3.0 in `claude-dementia`
- ✅ PR migrated to production repo
- ⚠️ DigitalOcean still deploying from old repo/branch (will fail on next deployment)

**After Fix:**
- ✅ DigitalOcean deploys from `dementia-production:main`
- ✅ Automatic deployments on push to main
- ✅ Production deployment fully operational

## Timeline

**Urgency:** High
- Current deployment continues to work (until next push)
- No immediate outage
- But must be fixed before next deployment

**Estimated Time:** 5-10 minutes
- Grant GitHub access: 2-3 minutes
- Apply updated spec: 1 minute
- Verify deployment: 2-5 minutes

## Checklist

- [ ] Grant DigitalOcean access to `dementia-production` repository
- [ ] Verify access granted (check GitHub settings)
- [ ] Apply updated app spec: `doctl apps update $APP_ID --spec /tmp/app-spec.yaml`
- [ ] Trigger deployment (should happen automatically)
- [ ] Monitor deployment logs
- [ ] Verify health endpoint responds
- [ ] Test MCP tools work correctly
- [ ] Document completion

## Related Documentation

- **Repository Split Report:** REPOSITORY_SPLIT_COMPLETED.md
- **Migration Notice:** PRODUCTION_MIGRATION.md
- **App Spec:** /tmp/app-spec.yaml (prepared, awaiting GitHub access)

## Support

If issues persist:
1. Check GitHub app permissions: https://github.com/settings/installations
2. Check DigitalOcean app logs: `doctl apps logs $APP_ID`
3. Verify repository exists and is private: https://github.com/banton/dementia-production
4. Contact DigitalOcean support if authorization issues continue

---

**Next Step:** Grant DigitalOcean access to `dementia-production` repository via GitHub settings or DigitalOcean UI.

**Status:** Waiting for manual GitHub authorization before deployment can proceed.
