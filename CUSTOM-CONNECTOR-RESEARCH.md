# Claude.ai Custom Connectors for MCP: Complete Technical Guide

Model Context Protocol (MCP) Custom Connectors enable Claude to access remote tools and data sources through cloud-hosted servers, fundamentally different from local MCP integrations. This guide provides comprehensive coverage of setup, architecture, deployment, and debugging—with specific focus on resolving initialization timeouts, WSL/Windows issues, and network restrictions affecting your PostgreSQL/Neon MCP server.

## Initialization timeout troubleshooting for restricted networks

**Initialization timeouts are the most common failure mode** for Custom Connectors, particularly in enterprise environments with network restrictions like NATO organizations. The default 60-second timeout often proves insufficient when servers must activate cold-start databases, traverse complex firewall rules, or complete OAuth handshakes through proxy servers.

### Root causes and immediate solutions

**Server startup failures** account for most timeout issues. Missing dependencies (Node.js versions below v18.0.0, unpinned Python modules), misconfigured environment variables, or port conflicts prevent servers from responding within the timeout window. Test your server standalone before integration: `node server.js` or `python -m myserver` should start without errors. The MCP Inspector tool (`npx @modelcontextprotocol/inspector`) provides isolated testing that eliminates client-side variables.

**Timeout configuration requires multiple layers**. For Claude Desktop, edit your configuration file with extended timeouts:

```json
{
  "mcpServers": {
    "myserver": {
      "command": "node",
      "args": ["./server.js"],
      "timeout": 300000,
      "env": {
        "MCP_SERVER_REQUEST_TIMEOUT": "300"
      }
    }
  }
}
```

However, **the TypeScript SDK enforces a hard 60-second limit** regardless of configuration. If using TypeScript, implement progress notifications to keep the connection alive during long initialization. Python's FastMCP respects timeout settings: `FastMCP("myserver", settings={"initialization_timeout": 10.0})`.

**Protocol handshake problems** manifest when the initialization sequence breaks down. The correct flow: (1) Client sends `initialize` request, (2) Server processes and responds, (3) Client sends `initialized` notification, (4) Normal operations begin. Any interruption causes timeouts. Enable debug logging to stderr (never stdout, which corrupts the JSON-RPC protocol) to trace handshake progression.

### Network restriction patterns in NATO/enterprise environments

**Firewall rules block MCP endpoints by default** in defense and government networks. Custom Connectors require HTTPS (port 443) access to your remote server. Request allowlisting for your MCP server's domain through your network security team. Anthropic provides official IP addresses for whitelisting Claude's outbound connections—find these at the documented IP addresses endpoint.

**Corporate proxies interfere with OAuth flows**. The standard OAuth callback URL `https://claude.ai/api/mcp/auth_callback` must traverse your proxy without modification. If OAuth consistently fails while basic HTTPS works, your proxy may strip authentication headers or redirect callbacks. Consider these workarounds: (1) Use API key authentication instead of OAuth for internal servers, (2) Deploy the MCP server inside your corporate network perimeter, (3) Configure proxy exceptions for `*.claude.ai` domains.

**DNS tunneling in WSL environments** can resolve network packet blocks. WSL versions from September 2023 onward include DNS tunneling specifically to bypass enterprise firewall restrictions. Update WSL with `wsl --update` and verify version with `wsl --version`. Configure `.wslconfig` to enable mirrored networking:

```ini
[wsl2]
networkingMode = mirrored
```

Restart WSL with `wsl --shutdown`. This allows Windows applications like Claude Desktop to connect to `127.0.0.1` in WSL without additional port forwarding.

### PostgreSQL/Neon specific timeout issues

**Neon's scale-to-zero architecture** introduces unique timeout challenges. Neon suspends compute instances after 5 minutes of inactivity (free tier). Queries during compute activation receive `terminating connection due to administrator command` errors. Your initialization timeout may actually be compute activation time plus connection time.

**Three solutions exist**: (1) Disable scale-to-zero in Neon console (paid plans only) under Project Settings → Compute, (2) Increase Prisma connection timeout if using Prisma ORM:

```javascript
const prisma = new PrismaClient({
  __internal: {
    engine: {
      connectTimeout: 20000
    }
  }
});
```

(3) Implement connection retry logic:

```javascript
async function queryWithRetry(query, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await db.query(query);
    } catch (error) {
      if (error.message.includes('administrator command') && i < maxRetries - 1) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        continue;
      }
      throw error;
    }
  }
}
```

