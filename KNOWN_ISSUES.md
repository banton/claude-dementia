# Known Issues - Custom Connector (NOT Production Ready)

## Current Status: BARELY WORKING

We have a **hacky workaround** that allows Custom Connector to discover tools, but multiple critical issues remain.

## Critical Issues

### 1. ❌ Bearer Auth Completely Disabled
**Problem:** BearerAuthMiddleware is commented out
**Impact:** MCP endpoints are completely unauthenticated
**Risk:** Anyone can access the server without credentials
**Root Cause:** Custom Connector doesn't send Bearer token in MCP requests

```python
# app.add_middleware(BearerAuthMiddleware)  # Auth disabled for Custom Connector
```

### 2. ❌ OAuth Codes in Memory (Will Break on Restart)
**Problem:** Authorization codes stored in Python dict, not PostgreSQL
**Impact:** If server restarts between OAuth authorize and token exchange, code is lost
**Current Hack:** Accept ANY authorization code (insecure testing mode)

```python
# TESTING MODE: Accept authorization code even if not in memory
# (handles server restarts between authorize and token exchange)
# In production, store codes in PostgreSQL
```

### 3. ❌ Project Creation Fails
**Problem:** `create_project` tool throwing errors
**Evidence from test:**
```
Let me try creating the project first:
[Error creating project]
```
**Workaround:** Used existing "default" project instead

### 4. ❌ Project Switching Issues
**Problem:** Switched to "default" but context went to "workspace"
**Evidence:**
```
Step 2 Modified: Successfully switched to the "default" project
Step 3 Complete: Context locked (though it went to 'workspace' project instead of 'default')
```
**Impact:** Project isolation may be broken

### 5. ❌ Session Management Unclear
**Problem:** Session selection/creation errors during testing
**Evidence:** Multiple attempts to create/switch projects failed
**Impact:** Multi-project workflow may not work correctly

## What IS Working

✅ OAuth connection completes (with hacks)
✅ Tools appear in Custom Connector menu
✅ Basic tool execution works (lock_context, recall_context, dashboard)
✅ Database queries execute successfully
✅ 31 tools discovered by Custom Connector

## What Needs to be Fixed for Production

### Priority 1: Security
- [ ] Store OAuth codes in PostgreSQL (not memory)
- [ ] Fix Custom Connector to send Bearer tokens OR implement alternative auth
- [ ] Re-enable proper authentication on MCP endpoints

### Priority 2: Core Functionality
- [ ] Fix project creation (`create_project` tool)
- [ ] Fix project switching/routing (default → workspace issue)
- [ ] Fix session management for multi-project workflows
- [ ] Test all 31 tools to ensure they work via Custom Connector

### Priority 3: Testing
- [ ] Test tool execution with multiple projects
- [ ] Test session persistence across restarts
- [ ] Test OAuth flow across server deployments
- [ ] Verify project isolation works correctly

## Timeline to Production

**Current State:** Hacky demo (works for testing, NOT secure)
**Estimated Work:** 2-3 days of fixing core issues
**Blocker:** Custom Connector not sending Bearer tokens needs investigation

## Immediate Next Steps

1. Investigate WHY Custom Connector doesn't send Bearer token
2. Test project creation/switching issues locally
3. Implement PostgreSQL-backed OAuth code storage
4. Consider alternative auth mechanisms compatible with Custom Connector

## Testing Notes

**What was tested:**
- ✅ Tool discovery
- ✅ lock_context (basic)
- ✅ recall_context (basic)
- ✅ context_dashboard (basic)
- ✅ list_projects (works)
- ❌ create_project (FAILED)
- ❌ switch_project (BUGGY - wrong project)

**What was NOT tested:**
- All other 26 tools
- Multi-project workflows
- Session handovers
- Semantic search
- Database migrations
- File operations
- Workspace tables
- And more...

## Bottom Line

**This is a proof-of-concept hack, not a production deployment.**

We proved Custom Connector CAN work with dementia, but significant work remains to make it secure, reliable, and fully functional.
