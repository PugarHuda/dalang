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
from pipeline import render  # imported after .env load

# A remote A2MCP caller can't read the host's filesystem, so we embed the video
# in the result. Above this size we still embed (a paid render is never dropped)
# but flag it — bump the cap or host object storage for very large outputs.
MAX_INLINE_BYTES = int(os.environ.get("DALANG_MAX_INLINE_BYTES", 8_000_000))

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
        access_key: required only if the server sets DALANG_ACCESS_KEY.

    Returns the animatic (base64 data URI), a poster frame, the shot list, and metadata.
    On failure returns {"error": ...} instead of raising.
    """
    if ACCESS_KEY and not hmac.compare_digest(access_key, ACCESS_KEY):  # constant-time
        return {"error": "unauthorized: valid access_key required"}
    brief = (brief or "").strip()
    if not brief:
        return {"error": "brief is required"}
    if aspect_ratio not in VALID_ASPECTS:
        return {"error": f"aspect_ratio must be one of {list(VALID_ASPECTS)}"}

    workdir = os.path.join(WORKROOT, uuid.uuid4().hex[:12])
    try:
        target_seconds = max(8, min(90, int(target_seconds)))  # inside try: a bad value
        result = render(brief, style, aspect_ratio, target_seconds, voiceover, workdir,  # returns {error}, never raises
                        consistent, captions, voice)
        size = os.path.getsize(result["animatic"])
        with open(result["animatic"], "rb") as f:
            video = f.read()
        plan = json.load(open(result["shot_list"], encoding="utf-8"))
        out = {"title": result["title"], "duration_seconds": result["duration_seconds"],
               "animatic_bytes": size, "subject": plan.get("subject", ""), "shots": plan.get("shots", [])}
        if result.get("frames"):  # hero frame as a poster/thumbnail for sharing (og:image)
            with open(result["frames"][0], "rb") as pf:
                out["poster_data_uri"] = "data:image/png;base64," + base64.b64encode(pf.read()).decode()
        # Always embed: a remote A2MCP caller can't read the host FS, and the file is
        # deleted in `finally`, so the data URI is the ONLY delivery channel. Over the
        # cap we still embed (never drop a paid render) and just flag the large payload.
        out["animatic_data_uri"] = "data:video/mp4;base64," + base64.b64encode(video).decode()
        if size > MAX_INLINE_BYTES:
            out["warning"] = f"animatic {size} bytes exceeds inline cap ({MAX_INLINE_BYTES}); large payload"
        if KEEP_FILES:  # local debugging keeps the files + paths
            out.update({k: result[k] for k in ("animatic", "frames", "shot_list")})
        return out
    except Exception as e:  # clean error at the paid boundary, never a raw stack trace
        return {"error": f"render failed: {e}"}
    finally:
        if not KEEP_FILES:  # no disk leak on the host
            shutil.rmtree(workdir, ignore_errors=True)

if __name__ == "__main__":
    port = os.environ.get("PORT")  # container hosts (Railway/Render/Fly) set PORT
    if port:
        mcp.run(transport="http", host="0.0.0.0", port=int(port))
    else:
        mcp.run()  # stdio for local MCP clients (Claude/Cursor)
