# Hosted Dementia Service Architecture

**Date:** 2025-10-26
**Scope:** Running Dementia as a cloud-hosted SaaS MCP server
**Context:** Alternative to local MCP server installation

---

## Vision: Dementia as a Service

Instead of users running their own local MCP server with SQLite, provide a hosted service where:

- **MCP server runs in the cloud** (AWS, DigitalOcean, Railway, etc.)
- **PostgreSQL database managed service** (Supabase, Neon, RDS, etc.)
- **Users connect remotely** via MCP SSE (Server-Sent Events) transport
- **Multi-tenant architecture** with user/project isolation
- **Authentication/authorization** via API keys
- **Pay-as-you-go or subscription** pricing model

---

## Architecture Comparison

### Current: Local Installation

```
┌─────────────────────────────────┐
│   User's Machine                │
│                                 │
│  ┌──────────────────┐          │
│  │  Claude Desktop  │          │
│  └────────┬─────────┘          │
│           │ stdio               │
│  ┌────────▼─────────────┐      │
│  │  MCP Server (Python) │      │
│  └────────┬─────────────┘      │
│           │                     │
│  ┌────────▼─────────┐          │
│  │  SQLite Database │          │
│  └──────────────────┘          │
│                                 │
└─────────────────────────────────┘
```

**Pros:**
- Fast (local filesystem)
- Works offline
- No network latency
- Private data (never leaves machine)
- No hosting costs

**Cons:**
- Users must install Python, dependencies
- Can't share contexts across machines
- No team collaboration
- Each user isolated
- Support/troubleshooting harder

---

### Proposed: Hosted Service

```
┌──────────────────────┐         ┌────────────────────────────┐
│   User's Machine     │         │      Cloud Infrastructure  │
│                      │         │                            │
│  ┌────────────────┐ │         │  ┌──────────────────────┐ │
│  │ Claude Desktop │ │         │  │  Load Balancer       │ │
│  └────────┬───────┘ │         │  └──────────┬───────────┘ │
│           │         │         │             │              │
│           │ HTTPS   │         │  ┌──────────▼───────────┐ │
│           │ SSE     │         │  │  MCP Server Instance │ │
│           └─────────┼─────────┼──▶  (Docker Container)  │ │
│                     │         │  └──────────┬───────────┘ │
│                     │         │             │              │
│                     │         │  ┌──────────▼───────────┐ │
│                     │         │  │  MCP Server Instance │ │
│                     │         │  │  (Docker Container)  │ │
│                     │         │  └──────────┬───────────┘ │
│                     │         │             │              │
│                     │         │  ┌──────────▼───────────┐ │
│                     │         │  │  PostgreSQL Database │ │
│                     │         │  │  (Managed Service)   │ │
│                     │         │  └──────────────────────┘ │
│                     │         │                            │
└──────────────────────┘         └────────────────────────────┘
```

**Pros:**
- ✅ Zero local installation (just API key)
- ✅ Access from any machine
- ✅ Team collaboration (shared contexts)
- ✅ Always up-to-date (no user updates needed)
- ✅ Centralized support/monitoring
- ✅ Scale to many concurrent users
- ✅ Cross-device sync automatic

**Cons:**
- ⚠️ Requires internet connection
- ⚠️ Network latency (~50-200ms per request)
- ⚠️ User data stored in cloud
- ⚠️ Hosting costs (compute + database)
- ⚠️ Need authentication/security infrastructure
- ⚠️ Privacy concerns for some users

---

## PostgreSQL: Why It's Essential for Hosted Service

### SQLite is NOT Viable for Hosted Service

**Problems with SQLite in cloud:**

1. **File-based storage** - Requires shared filesystem across server instances
2. **No concurrent writes** - Write locks block other connections
3. **No connection pooling** - Each connection = file handle
4. **No network protocol** - Can't connect over TCP/IP natively
5. **No replication** - Can't have standby/failover
6. **Limited scaling** - Can't distribute across multiple servers

**Verdict:** SQLite only works for single-process, local scenarios.

