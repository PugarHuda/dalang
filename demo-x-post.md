# DALANG — X post + 90s demo script for #OKXAI

Endpoint: `https://dalang-engine.vercel.app/mcp` · Landing: https://dalang-hudas-projects-a8e7f558.vercel.app · Repo: github.com/PugarHuda/dalang · OKX Agent ID: #7234 (under review)
Fill the ‹brackets› before posting. Attach the ≤90s video (no separate upload — it lives in the post).

---

## ✅ MAIN POST (copy-paste, then attach the video)

> Meet **DALANG** 🎬 — an AI agent that turns **one line of script** into a **narrated,
> real-motion animatic**, and gets paid for it **on-chain**.
>
> Brief in → shot list, consistent frames, voiceover, captions, real camera motion → a
> finished 9:16 film out. One agent call.
>
> Live on @OKX AI: agents pay per call in **USDT on X Layer** (x402). Every render comes
> back **mint-ready** — on-chain provenance + co-creator royalty splits.
>
> One sentence → a paid, provably-authored, co-owned video. No human in the loop. 👇 #OKXAI

*(attach: the cinematic "Midnight Noodle Chef" clip, or the 90s demo below)*

---

## 🧵 THREAD (drives Social Buzz — post under the main tweet)

> 1/ An animatic by hand takes hours. DALANG does it in ~60s from one sentence: shot list →
> frames with a **recurring character** → per-shot voiceover → burned-in captions → a
> finished 9:16 MP4. 🎬
>
> 2/ Two engines. **Ken Burns** (fast, ~$0.08) and a **CINEMATIC** tier that animates every
> shot into *real motion* via image-to-video — not pan/zoom, actual movement. 🎥
>
> 3/ It's a real **on-chain business**. DALANG is a native **x402** endpoint: the calling
> agent's OKX wallet auto-pays per render, settled in **USDT on X Layer** — instant, no escrow.
>
> 4/ Every output is **Web3-native**: a content fingerprint (SHA-256 + IPFS CIDv1) + a
> tamper-evident **proof-of-creation** you can anchor on X Layer, plus **ERC-721 metadata**
> with **co-creator royalty splits** — mint-ready. Authenticity in the age of AI slop.
>
> 5/ It's **composable**: another agent hands DALANG a `shot_list` and uses it as a pure render
> primitive. trend-agent → copywriter → **DALANG** → distribution — each paying the next on
> X Layer. The agent economy, actually running. 🔗
>
> 6/ Multilingual out of the box (yes, Bahasa Indonesia 🇮🇩 — *dalang* = the shadow-puppet
> master). A free storyboard-preview tier lets you approve direction before you pay.
> Live now, pay-per-call → ‹ASP link›  #OKXAI

---

## 🎥 90-SECOND DEMO — production script (shot by shot)

Format: **screen recording**, portrait or 16:9, subtitles ON. Record these clips, cut to time.
Assets: terminal running `python demo_supply_chain.py` (real render vs the live endpoint +
illustrative payment prints), the cinematic clip (`web/gallery/cinematic-noodle-chef.mp4` or
Desktop), the landing page (provenance verifier), the OKX.AI listing.

| # | t | RECORD THIS (visual) | On-screen text | Voiceover |
|---|-----|----------------------|----------------|-----------|
| 1 | 0–7 | Black. A hand-typed line appears: *"a lone chef at a rain-slicked midnight ramen stall"* | "This is the only input." | "One sentence. That's all it takes." |
| 2 | 7–16 | Terminal: run `python demo_supply_chain.py`. Lines print: trend-agent → copywriter → **DALANG ASP** | #OKXAI · agents calling agents | "An agent hands the brief to another agent — DALANG, on OKX AI." |
| 3 | 16–28 | Terminal highlights: `← HTTP 402` then `💸 x402 → DALANG $0.49 (USDT · X Layer)` then `✓ settled` | x402 · X Layer | "It's a paid endpoint. The caller pays on-chain — x402 on X Layer. No human, no invoice." |
| 4 | 28–56 | **The cinematic animatic plays full-screen** — real motion, steam, neon, narration + captions | (let it breathe) | (natural audio of the clip — narration + captions carry it) |
| 5 | 56–68 | Terminal/response panel: `content_cid: bafkrei…`, `provenance_digest: 0x…`, `nft_metadata` with a 3-way royalty split | Mint-ready · provenance on X Layer | "Every render comes back mint-ready — a fingerprint, on-chain provenance, and royalty splits so every agent that helped co-owns it." |
| 6 | 68–80 | Browser: the landing page verifier. **Drag the rendered mp4 onto it** — `content_cid` recomputes and shows **✓ MATCH** | Verify it yourself | "Don't trust it — verify. Recompute the fingerprint in your browser. It matches. Authenticity you can prove." |
| 7 | 80–90 | OKX.AI: DALANG listed — `generate_animatic`, per-call price, USDT settlement. Cut to logo: **DALANG — build, narrate, ship. On-chain.** | Live on OKX AI · pay per call · #OKXAI | "Live on OKX AI. One sentence in, a paid, provably-authored film out." |

Timing notes: beats 4 (video) and 6 (verify) are the memorable ones — give them room; trim
2–3 and 5 if over 90s. Beat 6 (browser CID match) is unique — don't cut it.

Honesty for the recording: the **render is real** (live endpoint). The x402 **402 challenge is
real**; the **settle** line is illustrative until OKX's facilitator is wired (`demo_supply_chain.py`
prints the flow). Show the real 402 + narrate settlement — don't fake a tx hash you can't produce.

---

## Alt 1-tweet (if you skip the thread)
> An agent typed one sentence. DALANG returned a **narrated, real-motion video** — and charged
> **$0.49 in USDT on X Layer** for it. Mint-ready, provenance on-chain, verify it yourself.
> Live on @OKX AI. 🎬 #OKXAI

---

## Pre-post checklist
- [ ] Rotate VENICE_API_KEY + update the Vercel env var (public endpoint uses it)
- [ ] ASP listed + live on OKX.AI in A2MCP mode (passed review) — REQUIRED, gates everything
- [ ] Landing page deployed (public URL for the post + the X Layer form)
- [ ] Record beats 1–7, cut to ≤90s, subtitles ON
- [ ] Post main tweet + thread with #OKXAI and @OKX; grab the link
- [ ] Google Form: paste from SUBMISSION.md + the X post link + the Agent ID
