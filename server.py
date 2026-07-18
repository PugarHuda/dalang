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
import time, urllib.request
import x402       # x402/X Layer paid-endpoint gate (opt-in via DALANG_X402_PAYTO)
import provenance  # Web3 provenance: content fingerprint + CID + mint-ready NFT metadata
import tokengate   # X Layer token-gating (opt-in via DALANG_TOKENGATE_CONTRACT)
from pipeline import render, storyboard as _storyboard  # imported after .env load

# A remote A2MCP caller can't read the host FS, so the video is delivered inline as a
# data URI. Default cap is serverless-safe: Vercel caps a function response at ~4.5 MB
# and base64 inflates ~33%, so keep inline bytes under ~3.3 MB there. Containers can
# raise DALANG_MAX_INLINE_BYTES. Over the cap, if object storage is configured
# (DALANG_UPLOAD_ENDPOINT) the mp4 is uploaded and a URL returned instead.
MAX_INLINE_BYTES = int(os.environ.get("DALANG_MAX_INLINE_BYTES", 3_300_000))
ROYALTY_BPS = int(os.environ.get("DALANG_ROYALTY_BPS", 0))       # e.g. 500 = 5%
ROYALTY_RECIPIENT = os.environ.get("DALANG_ROYALTY_RECIPIENT", "")

