"""DALANG — Storyboard-to-Animatic ASP for OKX.AI (A2MCP, pay-per-call).

One tool = one billable call. Register this MCP server on OKX.AI in A2MCP mode;
OKX wraps the pay-per-call settlement (USDT/USDG on X Layer) around it.
"""
import os, uuid
from fastmcp import FastMCP
from pipeline import render

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
    workdir = os.path.join(WORKROOT, uuid.uuid4().hex[:12])
    return render(brief, style, aspect_ratio, target_seconds, voiceover, workdir)

if __name__ == "__main__":
    port = os.environ.get("PORT")  # container hosts (Railway/Render/Fly) set PORT
    if port:
        mcp.run(transport="http", host="0.0.0.0", port=int(port))
    else:
        mcp.run()  # stdio for local MCP clients (Claude/Cursor)
