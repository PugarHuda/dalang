# Deploying the DALANG ASP (render engine)

The render engine (`server.py` + `pipeline.py` + ffmpeg) runs best on a **container
host** — the repo ships a `Dockerfile`, so Railway/Render/Fly are one command. The
`web/` landing page is separate and already on Vercel.

**Can Vercel host the engine too?** As of 2026, technically yes — Vercel **Fluid
Compute** now runs ffmpeg (bundle a static binary) with up to **800s** duration (Pro),
so the old "no ffmpeg / 60s cap" no longer holds. But it's the harder path for DALANG:
you'd bundle a static ffmpeg, run FastMCP in `stateless_http` mode (serverless keeps no
session between requests), watch the 250 MB bundle cap and cold starts, and the cinematic
tier can poll Venice for minutes. A container gives a persistent MCP endpoint + a real
ffmpeg for free. **Recommended: engine on a container, landing page on Vercel.**

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

## Option D — Vercel (free tier, no container) — via Fluid Compute
The repo ships the serverless entrypoint (`api/index.py`, `vercel.json`, `.vercelignore`):
a stateless MCP app with a **pip-bundled ffmpeg** (`imageio-ffmpeg`), so no Docker needed.
This is a **separate** Vercel project from the landing page.

1. **vercel.com → Add New → Project → import `PugarHuda/dalang`.**
   Set **Root Directory = repo root** (the folder with `api/`, NOT `web/`).
2. **Settings → Functions → enable *Fluid Compute*** (required for ffmpeg + long runs).
   On Pro you can raise `maxDuration` up to 800s; the free/Hobby default in `vercel.json`
   is 300s (fine for the Ken Burns tier).
3. **Settings → Environment Variables → `VENICE_API_KEY`** (+ any `DALANG_X402_*`,
   `DALANG_TOKENGATE_*`, `VENICE_*`). Do **not** commit the key.
4. **Deploy.** Endpoint: `https://<app>.vercel.app/mcp`.

Caveats: serverless keeps no session (we run MCP `stateless_http`); only `/tmp` is
writable (WORKROOT is set there); the **cinematic tier** polls Venice for minutes and can
exceed the duration limit, so prefer it on a container or keep shot counts low on Vercel.
The default **Ken Burns** tier renders comfortably within 300s.

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
