"""Offline integration test for the render pipeline + paid boundary.

Venice (LLM/image/TTS) is stubbed to emit real dummy assets via ffmpeg, so this
runs with NO API key and exercises the parts self-check can't: the real ffmpeg
Ken Burns + caption + concat chain, best-effort error handling, and the MCP
tool's guards and response shape.

    python test_render.py     # exits non-zero on any failure; SKIPs if no ffmpeg
"""
import base64, json, os, shutil, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline, server

def _have(bin_: str) -> bool:
    return shutil.which(bin_) is not None

if not (_have("ffmpeg") and _have("ffprobe")):
    print("SKIP test_render: ffmpeg/ffprobe not on PATH")
    sys.exit(0)

FAILS = []
def check(name, cond, extra=""):
    print(("  ok  " if cond else " FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)

def _probe(path, entries):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", entries, "-of", "json", path], capture_output=True, text=True)
    return json.loads(r.stdout)["streams"][0]
def _duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nk=1:nw=1", path], capture_output=True, text=True)
    return float(r.stdout.strip())
def _stream_types(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return r.stdout.split()

# ---- stub Venice with real dummy assets (no API key) ----
def fake_gen(prompt, out, w, h, subject="", seed=None):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=teal:s={max(64, w // 2)}x{max(64, h // 2)}:d=1",
                    "-frames:v", "1", out], check=True, capture_output=True)
def fake_edit(prompt, ref, out, subject=""):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=maroon:s=700x1200:d=1",
                    "-frames:v", "1", out], check=True, capture_output=True)
def fake_tts(text, out, voice=""):
    if not text.strip():
        return False
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=1",
                    "-c:a", "libmp3lame", out], check=True, capture_output=True)
    return True
PLAN = {"title": "QA Run", "subject": "a red enamel mug", "shots": [
    {"scene": 1, "image_prompt": "wide kitchen", "voiceover": "Colons: and 'quotes' survive.", "seconds": 3, "motion": "zoom_in"},
    {"scene": 2, "image_prompt": "close up", "voiceover": "", "seconds": 2, "motion": "static"},
    {"scene": 3, "image_prompt": "pour shot", "voiceover": "Third line here.", "seconds": 2.5, "motion": "pan_left"}]}
def fake_breakdown(brief, style, target_seconds, language=""):
    return pipeline.validate_plan(json.loads(json.dumps(PLAN)))

pipeline.gen_image, pipeline.edit_image = fake_gen, fake_edit
pipeline.tts, pipeline.breakdown = fake_tts, fake_breakdown

def render_tmp(**kw):
    d = tempfile.mkdtemp()
    try:
        return pipeline.render(kw.pop("brief", "b"), kw.pop("style", "cinematic"),
                               kw.pop("aspect", "9:16"), kw.pop("target", 20),
                               kw.pop("voiceover", True), d, **kw), d
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise

