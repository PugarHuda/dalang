"""DALANG — Storyboard-to-Animatic ASP for OKX.AI (A2MCP, pay-per-call).

One tool = one billable call. Register this MCP server on OKX.AI in A2MCP mode;
OKX wraps the pay-per-call settlement (USDT/USDG on X Layer) around it.
"""
import base64, hmac, json, os, shutil, uuid
from fastmcp import FastMCP


def _load_dotenv(path: str = ".env") -> None:
    """Load .env if present so `python server.py` works after `cp .env.example .env`
    without exporting first — no python-dotenv dependency needed."""
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):  # tolerate copied shell-style lines
                line = line[7:]
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":  # strip wrapping quotes,
                v = v[1:-1]                                        # else the key carries them -> 401
            os.environ.setdefault(k.strip(), v)


_load_dotenv()
import re, time, urllib.request
                 # our payment gate. The file is okxpay.py, NOT x402.py: OKX's official
                 # seller SDK installs a package literally named `x402`, and a local module
                 # with that name shadows it, so the SDK could never be imported.
import okxpay as x402
import provenance  # Web3 provenance: content fingerprint + CID + mint-ready NFT metadata
import tokengate   # X Layer token-gating (opt-in via DALANG_TOKENGATE_CONTRACT)
from pipeline import (render, storyboard as _storyboard,  # imported after .env load
                      thumbnail as _thumbnail, shrink_video as _shrink_video)

# A remote A2MCP caller can't read the host FS, so the video is delivered inline as a
# base64 data URI inside the JSON response. Vercel caps a function response at ~4.5 MB,
# so the WHOLE inline body (base64 video + poster + srt) must stay under that. Over the
# cap, if object storage is configured (DALANG_UPLOAD_ENDPOINT) the mp4 is uploaded and a
# URL returned instead. Containers with no such cap can raise DALANG_MAX_RESPONSE_BYTES.
MAX_RESPONSE_BYTES = int(os.environ.get("DALANG_MAX_RESPONSE_BYTES", 4_300_000))
ROYALTY_BPS = int(os.environ.get("DALANG_ROYALTY_BPS", 0))       # e.g. 500 = 5%
ROYALTY_RECIPIENT = os.environ.get("DALANG_ROYALTY_RECIPIENT", "")

def _upload_mp4(data: bytes, name: str) -> str | None:
    """PUT the mp4 to object storage (S3/R2/Blob-compatible) so large outputs beat the
    serverless response cap. Returns the public URL, or None if not configured."""
    base = os.environ.get("DALANG_UPLOAD_ENDPOINT")
    if not base:
        return None
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "animatic.mp4"  # LLM/caller title -> safe key
    url = base.rstrip("/") + "/" + name
    headers = {"Content-Type": "video/mp4"}
    if os.environ.get("DALANG_UPLOAD_AUTH"):
        headers["Authorization"] = os.environ["DALANG_UPLOAD_AUTH"]
    urllib.request.urlopen(urllib.request.Request(url, data=data, method="PUT", headers=headers), timeout=60)
    return os.environ.get("DALANG_UPLOAD_PUBLIC_BASE", base).rstrip("/") + "/" + name

mcp = FastMCP("dalang")

WORKROOT = os.environ.get("DALANG_WORKROOT", os.path.join(os.getcwd(), "runs"))
VALID_ASPECTS = ("9:16", "16:9", "1:1")
# Opt-in gate: if set, the paid tool requires a matching access_key. Leave unset
# behind OKX's own A2MCP gating; set it if you expose /mcp directly to the public.
ACCESS_KEY = os.environ.get("DALANG_ACCESS_KEY")
KEEP_FILES = bool(os.environ.get("DALANG_KEEP_FILES"))  # else workdir is cleaned per call

