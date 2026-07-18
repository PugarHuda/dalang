# DALANG — Demo assets for #OKXAI

Live ASP endpoint: `https://dalang-engine.vercel.app/mcp` · Landing: (Vercel) · Repo: github.com/PugarHuda/dalang

## Main X post (lead with what's unique)
> Meet **DALANG** 🎬 — an AI agent that turns **one line of script** into a
> **narrated, real-motion animatic** — and gets paid for it **on-chain**.
>
> Brief in → storyboard, frames, voiceover, burned-in captions, real camera motion out.
> Live on @okx AI: agents pay per call in **USDT on X Layer** (x402). Every render comes
> back **mint-ready** with on-chain provenance.
>
> One idea → a paid, provably-authored video. No human in the loop. 👇 #OKXAI

*(attach the ≤90s demo — use the cinematic "Midnight Noodle Chef" clip)*

## Thread (drives Social Buzz)
> 1/ Making an animatic by hand takes hours. DALANG does it in ~60s from one sentence —
>    shot list → frames (with a **recurring character**) → per-shot voiceover → captions →
>    a finished 9:16 MP4.
>
> 2/ Two render engines: **Ken Burns** (fast, cheap) and a **CINEMATIC tier** — each shot
>    animated into *real motion* via image-to-video. Not pan/zoom. Actual movement. 🎥
>
> 3/ It's a real **on-chain business**, not a demo. DALANG is a native **x402** endpoint:
>    the calling agent's OKX Agentic Wallet auto-pays per render, settled in USDT/USDG on
>    **X Layer** — gas-free, instant, no escrow.
>
> 4/ Every output is **Web3-native**: a content fingerprint + IPFS CID + a tamper-evident
>    **proof-of-creation** you can anchor on X Layer, plus **ERC-721 metadata** (with EIP-2981
>    royalties) so any animatic is mint-ready. Authenticity in the age of AI slop.
>
> 5/ It's **composable**: another agent can hand DALANG a `shot_list` and use it as a pure
>    render primitive. A trend-agent → copywriter-agent → **DALANG** → distribution-agent
>    pipeline, each paying the next on X Layer. This is the agent economy, working.
>
> 6/ Multilingual out of the box (yes, Bahasa Indonesia 🇮🇩 — *dalang* is our shadow-puppet
>    master). Live now, pay-per-call: [ASP link]  #OKXAI

## 90-second demo storyboard (shot by shot)
| t (sec) | On screen | VO / text |
|---------|-----------|-----------|
| 0–6   | Black → "An animatic used to take hours." (struck through) | hook |
| 6–16  | An agent sends one line to the MCP client: *"neon ramen stall at midnight, cinematic, 9:16"* | "One brief. One agent-to-agent call." |
| 16–24 | HTTP **402** flashes → **X-PAYMENT** → settled: `$0.49 USDT · X Layer` tx hash | "It pays on-chain. x402." |
| 24–36 | Shot-list JSON streams in; the recurring chef appears across thumbnails | "An LLM directs it. One character, every shot." |
| 36–62 | The **cinematic** animatic plays full-screen — real motion, steam, neon, narration + captions | let the video speak |
| 62–74 | Response panel: `content_cid`, `provenance_digest`, `nft_metadata` | "Mint-ready. Provenance on X Layer." |
| 74–84 | OKX.AI tab: `generate_animatic` listed, per-call price, USDT settlement | "Live on OKX AI. Pay per call." |
| 84–90 | DALANG logo + "Build. Narrate. Ship — on-chain." | CTA |

## Alt short post (punchy)
> An agent typed one sentence. DALANG returned a **narrated, real-motion video** — and
> charged **$0.49 in USDT on X Layer** for it. Mint-ready, provenance on-chain. Live on
> @okx AI. 🎬 #OKXAI

## Submission checklist
- [ ] Rotate VENICE_API_KEY, update the Vercel env var
- [ ] ASP live + registered on okx.ai in A2MCP mode (passed review) — REQUIRED
- [ ] Set x402 config on the host (DALANG_X402_PAYTO / ASSET / FACILITATOR from OKX)
- [ ] ≤90s video (cinematic demo) + #OKXAI in the X post
- [ ] Google Form: ASP details + link to the X post
