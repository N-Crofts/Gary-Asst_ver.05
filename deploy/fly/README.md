# Fly.io Deployment Guide for Gary-Asst

This guide provides step-by-step instructions for deploying Gary-Asst to Fly.io.

## Prerequisites

- [Fly.io CLI](https://fly.io/docs/getting-started/installing-flyctl/) installed
- Fly.io account created
- Environment variables ready (see below)

## Deployment Steps

### 1. Authenticate with Fly.io

```bash
fly auth login
```

Follow the prompts to authenticate with your Fly.io account.

### 2. Launch the Application

```bash
fly launch
```

This command will:
- Detect your `fly.toml` configuration
- Create a new Fly.io app (or use existing)
- Prompt for app name (default: `gary-asst`)
- Prompt for region (choose closest to your users)
- Deploy the application

**Note:** During `fly launch`, you may be prompted to create a Postgres database. For this phase, you can skip database creation by selecting "No" when prompted.

### 3. Set Environment Secrets

Set all required environment variables as Fly.io secrets:

```bash
# Azure/Microsoft Graph credentials
fly secrets set AZURE_TENANT_ID=your-tenant-id
fly secrets set AZURE_CLIENT_ID=your-client-id
fly secrets set AZURE_CLIENT_SECRET=your-client-secret

# API key for internal endpoints
fly secrets set INTERNAL_API_KEY=your-api-key

# Tavily API key (placeholder - not implemented yet)
fly secrets set TAVILY_API_KEY=your-tavily-api-key
```

**Important:** Secrets are encrypted and only accessible to your application. Never commit secrets to version control.

### 4. Deploy the Application

```bash
fly deploy
```

This will:
- Build the Docker image
- Push it to Fly.io
- Deploy the new version
- Run health checks

### 5. View Application Logs

```bash
fly logs
```

To follow logs in real-time:

```bash
fly logs --follow
```

## POST /run-digest

The `POST /run-digest` endpoint runs the digest pipeline and returns a JSON result. It requires the `X-API-Key` header to match your `INTERNAL_API_KEY` secret.

### curl example (live source)

```bash
curl -X POST "https://your-app-name.fly.dev/run-digest" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_INTERNAL_API_KEY" \
  -d '{"mailbox": "sorum.crofts@rpck.com", "date": "2025-02-18", "source": "live"}'
```

### curl example with source=stub (no Graph required)

Use `source=stub` to run the pipeline with hardcoded stub meetings. Useful for testing without Microsoft Graph:

```bash
curl -X POST "https://your-app-name.fly.dev/run-digest" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_INTERNAL_API_KEY" \
  -d '{"source": "stub"}'
```

Optional: include HTML in the response:

```bash
curl -X POST "https://your-app-name.fly.dev/run-digest?include_html=true" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_INTERNAL_API_KEY" \
  -d '{"source": "stub"}'
```

**Note:** If `X-API-Key` is missing or invalid, the API returns **HTTP 403**.

---

## Verification

### Check Deployment Status

```bash
fly status
```

### Test Health Endpoint

```bash
curl https://your-app-name.fly.dev/health
```

Expected response:

```json
{"status":"ok"}
```

### View Application Info

```bash
fly info
```

## Common Commands

### View Logs

```bash
# All logs
fly logs

# Follow logs in real-time
fly logs --follow

# Filter logs
fly logs | grep ERROR
```

### Scale Application

```bash
# Scale to 1 instance
fly scale count 1

# Scale to 2 instances
fly scale count 2
```

### SSH into Container

```bash
fly ssh console
```

### View Environment Variables

```bash
fly secrets list
```

### Update Secrets

```bash
fly secrets set KEY=value
```

### Remove Secrets

```bash
fly secrets unset KEY
```

### Restart Application

```bash
fly apps restart gary-asst
```

## Troubleshooting

### Health Check Failing

If `/health` endpoint returns errors:

1. Check logs: `fly logs`
2. Verify the application is running: `fly status`
3. Test locally: `curl http://localhost:8000/health`

### Build Failures

If Docker build fails:

1. Test locally: `docker build -t gary-asst .`
2. Check `Dockerfile` syntax
3. Verify `requirements.txt` is valid

### Application Not Starting

1. Check logs: `fly logs`
2. Verify all secrets are set: `fly secrets list`
3. Check application status: `fly status`

### Port Issues

- Ensure `fly.toml` has `internal_port = 8000`
- Verify Dockerfile exposes port 8000
- Check that uvicorn binds to `0.0.0.0`

## Next Steps

After successful deployment:

1. Configure custom domain (if needed)
2. Set up monitoring and alerts
3. Configure scheduled tasks (when scheduler is implemented)
4. Set up database (when needed)

## Additional Resources

- [Fly.io Documentation](https://fly.io/docs/)
- [Fly.io CLI Reference](https://fly.io/docs/flyctl/)
- [FastAPI Deployment Guide](https://fastapi.tiangolo.com/deployment/)
