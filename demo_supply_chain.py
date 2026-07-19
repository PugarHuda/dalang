"""Creative supply chain — DALANG as a paid node in an autonomous agent economy.

A story in code: four agents collaborate to ship a social video, each PAYING the next
per call via x402 on X Layer. DALANG is the render primitive in the middle. This is the
OKX.AI thesis made concrete — agents doing real business, settling on-chain — and it's
the 60-second live demo: one sentence in, an HTTP 402 challenge, an on-chain settle, and
a scored, provably-authored, co-owned video out, with no human in the loop.

    python demo_supply_chain.py            # calls the live ASP for a real render
    DALANG_MCP_URL=... python demo_supply_chain.py

The surrounding agents are stubbed (an LLM call each in reality); the DALANG render is
REAL — it hits the deployed ASP and returns an actual animatic + on-chain provenance.
Payments are illustrated (in production the OKX Agentic Wallet auto-pays via x402).
"""
import asyncio, os, sys
from fastmcp import Client

try:  # the emoji/arrows below need UTF-8; a Windows cp1252 console would crash on them
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MCP_URL = os.environ.get("DALANG_MCP_URL", "https://dalang-engine.vercel.app/mcp")

# Each agent has an X Layer wallet — and each co-OWNS the finished video via a royalty
# split, so secondary sales pay everyone who helped make it (the agent-economy thesis:
# agents don't just pay per call, they co-own what they create).
WALLETS = {"trend": "0x7ends", "writer": "0xWr1ter", "dalang": "0xDA1a46", "distro": "0xD15750"}
SPLIT = [{"recipient": WALLETS["trend"], "bps": 150},    # 1.5% to the trend-spotter
         {"recipient": WALLETS["writer"], "bps": 350},   # 3.5% to the copywriter
         {"recipient": WALLETS["dalang"], "bps": 500}]   # 5%   to DALANG (the render node)

def pay(frm, to, usd, what):
    # In production this is an x402 402->pay->settle on X Layer (USDT/USDG via APP).
    print(f"    💸 x402: {frm} → {to}  ${usd:<5} (USDT · X Layer)   for: {what}")

def trend_agent():
    print("① trend-agent  — scanning X Layer / social for a hook")
    topic = "the quiet magic of a neighborhood ramen shop at 2am"
    print(f"    → picked: “{topic}”")
    return topic

def copywriter_agent(topic):
    pay("trend-agent", "copywriter-agent", 0.02, "topic → brief")
    print("② copywriter-agent — turning the topic into a director's brief")
    brief = f"A lone chef finishing the last bowl at a rain-slicked midnight ramen stall; {topic}"
    print(f"    → brief: “{brief[:60]}…”")
    return brief

async def dalang_render(brief):
    print("③ DALANG ASP    — the paid render node")
    print(f"    ↔ POST {MCP_URL}  (generate_animatic)")
    print( "    ← HTTP 402 Payment Required  — x402 challenge (scheme=exact, USDT · X Layer)")
    pay("copywriter-agent", "DALANG (ASP)", 0.49, "brief → narrated animatic")
    print( "    → X-PAYMENT header (signed transfer authorization) → settle on X Layer")
    async with Client(MCP_URL) as c:
        r = await c.call_tool("generate_animatic", {
            "brief": brief, "target_seconds": 8, "aspect_ratio": "9:16",
            "bookends": True, "music": "auto",   # Score + Sting: title/end cards + a scored bed
            "mint": True, "royalties": SPLIT})   # mint-ready NFT with a co-creator royalty split
        out = r.structured_content or {}
    if "error" in out:
        print("    ✗ render error:", out["error"][:120]); return None
    print(f"    ✓ settled — DALANG earned $0.49 USDT on X Layer for one tool call")
    print(f"    → “{out['title']}”  {out['duration_seconds']}s  ({out['animatic_bytes']} bytes)")
    print(f"    → provenance: cid {out['content_cid'][:20]}…  digest {out['provenance_digest'][:14]}…")
    split = out.get("nft_metadata", {}).get("properties", {}).get("royalty", {})
    print(f"    → co-owned NFT: {len(split.get('splits', []))} co-creators, {split.get('total_bps', 0)/100:.1f}% royalty split")
    return out

def distribution_agent(out):
    pay("client", "distribution-agent", 0.03, "post + anchor provenance")
    print("④ distribution-agent — posting the clip + anchoring provenance on X Layer")
    print(f"    → would POST the scored animatic to social with #OKXAI")
    print(f"    → would store {out['provenance_digest'][:14]}… on X Layer (tamper-evident proof-of-creation)")
    print(f"    → a remix would call generate_animatic(parent_cid=\"{out['content_cid'][:16]}…\") → on-chain lineage")

async def main():
    print("\n=== Creative supply chain: agents paying agents on X Layer ===\n")
    topic = trend_agent()
    brief = copywriter_agent(topic)
    out = await dalang_render(brief)
    if out:
        distribution_agent(out)
        print("\n✓ One sentence → a paid, scored, provably-authored, co-owned video — no human in the loop.")
        print("  Every agent that touched it earns on secondary sales. That's the agent economy.\n")

if __name__ == "__main__":
    asyncio.run(main())
