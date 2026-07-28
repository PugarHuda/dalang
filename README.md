# DALANG 🎬 — Storyboard-to-Animatic ASP

*Dalang* is the Indonesian shadow-puppet master who turns a script into a moving
visual performance. This agent does the same: give it an idea or script, and it
returns a **shot list + storyboard + narrated animatic video**.

An **Agentic Service Provider (ASP)** for the **OKX.AI Genesis Hackathon**.
Target: **Artistic Excellence** (an underserved category) + **Social Buzz** (a
shareable demo video). Mode: **A2MCP pay-per-call**.

## ✅ Proven end-to-end
Real runs: shot list → frames → per-shot voiceover → blurred-reframe Ken Burns →
`animatic.mp4` (h264 **1080×1920** + AAC). The landing-page demo ("From Seed to Cup",
20s, 1.4 MB) keeps one recurring barista across 6 shots. HTTP MCP transport tested
with a real client (`tools/list` + `generate_animatic` → data-URI video).

**Performance:** default (`z-image-turbo`, `consistent=True`) ≈ 60–80s per render;
`consistent=False` or a faster editor is quicker. This is a generative ASP — expect
tens of seconds per call, and give the MCP host a generous timeout.

## Architecture — one Venice key for all three stages
```
brief ──► Venice LLM (chat, JSON) ──► shot list
                                         │  per shot
              ┌──────────────────────────┼──────────────────────┐
              ▼                           ▼                      ▼
       Venice image (frame)      Venice TTS (voiceover)   Ken Burns (ffmpeg)
              └────────────────► concat ◄─────────────────────────┘
                                   ▼
                   animatic.mp4 + frames + shot_list.json
```
Venice is OpenAI-compatible, so LLM + image + TTS all run through **one API key**.
One tool, `generate_animatic`, equals one billable call.

## Run locally
```bash
pip install -r requirements.txt          # + ffmpeg on PATH
cp .env.example .env                      # fill in VENICE_API_KEY
export VENICE_API_KEY=...                 # or load .env
python pipeline.py                        # self-check (no API needed)
python server.py                          # start the MCP server (stdio)
```
Call from any MCP client: `generate_animatic(brief="...", aspect_ratio="9:16", target_seconds=30)`.
Options: `style` accepts a preset name (`cinematic`, `anime`, `noir`, `watercolor`,
`claymation`, `storybook`, `3d`) or your own art direction; `template` picks a vertical
structure (`product_ad`, `book_trailer`, `recipe_reel`, `real_estate`, `event_promo`,
`explainer`); `captions=True` burns the spoken line into each shot (readable on muted
autoplay); `voice="..."` picks a TTS voice; `language="Bahasa Indonesia"` writes the
title/voiceover in another language (non-Latin scripts need a caption font via `DALANG_FONT`).
The result includes a `poster_data_uri` (hero frame) for thumbnails/`og:image` and an
`srt` subtitle track (editable soft-subs) alongside the burned-in captions.

**Score + Sting** — `bookends=True` wraps the clip in a branded title card + DALANG end
card; `music="auto"` (or `warm`/`tense`/`upbeat`/`noir`) scores it with a ducked music bed
(bundled beds in `assets/music/`, override via `DALANG_MUSIC_DIR`). Together they turn a
silent tech demo into something that reads as a film — the biggest muted-autoplay lever.

> **Burned-in text needs a `drawtext`-enabled ffmpeg.** The Docker container (real ffmpeg
> + fonts) and local runs burn captions + title/end-card text into the video. The **Vercel
> serverless** build has no `drawtext`, so there text is skipped — the cards render without
> text and captions fall back to the `srt` soft-subs. Run the container for full-fidelity
> burned text; music, Ken Burns, cinematic motion, and provenance work on both.

**Agent composability:** pass a ready-made `shot_list` (the same JSON the tool returns)
to render it directly and skip the LLM — so an upstream "director" agent can own the
storyboard and call DALANG purely as the render primitive.

**Two-tier funnel:** a cheap `storyboard(brief=...)` tool returns just the shot list +
a hero frame (a preview, free at the x402 layer) so a caller can approve the direction
before paying for the full `generate_animatic` render. The hero comes back as a small
JPEG thumbnail — a full-size PNG alone pushed the response past the ~4.5 MB serverless
body cap, and this is the first tool most callers try.