### PostgreSQL is Required for Hosted Service

**Why PostgreSQL:**

1. **Client-server architecture** - Designed for network access
2. **MVCC (Multi-Version Concurrency Control)** - Multiple simultaneous readers/writers
3. **Connection pooling** - Handle thousands of concurrent connections efficiently
4. **Row-level locking** - Fine-grained concurrency
5. **Replication** - Hot standby, read replicas, automatic failover
6. **Schema isolation** - Built-in multi-tenancy support
7. **ACID transactions** - Data consistency across concurrent operations
8. **Mature ecosystem** - Monitoring, backup, performance tools
9. **Managed services** - Supabase, Neon, RDS, etc. handle operations

---

## Multi-Tenant Architecture

### Schema-Based Isolation

Each user (or organization) gets their own PostgreSQL schema:

```sql
-- Database: dementia_production

-- User 1's schema
CREATE SCHEMA user_abc123;
CREATE TABLE user_abc123.sessions (...);
CREATE TABLE user_abc123.context_locks (...);
CREATE TABLE user_abc123.audit_trail (...);

-- User 2's schema
CREATE SCHEMA user_def456;
CREATE TABLE user_def456.sessions (...);
CREATE TABLE user_def456.context_locks (...);
CREATE TABLE user_def456.audit_trail (...);

-- Project-level isolation within user
CREATE SCHEMA user_abc123_innkeeper;
CREATE SCHEMA user_abc123_linkedin;
```

### Connection Management

```python
class DementiaService:
    def __init__(self, connection_pool):
        self.pool = connection_pool

    def get_connection(self, user_id: str, project_id: str):
        """Get connection with schema isolation."""
        conn = self.pool.getconn()

        # Set search_path for schema isolation
        schema = f"user_{user_id}_project_{project_id}"
        with conn.cursor() as cur:
            cur.execute(f"SET search_path TO {schema}, public")

        return conn
```

### Security Model

**API Key Authentication:**
```
dementia-api-key-abc123def456...
  ↓
Validates user_id
  ↓
Routes to correct schema
  ↓
Row-level security policies
```

**Row-Level Security (RLS):**
```sql
-- Ensure users can only access their own data
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_isolation ON sessions
    USING (user_id = current_setting('app.user_id')::text);
```

---

## MCP SSE Transport

### Current: stdio Transport (Local)

```json
{
  "mcpServers": {
    "dementia": {
      "command": "python3",
      "args": ["claude_mcp_hybrid.py"]
    }
  }
}
```

MCP server runs as subprocess, communication via stdin/stdout.

### Hosted: SSE Transport (Remote)

```json
{
  "mcpServers": {
    "dementia-hosted": {
      "transport": "sse",
      "url": "https://api.dementia.ai/mcp",
      "headers": {
        "Authorization": "Bearer dementia-api-key-abc123..."
      }
    }
  }
}
```

MCP server runs remotely, communication via HTTPS Server-Sent Events.

**SSE Protocol:**
- Client → Server: HTTP POST requests with JSON-RPC
- Server → Client: SSE stream for responses/notifications
- Bidirectional communication over HTTP/2
- Works through firewalls (unlike WebSockets in some cases)

---

## Managed PostgreSQL Services

### Supabase (RECOMMENDED for MVP)

**Pricing:**
- Free tier: 500MB database, 2 CPU cores, 1GB RAM
- Pro: $25/month - 8GB database, 2 CPU cores, 4GB RAM
- Team: $599/month - 100GB database, 8 CPU cores, 32GB RAM

**Features:**
- ✅ Built-in authentication (can use for API keys)
- ✅ Row-level security policies
- ✅ Automatic backups
- ✅ Connection pooling (PgBouncer)
- ✅ RESTful API (optional, not needed for MCP)
- ✅ Real-time subscriptions (optional)
- ✅ Dashboard and monitoring
- ✅ Auto-scaling

**MCP Integration:**
```python
import os
from supabase import create_client, Client

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# Use PostgreSQL connection string directly
import psycopg2
conn = psycopg2.connect(os.environ.get("SUPABASE_DB_URL"))
```