**SNI (Server Name Indication) support is mandatory** for Neon connections. Older PostgreSQL client libraries (libpq < 14) fail with `ERROR: The endpoint ID is not specified`. Upgrade to libpq 14+ or add the endpoint parameter explicitly to your connection string:

```
postgresql://user:pass@ep-name-123456.region.aws.neon.tech/db?options=endpoint%3Dep-name-123456
```

**Connection pooling creates prepared statement conflicts**. Neon's PgBouncer in transaction mode doesn't persist `SET` statements including search_path. Use schema-qualified table names (`myschema.mytable`) or set search_path at the role level: `ALTER ROLE your_role SET search_path TO schema1, schema2, public;`

## WSL/Windows environment debugging

**VS Code and Cursor cannot find MCP servers in WSL** due to path resolution issues. The error `spawn npx ENOENT` indicates the Windows application cannot locate the Linux executable. Use the `wsl.exe` wrapper in your configuration:

```json
{
  "servers": {
    "myserver": {
      "type": "stdio",
      "command": "wsl",
      "args": ["bash", "-c", "$HOME/path/to/server.sh"]
    }
  }
}
```

Alternatively, configure on the WSL-side settings file: `~/.vscode-server/data/User/mcp.json` instead of the Windows-side `C:/Users/user/AppData/Roaming/Code/User/mcp.json`.

**Environment variables fail to propagate from Windows to WSL**. Use `bash -ic` (interactive mode) to ensure `.bashrc` loads:

```json
{
  "command": "wsl",
  "args": ["bash", "-ic", "npx -y @your/mcp-server"],
  "env": {
    "API_KEY": "key-value"
  }
}
```

**NVM (Node Version Manager) complicates WSL execution**. WSL doesn't automatically source NVM, causing "npx not found" errors. Source NVM explicitly and use absolute paths:

```json
{
  "command": "wsl",
  "args": [
    "bash", "-ic",
    "source ~/.nvm/nvm.sh && /home/user/.nvm/versions/node/v20.18.0/bin/node /path/to/server.js"
  ]
}
```

**Docker in WSL requires user ID mapping**. File ownership mismatches cause permission errors. Specify your WSL user ID:

```json
{
  "command": "wsl",
  "args": [
    "docker", "run", "-i", "--rm",
    "--user", "1000:1000",
    "--mount", "type=bind,src=/home/user/data,dst=/data",
    "mcp/myserver"
  ]
}
```

Get your user ID with `id -u` and group ID with `id -g`.

## Custom Connector setup process

**Claude.ai Custom Connectors use UI-based configuration**, fundamentally different from Claude Desktop's JSON file approach. Access Settings → Connectors → "Add custom connector" and provide only the server URL. No local configuration files exist for Custom Connectors—all settings sync through Claude's cloud infrastructure.

### Authentication configuration

**OAuth 2.1 with Dynamic Client Registration (DCR)** provides the smoothest experience. The server advertises OAuth endpoints during initialization, Claude auto-registers as a client, and users complete authentication in-browser. Claude's callback URL is `https://claude.ai/api/mcp/auth_callback` (future: `https://claude.com/api/mcp/auth_callback`—allowlist both).

**Manual OAuth configuration** supports servers without DCR. Click "Advanced settings" when adding the connector, then enter OAuth Client ID and Client Secret. The MCP server must be pre-registered with these credentials in your OAuth provider.

**API key authentication** works for simpler integrations. The server accepts keys via HTTP headers or query parameters. Users enter the key during connector setup; Claude stores it securely and includes it with every request.

**Enterprise Team/Enterprise plans** require admin approval. Only Primary Owners can enable connectors organization-wide via Admin Settings → Connectors. Individual users then authenticate separately, ensuring Claude only accesses data each user has permission to view.

### Critical differences from Claude Desktop

| Aspect | Claude Desktop (Local MCP) | Claude.ai (Custom Connectors) |
|--------|---------------------------|-------------------------------|
| **Server Location** | Local machine | Cloud-hosted, internet-accessible |
| **Configuration** | JSON file editing | UI-based, no local files |
| **Transport** | stdio (standard input/output) | Streamable HTTP or SSE |
| **Dependencies** | User manages Node.js/Python | Server handles everything |
| **Availability** | Single device | Synced across all devices |