@mcp.tool
def generate_animatic(
    brief: str,
    style: str = "cinematic, warm color grade, shallow depth of field",
    aspect_ratio: str = "9:16",
    target_seconds: int = 30,
    voiceover: bool = True,
    consistent: bool = True,
    captions: bool = True,
    voice: str = "",
    language: str = "",
    template: str = "",
    shot_list: dict | None = None,
    cinematic: bool = False,
    bookends: bool = False,
    music: str = "",
    mint: bool = False,
    parent_cid: str = "",
    royalties: list | None = None,
    wallet: str = "",
    access_key: str = "",
) -> dict:
    """Turn a script or idea into a storyboard + narrated animatic video.

    Args:
        brief: the script, logline, or idea to visualize.
        style: art direction, or a preset name (cinematic, anime, noir, watercolor,
            claymation, storybook, 3d) — any other string is used verbatim.
        aspect_ratio: "9:16" | "16:9" | "1:1".
        target_seconds: rough total length (8-90); shot count scales with it up to a cap.
        voiceover: narrate each shot with text-to-speech.
        consistent: keep one recurring subject across shots (hero frame + edits).
        captions: burn the spoken line into each shot (readable on muted autoplay). Needs a
            drawtext-enabled ffmpeg — present on the Docker/local host, ABSENT on the Vercel
            serverless build, where captions fall back to the SRT soft-subs in the response.
        voice: TTS voice override (empty -> server default); e.g. a Kokoro voice id.
        language: write the title/voiceover in this language (e.g. "Bahasa Indonesia").
            Non-Latin scripts (CJK/Arabic) need a matching caption font via DALANG_FONT.
        template: a vertical structure preset — product_ad, book_trailer, recipe_reel,
            real_estate, event_promo, explainer.
        shot_list: a ready-made storyboard (same JSON shape the tool returns) to render
            directly, skipping the LLM — for agents that own the storyboard step.
        cinematic: PREMIUM real-motion tier — animate each shot with image-to-video
            (~$0.55/shot) instead of stills + Ken Burns. Price this call accordingly.
        bookends: add a branded title card + DALANG end card so the clip reads as a film.
        music: score under the video — "auto" (mood from style) or warm/tense/upbeat/noir,
            "" = none. Ducked under narration; pairs with voiceover/bookends for a full bed.
        mint: also return ERC-721 metadata (image, animation_url, attributes) so the
            caller can mint the animatic as an NFT on X Layer.
        parent_cid: the content_cid this render remixes — records on-chain remix lineage
            (a verifiable descendant link) in the provenance manifest + digest.
        royalties: co-creator split for the NFT, [{"recipient": "0x..", "bps": 250}, ...] —
            every agent that helped make the video co-owns it (OpenSea off-chain hints).
        wallet: caller's X Layer address — required only if the server sets
            DALANG_TOKENGATE_CONTRACT (a SOFT gate on the balance of this claimed address;
            it does not prove ownership, so pair it with x402 for real access control).
        access_key: required only if the server sets DALANG_ACCESS_KEY.

    Returns the animatic (base64 data URI), a poster frame, an SRT subtitle track,
    a content fingerprint (content_sha256) + IPFS content id (content_cid) for on-chain
    provenance, the shot list, and metadata. On failure returns {"error": ...}.
    """
    if ACCESS_KEY and not hmac.compare_digest(access_key.encode(), ACCESS_KEY.encode()):  # constant-time
        return {"error": "unauthorized: valid access_key required"}
    if cinematic and not os.environ.get("DALANG_ENABLE_CINEMATIC"):  # the ~$0.55/shot tier is a credit
        return {"error": "cinematic tier is disabled on this endpoint"}  # sink on a free/public endpoint
    if tokengate.enabled():  # X Layer balance soft-gate, if configured (see tokengate.py security note)
        ok, reason = tokengate.check(wallet)
        if not ok:
            return {"error": f"token-gated: {reason}"}
    brief = (brief or "").strip()[:4000]  # cap: unbounded briefs = unbounded LLM token spend
    if not brief and not shot_list:  # one of the two must drive the render
        return {"error": "brief is required (or pass a shot_list)"}
    if aspect_ratio not in VALID_ASPECTS:
        return {"error": f"aspect_ratio must be one of {list(VALID_ASPECTS)}"}

    workdir = os.path.join(WORKROOT, uuid.uuid4().hex[:12])
    try:
        target_seconds = max(8, min(90, int(target_seconds)))  # inside try: a bad value
        result = render(brief, style, aspect_ratio, target_seconds, voiceover, workdir,  # returns {error}, never raises
                        consistent, captions, voice, language, template, shot_list,
                        motion_engine="video" if cinematic else "kenburns",
                        bookends=bookends, music=music)
        with open(result["animatic"], "rb") as f:
            video = f.read()
        plan = json.load(open(result["shot_list"], encoding="utf-8"))
        out = {"title": result["title"], "duration_seconds": result["duration_seconds"],
               "subject": plan.get("subject", ""), "shots": plan.get("shots", []),
               "srt": result.get("srt", "")}  # editable soft-subs (the caption channel where drawtext is absent)
        if result.get("frames"):  # hero frame -> a SMALL jpeg poster; a full PNG (~3MB b64) alone blows the cap
            try:
                thumb = os.path.join(workdir, "poster.jpg")
                _thumbnail(result["frames"][0], thumb)
                with open(thumb, "rb") as pf:
                    out["poster_data_uri"] = "data:image/jpeg;base64," + base64.b64encode(pf.read()).decode()
            except Exception:  # thumbnailing failed -> fall back to the raw frame
                with open(result["frames"][0], "rb") as pf:
                    out["poster_data_uri"] = "data:image/png;base64," + base64.b64encode(pf.read()).decode()
        # Delivery: pick the channel + the EXACT bytes the caller receives, then compute
        # provenance on those bytes so the returned fingerprint always matches what's delivered.
        def inline_len(vb):  # whole JSON body: base64 video (~4/3) + poster + srt + slack
            return (len(vb) + 2) // 3 * 4 + len(out.get("poster_data_uri", "")) + len(out.get("srt", "")) + 2000
        uploaded, deliver = None, video
        if inline_len(video) > MAX_RESPONSE_BYTES:  # too big to inline safely
            try:  # prefer object storage (serves the full-quality original)
                uploaded = _upload_mp4(video, f"{result['title'][:40] or 'animatic'}-{uuid.uuid4().hex[:8]}.mp4")
            except Exception:
                uploaded = None
            if not uploaded:  # no storage -> shrink to fit rather than ship a body the platform rejects
                try:
                    small = os.path.join(workdir, "small.mp4")
                    _shrink_video(result["animatic"], small)
                    sb = open(small, "rb").read()
                    if len(sb) < len(video):
                        deliver = sb
                        out["downscaled"] = "re-encoded smaller to fit the inline response limit; set DALANG_UPLOAD_ENDPOINT for full quality"
                except Exception:
                    pass
        prov_bytes = video if uploaded else deliver  # fingerprint the bytes the caller actually gets
        out["animatic_bytes"] = len(prov_bytes)
        out["content_sha256"] = provenance.content_sha256(prov_bytes)
        out["content_cid"] = provenance.content_cid(prov_bytes)
        if uploaded:
            out["animatic_url"] = uploaded
        else:
            out["animatic_data_uri"] = "data:video/mp4;base64," + base64.b64encode(deliver).decode()
            if inline_len(deliver) > MAX_RESPONSE_BYTES:
                out["warning"] = (f"inline response ~{inline_len(deliver)} bytes exceeds the serverless body "
                                  f"limit (~{MAX_RESPONSE_BYTES}); set DALANG_UPLOAD_ENDPOINT to offload the mp4")
        # animation_url for minting: a resolvable URL or the self-contained data URI —
        # never ipfs://<content_cid> (that CID is a fingerprint, won't resolve once chunk-pinned).
        media_url = out.get("animatic_url") or out.get("animatic_data_uri", "")
        # Proof-of-creation: a tamper-evident manifest; anchor manifest_digest on X Layer.
        # parent_cid (if a remix) records verifiable on-chain lineage.
        manifest = provenance.provenance_manifest(out["title"], out["content_sha256"], out["content_cid"],
                                                  int(time.time()), "cinematic" if cinematic else "Ken Burns",
                                                  parent_cid=(parent_cid or "").strip())
        out["provenance_manifest"] = manifest
        out["provenance_digest"] = provenance.manifest_digest(manifest)
        if mint:  # ERC-721 metadata ready to pin + mint on X Layer (with optional royalties)
            out["nft_metadata"] = provenance.erc721_metadata(
                out["title"], plan.get("subject", "") or brief,
                out.get("poster_data_uri", "") or media_url, media_url,
                {"Style": style, "Aspect": aspect_ratio, "Shots": len(out["shots"]),
                 "Duration (s)": out["duration_seconds"],
                 "Engine": "cinematic" if cinematic else "Ken Burns", "Language": language},
                out["content_sha256"], out["content_cid"], ROYALTY_BPS, ROYALTY_RECIPIENT,
                royalties=royalties)
        if KEEP_FILES:  # local debugging keeps the files + paths
            out.update({k: result[k] for k in ("animatic", "frames", "shot_list")})
        return out
    except Exception as e:  # clean error at the paid boundary, never a raw stack trace
        return {"error": f"render failed: {e}"}
    finally:
        if not KEEP_FILES:  # no disk leak on the host
            shutil.rmtree(workdir, ignore_errors=True)