### Neon (ALTERNATIVE)

**Pricing:**
- Free tier: 0.5GB database, shared compute
- Launch: $19/month - 10GB, dedicated compute
- Scale: $69/month - 50GB, faster compute

**Features:**
- ✅ Serverless PostgreSQL (scales to zero)
- ✅ Instant branching (great for dev/staging)
- ✅ Connection pooling built-in
- ✅ Automatic backups
- ✅ Low latency (edge network)
- ✅ PostgreSQL 16 latest features

**Best For:** Cost-sensitive, variable traffic

### Railway

**Pricing:**
- Free tier: $5 free credit/month
- Usage-based: ~$20-50/month typical

**Features:**
- ✅ Simple deployment (Git push to deploy)
- ✅ PostgreSQL included
- ✅ Environment variables management
- ✅ Logs and metrics
- ✅ Easy scaling

**Best For:** Quick MVP, simple setup

### DigitalOcean Managed PostgreSQL

**Pricing:**
- Basic: $15/month - 1GB RAM, 10GB disk, 1 vCPU
- Professional: $60/month - 4GB RAM, 80GB disk, 2 vCPU

**Features:**
- ✅ Automatic backups (daily)
- ✅ High availability (standby nodes)
- ✅ Monitoring and alerting
- ✅ Connection pooling
- ✅ Trusted infrastructure

**Best For:** Production stability, known costs

---

## Cost Analysis

### Infrastructure Costs

**MCP Server (Compute):**
- Railway: ~$5-10/month (hobby tier)
- DigitalOcean Droplet: $6/month (1GB RAM)
- AWS ECS Fargate: ~$15/month (0.25 vCPU, 0.5GB RAM)
- Fly.io: $3-5/month (shared CPU)

**Database (PostgreSQL):**
- Supabase Free: $0 (up to 500MB)
- Supabase Pro: $25/month (8GB)
- Neon Free: $0 (up to 0.5GB)
- Neon Launch: $19/month (10GB)
- Railway: ~$10/month (usage-based)
- DigitalOcean: $15/month (1GB RAM)

**Total MVP (Free Tier):**
- Compute: $5/month
- Database: $0 (free tier)
- **Total: $5/month**

**Total Production (100 users):**
- Compute: $20/month (2 instances)
- Database: $25-69/month (Supabase Pro or Neon Scale)
- Monitoring: $0 (built-in)
- **Total: $45-89/month**

**At Scale (1000+ users):**
- Compute: $100-200/month (load balanced)
- Database: $599/month (Supabase Team)
- CDN/Edge: $20/month
- Monitoring: $29/month (Datadog/New Relic)
- **Total: ~$750/month**

---

## Migration Strategy

### Phase 1: Keep Local SQLite (Current)

**No changes to existing users.**

Local installation remains primary option for:
- Individual users
- Privacy-conscious users
- Offline-first workflows
- No recurring costs

### Phase 2: Add Hosted Option (Parallel)

**New codebase branch:** `feature/hosted-service`

1. **Implement PostgreSQL support**
   - Replace SQLite-specific code
   - Add connection pooling
   - Implement schema-based isolation

2. **Add SSE transport**
   - HTTP server for MCP protocol
   - Authentication middleware
   - Rate limiting

3. **Create hosted infrastructure**
   - Deploy to Railway/Fly.io
   - Set up Supabase PostgreSQL
   - Configure environment

4. **Beta testing**
   - Invite users to hosted version
   - Gather feedback
   - Fix issues

### Phase 3: Hybrid Model

**Users choose:**
- Local (free, SQLite, self-hosted)
- Hosted Free (limited contexts, shared infra)
- Hosted Pro ($9/month, more contexts, priority)
- Hosted Team ($29/month, shared workspaces)

---

## Implementation Checklist

### Backend (MCP Server)