**Claude Desktop CANNOT connect to remote servers** configured in `claude_desktop_config.json`. The JSON configuration file exclusively supports local stdio servers. For remote MCP servers, you must add them through Settings → Connectors in the application UI, which works across both Claude Desktop and Claude.ai.

## MCP server architecture for Custom Connectors

**Custom Connectors require internet-accessible HTTPS endpoints**, not local processes. Your server must implement either Streamable HTTP (recommended) or SSE transport, expose a single `/mcp` endpoint, and handle JSON-RPC 2.0 messages over HTTP POST and GET.

### Transport layer selection: stdio vs SSE vs Streamable HTTP

**stdio (standard input/output)** works exclusively for local servers. It provides the lowest latency (sub-1ms) and highest throughput (10,000+ ops/sec) but requires process spawning and cannot cross network boundaries. Use stdio only for Claude Desktop local integrations or development testing.

**SSE (Server-Sent Events)** enables remote access through persistent HTTP connections. However, **SSE is being deprecated** as of March 2025. The dual-endpoint architecture (separate `/sse` and `/messages` endpoints) adds complexity. Do not build new servers with SSE—migrate existing implementations to Streamable HTTP.

**Streamable HTTP is the recommended transport** for all new Custom Connectors. It uses a single `/mcp` endpoint supporting both immediate JSON responses and streaming via SSE protocol, simplifies load balancing and firewall rules, provides better scalability through stateless design, and represents the strategic direction for MCP protocol evolution.

**Implementation example for Streamable HTTP:**

```typescript
import express from 'express';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';

const app = express();
app.use(express.json());

const server = new McpServer({
  name: 'example-server',
  version: '1.0.0'
});

// Register tools, resources, prompts

app.post('/mcp', async (req, res) => {
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true
  });
  
  res.on('close', () => transport.close());
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
});

app.listen(3000);
```

### Environment variable and secrets management

**Never hardcode secrets in source code or commit them to version control.** Use dedicated secrets managers: HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, or Cloudflare Workers secrets. Implement least privilege access with role-based permissions and minimal scopes. Rotate credentials regularly with automated schedules.

**For PostgreSQL/Neon specifically**, store connection strings as environment variables with sensitive data separated:

```javascript
const connectionString = `postgresql://${process.env.NEON_USER}:${process.env.NEON_PASSWORD}@${process.env.NEON_HOST}/${process.env.NEON_DATABASE}?sslmode=require`;
```

**OAuth token management** requires implementing token refresh logic. Claude handles token expiry and refresh automatically for properly configured OAuth servers, but your server must validate tokens and handle refresh token grants. Use short-lived access tokens (15-30 minutes) with secure refresh token storage.

**Wrapper scripts bridge legacy servers without secrets support:**

```bash
#!/bin/bash
export PGPASSWORD=$(vault kv get -field=password secret/postgres)
npx @modelcontextprotocol/server-postgres
```

### Tool definition schemas and validation

**JSON Schema with Zod provides type-safe tool definitions.** Every tool requires name, description, and inputSchema. Use Zod for automatic runtime validation:

```typescript
import { z } from 'zod';

