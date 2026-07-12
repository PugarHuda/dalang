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
A raw `curl` won't work — MCP streamable HTTP needs the `initialize` handshake and a
session. Use a FastMCP client (`pip install fastmcp`):
```bash
python - <<'PY'
import asyncio
from fastmcp import Client
async def main():
    async with Client("https://<host>/mcp") as c:      # e.g. .../mcp
        print("tools:", [t.name for t in await c.list_tools()])
asyncio.run(main())
PY
# expect: tools: ['generate_animatic']
```

## Register on OKX.AI
1. OKX Agentic Wallet → `okx.ai/tutorial/asp` → mode **A2MCP**.
2. Register the `/mcp` endpoint URL as your ASP; set the per-call price.
3. Pass internal review → go live. Then post the demo on X with **#OKXAI**.

> Cost per call ≈ $0.05–0.08 (Venice LLM + images + TTS). Keep `VENICE_API_KEY`
> only in the host's secret store — never in the repo.

## Protect a directly-exposed endpoint
`/mcp` runs paid compute. Behind OKX's A2MCP gating you can leave it open, but if the
URL is reachable publicly, set **`DALANG_ACCESS_KEY`** — the tool then rejects any call
without a matching `access_key` argument, so a leaked URL can't drain your Venice balance.
Per-render files are cleaned automatically (set `DALANG_KEEP_FILES=1` to keep them for debugging).