- [ ] PostgreSQL adapter replacing SQLite
- [ ] Connection pooling (psycopg2.pool or pgbouncer)
- [ ] Schema-based multi-tenancy
- [ ] API key authentication
- [ ] Row-level security policies
- [ ] SSE transport implementation
- [ ] Rate limiting middleware
- [ ] Health check endpoints
- [ ] Metrics/logging (Prometheus/Grafana)

### Database Schema

- [ ] User accounts table (id, email, api_key_hash, created_at)
- [ ] Projects table (id, user_id, name, schema_name)
- [ ] Per-project schemas (sessions, context_locks, etc.)
- [ ] Usage tracking (API calls, storage used)
- [ ] Audit logs (who did what when)

### Infrastructure

- [ ] MCP server deployment (Docker, Railway/Fly.io)
- [ ] PostgreSQL setup (Supabase/Neon)
- [ ] Environment variables management
- [ ] TLS/SSL certificates (Let's Encrypt)
- [ ] Domain setup (api.dementia.ai)
- [ ] Load balancer (if needed)
- [ ] Monitoring (uptime, errors, latency)
- [ ] Backup strategy (automated, tested)

### Security

- [ ] API key generation/hashing
- [ ] HTTPS enforcement
- [ ] SQL injection prevention (parameterized queries)
- [ ] Rate limiting (per user, per API key)
- [ ] CORS configuration
- [ ] Secret management (environment variables)
- [ ] Database connection string encryption

### Client Experience

- [ ] Claude Desktop config example
- [ ] API key signup flow
- [ ] Usage dashboard (contexts, API calls, storage)
- [ ] Documentation (quick start, migration guide)
- [ ] Troubleshooting guide

---

## User Onboarding Flow

### Hosted Service

1. **User visits https://dementia.ai**

2. **Sign up / Get API Key**
   ```
   Email: user@example.com
   → Generates API key: dementia-sk-abc123...
   ```

3. **Configure Claude Desktop**
   ```json
   {
     "mcpServers": {
       "dementia": {
         "transport": "sse",
         "url": "https://api.dementia.ai/mcp",
         "headers": {
           "Authorization": "Bearer dementia-sk-abc123..."
         }
       }
     }
   }
   ```

4. **Start using**
   ```
   Claude Desktop → dementia:wake_up()
   → Connects to hosted service
   → Creates user schema automatically
   → Ready to use
   ```

### Data Migration (Local → Hosted)

```bash
# Export from local SQLite
dementia-export --output my-contexts.json

# Import to hosted service
dementia-import --api-key dementia-sk-abc123... --input my-contexts.json
```

---

## Revenue Model (Optional)

### Free Tier
- 50 contexts maximum
- 1,000 API calls/month
- Single project
- Community support

### Pro ($9/month)
- 500 contexts
- 10,000 API calls/month
- Unlimited projects
- Email support
- 30-day retention

### Team ($29/month)
- Unlimited contexts
- 50,000 API calls/month
- Shared workspaces
- Priority support
- Custom retention
- Audit logs

### Enterprise ($custom)
- Self-hosted option
- SLA guarantees
- Dedicated support
- Custom integrations
- Training

---

## Advantages of Hosted Service

### For Users

1. **Zero Setup** - No Python, dependencies, or configuration
2. **Cross-Device** - Access contexts from any machine
3. **Team Collaboration** - Share contexts with teammates
4. **Always Updated** - No manual updates needed
5. **Reliable Backups** - Automatic, tested backups
6. **Better Performance** - Optimized infrastructure
7. **Support** - Dedicated support team

### For Provider (You)

1. **Revenue Stream** - Subscription model
2. **Centralized Updates** - Deploy once, everyone benefits
3. **Better Analytics** - Usage patterns, popular features
4. **Easier Support** - Access to logs, metrics
5. **Scale Economies** - Lower per-user cost at scale
6. **Network Effects** - Public context marketplace (future)

---

## Risks and Mitigations

### Risk 1: Latency

**Issue:** Network calls slower than local SQLite.

**Mitigation:**
- Connection pooling (reuse connections)
- Edge deployment (Fly.io, Cloudflare Workers)
- Caching layer (Redis for hot data)
- Async operations where possible

**Benchmark:**
- SQLite (local): ~1-5ms
- PostgreSQL (cloud): ~50-150ms
- User perception: <200ms acceptable

### Risk 2: Data Privacy

**Issue:** Users concerned about contexts in cloud.

**Mitigation:**
- Encryption at rest (PostgreSQL native)
- Encryption in transit (TLS)
- Optional end-to-end encryption (encrypt before upload)
- Data residency options (EU, US, etc.)
- Self-hosted option for enterprises
- Clear privacy policy

### Risk 3: Service Availability

**Issue:** Downtime affects all users.

**Mitigation:**
- High availability (multiple servers)
- Database replication (standby nodes)
- Health monitoring (uptime checks)
- Status page (status.dementia.ai)
- SLA for paid tiers (99.9% uptime)
- Fallback to cached data client-side

### Risk 4: Cost Scaling

**Issue:** Costs increase faster than revenue.

**Mitigation:**
- Start with free tier databases
- Monitor costs closely
- Optimize queries (indexes, explain analyze)
- Archive old data (cold storage)
- Usage-based pricing (aligns cost/revenue)
- Connection pooling (reduce DB load)

---

## Timeline Estimate

### MVP (Hosted Beta)

**Week 1-2: Backend**
- PostgreSQL adapter
- Multi-tenancy
- SSE transport
- Authentication

**Week 3: Infrastructure**
- Deploy to Railway
- Supabase setup
- Testing

**Week 4: Client**
- Documentation
- Config examples
- Beta invites

**Total: 4 weeks for MVP**

### Production-Ready

**Week 5-6: Hardening**
- Security audit
- Load testing
- Error handling
- Monitoring

**Week 7-8: Polish**
- Dashboard UI
- Billing integration
- Migrations tools
- Documentation

**Total: 8 weeks for production**

---

## Comparison: Local vs Hosted

| Feature | Local SQLite | Hosted PostgreSQL |
|---------|-------------|-------------------|
| **Setup Complexity** | High (Python, deps) | Low (API key) |
| **Performance** | Fast (1-5ms) | Good (50-150ms) |
| **Offline Support** | ✅ Yes | ❌ No |
| **Cross-Device** | ❌ No | ✅ Yes |
| **Team Sharing** | ❌ No | ✅ Yes |
| **Data Privacy** | ✅ Local only | ⚠️ Cloud stored |
| **Backup** | ⚠️ Manual | ✅ Automatic |
| **Cost** | Free (DIY) | $0-29/month |
| **Scalability** | Limited | Unlimited |
| **Support** | Community | Dedicated |

---

## Recommendation

### Short Term: Both Options

**Maintain local SQLite version** for:
- Privacy-conscious users
- Offline workflows
- Self-hosters
- Cost-sensitive users

**Add hosted PostgreSQL option** for:
- Teams
- Cross-device users
- No-setup preference
- Revenue generation

### Long Term: Hybrid Default

Most users prefer hosted (convenience), but keep local option available.

**Implementation Priority:**
1. Fix immediate local multi-project issue (env variables)
2. Start hosted service development in parallel
3. Beta test hosted service with early adopters
4. Launch both options publicly

---

## Next Steps

1. **Decision Point:** Commit to building hosted service?
   - Market research (would users pay?)
   - Competitive analysis (similar products?)
   - Revenue projections

2. **If Yes - Start MVP:**
   - Set up Supabase account (free tier)
   - Create PostgreSQL adapter
   - Implement SSE transport
   - Deploy to Railway
   - Beta test with 5-10 users

3. **If No - Focus on Local:**
   - Implement env variable solution
   - Improve local multi-project experience
   - Document best practices
   - Community support model

---

**Conclusion:**

PostgreSQL is **essential** for a hosted Dementia service, but requires significant architecture changes. The hosted model offers better UX and revenue potential, but comes with operational complexity and costs.

Recommend pursuing both: fix local multi-project issue now (quick win), develop hosted service in parallel (long-term value).

---

*Document version: 1.0*
*Last updated: 2025-10-26*
