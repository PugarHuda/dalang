#!/usr/bin/env bash
# Heartbeat loop. Waits until the wallet is logged in (do that once via `fly ssh console`),
# then reports the OKX agent online every 10 minutes. Session persists on the mounted volume.
export PATH="/root/.local/bin:$PATH"
CHAIN=196   # X Layer

onchainos preflight --skill-version 4.3.0 >/dev/null 2>&1 || true
echo "[keep-online] started $(date -u)"

while true; do
  if onchainos wallet status 2>/dev/null | grep -q '"loggedIn":true'; then
    if onchainos agent heartbeat --chain-index "$CHAIN" >/dev/null 2>&1; then
      echo "[keep-online] heartbeat ok $(date -u)"
    else
      echo "[keep-online] heartbeat FAILED $(date -u)"
    fi
  else
    echo "[keep-online] NOT logged in. Run once:  fly ssh console  ->  onchainos wallet login --phase init  (open URL, sign in hudapugar@gmail.com)  ->  onchainos wallet login --phase poll"
  fi
  sleep 600
done
