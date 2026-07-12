"""DALANG — Storyboard-to-Animatic ASP for OKX.AI (A2MCP, pay-per-call).

One tool = one billable call. Register this MCP server on OKX.AI in A2MCP mode;
OKX wraps the pay-per-call settlement (USDT/USDG on X Layer) around it.
"""
import base64, os, uuid
from fastmcp import FastMCP
from pipeline import render

# A remote A2MCP caller can't read the host's filesystem, so we embed the video
# (and shot list) in the result. Above this size, skip the blob and return the
# path only (host a file server / object storage for large outputs — see DEPLOY.md).
MAX_INLINE_BYTES = int(os.environ.get("DALANG_MAX_INLINE_BYTES", 8_000_000))

mcp = FastMCP("dalang")

WORKROOT = os.environ.get("DALANG_WORKROOT", os.path.join(os.getcwd(), "runs"))

@mcp.tool
def generate_animatic(
    brief: str,
    style: str = "cinematic, warm color grade, shallow depth of field",
    aspect_ratio: str = "9:16",
    target_seconds: int = 30,
    voiceover: bool = True,
) -> dict:
    """Turn a script or idea into a storyboard + narrated animatic video.

    Args:
        brief: the script, logline, or idea to visualize.
        style: visual style for every frame (art direction).
        aspect_ratio: "9:16" | "16:9" | "1:1".
        target_seconds: rough total length (8-90).
        voiceover: narrate each shot (needs ELEVENLABS_API_KEY; silent if absent).

    Returns paths to the animatic mp4, storyboard frames, and the shot-list JSON.
    """
    target_seconds = max(8, min(90, int(target_seconds)))  # cost guard: bound the render
    workdir = os.path.join(WORKROOT, uuid.uuid4().hex[:12])
    result = render(brief, style, aspect_ratio, target_seconds, voiceover, workdir)
    size = os.path.getsize(result["animatic"])
    result["animatic_bytes"] = size
    if size <= MAX_INLINE_BYTES:  # make the result usable by a remote caller
        with open(result["animatic"], "rb") as f:
            result["animatic_data_uri"] = "data:video/mp4;base64," + base64.b64encode(f.read()).decode()
    return result

if __name__ == "__main__":
    port = os.environ.get("PORT")  # container hosts (Railway/Render/Fly) set PORT
    if port:
        mcp.run(transport="http", host="0.0.0.0", port=int(port))
    else:
        mcp.run()  # stdio for local MCP clients (Claude/Cursor)
