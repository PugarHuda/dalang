# Keep the DALANG agent "online" 24/7 on Fly.io

DALANG (A2MCP) already serves paid renders 24/7 from the Vercel endpoint — this worker is
**only** for the OKX marketplace "online" heartbeat (discoverability). It runs
`onchainos agent heartbeat` every 10 min; the wallet session lives on a persistent Fly volume.

## One-time setup
Install flyctl (`iwr https://fly.io/install.ps1 -useb | iex` on Windows) and `fly auth login`, then
from this folder (`deploy/fly/`):

```bash
# 1) create the app (no deploy yet), a 1GB volume, and the smallest VM
fly launch --no-deploy --name dalang-keeponline --region sin
fly volumes create onchainos_data --region sin --size 1

# 2) build + deploy the worker
fly deploy

# 3) log the wallet in ONCE (session persists on the volume)
fly ssh console
#   inside the machine:
onchainos wallet login --phase init      # prints a URL — open it in your browser, sign in hudapugar@gmail.com
onchainos wallet login --phase poll      # after you finish in the browser
exit

# 4) confirm it's beating
fly logs        # look for "[keep-online] heartbeat ok"
```

That's it — the agent reports online 24/7 with no PC needed.

## Cost
A 256MB shared-cpu worker that sleeps between heartbeats is tiny; Fly's pay-as-you-go
free allowance usually covers it (≈ a couple of dollars/month at most if over). Scale to
zero isn't used here — a heartbeat worker must stay running.

## Cheaper/forever-free alternative
An **Oracle Cloud "Always Free"** VM is free forever — see `../keep-online.sh` (same heartbeat,
via cron on a plain Ubuntu VM).
