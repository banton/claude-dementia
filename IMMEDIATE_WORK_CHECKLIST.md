# Immediate Work Checklist - Next 2-3 Days

## Goal: Make Custom Connector stable enough for 3-week testing period

---

## Day 1: Fix Critical Bugs

### Morning: Project Management
- [ ] Debug `create_project` failure
  - Add debug logging to tool
  - Test locally with Claude Desktop
  - Test via Custom Connector
  - Fix and verify

- [ ] Debug project switching (default → workspace bug)
  - Add logging to session state changes
  - Trace project routing in middleware
  - Fix routing logic
  - Test multi-project workflow

### Afternoon: OAuth Persistence
- [ ] Create PostgreSQL table for OAuth codes
  ```sql
  CREATE TABLE oauth_authorization_codes (
    code TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    code_challenge TEXT NOT NULL,
    code_challenge_method TEXT NOT NULL,
    scope TEXT,
    user_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
  );
  ```

- [ ] Migrate `oauth_mock.py` to use PostgreSQL
  - Replace dict with database queries
  - Add cleanup job for expired codes
  - Test across server restarts

---

## Day 2: Test All Tools + Core Logging

### Morning: Comprehensive Tool Testing
- [ ] Create test script for all 31 tools
- [ ] Test each tool via Custom Connector
- [ ] Document failures in spreadsheet
- [ ] Fix critical tool failures (top 10 most used)

### Afternoon: Implement Core Logging
- [ ] **Layer 1:** Enhance request/response logging
  - Add `tool_name` field
  - Add `project` field
  - Add `error_type` classification

- [ ] **Layer 2:** Add database operation logging
  - Modify `postgres_adapter.py`
  - Log all queries with timing
  - Track connection pool stats

- [ ] **Layer 3:** Add tool execution logging
  - Create decorator for tools
  - Track execution time
  - Track database calls per tool

---

## Day 3: Deploy + 24hr Soak Test

### Morning: Deploy to Production
- [ ] Commit all fixes
- [ ] Deploy to DigitalOcean
- [ ] Verify deployment active
- [ ] Test Custom Connector connection
- [ ] Run smoke test (5 key tools)

### Afternoon: Monitor + Document
- [ ] Watch logs for errors (first 2 hours)
- [ ] Create monitoring dashboard
- [ ] Document known issues
- [ ] Create testing guide for 3-week period

### Evening: 24-Hour Soak Test
- [ ] Run automated test script (loops tools)
- [ ] Monitor for crashes
- [ ] Check memory leaks
- [ ] Review error patterns

---

## Quick Wins (If Time Permits)

- [ ] Add health check endpoint: `GET /health/detailed`
  ```json
  {
    "status": "healthy",
    "database": "connected",
    "oauth": "ready",
    "sessions": 5,
    "uptime_seconds": 3600
  }
  ```

- [ ] Add session cleanup job (runs hourly)
  - Delete sessions inactive >24hrs
  - Clean up orphaned data

- [ ] Add error dashboard endpoint: `GET /errors/summary`
  - Show error frequency by type
  - Last 24 hours

---

## Testing Checklist (Before Starting 3-Week Period)

### Functionality
- [ ] All 31 tools tested and working (or documented as broken)
- [ ] Project creation works
- [ ] Project switching works
- [ ] OAuth survives server restart
- [ ] Sessions persist across requests
- [ ] Multi-project isolation verified

### Logging
- [ ] Request/response logs include all fields
- [ ] Database operation logs working
- [ ] Tool execution logs working
- [ ] Can correlate logs across layers
- [ ] Error logs include stack traces

### Monitoring
- [ ] Prometheus metrics exposed
- [ ] Key metrics identified
- [ ] Baseline metrics captured
- [ ] Alert thresholds defined

### Documentation
- [ ] Known issues documented
- [ ] Testing guide created
- [ ] Daily review process defined
- [ ] Escalation process defined

---

## Success Criteria for Day 3

✅ Project creation works via Custom Connector
✅ Project switching routes correctly
✅ OAuth codes survive server restart
✅ At least 25/31 tools working
✅ Core logging (Layers 1-3) implemented
✅ 24-hour soak test shows no crashes
✅ Ready to start 3-week testing period

---

## If Something Goes Wrong

**Rollback Plan:**
1. `git revert` to last known good commit
2. Deploy immediately
3. Document what broke
4. Fix in local environment first
5. Test thoroughly before redeploying

**Emergency Contacts:**
- GitHub Issues: https://github.com/banton/claude-dementia/issues
- Logs: `doctl apps logs 20c874aa-0ed2-44e3-a433-699f17d88a44 --type run --tail 200`

---

**Current Status:** Day 0 - Custom Connector barely working
**Target Status:** Day 3 - Stable enough for real-world testing
**Timeline:** 2-3 days of focused work