**Serverless gotcha worth keeping:** `api/index.py` builds the MCP app with
`json_response=True`. With the default SSE transport, Vercel's ASGI bridge cancels the
stream before it flushes and **every call returns HTTP 200 with an empty body** — tools
list included. Status-code-only smoke tests never catch it; `vercel logs` shows
`ASGI callable returned without completing response`.

## Native x402 payments on X Layer (OKX A2MCP)
OKX A2MCP settles pay-per-call as an **x402** flow on **X Layer**. DALANG speaks it
natively: set `DALANG_X402_PAYTO` (your X Layer wallet) and the paid `tools/call` answers
**HTTP 402** until the caller pays — the handshake, `tools/list`, `quote` and the
`storyboard` preview stay free. No private key ever touches this server. Off by default
(unset → the free / access_key flow is unchanged). See `okxpay.py` + `test_x402.py`.

**The wire protocol as OKX actually speaks it** — each line below cost a listing
rejection to learn:

| | |
|---|---|
| Challenge out | `PAYMENT-REQUIRED` **response header**, base64 of `{x402Version, resource, accepts:[…]}` — a body-only 402 is not enough |
| Version | **x402 v2**: `amount`, `payTo`, `resource` as an *object*; the v1 keys ride along inside `accepts` for older clients |
| Payment in | `PAYMENT-SIGNATURE` (v2) or `X-PAYMENT` (v1) |
| Proof out | `PAYMENT-RESPONSE` **and** `X-PAYMENT-RESPONSE` |
| Verify/settle | OKX's **official seller SDK** (`pip install okxweb3-app-x402`) when `OKX_API_KEY` / `OKX_SECRET_KEY` / `OKX_PASSPHRASE` are set — the facilitator **403s unsigned calls**, so the credentials are not optional ([Developer Portal](https://web3.okx.com/onchainos/dev-portal)) |

The payment is verified against **our** quoted requirement, never the `accepted` block a
caller claims — otherwise anyone could assert they had agreed to pay 1 atomic unit. The
module is `okxpay.py`, not `x402.py`, because the official SDK installs a package by that
exact name and a local module would shadow it.

This is the piece that only works inside OKX's ecosystem — the render engine is portable,
the *on-chain metered billing* is not.

## Web3 provenance & NFT-ready output
Every render returns on-chain-ready provenance (dep-free, deterministic, no RPC):
- `content_sha256` — a `0x…` SHA-256 fingerprint of the exact animatic bytes.
- `content_cid` — a CIDv1 (raw codec, sha2-256, `bafkrei…`) content fingerprint. It equals
  the `ipfs add --raw-leaves` CID for single-block files (≤256 KiB); a full mp4 gets chunked
  into a different UnixFS DAG root, so treat this as the **exact-bytes fingerprint**, not a
  resolvable pin address. (Anyone can recompute it from the bytes to verify authorship.)
- `mint=True` → `nft_metadata`: OpenSea/ERC-721 metadata (image, animation_url, attributes:
  style/aspect/shots/duration/engine/language), plus off-chain royalty hints
  (`seller_fee_basis_points`) and, if you pass `royalties=[...]`, a co-creator **split** —
  ready to pin + mint on an ERC-721 you deploy on X Layer (this repo ships the metadata and
  the ERC-20 credit token, not the NFT contract). On-chain EIP-2981 needs `royaltyInfo()` on
  that contract; the metadata carries the intent.
- `parent_cid=...` → **remix lineage**: the manifest records the CID this render descends
  from, and the tamper-evident `provenance_digest` covers it — a verifiable on-chain remix
  DAG. `royalties=[{recipient, bps}, …]` → every agent that co-created the video co-owns it.

So the full agentic loop closes on-chain: an agent **pays** per render (x402 on X Layer)
and receives a **provably-authored, mint-ready, co-owned** creative asset. See `provenance.py`.

## Repository layout
```
dalang/
├── pipeline.py     # script → shot list → frames → voiceover → animatic (+ self-check)
├── server.py       # FastMCP server; one tool = one pay-per-call
├── okxpay.py       # x402 v2 gate + OKX seller-SDK verify/settle (opt-in)
├── provenance.py   # content fingerprint + IPFS CID + mint-ready NFT metadata
├── tokengate.py    # X Layer token-gating (balanceOf)
├── contracts/      # DalangCredits.sol — ERC-20 render-credit token (1 credit = 1 render)
├── test_render.py  # offline integration test (real ffmpeg, stubbed Venice)
├── test_x402.py    # x402 payment-gate test (pure)
├── web/            # landing page (deployed to Vercel), embeds the demo video
├── requirements.txt
├── .env.example
└── demo-x-post.md  # #OKXAI post + 90s storyboard
```

