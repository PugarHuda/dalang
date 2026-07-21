"""DALANG pipeline: script -> shot list -> storyboard frames -> animatic mp4.

Pure helpers (dims / zoompan_filter / validate_plan / total_seconds) carry the
non-trivial logic and are exercised by demo() below. The impure steps
(Venice LLM/image/TTS, ffmpeg) are thin wrappers around external tools — each is
a calibration knob, not clever code. One Venice key powers all three stages.
"""
from __future__ import annotations
import base64, hashlib, json, os, subprocess, tempfile, textwrap, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

# ---------- pure logic (tested by demo()) ----------

ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
MOTIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right", "static"}
MAX_SHOTS = 10  # cost guard: refuse runaway shot lists

# Named looks so a caller can pick a vibe without writing art direction. Any string
# that isn't a preset name passes through unchanged (write your own).
STYLE_PRESETS = {
    "cinematic": "cinematic, warm color grade, shallow depth of field",
    "anime": "anime cel-shaded key art, vibrant, clean linework",
    "noir": "high-contrast black-and-white film noir, hard shadows, moody",
    "watercolor": "soft watercolor painting, textured paper, gentle washes",
    "claymation": "claymation stop-motion, sculpted plasticine, tactile",
    "storybook": "warm children's storybook illustration, soft and whimsical",
    "3d": "polished 3D animated film render, soft global illumination",
}

def resolve_style(style: str) -> str:
    """Expand a preset name (e.g. 'anime') to full art direction; pass any other
    string through unchanged."""
    return STYLE_PRESETS.get((style or "").strip().lower(), style)

# Vertical recipes: a named structure prepended to the brief so a buyer gets a
# usable ad/trailer/reel without describing the arc themselves. Combine with any style.
TEMPLATES = {
    "product_ad": "Structure as a product ad: hook, the problem, the product reveal, a key benefit, and a call to action.",
    "book_trailer": "Structure as a cinematic book trailer: mood, the stakes, a glimpse of the hero, the central conflict, and a title-card ending.",
    "recipe_reel": "Structure as a fast recipe reel: the finished dish hero, key ingredients, two or three prep/cook beats, and the final plated result.",
    "real_estate": "Structure as a property tour: exterior approach, the entry, the main living space, a standout feature, and a lifestyle closing shot.",
    "event_promo": "Structure as an event promo: an energy hook, the what/when/where, a highlight moment, and a 'get your tickets' call to action.",
    "explainer": "Structure as a short explainer: the problem, a simple analogy, how it works in two or three beats, and the takeaway.",
}

def apply_template(brief: str, template: str) -> str:
    """Prepend a named vertical structure to the brief; unknown/empty -> unchanged."""
    hint = TEMPLATES.get((template or "").strip().lower())
    return f"{hint}\n\n{brief}" if hint else brief

def _norm_motion(m: str) -> str:
    """Map a model's free-text motion to a valid token (default static).
    Fixes gap: models return e.g. 'slow zoom in' -> was silently dropped."""
    m = str(m or "").lower().strip().replace(" ", "_").replace("-", "_")  # str(): motion may be a non-string
    if m in MOTIONS:
        return m
    if "zoom" in m and "in" in m:
        return "zoom_in"
    if "zoom" in m and "out" in m:
        return "zoom_out"
    if "left" in m:
        return "pan_left"
    if "right" in m:
        return "pan_right"
    return "static"

def dims(aspect: str) -> tuple[int, int]:
    if aspect not in ASPECTS:
        raise ValueError(f"aspect must be one of {list(ASPECTS)}, got {aspect!r}")
    return ASPECTS[aspect]

def zoompan_filter(motion: str, sec: float, w: int, h: int, fps: int = 30) -> str:
    """Reframe any-aspect still to the WxH canvas WITHOUT cropping the subject:
    a blurred cover-fill background + the full frame contained on top, then Ken Burns.
    Image models often ignore requested dimensions, so we must not center-crop.
    ponytail: linear z/x/y ramps; swap for eased curves if the motion looks robotic."""
    frames = max(1, round(sec * fps))
    z_in = "'min(zoom+0.0012,1.35)'"
    z_out = "'if(lte(zoom,1.0),1.35,max(1.001,zoom-0.0012))'"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    moves = {
        "zoom_in":   (z_in,  cx, cy),
        "zoom_out":  (z_out, cx, cy),
        "pan_left":  ("1.25", f"(iw-iw/zoom)*(1-on/{frames})", cy),
        "pan_right": ("1.25", f"(iw-iw/zoom)*(on/{frames})", cy),
        "static":    ("1.15", cx, cy),
    }
    z, x, y = moves.get(motion, moves["static"])
    long = max(w, h)  # cap the (often 2500px) source first so boxblur isn't glacial
    # downscale -> split -> blurred cover bg + contained fg overlay -> zoompan (single -vf chain)
    return (
        f"scale={long}:{long}:force_original_aspect_ratio=decrease,"
        f"split=2[bg][fg];"
        f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"boxblur=24:2,eq=brightness=-0.18:saturation=1.15[bg];"
        f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,"
        f"zoompan=z={z}:x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},format=yuv420p"
    )

