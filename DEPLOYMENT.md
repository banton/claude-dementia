# Cloud Deployment Guide - DigitalOcean App Platform

## Overview

This guide covers deploying Dementia MCP to DigitalOcean App Platform for remote access from Claude Desktop, mobile, and other MCP clients.

**Time to deploy**: ~15 minutes
**Monthly cost**: $5-10 (basic tier)

---

## Prerequisites

1. ✅ DigitalOcean account ([sign up](https://cloud.digitalocean.com/registrations/new))
2. ✅ Neon PostgreSQL database (already configured)
3. ✅ GitHub repository with this code
4. ✅ API key generated (see below)

---

## Step 1: Generate API Key

Generate a secure random API key for authentication:

```bash
# macOS/Linux
openssl rand -hex 32

# Or Python
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Save this key securely** - you'll need it for both DigitalOcean and Claude Desktop configuration.

---

## Step 2: Test Locally First

Before deploying, validate the server works locally:

```bash
# Set environment variables
export DATABASE_URL="your_neon_postgres_url"
export DEMENTIA_API_KEY="your_generated_key"

# Install dependencies
pip install -r requirements.txt

# Start server (Terminal 1)
python3 server_hosted.py

# Run tests (Terminal 2)
python3 test_hosted_api.py
```

Expected output:
```
✅ ALL TESTS PASSED
Server is ready for deployment!
```

**If tests fail, DO NOT deploy.** Fix issues locally first.

---

## Step 3: Deploy to DigitalOcean

### Option A: Deploy via Dashboard (Recommended)

1. **Go to Apps**: https://cloud.digitalocean.com/apps
2. **Click "Create App"**
3. **Connect GitHub**:
   - Select your repository
   - Branch: `main` (or your deployment branch)
   - Auto-deploy: ✅ Enabled

4. **Configure App**:
   - **Name**: `dementia-mcp` (or your preferred name)
   - **Region**: Choose closest to you (e.g., `NYC`, `SFO`, `AMS`)
   - **Plan**: Basic ($5/month) is sufficient for testing

5. **Edit Build & Run Settings**:
   - **Build Command**: (leave default)
   - **Run Command**: `uvicorn server_hosted:app --host 0.0.0.0 --port 8080`
   - **HTTP Port**: `8080`
   - **Health Check**: `/health`

6. **Add Environment Variables**:
   Click "Edit" next to environment variables and add:

   | Key | Value | Encrypt? |
   |-----|-------|----------|
   | `DATABASE_URL` | Your Neon PostgreSQL URL | ✅ Yes |
   | `DEMENTIA_API_KEY` | Your generated API key | ✅ Yes |
   | `ENVIRONMENT` | `production` | ❌ No |
   | `LOG_LEVEL` | `INFO` | ❌ No |

7. **Review & Create**:
   - Review settings
   - Click "Create Resources"
   - Wait 5-10 minutes for first deployment

8. **Get Your URL**:
   - After deployment completes, copy the URL
   - Format: `https://dementia-mcp-xxxxx.ondigitalocean.app`

### Option B: Deploy via CLI (Advanced)

```bash
# Install doctl CLI
brew install doctl  # macOS
# or: https://docs.digitalocean.com/reference/doctl/how-to/install/

# Authenticate
doctl auth init

# Create app from spec
doctl apps create --spec .do/app.yaml

# Update environment variables
doctl apps update <app-id> --env DATABASE_URL=<value>
```

---

## Step 4: Verify Deployment

Test your deployed server:

```bash
# Health check (no auth required)
curl https://your-app-url.ondigitalocean.app/health

# Expected: {"status":"healthy","version":"4.2.0",...}

# List tools (requires auth)
curl -H "Authorization: Bearer YOUR_API_KEY" \
     https://your-app-url.ondigitalocean.app/tools

# Execute tool
curl -X POST \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"tool":"wake_up","arguments":{}}' \
     https://your-app-url.ondigitalocean.app/execute
```

---

## Step 5: Configure Claude Desktop

Add remote MCP server to Claude Desktop configuration:

**File**: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)

```json
{
  "mcpServers": {
    "dementia-local": {
      "command": "/path/to/claude-dementia/claude-dementia-server.sh"
    },
    "dementia-cloud": {
      "url": "https://your-app-url.ondigitalocean.app/execute",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY",
        "Content-Type": "application/json"
      }
    }
  }
}
```

**Note**: Keep both local and cloud configurations. Use local for development, cloud for multi-device access.

---

## Step 6: Test in Claude Desktop

1. **Restart Claude Desktop** after config changes
2. **Start new conversation**
3. **Test tools**:
   ```
   User: Use the wake_up tool from dementia-cloud
   ```
4. **Verify tools appear** in Claude's tool list

---

## Monitoring & Debugging

### View Logs

**DigitalOcean Dashboard**:
1. Go to Apps → Your App → Logs
2. All logs are JSON format for easy filtering
3. Search for `"level":"ERROR"` to find issues

**Example log entries**:
```json
{"timestamp":"2025-01-30T12:34:56Z","level":"INFO","event":"tool_execute_start","tool":"wake_up"}
{"timestamp":"2025-01-30T12:34:56Z","level":"INFO","event":"tool_execute_success","tool":"wake_up","latency_ms":145.23}
{"timestamp":"2025-01-30T12:35:00Z","level":"ERROR","event":"tool_execute_error","tool":"lock_context","error":"...","traceback":"..."}
```

### Check Metrics

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     https://your-app-url.ondigitalocean.app/metrics
```

Response shows:
- Total requests
- Success/error counts
- Per-tool execution counts
- Average response times
- Error rates

### Common Issues

**Issue**: `401 Unauthorized`
**Fix**: Check API key matches in both DigitalOcean env vars and Claude config

**Issue**: `500 Internal Server Error`
**Fix**: Check logs for error details. Usually database connection or missing env var.

**Issue**: Tools execute but Claude doesn't show results
**Fix**: Check URL format in `claude_desktop_config.json` - should end with `/execute`

**Issue**: Slow responses (>5 seconds)
**Fix**: Check database connection pool settings in Neon. May need to upgrade plan.

---

## Scaling & Performance

### Current Setup (Basic Tier)
- **1 container**, 512MB RAM, 0.5 CPU
- **Sufficient for**: 1-5 users, <100 requests/hour
- **Response time**: <1 second for most tools

### When to Scale Up
Monitor `/metrics` endpoint. Scale if:
- Average response time > 2 seconds consistently
- Error rate > 5%
- Database connection errors

### Scaling Options
1. **Vertical**: Upgrade to Professional tier ($12/month, 1GB RAM, 1 CPU)
2. **Horizontal**: Add more containers (auto-scaling)
3. **Database**: Upgrade Neon plan for more connections

---

## Security Best Practices

### ✅ Current Security (Phase 1)
- ✅ HTTPS only (automatic with App Platform)
- ✅ Bearer token authentication
- ✅ Environment variables encrypted
- ✅ No secrets in code/git
- ✅ PostgreSQL SSL connections

### 🔒 Future Enhancements (Phase 2+)
- OAuth 2.1 for proper user authentication
- Rate limiting per API key
- Request validation middleware
- CORS configuration for web clients
- Audit logging to database

---

## Costs

### Estimated Monthly Costs
| Service | Plan | Cost |
|---------|------|------|
| DigitalOcean App Platform | Basic | $5 |
| Neon PostgreSQL | Free tier | $0 |
| **Total** | | **$5/month** |

**Note**: Neon free tier includes 512MB storage, 0.5GB RAM. Upgrade to $19/month if you need more.

---

## Rollback Plan

If deployment fails or has critical issues:

1. **Immediate**: Switch Claude Desktop back to local config
2. **Investigate**: Check DO logs for errors
3. **Fix**: Update code, test locally, redeploy
4. **DO NOT**: Delete the deployment - fix and redeploy instead

---

## Next Steps After Successful Deployment

1. ✅ Test all tools from Claude Desktop
2. ✅ Test from mobile device (if Claude mobile has MCP support)
3. ✅ Monitor logs for first 24 hours
4. ✅ Document any performance issues
5. ✅ Plan Phase 2 improvements based on actual usage

---

## Support

**Issues**: GitHub Issues
**Logs**: DigitalOcean Dashboard → Apps → Logs
**Database**: Neon Dashboard → Monitoring

---

**Deployment checklist**:
- [ ] API key generated and saved securely
- [ ] Local tests passed
- [ ] DigitalOcean app created
- [ ] Environment variables configured
- [ ] Deployment successful
- [ ] Health check returns 200 OK
- [ ] Claude Desktop configured
- [ ] Tools execute successfully
- [ ] Logs visible in DO dashboard
- [ ] Metrics endpoint working