server.registerTool('fetch-weather', {
  title: 'Weather Fetcher',
  description: 'Get current weather for a city',
  inputSchema: {
    city: z.string().min(1),
    units: z.enum(['metric', 'imperial']).default('metric')
  },
  outputSchema: {
    temperature: z.number(),
    conditions: z.string()
  }
}, async ({ city, units }) => {
  const response = await fetch(
    `https://api.weather.com/v1/current?city=${city}`,
    { headers: { 'Authorization': `Bearer ${process.env.WEATHER_API_KEY}` } }
  );
  const data = await response.json();
  return {
    content: [{ type: 'text', text: JSON.stringify(data) }],
    structuredContent: data
  };
});
```

**Security validation beyond schema checking**. Prevent SQL injection, path traversal, and command injection:

```typescript
function validateAndSanitize(params: any) {
  if (/\b(SELECT|INSERT|UPDATE|DELETE)\b/i.test(params.query)) {
    throw new ValidationError('Unsafe SQL detected');
  }
  
  if (params.path?.includes('..')) {
    throw new ValidationError('Path traversal not allowed');
  }
  
  if (/[;&|`$]/.test(params.command)) {
    throw new ValidationError('Unsafe command detected');
  }
  
  return params;
}
```

### Error handling patterns

**Separate protocol errors from tool execution errors.** JSON-RPC errors (-32000 series) indicate protocol-level failures. Tool execution errors should return structured error content:

```typescript
server.registerTool('query-database', config, async (params) => {
  try {
    const result = await db.query(params.sql);
    return { 
      content: [{ type: 'text', text: JSON.stringify(result) }],
      structuredContent: result 
    };
  } catch (error) {
    logger.error('Query failed', { sql: params.sql, error: error.stack });
    
    return {
      content: [{ type: 'text', text: `Database error: ${error.message}` }],
      isError: true
    };
  }
});
```

**Implement retry logic with exponential backoff** for transient failures:

```typescript
async function retryWithBackoff<T>(
  operation: () => Promise<T>,
  maxAttempts = 3
): Promise<T> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await operation();
    } catch (error) {
      if (attempt === maxAttempts - 1 || !isRetryable(error)) {
        throw error;
      }
      const delay = Math.pow(2, attempt) * 1000 + Math.random() * 1000;
      await sleep(delay);
    }
  }
}
```

## Deployment and hosting requirements

**Custom Connectors must be remotely accessible via HTTPS**. HTTP is not supported; TLS 1.3+ is mandatory for production. Your server must respond to both POST requests (tool calls) and GET requests (SSE connections if using SSE transport).

### Network configuration for enterprise environments

**Inbound firewall rules** must allow HTTPS on port 443 from Claude's IP addresses. Anthropic documents official IP ranges for allowlisting. Implement network segmentation by deploying MCP servers in isolated DMZ/VLAN segments, separate from production databases.

```bash
# UFW firewall example for internal network only
ufw allow from 10.0.0.0/16 to any port 443 proto tcp
ufw deny in to any port 443

# IPTables equivalent
iptables -A INPUT -p tcp --dport 443 -s 10.0.0.0/16 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j DROP
```

**Outbound rules in restricted networks** require allowlisting your database endpoints. For Neon PostgreSQL: `*.region.aws.neon.tech` on port 5432. Implement egress filtering to prevent data exfiltration—allowlist only necessary external APIs.

**Corporate proxies require special handling**. Configure your MCP server to use the proxy for outbound connections:

```javascript
import { HttpsProxyAgent } from 'https-proxy-agent';

const agent = new HttpsProxyAgent(process.env.HTTPS_PROXY);
fetch(url, { agent });
```

### CORS configuration essentials

**CORS is mandatory for browser-based clients** and SSE connections. Without proper CORS headers, browsers block all MCP requests. Required headers:

```javascript
const corsOptions = {
  origin: function (origin, callback) {
    const allowedOrigins = [
      'http://localhost:3000',
      'https://your-app.com'
    ];
    
    if (!origin || allowedOrigins.indexOf(origin) !== -1) {
      callback(null, true);
    } else {
      callback(new Error('Not allowed by CORS'));
    }
  },
  methods: ['GET', 'POST', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'Mcp-Session-Id'],
  exposedHeaders: ['Mcp-Session-Id', 'X-Request-Id'],
  credentials: true,
  maxAge: 86400
};

app.use(cors(corsOptions));
app.options('*', cors(corsOptions));
```

**Never use `Access-Control-Allow-Origin: *` with credentials**. Always specify exact origins. Expose the `Mcp-Session-Id` header explicitly—it's critical for protocol operation.

**SSE endpoints require additional CORS headers:**

```javascript
app.get('/mcp/sse', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache, no-transform',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no',
    'Access-Control-Allow-Origin': req.headers.origin || '*',
    'Access-Control-Allow-Credentials': 'true'
  });
});
```

### Cloud hosting platforms

**Cloudflare Workers** provides the simplest deployment for Custom Connectors. Built-in HTTPS, automatic scaling to handle traffic spikes, integrated OAuth token management via KV storage, and pay-per-request pricing. Deploy with:

```bash
wrangler login
wrangler secret put GITHUB_CLIENT_ID
wrangler secret put GITHUB_CLIENT_SECRET
wrangler deploy
```

Limitations: 50ms CPU time per request, cannot spawn native binaries.

**Google Cloud Run** offers rapid autoscaling with Python/Node.js support. Deploy with authentication required using `--no-allow-unauthenticated` flag. Use Cloud Run proxy for authenticated local tunnels during development:

```bash
gcloud run deploy mcp-server \
  --source . \
  --region us-central1 \
  --no-allow-unauthenticated \
  --port 8080
```

Cold starts (1-2 seconds) can contribute to initialization timeouts. Configure minimum instances to reduce cold start impact.

**Azure Container Apps** integrates deeply with enterprise Azure environments. Supports managed identity for passwordless database connections, OAuth with Microsoft Entra ID, and application insights for monitoring. Deploy using `azd`:

```bash
azd init -t azmcp-copilot-studio-aca-mi
azd up
```

**Self-hosted options** provide maximum control for sensitive environments. Deploy to VMs or Kubernetes within your network perimeter. Use Docker Compose for simple deployments:

```yaml
version: '3.8'
services:
  mcp-server:
    image: your-mcp-server:latest
    ports:
      - "443:443"
    environment:
      - OAUTH_CLIENT_ID=${OAUTH_CLIENT_ID}
      - DATABASE_URL=${DATABASE_URL}
    restart: unless-stopped
```

## Testing methodologies

**MCP Inspector is the primary testing tool** for Custom Connectors. It provides isolated server testing without client interference:

```bash
npx @modelcontextprotocol/inspector node server.js
```

Opens a web interface at `http://localhost:5173` where you can test initialization handshakes, view raw JSON-RPC messages, execute tools with custom inputs, and inspect server responses in real-time.

**Pre-deployment testing checklist:**

1. **Standalone testing**: Verify `node server.js` or `python -m myserver` starts without errors
2. **Inspector testing**: Confirm initialization completes, tools list correctly, resources are accessible, each tool executes successfully
3. **Schema validation**: Test with invalid inputs to verify error handling
4. **Load testing**: Simulate concurrent requests for production servers
5. **Integration testing**: Test with actual client (Claude Desktop, Claude.ai) before production deployment

**Automated testing patterns:**

```javascript
// Jest example
test("handles database connection failures", async () => {
  const result = await runTool("queryDatabase", {
    sql: "SELECT * FROM nonexistent"
  });
  
  expect(result.isError).toBe(true);
  expect(result.content[0].text).toContain('does not exist');
});
```

**Production monitoring metrics:**

- Error rate by tool name and status
- P50/P95/P99 response time latencies
- Memory and CPU usage patterns
- External service availability (database, APIs)
- Connection pool utilization
- Initialization success/failure rates

Implement Prometheus metrics for quantitative monitoring:

```javascript
import client from 'prom-client';

const toolDuration = new client.Histogram({
  name: 'mcp_tool_duration_seconds',
  help: 'Tool execution duration',
  labelNames: ['tool_name', 'status']
});
```

## Logging best practices

**Critical rule: Never log to stdout in stdio servers**. Standard output is the JSON-RPC communication channel. Writing anything else corrupts the protocol and causes connection failures. Always use stderr for logging:

```javascript
// ❌ WRONG - Breaks protocol
console.log("Debug info");

// ✅ CORRECT - Logs to stderr
console.error("Debug info");
```

Python equivalent:

```python
# ❌ WRONG
print("Debug info")

# ✅ CORRECT
import sys
print("Debug info", file=sys.stderr)

# Or use logging
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s',
    stream=sys.stderr
)
```

**For HTTP/SSE servers, stdout logging is acceptable**, but structured logging remains best practice.

**Log locations by platform:**

- Claude Desktop (macOS): `~/Library/Logs/Claude/mcp*.log`
- Claude Desktop (Windows): `%APPDATA%\Claude\logs\mcp*.log`
- VS Code: View → Output → Select "MCP" from dropdown
- Docker containers: `docker logs <container-id>`

**Key events to log:**

- Server startup time and initialization duration
- Client connection attempts with session IDs
- Protocol version negotiation outcomes
- Authentication success/failure with sanitized details
- Request/response pairs with unique IDs
- Error details with full stack traces
- Performance metrics (query time, API latency)

## Claude Code integration

**Claude Code is a terminal-based AI coding assistant** separate from Claude Desktop. It supports Custom Connectors through three transport methods: HTTP, SSE, and local stdio. Add connectors via CLI commands:

```bash
# HTTP transport (recommended)
claude mcp add --transport http sentry https://mcp.sentry.dev/mcp

# SSE transport
claude mcp add --transport sse linear https://mcp.linear.app/sse

# Local stdio
claude mcp add myserver -- npx -y @package/server-name
```

**Configuration scopes** determine connector availability:

- **Local scope** (default): Project-specific, private to the user
- **Project scope**: Shared via `.mcp.json` in version control
- **User scope**: Available across all projects for the user

**Configuration file location**: `~/.claude.json` (different from Claude Desktop's config location)

**Key differences from Claude Desktop:**

- No message limits, only token-based usage
- Autonomous multi-step execution with subagents
- Native OAuth support for remote servers
- Can act as both MCP client and MCP server (`claude mcp serve`)
- Direct file system access without copying/pasting
- Support for Docker MCP Toolkit (200+ servers)

## Official documentation resources

**Primary documentation:**

- MCP Specification (latest): https://modelcontextprotocol.io/specification/2025-06-18
- Claude Help Center - Building Custom Connectors: https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers
- Claude API Documentation - MCP Connector: https://docs.claude.com/en/docs/agents-and-tools/mcp-connector
- Official MCP Website: https://modelcontextprotocol.io

**GitHub repositories:**

- MCP Specification: https://github.com/modelcontextprotocol/modelcontextprotocol
- TypeScript SDK: https://github.com/modelcontextprotocol/typescript-sdk
- Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Reference Servers: https://github.com/modelcontextprotocol/servers
- MCP Inspector: https://github.com/modelcontextprotocol/inspector

**Educational resources:**

- Introduction to Model Context Protocol: https://anthropic.skilljar.com/introduction-to-model-context-protocol
- Model Context Protocol: Advanced Topics: https://anthropic.skilljar.com/model-context-protocol-advanced-topics
- Microsoft MCP for Beginners: https://github.com/microsoft/mcp-for-beginners

**Version information:**

- Current specification: 2025-06-18 (June 18, 2025)
- Previous specification: 2025-03-26
- Changelog: https://modelcontextprotocol.io/specification/draft/changelog

**Known limitations:**

- Resource subscriptions NOT yet supported in Claude
- Sampling NOT yet supported in Claude
- SSE transport being deprecated in favor of Streamable HTTP
- Free plans do NOT support Custom Connectors
- Mobile apps cannot add NEW connectors (only use pre-configured ones)

## Debugging quick reference

### Error code reference

| Code | Error | Common Cause | Quick Fix |
|------|-------|--------------|-----------|
| -32000 | Connection closed | Server crashed or transport issue | Check server logs, verify transport config |
| -32001 | Request timeout | Operation too slow | Increase timeout, add progress notifications |
| -32600 | Invalid Request | Malformed JSON-RPC | Check message format, verify JSON syntax |
| -32601 | Method not found | Tool/method doesn't exist | Verify tool name, check server capabilities |
| -32602 | Invalid params | Wrong parameter types | Validate input schema, check parameter format |
| -32603 | Internal error | Server-side exception | Check server logs, review error handling |

### Common command patterns

```bash
# Test server initialization
echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}' | node server.js

# List tools
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | node server.js | jq

# Start with Inspector
npx @modelcontextprotocol/inspector node server.js

# View logs in real-time
tail -f ~/Library/Logs/Claude/mcp*.log
```

### Timeout configuration summary

**Client-side (Claude Desktop):**
```json
{
  "timeout": 300000,
  "env": {
    "MCP_SERVER_REQUEST_TIMEOUT": "300"
  }
}
```

**Python (FastMCP):**
```python
mcp = FastMCP("name", request_timeout=300)
```

**TypeScript:** Use progress notifications (hard 60s limit)

## Conclusion

Custom Connectors represent a fundamental shift from local MCP integrations to cloud-hosted, remotely-accessible tool servers. Success requires understanding the transport layer differences (Streamable HTTP over stdio), implementing proper OAuth authentication, configuring CORS correctly for browser access, and debugging initialization timeouts through extended timeout settings, proper logging, and connection retry logic.

For your PostgreSQL/Neon MCP server in WSL/Windows with network restrictions, prioritize these actions: (1) Extend initialization timeout to 300 seconds, (2) Implement connection retry logic for Neon compute activation, (3) Configure WSL mirrored networking, (4) Request firewall allowlisting for your MCP endpoint and Neon database, (5) Use the MCP Inspector for isolated testing before client integration, (6) Enable comprehensive logging to stderr for protocol debugging.

The MCP ecosystem continues rapid evolution with Anthropic's commitment to open standards. Monitor the specification changelog, test across platform updates, and participate in community discussions to stay current with protocol changes and best practices.