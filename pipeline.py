"""DALANG pipeline: script -> shot list -> storyboard frames -> animatic mp4.

Pure helpers (dims / zoompan_filter / validate_plan / total_seconds) carry the
non-trivial logic and are exercised by demo() below. The impure steps
(Venice LLM/image/TTS, ffmpeg) are thin wrappers around external tools — each is
a calibration knob, not clever code. One Venice key powers all three stages.
"""
from __future__ import annotations
import base64, json, os, subprocess, tempfile, urllib.request

# ---------- pure logic (tested by demo()) ----------

ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}

def dims(aspect: str) -> tuple[int, int]:
    if aspect not in ASPECTS:
        raise ValueError(f"aspect must be one of {list(ASPECTS)}, got {aspect!r}")
    return ASPECTS[aspect]

def zoompan_filter(motion: str, sec: float, w: int, h: int, fps: int = 30) -> str:
    """Ken Burns filter for one still. ponytail: linear z/x/y ramps; swap for
    eased curves if the motion looks robotic."""
    frames = max(1, round(sec * fps))
    # oversample the source so pan has room, then zoompan crops back to WxH.
    base = f"scale={w*2}:-1,setsar=1"
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
    return (f"{base},zoompan=z={z}:x='{x}':y='{y}':"
            f"d={frames}:s={w}x{h}:fps={fps},format=yuv420p")

def validate_plan(plan: dict) -> dict:
    if not isinstance(plan.get("shots"), list) or not plan["shots"]:
        raise ValueError("plan has no shots")
    for i, s in enumerate(plan["shots"]):
        for k in ("image_prompt", "voiceover", "seconds", "motion"):
            if k not in s:
                raise ValueError(f"shot {i} missing {k}")
        if not (0.5 <= float(s["seconds"]) <= 15):
            raise ValueError(f"shot {i} seconds out of range: {s['seconds']}")
    return plan

def total_seconds(plan: dict) -> float:
    return round(sum(float(s["seconds"]) for s in plan["shots"]), 2)

# ---------- Claude breakdown ----------

VENICE_BASE = os.environ.get("VENICE_BASE_URL", "https://api.venice.ai/api/v1")
LLM_MODEL = os.environ.get("VENICE_LLM_MODEL", "qwen3-235b-a22b-instruct-2507")
IMAGE_MODEL = os.environ.get("VENICE_IMAGE_MODEL", "z-image-turbo")
TTS_MODEL = os.environ.get("VENICE_TTS_MODEL", "tts-kokoro")
TTS_VOICE = os.environ.get("VENICE_TTS_VOICE", "af_sky")

def _venice(path: str, body: dict, raw: bool = False):
    key = os.environ["VENICE_API_KEY"]
    req = urllib.request.Request(
        VENICE_BASE + path, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    return data if raw else json.loads(data)

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
        '{"title": string, "shots": [{"scene": int, "image_prompt": string, '
        '"voiceover": string, "seconds": number, "motion": one of '
        '["zoom_in","zoom_out","pan_left","pan_right","static"]}]}. '
        f"Total seconds near {target_seconds}. image_prompt: a vivid, self-contained still in "
        f"this style: {style}, <=30 words. voiceover: one short spoken line (<=18 words) or \"\". "
        "Use EXACTLY these motion tokens. 4-6 shots, each 2-4 seconds. No prose, JSON only."
    )
    r = _venice("/chat/completions", {
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": sys}, {"role": "user", "content": brief}],
        "max_tokens": 6000, "temperature": 0.7,
    })
    text = _strip_fence(r["choices"][0]["message"]["content"])
    return validate_plan(json.loads(text, strict=False))  # tolerate raw newlines in strings

def gen_image(prompt: str, out_path: str, w: int, h: int) -> None:
    """Venice image -> base64 PNG. ponytail: swap VENICE_IMAGE_MODEL for FLUX 2 / Seedream."""
    gw, gh = _gen_size(w, h)
    r = _venice("/image/generate", {"model": IMAGE_MODEL, "prompt": prompt,
                                     "width": gw, "height": gh, "format": "png"})
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(r["images"][0]))

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
        cmd += ["-i", audio, "-shortest"]
    cmd += ["-t", str(max(sec, 0.5)), "-vf", vf, "-r", "30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p"]
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
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", out])
    os.unlink(listfile)

def render(brief: str, style: str, aspect: str, target_seconds: int, voiceover: bool,
           workdir: str) -> dict:
    """Full pipeline. Returns paths + shot list. Caller (MCP tool) owns pricing."""
    w, h = dims(aspect)
    plan = breakdown(brief, style, target_seconds)
    os.makedirs(workdir, exist_ok=True)
    frames, clips = [], []
    for s in plan["shots"]:
        i = s["scene"]
        img = os.path.join(workdir, f"frame_{i:02d}.png")
        gen_image(s["image_prompt"], img, w, h)
        frames.append(img)
        aud = None
        if voiceover:
            cand = os.path.join(workdir, f"vo_{i:02d}.mp3")
            aud = cand if tts(s["voiceover"], cand) else None
        clip = os.path.join(workdir, f"clip_{i:02d}.mp4")
        build_clip(img, float(s["seconds"]), s["motion"], w, h, aud, clip)
        clips.append(clip)
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
    plan = {"title": "t", "shots": [
        {"scene": 1, "image_prompt": "a", "voiceover": "hi", "seconds": 3, "motion": "zoom_in"},
        {"scene": 2, "image_prompt": "b", "voiceover": "", "seconds": 2.5, "motion": "static"},
    ]}
    assert total_seconds(validate_plan(plan)) == 5.5
    try:
        validate_plan({"shots": [{"image_prompt": "x", "voiceover": "", "seconds": 99, "motion": "static"}]})
        assert False
    except ValueError:
        pass
    print("dalang pipeline self-check ok")

if __name__ == "__main__":
    demo()
