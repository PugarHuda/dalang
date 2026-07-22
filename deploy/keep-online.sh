#!/usr/bin/env bash
# DALANG — keep the OKX agent (#7234) "online" 24/7 on any always-on Linux host.
# Recommended host: Oracle Cloud "Always Free" VM (Ubuntu) — free forever.
#
# WHY (read first): DALANG is an A2MCP service. Its paid renders are served by the
# Vercel endpoint (dalang-engine.vercel.app/mcp) 24/7 — that already works even if your
# PC is off. This script is ONLY for the marketplace "online" heartbeat (discoverability).
# The okx-a2a daemon is for AGENT-TO-AGENT (A2A) chat, which DALANG (A2MCP) does not use.
#
# Run this ONCE on a fresh Ubuntu VM, then follow the printed login step.

set -e
EMAIL="hudapugar@gmail.com"
CHAIN=196   # X Layer

echo "==> [1/4] Install the onchainos CLI"
curl -sSL https://raw.githubusercontent.com/okx/onchainos-skills/main/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
grep -q '.local/bin' ~/.bashrc 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

echo "==> [2/4] Preflight"
onchainos preflight --skill-version 4.3.0 || true

echo "==> [3/4] Log in to the Agentic Wallet (this VM needs its OWN session)"
echo "    A URL will be printed. Open it in ANY browser and sign in with: $EMAIL"
onchainos wallet login --phase init
echo ""
read -p "    After you finish login in the browser, press ENTER to continue..." _
onchainos wallet login --phase poll
echo "    Logged in as: $(onchainos wallet status 2>/dev/null | grep -o '\"email\":\"[^\"]*\"' || echo '?')"

echo "==> [4/4] Install a heartbeat cron (every 10 min) so the agent stays 'online'"
CRON="*/10 * * * * \$HOME/.local/bin/onchainos agent heartbeat --chain-index $CHAIN >> \$HOME/dalang-heartbeat.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'agent heartbeat' ; echo "$CRON" ) | crontab -
onchainos agent heartbeat --chain-index $CHAIN >/dev/null 2>&1 && echo "    First heartbeat sent."
echo ""
echo "DONE. The agent will report online every 10 min from this VM, 24/7 — no PC needed."
echo "Check: crontab -l   |   tail -f ~/dalang-heartbeat.log"
echo ""
echo "OPTIONAL — also receive A2A tasks (not needed for A2MCP/DALANG):"
echo "  npm i -g @okxweb3/a2a-node && okx-a2a doctor --fix"
