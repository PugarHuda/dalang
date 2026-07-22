# OKX.AI Genesis Hackathon — Google Form draft

Deadline: **Jul 27, 23:59 UTC** (~6 days). Form: https://forms (OKX Team). Account: hudapugar@gmail.com

> Dependency: **Agent ID** is issued only AFTER the ASP is listed & goes live on OKX.AI
> (Step 2). List first → get the ID → then fill this. Listing is the gate; start it now.

---

### ASP Name *
```
DALANG — Storyboard-to-Animatic Studio
```

### Agent ID *
```
7234
```
(DALANG registered on-chain on X Layer — status "Listing under review" as of 2026-07-22.
tx: 0xa4147829e1b727ecee9a29a9badf512518bfda13473ca9be26d2b02dfe7d8dfc · EVM wallet:
0xc87ac386c485afd1c9b4087c8efe5daeeab08307)

### ASP Description *
```
DALANG turns a single line of brief into a finished, narrated vertical animatic — the whole
storyboard-to-video pipeline as ONE agent call. Give it an idea; it writes the shot list,
generates consistent frames (one recurring character/product held across every shot), voices
each line, burns in captions, and assembles a share-ready 1080×1920 MP4. Two engines: a cheap
Ken Burns tier (stills + motion, ~$0.05–0.12) and a PREMIUM cinematic tier that animates each
shot into real motion via image-to-video.

Built agent-native for OKX.AI: one tool = one billable call, priced and settled as x402 on
X Layer (USDT). It's composable — an upstream "director" agent can hand DALANG a ready-made
shot_list and use it purely as the render primitive — and every output is Web3-native: a
content fingerprint (SHA-256 + IPFS CIDv1) and a tamper-evident proof-of-creation you can
anchor on X Layer, plus mint-ready ERC-721 metadata with co-creator royalty splits (every
agent that helped make a video co-owns it) and on-chain remix lineage. Multilingual
title/voiceover, vertical templates (product ad, book trailer, recipe reel, real-estate,
explainer), style presets, editable SRT, and a FREE storyboard-preview tier so a caller can
approve the direction before paying. One sentence in → a paid, provably-authored, co-owned
film out, with no human in the loop.

Live MCP endpoint: https://dalang-engine.vercel.app/mcp
```

### ASP Type *
```
A2MCP
```
(DALANG is a FastMCP server — the paid tool is generate_animatic; also exposes storyboard + quote.)

### X Account Handle *
```
<< your @handle >>
```

### X Participation Post (Link) *
```
<< paste after you post the ≤90s demo with #OKXAI (Step 3) — draft in demo-x-post.md >>
```

### Telegram Handle *
```
<< your @telegram >>
```

---

## Category to target
Primary: **Artistic Excellence** (Art Creation, 7,500 USD pool). Also naturally competitive for
**Social Buzz** (X post, 10,000 USD) and **Creative Genius** (20,000 USD — the x402 on-chain
pay + co-owned NFT + remix lineage + agent supply-chain is the "use your imagination" angle).

## Before listing (blocker)
Rotate the leaked Venice key (Venice dashboard) + update the Vercel env var — the public /mcp
endpoint uses that key; once the ASP is live and discoverable, an unrotated key is drainable.
