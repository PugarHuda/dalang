# DALANG 🎬 — Storyboard-to-Animatic ASP

*Dalang* is the Indonesian shadow-puppet master who turns a script into a moving
visual performance. This agent does the same: give it an idea or script, and it
returns a **shot list + storyboard + narrated animatic video**.

An **Agentic Service Provider (ASP)** for the **OKX.AI Genesis Hackathon**.
Target: **Artistic Excellence** (an underserved category) + **Social Buzz** (a
shareable demo video). Mode: **A2MCP pay-per-call**.

## ✅ Proven end-to-end
Real run (Venice, brief "cinematic local-coffee ad", 9:16, 20s): 5-shot list →
5 flux-2-pro frames → 5 voiceovers → `animatic.mp4` **h264 1080×1920 + AAC audio,
2.5 MB, ~90s**. The 30s coffee demo on the landing page was produced by this code.

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
Venice cost/call ≈ LLM (~$0.01) + 4–6 frames (~$0.01/img) + TTS (~$0.005) ≈
**$0.05–0.08**. Sell at **$0.49/animatic** → healthy margin, cheap for creators.

## Calibration knobs (env — ponytail)
- `VENICE_LLM_MODEL` (default `qwen3-235b-a22b-instruct-2507`) — clean, strong JSON.
- `VENICE_IMAGE_MODEL` (default `z-image-turbo`; demo used `flux-2-pro`) — trade speed for fidelity.
- `VENICE_TTS_MODEL` / `VENICE_TTS_VOICE` (default `tts-kokoro` / `af_sky`) — swap for a multilingual voice as needed.
- Ken Burns `zoompan_filter()` — linear ramps; switch to eased curves if motion looks robotic.
- Next knobs: burned-in captions (drawtext) and padding clips to the exact target (clips currently `-shortest` to the voiceover length).

## Security
`.env` is gitignored; never commit the key. Any key that has appeared in a chat
or screenshot **must be rotated** in the Venice dashboard.