@mcp.tool
def quote(target_seconds: int = 30, cinematic: bool = False) -> dict:
    """Price discovery for an agent BEFORE it commits — no render, no payment, free.
    Lets a buyer agent learn the price and scope (and compare ASPs) without initiating a
    paid call — the OKX A2MCP market in miniature. The premium cinematic tier is priced
    per animated shot; Ken Burns is the flat list price.

    Args:
        target_seconds: rough length (8-90); shot count scales with it up to a cap.
        cinematic: PREMIUM real-motion tier (~$0.55/shot) vs flat-priced Ken Burns stills.
    Returns the shot count, engine, and the USD price the caller pays (x402 · X Layer).
    """
    from pipeline import shot_budget, MAX_VIDEO_SHOTS, MAX_SHOTS
    try:
        t = max(8, min(90, int(target_seconds)))
    except (TypeError, ValueError):
        return {"error": "target_seconds must be a number (8-90)"}
    n_shots = min(MAX_SHOTS, shot_budget(t)[0])
    # price_usd is the amount x402 ACTUALLY charges — a flat DALANG_X402_AMOUNT for any paid
    # call (the middleware doesn't vary by engine), so we must quote that, not a made-up number.
    price = round(int(os.environ.get("DALANG_X402_AMOUNT", "490000")) / 1_000_000, 2)
    out = {"shots": n_shots, "engine": "cinematic" if cinematic else "kenburns",
           "price_usd": price, "currency": "USDT",
           "network": os.environ.get("DALANG_X402_NETWORK", "x-layer"),
           "settlement": "x402 · X Layer", "note": "call generate_animatic to render (this quote is free)"}
    if cinematic:  # honest: the flat price does NOT cover premium video cost — flag it, don't hide it
        vshots = min(n_shots, MAX_VIDEO_SHOTS)
        out["premium"] = True
        out["est_video_cost_usd"] = round(vshots * 0.55, 2)  # ~$0.55/animated shot of Venice cost
        out["note"] = ("cinematic is a PREMIUM real-motion tier costing the operator "
                       f"~${out['est_video_cost_usd']} ({vshots} animated shots); the flat x402 price "
                       "does not auto-scale — set DALANG_X402_AMOUNT per tier before charging for it")
    return out