## On OKX.AI
DALANG is registered as an **A2MCP ASP — Agent #7234** on X Layer (chain 196), wallet
`0xc87ac386…8307`, paid service `Storyboard to Animatic Video` at **$0.49 USDT0**, live
endpoint `https://dalang-engine.vercel.app/mcp`. Listing status: **under review**.

To list one yourself: register an Agentic Wallet, `agent create` as **A2MCP** with your
deployed `https://…/mcp` endpoint and a per-call fee, then activate → review (~24h).

**What that review actually checks** — four rejections, four distinct causes:
1. **`PAYMENT-REQUIRED` header missing** — the challenge must be a base64 response
   header, not only a JSON body.
2. **Wrong protocol version** — OKX is on **x402 v2**; a v1-only endpoint that rejects
   v2 payloads fails.
3. **Not on the official SDK** — the facilitator 403s unsigned calls, so verification is
   impossible without Developer Portal credentials.
4. **"Missing description / parameter details / usage examples"** — describe the service
   by its exact tool names and arguments, and make sure `tools/list` actually returns the
   schema when they probe it (an empty-body deploy reads as "no parameters").

> Note: the `web/` landing page is on Vercel. The **render engine** runs on a
> container host (Railway/Render/Fly, one command via the shipped `Dockerfile`).
> Vercel *can* now run ffmpeg on **Fluid Compute** (up to 800s), but a persistent
> MCP endpoint + a bundled ffmpeg is simpler and sturdier on a container — see DEPLOY.md.

## Suggested per-call pricing
Venice cost/call ≈ LLM (~$0.01) + 4–10 frames (~$0.01/img, scales with `target_seconds`,
capped at 10) + TTS (~$0.005) ≈ **$0.05–0.12**. Sell at **$0.49/animatic** → healthy
margin, cheap for creators.

## Character consistency
`consistent=True` (default) generates one **hero frame**, then produces every other
frame by **editing the hero into the new scene** (Venice `/image/edit`), so the same
subject — e.g. "Liam, a bearded barista in a cream apron" — recurs across shots.
`consistent=False` makes each frame an independent text-to-image (cheaper, less coherent).

## Cinematic tier — real motion (`cinematic=True`)
Two render engines:
- **Ken Burns** (default) — stills + blurred-reframe pan/zoom. ~$0.05–0.12/animatic, ~60–80s.
- **Cinematic** (`cinematic=True`) — each shot's frame is animated into a real-motion
  clip via Venice **image-to-video** (`/video/queue` → poll `/video/retrieve`, default
  `wan-2-7-image-to-video`, 5s/720p), then reframed to the canvas with captions +
  narration. **PREMIUM: ~$0.55/shot** (a 5-shot clip ≈ $2.75), so it's opt-in and
  capped at `DALANG_MAX_VIDEO_SHOTS` (default 6). A single video failure falls back to
  Ken Burns for that shot, so the render never dies. Price this tier accordingly.

Venice exposed 90+ text/image-to-video models (Wan, Kling, Veo, LTX, …) — pick one via
`VENICE_VIDEO_MODEL`. (Earlier the video endpoints 404'd; that block has since lifted.)

## Calibration knobs (env — ponytail)
- `VENICE_LLM_MODEL` (default `qwen3-235b-a22b-instruct-2507`) — clean, strong JSON.
- `VENICE_IMAGE_MODEL` (default `z-image-turbo`; demo used `flux-2-pro`) — trade speed for fidelity.
- `VENICE_EDIT_MODEL` (default `qwen-image-2-edit`) — the reference/consistency editor.
- `VENICE_TTS_MODEL` / `VENICE_TTS_VOICE` (default `tts-kokoro` / `af_sky`) — swap for a multilingual voice as needed.
- `DALANG_FONT` — TTF for caption `drawtext`; defaults to DejaVu (installed in the image) / a system font locally.
- Ken Burns `zoompan_filter()` — linear ramps; switch to eased curves if motion looks robotic.
- Caption `_caption_filter()` — fontsize/position are ratios of height; tune if a language runs long.
- Next knob: a music bed (Venice has no music model yet — needs an asset or another provider).

## Security
`.env` is gitignored; never commit the key. Any key that has appeared in a chat
or screenshot **must be rotated** in the Venice dashboard.
