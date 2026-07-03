#!/usr/bin/env python
"""Assemble the AgentChaos demo video from storyboard.json + assets + voiceover.

Each scene is rendered as a self-contained clip that already carries its own
voiceover, so A/V stays perfectly in sync; clips are then concatenated. Stills
get a slow Ken-Burns zoom; every clip gets a burned-in caption and fade in/out.

Outputs:
  agentchaos-demo.mp4        (1920x1080, H.264)
  agentchaos-demo-720p.mp4   (1280x720 web copy)

Usage: uv run --project <repo_root> python examples/refund-agent/demo/build_video.py
  (plain `python3 examples/refund-agent/demo/build_video.py` also works — stdlib only.)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
VO = ASSETS / "vo"
WORK = HERE / "out" / "clips"
FPS = 30
PAD = 0.5  # trailing silence after each VO line
FADE = 0.3
FONT = "/System/Library/Fonts/SFNSMono.ttf"
CAP_BG = "0x12131c"


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


def probe_dur(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out) if out else 0.0


def caption_chain(textfile: Path) -> str:
    # bottom-left caption with a translucent rounded box.
    return (
        f"drawtext=textfile='{textfile}':fontfile='{FONT}':fontcolor=0xe6e9f2:"
        f"fontsize=42:x=72:y=h-128:box=1:boxcolor={CAP_BG}@0.72:boxborderw=26"
    )


def render_image_clip(img: Path, vo: Path, dur: float, cap: Path, out: Path) -> bool:
    frames = max(1, round(dur * FPS))
    fade_out = max(0.0, dur - FADE)
    vf = (
        "[0:v]scale=2400:1350:force_original_aspect_ratio=increase,"
        "crop=2400:1350,setsar=1,"
        f"zoompan=z='min(zoom+0.00045,1.10)':d={frames}:"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=" + str(FPS) + ","
        + caption_chain(cap) + ","
        f"fade=t=in:st=0:d={FADE},fade=t=out:st={fade_out:.3f}:d={FADE}[v];"
        f"[1:a]aresample=48000,apad[a]"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(vo),
        "-filter_complex", vf, "-map", "[v]", "-map", "[a]",
        "-t", f"{dur:.3f}", "-r", str(FPS), "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out),
    ]
    r = run(cmd)
    if r.returncode != 0:
        print(r.stderr[-600:])
    return r.returncode == 0


def render_video_clip(vid: Path, vo: Path, dur: float, cap: Path, out: Path) -> bool:
    fade_out = max(0.0, dur - FADE)
    vf = (
        "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
        "crop=1920:1080,setsar=1,fps=" + str(FPS) + ","
        + caption_chain(cap) + ","
        f"fade=t=in:st=0:d={FADE},fade=t=out:st={fade_out:.3f}:d={FADE}[v];"
        f"[1:a]aresample=48000,apad[a]"
    )
    cmd = [
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(vid), "-i", str(vo),
        "-filter_complex", vf, "-map", "[v]", "-map", "[a]",
        "-t", f"{dur:.3f}", "-r", str(FPS), "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out),
    ]
    r = run(cmd)
    if r.returncode != 0:
        print(r.stderr[-600:])
    return r.returncode == 0


def main() -> int:
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found", file=sys.stderr)
        return 1
    scenes = json.loads((HERE / "storyboard.json").read_text())["scenes"]
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True, exist_ok=True)

    clip_paths: list[Path] = []
    total = 0.0
    for sc in scenes:
        sid = sc["id"]
        asset = ASSETS / sc["asset"]
        vo = VO / f"{sid}.mp3"
        if not asset.exists():
            print(f"  ! missing asset {asset.name}, skipping {sid}")
            continue
        if not vo.exists():
            print(f"  ! missing vo {vo.name}, skipping {sid}")
            continue
        dur = probe_dur(vo) + PAD
        cap = WORK / f"{sid}.caption.txt"
        cap.write_text(sc.get("caption", ""))
        out = WORK / f"{sid}.mp4"
        kind = sc.get("kind", "image")
        ok = (render_video_clip if kind == "video" else render_image_clip)(
            asset, vo, dur, cap, out
        )
        print(f"  {sid}: {kind:5s} {asset.name:24s} {dur:5.2f}s  {'ok' if ok else 'FAILED'}")
        if ok:
            clip_paths.append(out)
            total += dur

    if not clip_paths:
        print("no clips rendered", file=sys.stderr)
        return 1

    # Concatenate (clips share codec/params → stream copy).
    concat_list = WORK / "concat.txt"
    concat_list.write_text("".join(f"file '{p}'\n" for p in clip_paths))
    final = HERE / "agentchaos-demo.mp4"
    r = run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-c", "copy", "-movflags", "+faststart", str(final)])
    if r.returncode != 0:
        # Fallback: re-encode during concat.
        print("  copy concat failed, re-encoding…")
        r = run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                 "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart", str(final)])
        if r.returncode != 0:
            print(r.stderr[-800:])
            return 1

    # 720p web copy.
    web = HERE / "agentchaos-demo-720p.mp4"
    run(["ffmpeg", "-y", "-i", str(final), "-vf", "scale=1280:720",
         "-c:v", "libx264", "-crf", "22", "-preset", "medium",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(web)])

    print(f"\nBuilt {final.name} (~{total:.1f}s target) and {web.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
