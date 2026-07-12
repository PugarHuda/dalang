"""DALANG pipeline: script -> shot list -> storyboard frames -> animatic mp4.

Pure helpers (dims / zoompan_filter / validate_plan / total_seconds) carry the
non-trivial logic and are exercised by demo() below. The impure steps
(Venice LLM/image/TTS, ffmpeg) are thin wrappers around external tools — each is
a calibration knob, not clever code. One Venice key powers all three stages.
"""
from __future__ import annotations
import base64, hashlib, json, os, subprocess, tempfile, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

# ---------- pure logic (tested by demo()) ----------

ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
MOTIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right", "static"}
MAX_SHOTS = 10  # cost guard: refuse runaway shot lists

def _norm_motion(m: str) -> str:
    """Map a model's free-text motion to a valid token (default static).
    Fixes gap: models return e.g. 'slow zoom in' -> was silently dropped."""
    m = (m or "").lower().strip().replace(" ", "_").replace("-", "_")
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
    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("plan has no shots")
    if len(shots) > MAX_SHOTS:
        raise ValueError(f"too many shots ({len(shots)} > {MAX_SHOTS})")
    for i, s in enumerate(shots):
        for k in ("image_prompt", "voiceover", "seconds"):
            if k not in s:
                raise ValueError(f"shot {i} missing {k}")
        if not (0.5 <= float(s["seconds"]) <= 15):
            raise ValueError(f"shot {i} seconds out of range: {s['seconds']}")
        s["motion"] = _norm_motion(s.get("motion", "static"))  # never trust the enum blindly
        s.setdefault("scene", i + 1)
    return plan

def total_seconds(plan: dict) -> float:
    return round(sum(float(s["seconds"]) for s in plan["shots"]), 2)

# ---------- Venice provider (LLM + image + TTS, one key) ----------

VENICE_BASE = os.environ.get("VENICE_BASE_URL", "https://api.venice.ai/api/v1")
LLM_MODEL = os.environ.get("VENICE_LLM_MODEL", "qwen3-235b-a22b-instruct-2507")
IMAGE_MODEL = os.environ.get("VENICE_IMAGE_MODEL", "z-image-turbo")
EDIT_MODEL = os.environ.get("VENICE_EDIT_MODEL", "qwen-image-2-edit")  # reliable editor (fast lite models refuse people)
TTS_MODEL = os.environ.get("VENICE_TTS_MODEL", "tts-kokoro")
TTS_VOICE = os.environ.get("VENICE_TTS_VOICE", "af_sky")

_RETRYABLE = {408, 409, 429, 500, 502, 503, 504}

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
            return data if raw else json.loads(data)
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

def breakdown(brief: str, style: str, target_seconds: int) -> dict:
    """Script/idea -> shot list, via Venice chat (OpenAI-compatible)."""
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
        "Use EXACTLY these motion tokens. 4-6 shots, each 2-4 seconds. No prose, JSON only."
    )
    r = _venice("/chat/completions", {
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": sys}, {"role": "user", "content": brief}],
        "max_tokens": 6000, "temperature": 0.7,
    })
    text = _strip_fence(r["choices"][0]["message"]["content"])
    return validate_plan(json.loads(text, strict=False))  # tolerate raw newlines in strings

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

def tts(text: str, out_path: str) -> bool:
    """Venice TTS (Kokoro). False (silent shot) when the line is empty."""
    if not text.strip():
        return False
    audio = _venice("/audio/speech", {"model": TTS_MODEL, "input": text,
                                      "voice": TTS_VOICE, "response_format": "mp3"}, raw=True)
    with open(out_path, "wb") as f:
        f.write(audio)
    return True

# ---------- ffmpeg assembly ----------

def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)

