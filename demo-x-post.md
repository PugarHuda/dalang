# DALANG — X post + 90s demo script for #OKXAI

Live ASP: OKX Agent ID **#7234** (X Layer, under review) · Endpoint: `https://dalang-engine.vercel.app/mcp`
Landing: https://dalang-studio.vercel.app · Repo: github.com/PugarHuda/dalang
Fill the ‹brackets›. Attach the ≤90s video (no separate upload — it lives in the post).

> Framing: DALANG is **live and PAID** on OKX.AI — pay-per-call **$0.49 in USDT0 on X Layer**
> via real x402 (OKX facilitator). Lead with the working on-chain business; the free `storyboard`
> + `quote` tiers let people try direction before paying. Billing is REAL, not illustrative.

---

## ✅ MAIN POST (copy-paste, then attach the video)

> Meet **DALANG** 🎬 — a live agent on @OKX AI that turns **one line of script** into a
> **narrated animatic video**, in a single call.
>
> Brief in → shot list, consistent frames, voiceover, captions → a finished 9:16 film out.
>
> Pay-per-call **$0.49 in USDT0 on X Layer** (real x402) — and every render comes back
> **mint-ready**: on-chain provenance + co-creator royalty splits. (Free `storyboard` preview
> to try direction first.)
>
> One sentence → a paid, provably-authored, co-owned video. No human in the loop. 👇 #OKXAI

*(attach: the 90s demo below, or the cinematic "Midnight Noodle Chef" clip)*

---

## 🧵 THREAD (drives Social Buzz — post under the main tweet)

> 1/ An animatic by hand takes hours. DALANG does it in ~60s from one sentence: shot list →
> frames with a **recurring character** → per-shot voiceover → burned-in captions → a
> finished 9:16 MP4. **Free to try on @OKX AI right now.** 🎬
>
> 2/ Two engines. **Ken Burns** (fast, free tier) and a **CINEMATIC** tier that animates every
> shot into *real motion* via image-to-video — not pan/zoom, actual movement. 🎥
>
> 3/ Built for the agent economy: DALANG is a native **x402** endpoint on **X Layer** —
> pay-per-call ready, so a calling agent's OKX wallet can auto-settle each render on-chain,
> instant, no escrow. (Free while we launch.)
>
> 4/ Every output is **Web3-native**: a content fingerprint (SHA-256 + IPFS CIDv1) + a
> tamper-evident **proof-of-creation** you can anchor on X Layer, plus **ERC-721 metadata**
> with **co-creator royalty splits** — mint-ready. Verify any render yourself in the browser.
> Authenticity in the age of AI slop. 🔗
>
> 5/ It's **composable**: another agent hands DALANG a `shot_list` and uses it as a pure render
> primitive. trend-agent → copywriter → **DALANG** → distribution. The agent economy, running.
>
> 6/ Multilingual out of the box (yes, Bahasa Indonesia 🇮🇩 — *dalang* = the shadow-puppet
> master). A free storyboard-preview tier lets you approve direction first.
> Try it → https://dalang-studio.vercel.app  · OKX Agent ID #7234  #OKXAI

---

## 🎥 90-SECOND DEMO — production script (shot by shot)

Format: **screen recording**, portrait or 16:9, subtitles ON. Record these, cut to time.
Assets: a terminal (a real FREE render against the live endpoint), the cinematic showcase clip
(`web/gallery/cinematic-noodle-chef.mp4`), the landing page (provenance verifier), the OKX.AI listing.

| # | t | RECORD THIS (visual) | On-screen text | Voiceover |
|---|-----|----------------------|----------------|-----------|
| 1 | 0–7 | Black. A hand-typed line appears: *"a lone chef at a rain-slicked midnight ramen stall"* | "This is the only input." | "One sentence. That's all it takes." |
| 2 | 7–20 | Terminal: an MCP call to the live endpoint returns a real animatic (the free Ken Burns tier) — shots + a video path stream back | Live on OKX AI · free to try | "An agent calls DALANG on OKX AI — and gets a finished, narrated video back." |
| 3 | 20–30 | Split: the x402 architecture — a `402 Payment Required` challenge body + `USDT · X Layer` (from the x402 layer / demo_supply_chain.py) | x402-native · X Layer | "It's built to be paid per call — a native x402 endpoint on X Layer. Free while we launch." |
| 4 | 30–56 | **The cinematic animatic plays full-screen** — real motion, steam, neon, narration + captions | (let it breathe) | (natural audio — narration + captions carry it) |
| 5 | 56–68 | Response panel: `content_cid: bafkrei…`, `provenance_digest: 0x…`, `nft_metadata` with a 3-way royalty split | Mint-ready · provenance on X Layer | "Every render comes back mint-ready — a fingerprint, on-chain provenance, and royalty splits so every agent that helped co-owns it." |
| 6 | 68–80 | Browser (dalang-studio.vercel.app): **drag the rendered mp4 onto the verifier** — `content_cid` recomputes → **✓ MATCH** | Verify it yourself | "Don't trust it — verify. Recompute the fingerprint in your browser. It matches. Authenticity you can prove." |
| 7 | 80–90 | OKX.AI: DALANG (#7234) listed — `generate_animatic`. Cut to logo: **DALANG — build, narrate, ship. On-chain.** | Live on OKX AI · #OKXAI | "Live on OKX AI. One sentence in, a provably-authored film out." |

Timing: beats 4 (video) and 6 (verify) are the memorable ones — give them room; trim 3 & 5 if over 90s.
Beat 6 (browser CID match) is unique — don't cut it.

Honesty for the recording: the endpoint is a **real PAID x402 endpoint** — a live `generate_animatic`
call returns a real HTTP 402 (eip155:196, USDT0, $0.49) and settles through **OKX's facilitator**
(web3.okx.com/facilitator). To show a **real settled tx** in beat 3, fund a caller wallet with a
little USDT0 on X Layer and pay via `onchainos payment quote/pay` — you'll get a real txHash (don't
fake one). The cinematic clip (beat 4) is a real DALANG output rendered offline (cinematic is off on
the paid endpoint since a flat $0.49 fee wouldn't cover the ~$0.55/shot video cost).

---

## Alt 1-tweet (if you skip the thread)
> An agent typed one sentence. DALANG returned a **narrated animatic video** — mint-ready, with
> on-chain provenance you can verify yourself. **Free to try**, built x402-native on X Layer.
> Live on @OKX AI (#7234). 🎬 #OKXAI

---

## Pre-post checklist
- [ ] Rotate VENICE_API_KEY + set a Venice spend cap (public endpoint uses it) — update the Vercel env
- [x] ASP registered on OKX.AI (A2MCP, #7234) — under review (approval gates final eligibility)
- [x] Landing page live: https://dalang-studio.vercel.app
- [ ] Record beats 1–7, cut to ≤90s, subtitles ON
- [ ] Post main tweet + thread with #OKXAI and @OKX; grab the link
- [ ] Google Form: paste from SUBMISSION.md + Agent ID 7234 + the X post link (before Jul 27 23:59 UTC)
