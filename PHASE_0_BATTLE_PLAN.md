# PHASE 0 - Systematic Isolation Battle Plan

## Problem
Custom Connector cannot discover MCP tools, even though:
- `/tools` REST endpoint works (returns 31 tools)
- `/mcp` endpoint exists and responds
- Local Claude Desktop can discover tools

## Goal
Isolate the SINGULAR thing preventing Custom Connector from discovering tools by systematically removing components from the **working production server**.

## Strategy
Start with WORKING server (commit 278e2c5), remove components ONE AT A TIME, deploy and test after each change.

## Current Deployment
- Deployment ID: 4bfec050-3c31-44f4-afe6-321c85ad2ead
- Status: Deploying restored working server
- Base: commit 278e2c5 (GracefulShutdownMiddleware fix)

## Removal Sequence (in production, one at a time)

### PHASE 1: Remove Auth/OAuth (FIRST PRIORITY per user)
**Why:** User explicitly requested OAuth removal for testing
**What to remove:**
1. Comment out `BearerAuthMiddleware` in middleware stack
2. Keep OAuth routes (for connector to connect), but make them no-op
3. Deploy and test

**Expected outcome:** Tools should appear if auth was blocking discovery

### PHASE 2: Remove Session Middleware
**Why:** Session middleware might interfere with MCP initialize flow
**What to remove:**
1. Comment out `MCPSessionPersistenceMiddleware`
2. Comment out session store initialization
3. Deploy and test

**Expected outcome:** Tools should appear if session management was the issue

### PHASE 3: Remove Request Logging Middleware
**Why:** Correlation ID tracking might interfere
**What to remove:**
1. Comment out `RequestLoggingMiddleware`
2. Deploy and test

### PHASE 4: Remove Metrics Middleware
**Why:** Prometheus metrics might add overhead
**What to remove:**
1. Comment out `MetricsMiddleware`
2. Deploy and test

### PHASE 5: Remove CORS Headers
**Why:** CORS might block Custom Connector
**What to remove:**
1. Comment out CORS header addition in middleware
2. Deploy and test

### PHASE 6: Remove Custom Routes
**Why:** Additional routes might conflict
**What to remove:**
1. Comment out `/health`, `/tools`, `/execute`, `/metrics` routes
2. Keep only OAuth routes and `/mcp`
3. Deploy and test

### PHASE 7: Remove GracefulShutdownMiddleware
**Why:** This was added to fix crashes, might interfere
**What to remove:**
1. Comment out `GracefulShutdownMiddleware`
2. Deploy and test

## Test Procedure (after each deployment)
1. Wait for deployment to go ACTIVE
2. Check logs for "ULTRA-MINIMAL" or startup message
3. Test Custom Connector tool discovery
4. If tools appear: **STOP** - we found the culprit
5. If tools don't appear: continue to next phase

## Success Criteria
- Custom Connector shows tools in UI
- Can invoke at least one test tool
- Document EXACTLY which component was blocking discovery

## Rollback Plan
If we break production:
- Git revert to commit 278e2c5
- Deploy immediately
- Regroup and try different approach

## Key Insights
1. **The working server has all tools registered** - verified via /tools endpoint
2. **FastMCP's /mcp endpoint exists** - it's a Mount object
3. **Session middleware allows discovery methods** - tools/list, initialize
4. **The issue is NOT in claude_mcp_hybrid_sessions.py** - those tools work locally

## Next Steps
1. Wait for current deployment (4bfec050) to complete
2. Verify it's working (tools should NOT appear yet)
3. Start PHASE 1: Remove Auth