def validate_plan(plan: dict) -> dict:
    """Sanitize a shot list into something always renderable. This is the single money-path
    gate for BOTH the LLM breakdown and a caller's shot_list, so it SELF-HEALS instead of
    raising — a missing/odd field on one shot must never sink a paid render. The only hard
    failure is no shots at all (nothing to render)."""
    if not isinstance(plan, dict):  # the LLM may return a top-level array/primitive, not an object
        raise ValueError(f"plan must be a JSON object, got {type(plan).__name__}")
    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("plan has no shots")
    # coerce non-dict elements to {} (they self-heal below) so a malformed shot_list like
    # {"shots": ["a", 2]} can't AttributeError and sink a paid render; then cost-cap the list.
    shots = [s if isinstance(s, dict) else {} for s in shots][:MAX_SHOTS]
    title = str(plan.get("title") or "Untitled animatic")
    subject = str(plan.get("subject") or "")
    for i, s in enumerate(shots):
        # coerce every field the render depends on so LLM omissions can't crash a paid call
        s["image_prompt"] = str(s.get("image_prompt") or "").strip() or subject or title  # a frame needs a prompt
        s["voiceover"] = str(s.get("voiceover") or "")            # missing line -> silent shot
        try:
            sec = float(s.get("seconds", 3))
        except (TypeError, ValueError):
            sec = 3.0
        s["seconds"] = min(15.0, max(0.5, sec))                   # clamp to the renderable range
        s["motion"] = _norm_motion(s.get("motion", "static"))     # never trust the enum blindly
        s["scene"] = i + 1  # renumber, don't trust: dup/misnumbered scenes collide frame/clip paths
    plan["shots"] = shots
    # render/server read title (seed) + subject; the LLM may omit them or send non-str.
    plan["title"], plan["subject"] = title, subject
    return plan

def total_seconds(plan: dict) -> float:
    return round(sum(float(s["seconds"]) for s in plan["shots"]), 2)