def build_clip(img: str, sec: float, motion: str, w: int, h: int,
               audio: str | None, out: str) -> None:
    vf = zoompan_filter(motion, sec, w, h)
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", img]
    if audio:
        cmd += ["-i", audio]
    # -t (not -shortest): clip is exactly `sec`; short VO leaves trailing silence,
    # so total duration matches the shot list instead of the voiceover length.
    cmd += ["-t", str(max(sec, 0.5)), "-vf", vf, "-r", "30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "26"]
    if audio:
        cmd += ["-c:a", "aac"]
    cmd += [out]
    _run(cmd)

def assemble(clips: list[str], out: str) -> None:
    """Concat re-encoding so mixed audio/no-audio clips join cleanly."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
        listfile = f.name
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "26",
          "-c:a", "aac", "-movflags", "+faststart", out])  # crf+faststart: smaller, streamable
    os.unlink(listfile)

def render(brief: str, style: str, aspect: str, target_seconds: int, voiceover: bool,
           workdir: str, consistent: bool = True) -> dict:
    """Full pipeline. Returns paths + shot list. Caller (MCP tool) owns pricing.

    consistent=True: generate a hero frame, then produce every other frame by
    editing the hero into the new scene, so the subject stays the same across shots.
    consistent=False: each frame is an independent text-to-image (cheaper, less coherent).
    """
    w, h = dims(aspect)
    plan = breakdown(brief, style, target_seconds)
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
        return cand if tts(s["voiceover"], cand) else None

    # frames
    if consistent and len(shots) > 1:
        hero = frame_path(shots[0])
        gen_image(shots[0]["image_prompt"], hero, w, h, subject, seed)  # hero first (dependency)

        def consistent_frame(s):
            out = frame_path(s)
            try:  # best-effort: a single edit refusal/failure must not kill the render
                edit_image(s["image_prompt"], hero, out, subject)
            except Exception:
                gen_image(s["image_prompt"], out, w, h, subject, seed)  # fall back to fresh gen
            return out

        with ThreadPoolExecutor(max_workers=6) as ex:
            edited = list(ex.map(consistent_frame, shots[1:]))
        frames = [hero] + edited
    else:
        with ThreadPoolExecutor(max_workers=6) as ex:
            frames = list(ex.map(
                lambda s: (gen_image(s["image_prompt"], frame_path(s), w, h, subject, seed)
                           or frame_path(s)),
                shots))
    # voiceovers (independent, parallel)
    with ThreadPoolExecutor(max_workers=6) as ex:
        auds = list(ex.map(do_tts, shots))

    def do_clip(args):
        s, img, aud = args
        clip = os.path.join(workdir, f"clip_{s['scene']:02d}.mp4")
        build_clip(img, float(s["seconds"]), s["motion"], w, h, aud, clip)
        return clip

    with ThreadPoolExecutor(max_workers=3) as ex:  # a few ffmpeg procs across cores
        clips = list(ex.map(do_clip, zip(shots, frames, auds)))
    animatic = os.path.join(workdir, "animatic.mp4")
    assemble(clips, animatic)
    shotlist = os.path.join(workdir, "shot_list.json")
    with open(shotlist, "w") as f:
        json.dump(plan, f, indent=2)
    return {"title": plan["title"], "animatic": animatic, "frames": frames,
            "shot_list": shotlist, "duration_seconds": total_seconds(plan)}

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
    plan = {"title": "t", "shots": [
        {"scene": 1, "image_prompt": "a", "voiceover": "hi", "seconds": 3, "motion": "zoom in"},
        {"image_prompt": "b", "voiceover": "", "seconds": 2.5},  # no scene/motion -> defaults
    ]}
    v = validate_plan(plan)
    assert total_seconds(v) == 5.5
    assert v["shots"][0]["motion"] == "zoom_in" and v["shots"][1]["motion"] == "static"
    assert v["shots"][1]["scene"] == 2
    for bad in ([{"image_prompt": "x", "voiceover": "", "seconds": 99}],
                [{"image_prompt": "x", "voiceover": "", "seconds": 3}] * 11):
        try:
            validate_plan({"shots": bad}); assert False
        except ValueError:
            pass
    print("dalang pipeline self-check ok")

if __name__ == "__main__":
    demo()
