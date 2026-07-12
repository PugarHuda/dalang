# Deploying the DALANG ASP (render engine)

The render engine (`server.py` + `pipeline.py` + ffmpeg) needs a **container host** —
NOT Vercel serverless (no ffmpeg, 60s cap). The `web/` landing page is separate and
already on Vercel. Any Docker host works; the repo ships a `Dockerfile`.

## Option A — Railway (fastest)
1. railway.app → New Project → Deploy from GitHub repo → `PugarHuda/dalang`.
2. Railway auto-detects the `Dockerfile`.
3. Variables → add `VENICE_API_KEY=...` (and optional `VENICE_*` model overrides).
4. Deploy. Railway injects `PORT`; `server.py` starts the HTTP MCP transport.
5. Public URL → the MCP endpoint is `https://<app>.up.railway.app/mcp`.

## Option B — Render
1. render.com → New → Web Service → connect the repo.
2. Runtime: Docker. Add env `VENICE_API_KEY`. Deploy.
3. Endpoint: `https://<app>.onrender.com/mcp`.

## Option C — Fly.io
```bash
fly launch --no-deploy          # detects Dockerfile
fly secrets set VENICE_API_KEY=...
fly deploy
# endpoint: https://<app>.fly.dev/mcp
```

## Smoke test after deploy
```bash
curl -s https://<host>/mcp -H "Accept: text/event-stream" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head
# expect the generate_animatic tool in the response
```

## Register on OKX.AI
1. OKX Agentic Wallet → `okx.ai/tutorial/asp` → mode **A2MCP**.
2. Register the `/mcp` endpoint URL as your ASP; set the per-call price.
3. Pass internal review → go live. Then post the demo on X with **#OKXAI**.

> Cost per call ≈ $0.05–0.08 (Venice LLM + images + TTS). Keep `VENICE_API_KEY`
> only in the host's secret store — never in the repo.