@mcp.tool
def storyboard(
    brief: str,
    style: str = "cinematic, warm color grade, shallow depth of field",
    aspect_ratio: str = "9:16",
    target_seconds: int = 30,
    language: str = "",
    template: str = "",
    wallet: str = "",
    access_key: str = "",
) -> dict:
    """Cheap PREVIEW of an animatic: the shot list + a single hero frame, no video.
    Lets a caller (or agent) approve the direction before paying for a full render via
    generate_animatic. Same args as generate_animatic (subset). Free at the x402 layer.

    Returns the shot list, a hero poster (data URI), an SRT preview, and metadata.
    On failure returns {"error": ...} instead of raising.
    """
    if ACCESS_KEY and not hmac.compare_digest(access_key.encode(), ACCESS_KEY.encode()):
        return {"error": "unauthorized: valid access_key required"}
    if tokengate.enabled():
        ok, reason = tokengate.check(wallet)
        if not ok:
            return {"error": f"token-gated: {reason}"}
    brief = (brief or "").strip()[:4000]  # cap LLM token spend on the free preview tier
    if not brief:
        return {"error": "brief is required"}
    if aspect_ratio not in VALID_ASPECTS:
        return {"error": f"aspect_ratio must be one of {list(VALID_ASPECTS)}"}
    workdir = os.path.join(WORKROOT, uuid.uuid4().hex[:12])
    try:
        target_seconds = max(8, min(90, int(target_seconds)))
        sb = _storyboard(brief, style, aspect_ratio, target_seconds, workdir, language, template)
        # Same cap as the paid path: a full-size hero PNG is ~3-5 MB base64 on its own and
        # rides right at Vercel's ~4.5 MB response limit (a live call measured 5.2 MB), so this
        # FREE preview — the first thing a caller tries — could 500 on a heavier frame.
        try:
            thumb = os.path.join(workdir, "hero.jpg")
            _thumbnail(sb["hero"], thumb)
            with open(thumb, "rb") as f:
                poster = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
        except Exception:  # thumbnailing failed -> the raw frame is still better than nothing
            with open(sb["hero"], "rb") as f:
                poster = "data:image/png;base64," + base64.b64encode(f.read()).decode()
        return {"title": sb["title"], "subject": sb["subject"], "shots": sb["shots"],
                "srt": sb["srt"], "hero_data_uri": poster,
                "next": "call generate_animatic with the same brief (or this shot_list) to render the full video"}
    except Exception as e:
        return {"error": f"storyboard failed: {e}"}
    finally:
        if not KEEP_FILES:
            shutil.rmtree(workdir, ignore_errors=True)

if __name__ == "__main__":
    port = os.environ.get("PORT")  # container hosts (Railway/Render/Fly) set PORT
    if port and x402.enabled():
        # Native x402 paid endpoint: wrap /mcp so the paid tools/call requires an
        # on-chain payment (USDT/USDG on X Layer via APP); handshake/list stay free.
        import uvicorn
        app = mcp.http_app()
        app.add_middleware(x402.X402Middleware)
        uvicorn.run(app, host="0.0.0.0", port=int(port))
    elif port:
        mcp.run(transport="http", host="0.0.0.0", port=int(port))
    else:
        mcp.run()  # stdio for local MCP clients (Claude/Cursor)