def _srt_time(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def build_srt(plan: dict, offset: float = 0.0) -> str:
    """SRT soft-subs from the shot list — editable captions to complement the burned-in
    ones. Timing uses max(sec,0.5) to match the actual clip length; silent shots advance
    the clock but emit no cue. offset shifts every cue (e.g. a prepended title card)."""
    out, t, n = [], float(offset), 0
    for s in plan["shots"]:
        dur = max(float(s["seconds"]), 0.5)
        text = " ".join(str(s.get("voiceover", "")).split())
        if text:
            n += 1
            out.append(f"{n}\n{_srt_time(t)} --> {_srt_time(t + dur)}\n{text}\n")
        t += dur
    return "\n".join(out)

# ---------- Venice provider (LLM + image + TTS, one key) ----------

VENICE_BASE = os.environ.get("VENICE_BASE_URL", "https://api.venice.ai/api/v1")
LLM_MODEL = os.environ.get("VENICE_LLM_MODEL", "qwen3-235b-a22b-instruct-2507")
IMAGE_MODEL = os.environ.get("VENICE_IMAGE_MODEL", "z-image-turbo")
EDIT_MODEL = os.environ.get("VENICE_EDIT_MODEL", "qwen-image-2-edit")  # reliable editor (fast lite models refuse people)
TTS_MODEL = os.environ.get("VENICE_TTS_MODEL", "tts-kokoro")
TTS_VOICE = os.environ.get("VENICE_TTS_VOICE", "af_sky")
# Cinematic tier: animate each still into real motion via Venice's video queue
# (image-to-video). PREMIUM — ~$0.55/clip, so it's opt-in and shot-capped.
VIDEO_MODEL = os.environ.get("VENICE_VIDEO_MODEL", "wan-2-7-image-to-video")
VIDEO_RES = os.environ.get("VENICE_VIDEO_RESOLUTION", "720p")
VIDEO_DURATION = os.environ.get("VENICE_VIDEO_DURATION", "5s")  # wan: 5s|10s|15s
VID_SECS = float(VIDEO_DURATION.rstrip("s"))
MAX_VIDEO_SHOTS = int(os.environ.get("DALANG_MAX_VIDEO_SHOTS", 6))  # cost guard

_RETRYABLE = {408, 409, 429, 500, 502, 503, 504}

def _download_auth(url: str) -> dict:
    """Headers for fetching a video download_url. Attach the Venice bearer token ONLY when the
    URL is on a Venice host — a completed job's download_url is often a SIGNED CDN/S3 URL on a
    third-party domain, and sending the API key there would leak it. Also reject non-http(s)
    schemes so a malicious/compromised response can't make us fetch file:// / gopher:// (SSRF)."""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https"):
        raise RuntimeError(f"video download_url has an unsupported scheme: {p.scheme!r}")
    vhost = urllib.parse.urlparse(VENICE_BASE).hostname or ""
    host = (p.hostname or "").lower()
    if host == vhost.lower() or host.endswith(".venice.ai"):
        return {"Authorization": f"Bearer {os.environ.get('VENICE_API_KEY', '')}"}
    return {}  # signed CDN URL -> no token (it doesn't need one, and we must not leak it)

def _venice(path: str, body: dict, raw: bool = False, tries: int = 3):
    """POST to Venice with retry/backoff on transient errors and clean errors
    on failure — this is a paid boundary, so it must not raise raw urllib noise."""
    key = os.environ["VENICE_API_KEY"]
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(
            VENICE_BASE + path, data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            if raw:
                return data
            parsed = json.loads(data)
            # Venice can answer 200 with a top-level {"error": ...} (rate limit / moderation);
            # surface it as the real message instead of a confusing downstream KeyError.
            if isinstance(parsed, dict) and parsed.get("error"):
                err = parsed["error"]
                raise RuntimeError(f"Venice {path}: {err.get('message', err) if isinstance(err, dict) else err}")
            return parsed
        except urllib.error.HTTPError as e:
            last = e
            if e.code in _RETRYABLE and attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1)); continue
            detail = e.read()[:200].decode("utf-8", "replace")
            raise RuntimeError(f"Venice {path} HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1)); continue
            raise RuntimeError(f"Venice {path} unreachable: {e}") from e
    raise RuntimeError(f"Venice {path} failed after {tries} tries: {last}")

def _strip_fence(s: str) -> str:
    """Some models wrap JSON in ```json fences; grab the object body."""
    s = s.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
    return s[s.find("{"): s.rfind("}") + 1] if "{" in s else s

def _gen_size(w: int, h: int, cap: int = 1280) -> tuple[int, int]:
    """Scale target canvas down to a generation-friendly size (<=cap, mult of 8).
    ffmpeg upscales during Ken Burns, so the still need not be full-canvas."""
    k = min(1.0, cap / max(w, h))
    return (max(8, round(w * k / 8) * 8), max(8, round(h * k / 8) * 8))

def shot_budget(target_seconds: int) -> tuple[int, int]:
    """Turn a requested length into a (shot count, per-shot seconds) the prompt can
    honour, bounded by MAX_SHOTS (cost guard). Makes target_seconds actually mean
    something instead of the old hardcoded '4-6 shots × 2-4s' that capped every
    render near ~24s regardless of the request. Per-shot capped at 6s — a Ken Burns
    move on a still drags past that."""
    n = max(3, min(MAX_SHOTS, round(target_seconds / 4)))
    per = max(2, min(6, round(target_seconds / n)))
    return n, per

def breakdown(brief: str, style: str, target_seconds: int, language: str = "") -> dict:
    """Script/idea -> shot list, via Venice chat (OpenAI-compatible).
    language: write the title/voiceover in this language (empty -> the brief's)."""
    n_shots, per = shot_budget(target_seconds)
    lang = f" Write the title and every voiceover line in {language}." if language.strip() else ""
    sys = (
        "You are a film director's assistant. Turn the brief into a shot list for a "
        f"~{target_seconds}s animatic. Return ONLY a JSON object with this shape: "
        '{"title": string, "subject": string, "shots": [{"scene": int, "image_prompt": string, '
        '"voiceover": string, "seconds": number, "motion": one of '
        '["zoom_in","zoom_out","pan_left","pan_right","static"]}]}. '
        "subject: a fixed, concrete description of ONE recurring hero — prefer a specific "
        "person or the actual product (face/look, colors, wardrobe/packaging) so it is "
        "recognizably the SAME in every shot; avoid abstract symbols. "
        f"Total seconds near {target_seconds}. image_prompt: a vivid, self-contained still in "
        f"this style: {style}, <=30 words; do NOT restate the subject, it is added automatically. "
        "voiceover: one short spoken line (<=18 words) or \"\". "
        f"Use EXACTLY these motion tokens. About {n_shots} shots, each roughly {per} "
        f"seconds, summing near {target_seconds}s. No prose, JSON only." + lang
    )
    r = _venice("/chat/completions", {
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": sys}, {"role": "user", "content": brief}],
        "max_tokens": 6000, "temperature": 0.7,
    })
    try:  # a malformed 200 (choices=[]/missing/content=null) -> a clean error, not a raw KeyError
        content = r["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"Venice chat returned an unexpected shape: {str(r)[:200]}")
    try:
        return validate_plan(json.loads(_strip_fence(content), strict=False))  # tolerate raw newlines
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Venice chat content was not valid JSON: {e}")

def gen_image(prompt: str, out_path: str, w: int, h: int,
              subject: str = "", seed: int | None = None) -> None:
    """Venice image -> base64 PNG. Prepends the recurring `subject` and reuses one
    `seed` across shots so frames share a character/palette (consistency fix).
    ponytail: swap VENICE_IMAGE_MODEL for FLUX 2 / Seedream."""
    gw, gh = _gen_size(w, h)
    full = f"{subject.strip()}. {prompt}".strip(". ") if subject.strip() else prompt
    body = {"model": IMAGE_MODEL, "prompt": full, "width": gw, "height": gh, "format": "png"}
    if seed is not None:
        body["seed"] = seed
    r = _venice("/image/generate", body)
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(r["images"][0]))

def edit_image(prompt: str, ref_path: str, out_path: str, subject: str = "") -> None:
    """Transform a reference frame into a new scene while keeping the same subject
    (Venice /image/edit; returns raw PNG bytes). This is the strong consistency path:
    every shot after the hero is an edit of the hero, so the character/product holds."""
    b64 = base64.b64encode(open(ref_path, "rb").read()).decode()
    keep = f" Keep the exact same {subject}." if subject.strip() else ""
    img = _venice("/image/edit",
                  {"model": EDIT_MODEL, "prompt": f"{prompt}.{keep}", "image": b64}, raw=True)
    with open(out_path, "wb") as f:
        f.write(img)

def tts(text: str, out_path: str, voice: str = "") -> bool:
    """Venice TTS (Kokoro). False (silent shot) when the line is empty.
    `voice` overrides the default per call (empty -> VENICE_TTS_VOICE)."""
    if not text.strip():
        return False
    audio = _venice("/audio/speech", {"model": TTS_MODEL, "input": text,
                                      "voice": voice or TTS_VOICE, "response_format": "mp3"}, raw=True)
    with open(out_path, "wb") as f:
        f.write(audio)
    return True

# ---------- cinematic tier: image-to-video (Venice async video queue) ----------

_MOTION_PHRASE = {
    "zoom_in": "slow cinematic push-in", "zoom_out": "slow pull-back reveal",
    "pan_left": "smooth pan left", "pan_right": "smooth pan right",
    "static": "locked-off camera, subtle ambient motion",
}

def video_quote(model: str = "", duration: str = "", resolution: str = "") -> float:
    """USD price for ONE image-to-video clip, no generation — for cost display/guards."""
    r = _venice("/video/quote", {"model": model or VIDEO_MODEL,
                                 "duration": duration or VIDEO_DURATION,
                                 "resolution": resolution or VIDEO_RES})
    return float(r.get("quote", 0))

# Keep max_wait comfortably under a serverless maxDuration (Vercel Hobby = 300s): a
# stalled job must fail fast so the Ken Burns fallback runs before the function is killed.
VIDEO_MAX_WAIT = int(os.environ.get("DALANG_VIDEO_MAX_WAIT", 240))
_VIDEO_TERMINAL_FAIL = {"FAILED", "ERROR", "CANCELED", "CANCELLED"}

def gen_video(frame_path: str, image_prompt: str, motion: str, out_path: str,
              poll_every: int = 5, max_wait: int = 0) -> None:
    """Animate a still into a real-motion clip (Venice image-to-video, async queue).
    PREMIUM ~$0.55/clip. queue -> poll /video/retrieve -> save mp4. Raises on failure
    (so the caller falls back to Ken Burns). No aspect_ratio — wan derives it."""
    max_wait = max_wait or VIDEO_MAX_WAIT
    b64 = "data:image/png;base64," + base64.b64encode(open(frame_path, "rb").read()).decode()
    prompt = f"{image_prompt}. Camera: {_MOTION_PHRASE.get(motion, _MOTION_PHRASE['static'])}. Subtle lifelike motion."
    q = _venice("/video/queue", {"model": VIDEO_MODEL, "prompt": prompt, "image_url": b64,
                                 "duration": VIDEO_DURATION, "resolution": VIDEO_RES})
    qid = q["queue_id"]
    waited = 0
    while waited < max_wait:
        raw = _venice("/video/retrieve", {"model": VIDEO_MODEL, "queue_id": qid}, raw=True)
        if b"ftyp" in raw[:64]:  # the mp4 bytes came back inline
            with open(out_path, "wb") as f:
                f.write(raw)
            return
        try:
            body = json.loads(raw)
        except Exception:
            body = {}
        status = str(body.get("status", "")).upper()
        if status in _VIDEO_TERMINAL_FAIL:  # fail fast -> fallback runs; don't burn max_wait
            raise RuntimeError(f"video job {status.lower()}: {body.get('error', qid)}")
        if status == "COMPLETED":  # fetch from the private-share URL
            url = body.get("download_url")
            if not url:
                raise RuntimeError("video COMPLETED without a download_url")
            req = urllib.request.Request(url, headers=_download_auth(url))  # token only if it's a Venice host
            with urllib.request.urlopen(req, timeout=180) as r, open(out_path, "wb") as f:
                f.write(r.read())
            return
        time.sleep(poll_every)
        waited += poll_every
    raise RuntimeError(f"video generation timed out after {max_wait}s")

# ---------- ffmpeg assembly ----------

def _resolve_ffmpeg() -> str:
    """ffmpeg path: FFMPEG_BINARY env -> system PATH -> pip's imageio-ffmpeg static
    binary. The last one lets serverless hosts (Vercel Fluid Compute) that have no
    system ffmpeg still render — see api/index.py."""
    import shutil
    if os.environ.get("FFMPEG_BINARY"):
        return os.environ["FFMPEG_BINARY"]
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

FFMPEG = _resolve_ffmpeg()

FFMPEG_TIMEOUT = int(os.environ.get("DALANG_FFMPEG_TIMEOUT", 180))  # bound every ffmpeg call

def _run(cmd: list[str]) -> None:
    try:
        # timeout is critical: `ffmpeg -loop 1` on a decodable-but-invalid frame (Venice can
        # return a truncated/non-image body) HANGS forever, tying up the render worker. A bound
        # turns that into a clean failure the caller can fall back from.
        r = subprocess.run(cmd, capture_output=True, timeout=FFMPEG_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg timed out after {FFMPEG_TIMEOUT}s (likely a corrupt input)")
    if r.returncode != 0:  # surface ffmpeg's stderr tail — else the paid boundary returns a
        tail = r.stderr.decode("utf-8", "replace").strip().splitlines()[-4:]  # useless "Command [...]"
        raise RuntimeError(f"ffmpeg failed (exit {r.returncode}): {' | '.join(tail)}")

def _placeholder_frame(out: str, w: int, h: int) -> None:
    """A solid dark frame so one failed shot can't sink a whole paid render."""
    _run([FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c=0x1a1206:s={w}x{h}:d=1", "-frames:v", "1", out])

def _has_drawtext() -> bool:
    """Whether this ffmpeg build has the drawtext filter (needs libfreetype). The pip
    imageio-ffmpeg static build used on serverless (Vercel) does NOT — so attempting
    drawtext there fails the whole render. Gate every text overlay on this; where it's
    absent, captions/card text skip gracefully and the SRT soft-subs still ship."""
    if os.environ.get("DALANG_NO_DRAWTEXT"):  # test/ops override
        return False
    if not hasattr(_has_drawtext, "_c"):
        try:
            out = subprocess.run([FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
            _has_drawtext._c = " drawtext " in out
        except Exception:
            _has_drawtext._c = False
    return _has_drawtext._c

def _font_file() -> str | None:
    """A TTF for drawtext captions/cards. The repo bundles DejaVuSans-Bold so a font is
    always present for hosts that HAVE drawtext but no system font (bare local runs). NOTE:
    the Vercel serverless ffmpeg has no drawtext at all (see _has_drawtext), so text is
    gated off there regardless of this font. Override with DALANG_FONT; falls back to system
    DejaVu/Arial. None -> text skips gracefully."""
    bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts", "DejaVuSans-Bold.ttf")
    cands = [os.environ.get("DALANG_FONT"), bundled,
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"]
    return next((c for c in cands if c and os.path.exists(c)), None)

def _caption_filter(text: str, w: int, h: int, capfile: str) -> str:
    """Burn the spoken line in as a bottom-centered caption — social video autoplays
    muted, so captions are what make it land. A textfile keeps colons/quotes in the
    caption safe; an outline (not a box) stays cinematic. Returns '' when there's no
    text or no font on the host — captions are best-effort, never fatal.
    ponytail: fontsize/position are ratios of h; tune if a language runs long."""
    text = " ".join((text or "").split())
    font = _font_file()
    if not text or not font or not _has_drawtext():  # no drawtext (e.g. Vercel static ffmpeg) -> skip
        return ""
    lines = textwrap.wrap(text, width=max(16, int(w / (h * 0.026))))[:3]  # cap 3 lines
    with open(capfile, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    fs = max(20, round(h * 0.030))
    esc = lambda p: p.replace("\\", "/").replace(":", r"\:")  # ffmpeg filter path escaping
    # expansion=none: the VO is untrusted text — never let a '%{...}' token or a
    # backslash in a caption get interpreted by drawtext; render it literally.
    return (f",drawtext=textfile='{esc(capfile)}':fontfile='{esc(font)}':expansion=none:"
            f"fontsize={fs}:fontcolor=white:borderw={max(2, fs // 12)}:bordercolor=black@0.85:"
            f"x=(w-text_w)/2:y=h-text_h-{round(h * 0.06)}:line_spacing=8")

def build_clip(img: str, sec: float, motion: str, w: int, h: int,
               audio: str | None, out: str, caption: str = "") -> None:
    vf = zoompan_filter(motion, sec, w, h) + _caption_filter(caption, w, h, out + ".cap.txt")
    cmd = [FFMPEG, "-y", "-loop", "1", "-i", img]
    if audio:
        cmd += ["-i", audio]
    else:  # silent track so EVERY clip has audio -> the concat demuxer never trips on a
        cmd += ["-f", "lavfi", "-t", str(max(sec, 0.5)), "-i", "anullsrc=r=44100:cl=stereo"]  # mix of streams
    # -t (not -shortest): clip is exactly `sec`; short VO leaves trailing silence,
    # so total duration matches the shot list instead of the voiceover length.
    # Uniform aac 44.1k stereo so every clip's audio matches for the concat demuxer.
    cmd += ["-t", str(max(sec, 0.5)), "-vf", vf, "-r", "30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "26",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", out]
    _run(cmd)

def build_clip_from_video(video_in: str, w: int, h: int, audio: str | None,
                          out: str, caption: str = "") -> None:
    """Cinematic tier: fit a generated motion clip to the WxH canvas (same blurred
    cover-fill as the stills path, no crop) + burned-in caption. Uses narration `audio`
    when given, else a SILENT track (not the clip's own soundtrack) — a Venice clip may
    have no audio stream, and mixing present/absent audio across clips breaks the concat
    demuxer on the strict linux ffmpeg. Trimmed to VID_SECS to match the shot list."""
    long = max(w, h)
    vf = (f"scale={long}:{long}:force_original_aspect_ratio=decrease,split=2[bg][fg];"
          f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
          f"boxblur=24:2,eq=brightness=-0.18:saturation=1.15[bg];"
          f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p"
          + _caption_filter(caption, w, h, out + ".cap.txt"))
    cmd = [FFMPEG, "-y", "-i", video_in]
    if audio:  # narration track
        cmd += ["-i", audio]
    else:  # silent track so EVERY clip has uniform aac 44.1k stereo audio (concat-safe)
        cmd += ["-f", "lavfi", "-t", str(VID_SECS), "-i", "anullsrc=r=44100:cl=stereo"]
    cmd += ["-map", "0:v", "-map", "1:a", "-t", str(VID_SECS), "-vf", vf, "-r", "30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "26",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", out]
    _run(cmd)

def assemble(clips: list[str], out: str) -> None:
    """Concat re-encoding so mixed audio/no-audio clips join cleanly."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for c in clips:
            # forward slashes: '\' is an escape char in ffmpeg's concat format, so a
            # Windows backslash path fails to open. No-op on Linux (the deploy target).
            f.write(f"file '{os.path.abspath(c).replace(os.sep, '/')}'\n")
        listfile = f.name
    try:
        _run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", listfile,
              "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "26",
              "-c:a", "aac", "-movflags", "+faststart", out])  # crf+faststart: smaller, streamable
    finally:
        os.unlink(listfile)  # don't leak the concat list in system temp if ffmpeg fails

# ---------- Score + Sting: title/end cards + a music bed ----------

TITLE_SEC = float(os.environ.get("DALANG_TITLE_SEC", 1.6))
END_SEC = float(os.environ.get("DALANG_END_SEC", 2.2))
_BRAND_BG, _BRAND_GOLD = "0x140d06", "0xC8A45A"  # DALANG dark + gold

def _draw(textfile: str, font: str, fs: int, color: str, y: str, extra: str = "") -> str:
    esc = lambda p: p.replace("\\", "/").replace(":", r"\:")
    return (f",drawtext=textfile='{esc(textfile)}':fontfile='{esc(font)}':expansion=none:"
            f"fontsize={fs}:fontcolor={color}:x=(w-text_w)/2:y={y}{extra}")

def build_bookend(title: str, subtitle: str, sec: float, w: int, h: int, out: str,
                  gold_title: bool = False) -> None:
    """A branded card (dark bg + centered title + gold subtitle, fade in/out) with a
    silent audio track so it concats with narrated clips and carries a music bed.
    Text is best-effort: no font on the host -> a clean colored card, never a failure."""
    font = _font_file()
    draws = ""
    if font and title and _has_drawtext():  # no drawtext build (Vercel static) -> a clean textless card
        tf = out + ".t.txt"
        with open(tf, "w", encoding="utf-8") as f:
            f.write("\n".join(textwrap.wrap(title, 20)[:3]))
        draws += _draw(tf, font, max(24, round(h * 0.056)), _BRAND_GOLD if gold_title else "white",
                       "(h-text_h)/2-h*0.03", ":borderw=0:line_spacing=14")
        if subtitle:
            sf = out + ".s.txt"
            with open(sf, "w", encoding="utf-8") as f:
                f.write(" ".join(subtitle.split())[:60])
            draws += _draw(sf, font, max(16, round(h * 0.023)),
                           "white" if gold_title else _BRAND_GOLD, "h*0.56")
    # setsar=1 matches the shot clips (zoompan sets it) so the concat demuxer's video params line up
    vf = f"format=yuv420p,setsar=1{draws},fade=t=in:st=0:d=0.4,fade=t=out:st={max(0.1, sec - 0.5)}:d=0.5"
    _run([FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c={_BRAND_BG}:s={w}x{h}:d={sec}",
          "-f", "lavfi", "-t", str(sec), "-i", "anullsrc=r=44100:cl=stereo",
          "-vf", vf, "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
          "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-ar", "44100", "-ac", "2",
          "-shortest", out])

MUSIC_MOODS = {"warm", "tense", "upbeat", "noir"}
_STYLE_MOOD = {"cinematic": "warm", "anime": "upbeat", "noir": "noir", "watercolor": "warm",
               "claymation": "upbeat", "storybook": "warm", "3d": "upbeat"}

def resolve_bed(music: str, style: str) -> str | None:
    """Map a `music` request to a bed file (or None=off). ''/'none'/'off' -> off;
    an existing file path -> that track; 'auto' -> a mood from the style preset; a mood
    name (warm/tense/upbeat/noir) -> DALANG_MUSIC_DIR/<mood>.mp3 then the bundled bed."""
    m = (music or "").strip()
    if not m or m.lower() in ("none", "off"):
        return None
    if os.path.exists(m):
        return m
    ml = m.lower()
    if ml == "auto":
        ml = _STYLE_MOOD.get((style or "").strip().lower(), "warm")
    if ml not in MUSIC_MOODS:
        return None
    for d in (os.environ.get("DALANG_MUSIC_DIR"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "music")):
        if d and os.path.exists(os.path.join(d, ml + ".mp3")):
            return os.path.join(d, ml + ".mp3")
    return None

def mix_music(video: str, bed: str, out: str) -> None:
    """Loop the bed under the video and duck it beneath the narration (sidechain
    compress), then mux (video stream copied). Needs the video to carry an audio
    stream — narration or a bookend's silence; callers use it best-effort."""
    _run([FFMPEG, "-y", "-i", video, "-stream_loop", "-1", "-i", bed, "-filter_complex",
          "[1:a]volume=0.30[bed];"
          "[bed][0:a]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=380[duck];"
          "[0:a][duck]amix=inputs=2:duration=first:dropout_transition=2[a]",
          "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
          "-movflags", "+faststart", out])

# ---------- serverless delivery helpers (keep the inline response under the body cap) ----------

def thumbnail(png_in: str, out_jpg: str, width: int = 480) -> None:
    """A small JPEG poster from a frame. A full hero PNG is ~2 MB (~3 MB base64) and alone
    blows a serverless response cap; this is ~60 KB, so the poster stops eating the budget."""
    _run([FFMPEG, "-y", "-i", png_in, "-vf", f"scale={width}:-2", "-q:v", "5", out_jpg])

def shrink_video(video_in: str, out: str, height: int = 1280, crf: int = 30) -> None:
    """Re-encode smaller (downscale + higher crf) so a render can still be delivered inline
    on a host with no object storage, instead of shipping a body the platform rejects."""
    _run([FFMPEG, "-y", "-i", video_in, "-vf", f"scale=-2:{height}", "-c:v", "libx264",
          "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", str(crf),
          "-c:a", "aac", "-ar", "44100", "-ac", "2", "-movflags", "+faststart", out])

def storyboard(brief: str, style: str, aspect: str, target_seconds: int, workdir: str,
               language: str = "", template: str = "") -> dict:
    """Cheap preview tier (~1 LLM + 1 image call, no video): the shot list + a single
    hero frame, so a caller can approve the direction before paying for a full render."""
    w, h = dims(aspect)
    plan = breakdown(apply_template(brief, template), resolve_style(style), target_seconds, language)
    os.makedirs(workdir, exist_ok=True)
    hero = os.path.join(workdir, "hero.png")
    seed = int(hashlib.sha256(plan["title"].encode()).hexdigest(), 16) % 100000
    gen_image(plan["shots"][0]["image_prompt"], hero, w, h, plan.get("subject", ""), seed)
    return {"title": plan["title"], "subject": plan.get("subject", ""),
            "shots": plan["shots"], "hero": hero, "srt": build_srt(plan)}

def render(brief: str, style: str, aspect: str, target_seconds: int, voiceover: bool,
           workdir: str, consistent: bool = True, captions: bool = True, voice: str = "",
           language: str = "", template: str = "", shot_list: dict | None = None,
           motion_engine: str = "kenburns", bookends: bool = False, music: str = "") -> dict:
    """Full pipeline. Returns paths + shot list. Caller (MCP tool) owns pricing.

    consistent=True: generate a hero frame, then produce every other frame by
    editing the hero into the new scene, so the subject stays the same across shots.
    consistent=False: each frame is an independent text-to-image (cheaper, less coherent).
    captions: burn the voiceover line into each shot (bottom-centered).
    voice: override the TTS voice per render (empty -> VENICE_TTS_VOICE).
    language: write title/voiceover in this language (ignored if shot_list is given).
    template: prepend a vertical structure (see TEMPLATES) to the brief.
    shot_list: render this ready-made plan directly and skip the LLM breakdown —
        lets an upstream 'director' agent own the storyboard (agent composability).
    motion_engine: "kenburns" (default, stills + Ken Burns) or "video" (PREMIUM —
        animate each still into real motion via image-to-video, ~$0.55/shot).
    bookends: prepend a branded title card + append a DALANG end card (makes the clip
        read as a film, not a tech demo). Adds TITLE_SEC + END_SEC to the duration.
    music: score under the video — ''/'none' off, 'auto' picks a mood from the style,
        or a mood name (warm/tense/upbeat/noir) / a file path. Best-effort (needs an
        audio track: narration or bookends), ducked under narration.
    """
    w, h = dims(aspect)
    plan = (validate_plan(shot_list) if shot_list
            else breakdown(apply_template(brief, template), resolve_style(style),
                           target_seconds, language))
    cinematic = motion_engine == "video"
    if cinematic and len(plan["shots"]) > MAX_VIDEO_SHOTS:  # cost guard: video is ~$0.55/shot
        plan["shots"] = plan["shots"][:MAX_VIDEO_SHOTS]
    if cinematic:  # each clip is a fixed-length motion shot; keep the shot list honest
        for s in plan["shots"]:
            s["seconds"] = VID_SECS
    subject = plan.get("subject", "")
    seed = int(hashlib.sha256(plan["title"].encode()).hexdigest(), 16) % 100000  # stable per render
    os.makedirs(workdir, exist_ok=True)
    shots = plan["shots"]

    def frame_path(s):
        return os.path.join(workdir, f"frame_{s['scene']:02d}.png")

    def do_tts(s):
        if not voiceover:
            return None
        cand = os.path.join(workdir, f"vo_{s['scene']:02d}.mp3")
        try:  # best-effort like frames: a flaky VO -> silent shot, never a failed render
            return cand if tts(s["voiceover"], cand, voice) else None
        except Exception:
            return None

    # frames
    if consistent and len(shots) > 1:
        hero = frame_path(shots[0])
        gen_image(shots[0]["image_prompt"], hero, w, h, subject, seed)  # hero first (dependency)

        def consistent_frame(s):
            out = frame_path(s)
            try:  # best-effort: a single edit refusal/failure must not kill the render
                edit_image(s["image_prompt"], hero, out, subject)
            except Exception:
                try:
                    gen_image(s["image_prompt"], out, w, h, subject, seed)  # fall back to fresh gen
                except Exception:
                    _placeholder_frame(out, w, h)  # ...and a solid frame before we'd ever fail the render
            return out

        with ThreadPoolExecutor(max_workers=6) as ex:
            edited = list(ex.map(consistent_frame, shots[1:]))
        frames = [hero] + edited
    else:
        def independent_frame(s):
            out = frame_path(s)
            try:  # best-effort: one shot's failure must not sink the whole render
                gen_image(s["image_prompt"], out, w, h, subject, seed)
            except Exception:
                _placeholder_frame(out, w, h)
            return out

        with ThreadPoolExecutor(max_workers=6) as ex:
            frames = list(ex.map(independent_frame, shots))
    # voiceovers (independent, parallel)
    with ThreadPoolExecutor(max_workers=6) as ex:
        auds = list(ex.map(do_tts, shots))

    _has_drawtext()  # warm the cache once now so the concurrent do_clip calls below don't race to probe

    def do_clip(args):
        s, img, aud = args
        clip = os.path.join(workdir, f"clip_{s['scene']:02d}.mp4")
        cap = s["voiceover"] if captions else ""
        if cinematic:
            motion_mp4 = os.path.join(workdir, f"motion_{s['scene']:02d}.mp4")
            try:  # best-effort: a video failure falls back to Ken Burns on the still
                gen_video(img, s["image_prompt"], s["motion"], motion_mp4)
                build_clip_from_video(motion_mp4, w, h, aud, clip, caption=cap)
                return clip
            except Exception:
                pass
        try:
            build_clip(img, float(s["seconds"]), s["motion"], w, h, aud, clip, caption=cap)
        except Exception:  # a corrupt frame (ffmpeg fails/times out) must not sink the render ->
            ph = os.path.join(workdir, f"ph_{s['scene']:02d}.png")  # fall back to a placeholder clip
            _placeholder_frame(ph, w, h)
            build_clip(ph, float(s["seconds"]), "static", w, h, aud, clip, caption=cap)
        return clip

    # video clips run on Venice's queue (I/O-bound), so a wider pool is fine there
    with ThreadPoolExecutor(max_workers=6 if cinematic else 3) as ex:
        clips = list(ex.map(do_clip, zip(shots, frames, auds)))
    if bookends:  # branded title + end card so the clip reads as a film (Score + Sting)
        tcard, ecard = os.path.join(workdir, "card_title.mp4"), os.path.join(workdir, "card_end.mp4")
        build_bookend(plan["title"], subject or brief, TITLE_SEC, w, h, tcard, gold_title=True)
        build_bookend("DALANG", "storyboard → animatic · on-chain on X Layer", END_SEC, w, h, ecard)
        clips = [tcard] + clips + [ecard]
    animatic = os.path.join(workdir, "animatic.mp4")
    assemble(clips, animatic)
    bed = resolve_bed(music, style)
    if bed:  # best-effort music bed: a no-audio render (no VO, no bookends) just keeps the silent cut
        scored = os.path.join(workdir, "scored.mp4")
        try:
            mix_music(animatic, bed, scored)
            animatic = scored
        except Exception:
            pass
    extra = (TITLE_SEC + END_SEC) if bookends else 0.0
    shotlist = os.path.join(workdir, "shot_list.json")
    with open(shotlist, "w") as f:
        json.dump(plan, f, indent=2)
    return {"title": plan["title"], "animatic": animatic, "frames": frames,
            "shot_list": shotlist, "duration_seconds": round(total_seconds(plan) + extra, 2),
            "srt": build_srt(plan, offset=TITLE_SEC if bookends else 0.0)}

# ---------- self-check (no network / no ffmpeg needed) ----------

def demo() -> None:
    assert dims("9:16") == (1080, 1920)
    try:
        dims("4:3"); assert False
    except ValueError:
        pass
    f = zoompan_filter("pan_left", 3.0, 1080, 1920)
    assert "zoompan=" in f and "d=90" in f and "1080x1920" in f, f
    gw, gh = _gen_size(1080, 1920)
    assert max(gw, gh) <= 1280 and gw % 8 == 0 and gh % 8 == 0, (gw, gh)
    assert _gen_size(1024, 1024) == (1024, 1024)
    assert json.loads(_strip_fence('```json\n{"a":1}\n```')) == {"a": 1}
    assert json.loads(_strip_fence('{"b":2}')) == {"b": 2}
    assert _norm_motion("slow zoom in") == "zoom_in"
    assert _norm_motion("Pan-Right") == "pan_right"
    assert _norm_motion("dolly") == "static"
    assert _norm_motion(123) == "static" and _norm_motion(None) == "static"  # non-str motion -> no crash
    assert "Authorization" in _download_auth("https://api.venice.ai/video/x")  # Venice host -> token sent
    assert _download_auth("https://d1234.cloudfront.net/v.mp4?sig=abc") == {}   # signed CDN -> NO token leak
    assert _download_auth("https://evil.example.com/v.mp4") == {}               # third party -> NO token leak
    for bad in ("file:///etc/passwd", "gopher://x", "ftp://x/y"):
        try:
            _download_auth(bad); assert False
        except RuntimeError:
            pass  # non-http(s) scheme rejected (no SSRF via a malicious response)
    assert validate_plan({"shots": [{"image_prompt": "a", "motion": 123}]})["shots"][0]["motion"] == "static"
    assert shot_budget(20) == (5, 4)  # demo-scale request
    n90, per90 = shot_budget(90)      # long request stays within the cost cap
    assert n90 == MAX_SHOTS and 2 <= per90 <= 6
    assert shot_budget(8)[0] >= 3     # tiny request still gets a few shots
    assert resolve_style("ANIME ").startswith("anime cel")  # preset name -> art direction
    assert resolve_style("my own look") == "my own look"    # unknown -> passthrough
    assert apply_template("my brief", "product_ad").endswith("my brief") and "call to action" in apply_template("x", "product_ad")
    assert apply_template("my brief", "nope") == "my brief"  # unknown template -> passthrough
    srt = build_srt({"shots": [                              # cumulative timing, silent shot skipped
        {"voiceover": "First line.", "seconds": 3},
        {"voiceover": "", "seconds": 2},
        {"voiceover": "Third line.", "seconds": 2.5}]})
    assert "1\n00:00:00,000 --> 00:00:03,000\nFirst line." in srt
    assert "2\n00:00:05,000 --> 00:00:07,500\nThird line." in srt  # 3+2 silent -> starts at 5s
    assert _srt_time(3661.5) == "01:01:01,500"
    assert resolve_bed("", "cinematic") is None and resolve_bed("none", "anime") is None  # off
    assert resolve_bed("zzz", "cinematic") is None      # unknown mood -> off (not a crash)
    assert _STYLE_MOOD["noir"] == "noir" and _STYLE_MOOD["anime"] == "upbeat"  # auto maps style->mood
    assert build_srt({"shots": [{"voiceover": "hi", "seconds": 2}]}, offset=1.6).startswith(
        "1\n00:00:01,600 -->")                          # title card shifts every cue
    assert _caption_filter("", 1080, 1920, "unused.txt") == ""  # no text -> no drawtext, no write
    os.environ["DALANG_NO_DRAWTEXT"] = "1"  # simulate a build without drawtext (Vercel static ffmpeg)
    assert _caption_filter("hi", 1080, 1920, "unused.txt") == ""  # -> skip text, don't fail the render
    del os.environ["DALANG_NO_DRAWTEXT"]
    if _font_file() and _has_drawtext():  # font + a drawtext build -> a safe-escaped drawtext filter
        cf = _caption_filter("Colons: and 'quotes' are fine.", 1080, 1920,
                             os.path.join(tempfile.gettempdir(), "dalang_capcheck.txt"))
        assert cf.startswith(",drawtext=textfile=") and "fontfile=" in cf, cf
    plan = {"title": "t", "shots": [
        {"scene": 1, "image_prompt": "a", "voiceover": "hi", "seconds": 3, "motion": "zoom in"},
        {"image_prompt": "b", "voiceover": "", "seconds": 2.5},  # no scene/motion -> defaults
    ]}
    v = validate_plan(plan)
    assert total_seconds(v) == 5.5
    assert v["shots"][0]["motion"] == "zoom_in" and v["shots"][1]["motion"] == "static"
    assert v["shots"][1]["scene"] == 2
    dup = validate_plan({"title": "t", "shots": [  # model reused scene 7 -> must renumber unique
        {"scene": 7, "image_prompt": "a", "voiceover": "", "seconds": 2},
        {"scene": 7, "image_prompt": "b", "voiceover": "", "seconds": 2}]})
    assert [s["scene"] for s in dup["shots"]] == [1, 2]
    assert v["title"] == "t" and v["subject"] == ""  # subject defaulted when absent
    miss = validate_plan({"subject": 7, "shots": [  # no title, non-str subject: must not crash render
        {"image_prompt": "a", "voiceover": "", "seconds": 2}]})
    assert miss["title"] == "Untitled animatic" and miss["subject"] == "7"
    # self-heal (money path): an LLM omitting image_prompt on a shot must NOT fail a paid render
    healed = validate_plan({"subject": "a red mug", "shots": [{"voiceover": "hi", "seconds": 3}]})
    assert healed["shots"][0]["image_prompt"] == "a red mug"  # falls back to the subject
    nd = validate_plan({"subject": "S", "shots": ["oops", {"seconds": 2}]})  # non-dict element
    assert len(nd["shots"]) == 2 and nd["shots"][0]["image_prompt"] == "S"   # coerced, not crashed
    assert validate_plan({"shots": [{"seconds": 99}]})["shots"][0]["seconds"] == 15  # clamped, not raised
    assert validate_plan({"shots": [{"seconds": "bad"}]})["shots"][0]["seconds"] == 3  # non-numeric -> default
    assert len(validate_plan({"shots": [{"image_prompt": "x"}] * 15})["shots"]) == MAX_SHOTS  # truncated to cap
    try:
        validate_plan({"shots": []}); assert False  # no shots is the one hard failure
    except ValueError:
        pass
    for notdict in ([1, 2, 3], "oops", 5, None):  # LLM top-level array/primitive -> clean ValueError, not AttributeError
        try:
            validate_plan(notdict); assert False
        except ValueError:
            pass
    print("dalang pipeline self-check ok")

if __name__ == "__main__":
    demo()
