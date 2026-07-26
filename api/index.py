"""Vercel (Fluid Compute) entrypoint for the DALANG render engine.

Serves the MCP endpoint at /mcp as a **stateless** ASGI app (serverless keeps no
session between requests) using a **pip-bundled ffmpeg** (no system binary on Vercel).

Deploy checklist (see DEPLOY.md):
  - Enable **Fluid Compute** on the Vercel project (Settings → Functions).
  - Set env `VENICE_API_KEY` (and any DALANG_X402_* / DALANG_TOKENGATE_* / VENICE_* ).
  - maxDuration is set in vercel.json; raise it (Pro, up to 800s) for long renders.
  - Only `/tmp` is writable on serverless → WORKROOT points there.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point ffmpeg at the pip-bundled static binary BEFORE importing pipeline (it resolves
# the ffmpeg path at import time). imageio-ffmpeg ships a Linux build that runs on Vercel.
try:
    import imageio_ffmpeg
    os.environ.setdefault("FFMPEG_BINARY", imageio_ffmpeg.get_ffmpeg_exe())
except Exception:
    pass
os.environ.setdefault("DALANG_WORKROOT", "/tmp/dalang")  # only /tmp is writable on serverless

import server, pipeline  # loads .env, builds mcp + the x402/tokengate gates

# Cold-start health check: fail LOUD in the logs if ffmpeg isn't actually runnable,
# instead of every paid render dying with an opaque "render failed" at pay time.
try:
    import subprocess
    subprocess.run([pipeline.FFMPEG, "-version"], capture_output=True, timeout=10, check=True)
    print("[dalang] ffmpeg ok:", pipeline.FFMPEG)
except Exception as e:
    print("[dalang] WARNING ffmpeg not runnable:", pipeline.FFMPEG, "->", e)

# stateless_http: every request is self-contained, which is what a serverless function
# needs (no in-memory MCP session carried across invocations / instances).
# json_response: REQUIRED on Vercel. With the default SSE transport the ASGI bridge kills
# the stream before it flushes ("ASGI callable returned without completing response" in the
# function log) and callers get HTTP 200 with an EMPTY body on every tool call.
app = server.mcp.http_app(stateless_http=True, json_response=True)
if server.x402.enabled():  # native x402 paid endpoint on X Layer, if configured
    app.add_middleware(server.x402.X402Middleware)
