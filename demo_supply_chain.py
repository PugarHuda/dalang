"""Creative supply chain — DALANG as a paid node in an autonomous agent economy.

A story in code: four agents collaborate to ship a social video, each PAYING the next
per call via x402 on X Layer. DALANG is the render primitive in the middle. This is the
OKX.AI thesis made concrete — agents doing real business, settling on-chain.

    python demo_supply_chain.py            # calls the live ASP for a real render
    DALANG_MCP_URL=... python demo_supply_chain.py

The surrounding agents are stubbed (an LLM call each in reality); the DALANG render is
REAL — it hits the deployed ASP and returns an actual animatic + on-chain provenance.
Payments are illustrated (in production the OKX Agentic Wallet auto-pays via x402).
"""
import asyncio, os
from fastmcp import Client

MCP_URL = os.environ.get("DALANG_MCP_URL", "https://dalang-engine.vercel.app/mcp")

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
    pay("copywriter-agent", "DALANG (ASP)", 0.49, "brief → narrated animatic")
    print(f"③ DALANG ASP    — rendering at {MCP_URL}")
    async with Client(MCP_URL) as c:
        r = await c.call_tool("generate_animatic",
                              {"brief": brief, "target_seconds": 8, "aspect_ratio": "9:16", "mint": True})
        out = r.structured_content or {}
    if "error" in out:
        print("    ✗ render error:", out["error"][:120]); return None
    print(f"    → “{out['title']}”  {out['duration_seconds']}s  ({out['animatic_bytes']} bytes)")
    print(f"    → provenance: {out['content_cid'][:20]}…  digest {out['provenance_digest'][:14]}…")
    print(f"    → mint-ready: nft_metadata present = {bool(out.get('nft_metadata'))}")
    return out

def distribution_agent(out):
    pay("client", "distribution-agent", 0.03, "post + anchor provenance")
    print("④ distribution-agent — posting the clip + anchoring provenance on X Layer")
    print(f"    → would POST the animatic to social with #OKXAI")
    print(f"    → would store {out['provenance_digest'][:14]}… on X Layer (tamper-evident proof-of-creation)")

async def main():
    print("\n=== Creative supply chain: agents paying agents on X Layer ===\n")
    topic = trend_agent()
    brief = copywriter_agent(topic)
    out = await dalang_render(brief)
    if out:
        distribution_agent(out)
        print("\n✓ One idea → a paid, provably-authored, mint-ready video — no human in the loop.")
        print("  DALANG earned $0.49 in USDT on X Layer for one tool call.\n")

if __name__ == "__main__":
    asyncio.run(main())
