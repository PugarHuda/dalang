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

## Repository layout
```
dalang/
├── pipeline.py     # script → shot list → frames → voiceover → animatic (+ self-check)
├── server.py       # FastMCP server; one tool = one pay-per-call
├── web/            # landing page (deployed to Vercel), embeds the demo video
├── requirements.txt
├── .env.example
└── demo-x-post.md  # #OKXAI post + 90s storyboard
```

## List on OKX.AI (required to be eligible)
1. Register an OKX Agentic Wallet → `okx.ai/tutorial/asp`, choose **A2MCP** mode.
2. Deploy `server.py` on a container/MCP host and register its URL as an ASP.
3. Set a **per-call price** (below). USDT/USDG settlement on X Layer is handled by OKX.
4. Pass OKX's internal review → **go live**. (Without this, the submission is invalid.)
5. Post a ≤90s demo on X with **#OKXAI** and submit the Google Form.

> Note: Vercel serverless has no ffmpeg and a 60s cap, so it hosts the **landing
> page**, not the render engine. The engine runs on the MCP/container host.

## Suggested per-call pricing
Venice cost/call ≈ LLM (~$0.01) + 4–10 frames (~$0.01/img, scales with `target_seconds`,
capped at 10) + TTS (~$0.005) ≈ **$0.05–0.12**. Sell at **$0.49/animatic** → healthy
margin, cheap for creators.

## Character consistency
`consistent=True` (default) generates one **hero frame**, then produces every other
frame by **editing the hero into the new scene** (Venice `/image/edit`), so the same
subject — e.g. "Liam, a bearded barista in a cream apron" — recurs across shots.
`consistent=False` makes each frame an independent text-to-image (cheaper, less coherent).

## Not built: native-video "cinematic tier"
Venice lists Kling/Veo/LTX video models, but they are **not exposed on the inference
API** (all video endpoints 404; `wan-2-7-image-to-video` → "model not found"). So DALANG
stays stills + Ken Burns; a real-motion tier is blocked upstream, not by us.

## Calibration knobs (env — ponytail)
- `VENICE_LLM_MODEL` (default `qwen3-235b-a22b-instruct-2507`) — clean, strong JSON.
- `VENICE_IMAGE_MODEL` (default `z-image-turbo`; demo used `flux-2-pro`) — trade speed for fidelity.
- `VENICE_EDIT_MODEL` (default `qwen-image-2-edit`) — the reference/consistency editor.
- `VENICE_TTS_MODEL` / `VENICE_TTS_VOICE` (default `tts-kokoro` / `af_sky`) — swap for a multilingual voice as needed.
- Ken Burns `zoompan_filter()` — linear ramps; switch to eased curves if motion looks robotic.
- Next knobs: burned-in captions (drawtext) and a music bed.

## Security
`.env` is gitignored; never commit the key. Any key that has appeared in a chat
or screenshot **must be rotated** in the Venice dashboard.