def _upload_mp4(data: bytes, name: str) -> str | None:
    """PUT the mp4 to object storage (S3/R2/Blob-compatible) so large outputs beat the
    serverless response cap. Returns the public URL, or None if not configured."""
    base = os.environ.get("DALANG_UPLOAD_ENDPOINT")
    if not base:
        return None
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
    mint: bool = False,
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
        captions: burn the spoken line into each shot (readable on muted autoplay).
        voice: TTS voice override (empty -> server default); e.g. a Kokoro voice id.
        language: write the title/voiceover in this language (e.g. "Bahasa Indonesia").
            Non-Latin scripts (CJK/Arabic) need a matching caption font via DALANG_FONT.
        template: a vertical structure preset — product_ad, book_trailer, recipe_reel,
            real_estate, event_promo, explainer.
        shot_list: a ready-made storyboard (same JSON shape the tool returns) to render
            directly, skipping the LLM — for agents that own the storyboard step.
        cinematic: PREMIUM real-motion tier — animate each shot with image-to-video
            (~$0.55/shot) instead of stills + Ken Burns. Price this call accordingly.
        mint: also return ERC-721 metadata (image, animation_url, attributes) so the
            caller can mint the animatic as an NFT on X Layer.
        wallet: caller's X Layer address — required only if the server sets
            DALANG_TOKENGATE_CONTRACT (renders gated to holders of that token/NFT).
        access_key: required only if the server sets DALANG_ACCESS_KEY.

    Returns the animatic (base64 data URI), a poster frame, an SRT subtitle track,
    a content fingerprint (content_sha256) + IPFS content id (content_cid) for on-chain
    provenance, the shot list, and metadata. On failure returns {"error": ...}.
    """
    if ACCESS_KEY and not hmac.compare_digest(access_key, ACCESS_KEY):  # constant-time
        return {"error": "unauthorized: valid access_key required"}
    if tokengate.enabled():  # X Layer holders-only, if configured
        ok, reason = tokengate.check(wallet)
        if not ok:
            return {"error": f"token-gated: {reason}"}
    brief = (brief or "").strip()
    if not brief and not shot_list:  # one of the two must drive the render
        return {"error": "brief is required (or pass a shot_list)"}
    if aspect_ratio not in VALID_ASPECTS:
        return {"error": f"aspect_ratio must be one of {list(VALID_ASPECTS)}"}

    workdir = os.path.join(WORKROOT, uuid.uuid4().hex[:12])
    try:
        target_seconds = max(8, min(90, int(target_seconds)))  # inside try: a bad value
        result = render(brief, style, aspect_ratio, target_seconds, voiceover, workdir,  # returns {error}, never raises
                        consistent, captions, voice, language, template, shot_list,
                        motion_engine="video" if cinematic else "kenburns")
        size = os.path.getsize(result["animatic"])
        with open(result["animatic"], "rb") as f:
            video = f.read()
        plan = json.load(open(result["shot_list"], encoding="utf-8"))
        out = {"title": result["title"], "duration_seconds": result["duration_seconds"],
               "animatic_bytes": size, "subject": plan.get("subject", ""), "shots": plan.get("shots", []),
               "srt": result.get("srt", "")}  # editable soft-subs alongside the burned-in captions
        if result.get("frames"):  # hero frame as a poster/thumbnail for sharing (og:image)
            with open(result["frames"][0], "rb") as pf:
                out["poster_data_uri"] = "data:image/png;base64," + base64.b64encode(pf.read()).decode()
        # Web3 provenance: a fingerprint + content id anyone can verify (see note on
        # content_cid — it's the exact-bytes CIDv1, a fingerprint, not a pinned DAG root).
        out["content_sha256"] = provenance.content_sha256(video)
        out["content_cid"] = provenance.content_cid(video)
        # Delivery: over the cap, offload to object storage if configured (beats the
        # serverless response cap); else embed inline (the only channel on a bare host).
        uploaded = _upload_mp4(video, f"{result['title'][:40] or 'animatic'}-{uuid.uuid4().hex[:8]}.mp4".replace(" ", "_")) \
            if size > MAX_INLINE_BYTES else None
        if uploaded:
            out["animatic_url"] = uploaded
        else:
            out["animatic_data_uri"] = "data:video/mp4;base64," + base64.b64encode(video).decode()
            if size > MAX_INLINE_BYTES:
                out["warning"] = (f"animatic {size} bytes exceeds inline cap ({MAX_INLINE_BYTES}) and no "
                                  "DALANG_UPLOAD_ENDPOINT is set; this response may exceed a serverless body limit")
        media_url = out.get("animatic_url") or f"ipfs://{out['content_cid']}"  # mint placeholder, not the doubled data URI
        # Proof-of-creation: a tamper-evident manifest; anchor manifest_digest on X Layer.
        manifest = provenance.provenance_manifest(out["title"], out["content_sha256"], out["content_cid"],
                                                  int(time.time()), "cinematic" if cinematic else "Ken Burns")
        out["provenance_manifest"] = manifest
        out["provenance_digest"] = provenance.manifest_digest(manifest)
        if mint:  # ERC-721 metadata ready to pin + mint on X Layer (with optional royalties)
            out["nft_metadata"] = provenance.erc721_metadata(
                out["title"], plan.get("subject", "") or brief,
                out.get("poster_data_uri", "") or media_url, media_url,
                {"Style": style, "Aspect": aspect_ratio, "Shots": len(out["shots"]),
                 "Duration (s)": out["duration_seconds"],
                 "Engine": "cinematic" if cinematic else "Ken Burns", "Language": language},
                out["content_sha256"], out["content_cid"], ROYALTY_BPS, ROYALTY_RECIPIENT)
        if KEEP_FILES:  # local debugging keeps the files + paths
            out.update({k: result[k] for k in ("animatic", "frames", "shot_list")})
        return out
    except Exception as e:  # clean error at the paid boundary, never a raw stack trace
        return {"error": f"render failed: {e}"}
    finally:
        if not KEEP_FILES:  # no disk leak on the host
            shutil.rmtree(workdir, ignore_errors=True)

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
    if ACCESS_KEY and not hmac.compare_digest(access_key, ACCESS_KEY):
        return {"error": "unauthorized: valid access_key required"}
    if tokengate.enabled():
        ok, reason = tokengate.check(wallet)
        if not ok:
            return {"error": f"token-gated: {reason}"}
    if not (brief or "").strip():
        return {"error": "brief is required"}
    if aspect_ratio not in VALID_ASPECTS:
        return {"error": f"aspect_ratio must be one of {list(VALID_ASPECTS)}"}
    workdir = os.path.join(WORKROOT, uuid.uuid4().hex[:12])
    try:
        target_seconds = max(8, min(90, int(target_seconds)))
        sb = _storyboard(brief.strip(), style, aspect_ratio, target_seconds, workdir, language, template)
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