def main():
    print("== render() across aspects (real ffmpeg, stubbed Venice) ==")
    for aspect, (W, H) in pipeline.ASPECTS.items():
        res, d = render_tmp(aspect=aspect, style="anime", captions=True)
        v = _probe(res["animatic"], "stream=width,height")
        check(f"{aspect}: dims {v['width']}x{v['height']}", (v["width"], v["height"]) == (W, H))
        check(f"{aspect}: duration ~7.5s", abs(_duration(res["animatic"]) - 7.5) < 0.6)
        check(f"{aspect}: has video+audio", set(_stream_types(res["animatic"])) >= {"video", "audio"})
        check(f"{aspect}: srt has 2 cues", res["srt"].count("-->") == 2)
        shutil.rmtree(d, ignore_errors=True)

    print("\n== toggles ==")
    res, d = render_tmp(voiceover=False, consistent=False, captions=True)
    # every clip carries a uniform (silent) audio track so the concat demuxer never trips
    # on mixed streams across platforms (the linux static ffmpeg is stricter than Windows).
    check("voiceover=False -> renders with a uniform silent audio track",
          os.path.exists(res["animatic"]) and "audio" in _stream_types(res["animatic"]))
    shutil.rmtree(d, ignore_errors=True)
    res, d = render_tmp(aspect="1:1", captions=False)
    check("captions=False renders", os.path.exists(res["animatic"]))
    shutil.rmtree(d, ignore_errors=True)

    print("\n== Score + Sting: bookends + music bed ==")
    res, d = render_tmp(aspect="9:16", style="anime", bookends=True, music="auto")
    dur = _duration(res["animatic"])
    check("bookends add title+end cards to duration",  # 7.5 shots + 1.6 title + 2.2 end
          abs(dur - (7.5 + pipeline.TITLE_SEC + pipeline.END_SEC)) < 0.8, f"{dur:.2f}s")
    check("scored render has video+audio", set(_stream_types(res["animatic"])) >= {"video", "audio"})
    check("srt cues shift by the title card", res["srt"].startswith("1\n00:00:01,600 -->"))
    check("music bed was mixed in (scored.mp4 used)", res["animatic"].endswith("scored.mp4"))
    check("reported duration includes bookends", abs(res["duration_seconds"] - (7.5 + pipeline.TITLE_SEC + pipeline.END_SEC)) < 0.1)
    shutil.rmtree(d, ignore_errors=True)

    print("\n== cinematic tier (motion_engine=video, stubbed gen_video) ==")
    def fake_video(frame, image_prompt, motion, out, **kw):  # real dummy motion clip, no API
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=s=720x1280:d=5:r=30",
                        "-f", "lavfi", "-i", "sine=frequency=220:duration=5", "-shortest",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", out],
                       check=True, capture_output=True)
    pipeline.gen_video = fake_video
    res, d = render_tmp(aspect="9:16", target=20, captions=True, motion_engine="video")
    v = _probe(res["animatic"], "stream=width,height")
    check("video tier: canvas 1080x1920", (v["width"], v["height"]) == (1080, 1920))
    check("video tier: has video+audio", set(_stream_types(res["animatic"])) >= {"video", "audio"})
    check("video tier: srt uses 5s shots", "00:00:05,000" in res["srt"])
    shutil.rmtree(d, ignore_errors=True)
    def video_boom(*a, **k): raise RuntimeError("video queue 500")
    pipeline.gen_video = video_boom
    res, d = render_tmp(aspect="9:16", target=20, motion_engine="video")  # must fall back to Ken Burns
    check("video failure -> Ken Burns fallback, render survives", os.path.exists(res["animatic"]))
    shutil.rmtree(d, ignore_errors=True)

    print("\n== best-effort resilience ==")
    def boom(*a, **k): raise RuntimeError("venice down")
    pipeline.tts = boom
    res, d = render_tmp(captions=True)
    check("raising TTS -> silent shot, render survives (uniform silent audio)",
          os.path.exists(res["animatic"]) and "audio" in _stream_types(res["animatic"]))
    shutil.rmtree(d, ignore_errors=True)
    pipeline.tts = fake_tts
    pipeline.edit_image = boom
    res, d = render_tmp(consistent=True)
    check("raising edit -> gen fallback, render survives", os.path.exists(res["animatic"]))
    shutil.rmtree(d, ignore_errors=True)
    pipeline.edit_image = fake_edit

    print("\n== server boundary: response shape ==")
    server.ACCESS_KEY, server.KEEP_FILES = None, False
    out = server.generate_animatic(brief="a cozy cafe", style="anime", aspect_ratio="9:16", target_seconds=20)
    check("animatic_data_uri", out.get("animatic_data_uri", "").startswith("data:video/mp4;base64,"))
    check("poster_data_uri (jpeg thumbnail)", out.get("poster_data_uri", "").startswith("data:image/jpeg;base64,"))
    check("content_sha256 matches the DELIVERED bytes", out["content_sha256"] ==
          __import__("provenance").content_sha256(base64.b64decode(out["animatic_data_uri"].split(",", 1)[1])))
    check("srt with cues", "-->" in out.get("srt", ""))
    check("title + 3 shots", bool(out.get("title")) and len(out.get("shots", [])) == 3)
    check("workdir cleaned (no paths leaked)", "animatic" not in out)
    check("web3 provenance: sha256 + cid", out.get("content_sha256", "").startswith("0x") and out.get("content_cid", "").startswith("bafkrei"))
    check("proof-of-creation manifest + digest", out.get("provenance_manifest", {}).get("spec") == "dalang-provenance/1" and out.get("provenance_digest", "").startswith("0x"))
    check("no nft_metadata unless mint=True", "nft_metadata" not in out)
    minted = server.generate_animatic(brief="a cozy cafe", aspect_ratio="9:16", target_seconds=20, mint=True)
    nft = minted.get("nft_metadata", {})
    check("mint=True -> ERC-721 metadata", bool(nft.get("image")) and bool(nft.get("animation_url")) and nft.get("properties", {}).get("content_cid", "").startswith("bafkrei"))

    print("\n== storyboard preview funnel (cheap: shots + hero, no video) ==")
    sb = server.storyboard(brief="a cozy cafe", aspect_ratio="9:16", target_seconds=20)
    check("preview: shots + hero poster, no video", len(sb.get("shots", [])) > 0
          and sb.get("hero_data_uri", "").startswith("data:image/png") and "animatic_data_uri" not in sb)

    print("\n== composability: shot_list skips breakdown ==")
    pipeline.breakdown = boom
    out = server.generate_animatic(brief="", shot_list=PLAN, aspect_ratio="16:9", target_seconds=30)
    check("shot_list renders without breakdown", out.get("animatic_data_uri", "").startswith("data:video"))
    pipeline.breakdown = fake_breakdown

    print("\n== guards return clean {error}, never raise ==")
    check("no brief & no shot_list", "error" in server.generate_animatic(brief="  "))
    check("bad aspect", "aspect_ratio" in server.generate_animatic(brief="x", aspect_ratio="4:3").get("error", ""))
    check("bad target_seconds", "error" in server.generate_animatic(brief="x", target_seconds="abc"))
    server.ACCESS_KEY = "secret"
    check("wrong access_key", "unauthorized" in server.generate_animatic(brief="x", access_key="no").get("error", ""))
    check("right access_key renders", server.generate_animatic(brief="x", access_key="secret", target_seconds=20).get("animatic_data_uri", "").startswith("data:video"))
    server.ACCESS_KEY = None

    print("\n== render failure -> clean error at the paid boundary ==")
    pipeline.gen_image = boom
    r = server.generate_animatic(brief="x", target_seconds=20)
    check("gen failure -> {error}", "error" in r and "render failed" in r["error"])
    pipeline.gen_image = fake_gen

    print("\n" + ("test_render: ALL PASSED" if not FAILS else f"test_render FAILURES: {FAILS}"))
    return 1 if FAILS else 0

if __name__ == "__main__":
    sys.exit(main())
