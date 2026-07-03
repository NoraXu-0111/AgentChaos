#!/usr/bin/env python
"""Generate short AI b-roll clips for the title and outro via fal.ai.

Primary: fal.ai text-to-video (queue API; reads FAL_KEY from .demo.env).
Fallback: a themed ffmpeg title card (so the build never blocks).

Writes assets/broll_title.mp4 and assets/broll_outro.mp4 (1920x1080).

Usage: uv run --project <repo_root> python examples/refund-agent/demo/falai_broll.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent
ASSETS = HERE / "assets"
ENV_FILE = REPO_ROOT / ".demo.env"

MODEL_ID = "fal-ai/ltx-video"

CLIPS = [
    {
        "name": "broll_title",
        "seconds": 8,
        "title": "AgentChaos",
        "subtitle": "reliability testing for tool-using AI agents",
        "prompt": (
            "Abstract dark tech visualization, glowing cyan and purple network "
            "nodes and data packets flowing along circuit lines, some packets "
            "flicker red and fail, cinematic, deep navy background, smooth slow "
            "camera push-in, 4k, high detail, no text"
        ),
    },
    {
        "name": "broll_outro",
        "seconds": 4,
        "title": "AgentChaos",
        "subtitle": "catch reliability regressions before they ship",
        "prompt": (
            "Abstract dark tech visualization, a single green checkmark of light "
            "forming from flowing cyan data streams on a deep navy background, "
            "calm, cinematic, slow camera pull-back, 4k, no text"
        ),
    },
]


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def fal_video(key: str, prompt: str, out: Path) -> bool:
    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    submit = f"https://queue.fal.run/{MODEL_ID}"
    try:
        r = httpx.post(submit, headers=headers, json={"prompt": prompt}, timeout=60)
        if r.status_code not in (200, 201):
            print(f"  fal submit {r.status_code}: {r.text[:200]}")
            return False
        data = r.json()
        req_id = data.get("request_id")
        status_url = data.get("status_url") or f"{submit}/requests/{req_id}/status"
        result_url = data.get("response_url") or f"{submit}/requests/{req_id}"
        if not req_id:
            print(f"  fal: no request_id in {data}")
            return False

        deadline = time.time() + 300
        while time.time() < deadline:
            s = httpx.get(status_url, headers=headers, timeout=30)
            st = s.json().get("status") if s.status_code == 200 else None
            if st == "COMPLETED":
                break
            if st in ("FAILED", "ERROR"):
                print(f"  fal job failed: {s.text[:200]}")
                return False
            time.sleep(5)
        else:
            print("  fal: timed out waiting for video")
            return False

        res = httpx.get(result_url, headers=headers, timeout=60).json()
        video = res.get("video") or {}
        url = video.get("url") if isinstance(video, dict) else None
        if not url:
            print(f"  fal: no video url in result: {str(res)[:200]}")
            return False
        with httpx.stream("GET", url, timeout=120) as dl:
            dl.raise_for_status()
            with open(out, "wb") as fh:
                for chunk in dl.iter_bytes():
                    fh.write(chunk)
        return out.stat().st_size > 10000
    except Exception as exc:
        print(f"  fal error: {exc}")
        return False


def title_card(clip: dict, out: Path) -> bool:
    """Themed animated ffmpeg fallback (slow zoom on a gradient + text)."""
    seconds = clip["seconds"]
    title = clip["title"].replace(":", r"\:").replace("'", "")
    subtitle = clip["subtitle"].replace(":", r"\:").replace("'", "")
    # Build a dark gradient background, gentle zoom, two centered text lines.
    vf = (
        "format=rgb24,"
        f"drawtext=text='{title}':fontcolor=0x7fd1ff:fontsize=120:"
        "x=(w-text_w)/2:y=(h-text_h)/2-60:font=Menlo:"
        "shadowcolor=black:shadowx=2:shadowy=2,"
        f"drawtext=text='{subtitle}':fontcolor=0xcdd3e1:fontsize=46:"
        "x=(w-text_w)/2:y=(h-text_h)/2+90:font=Menlo,"
        f"zoompan=z='min(zoom+0.0006,1.10)':d={seconds*30}:s=1920x1080:fps=30"
    )
    try:
        subprocess.run(
            ["ffmpeg", "-y",
             "-f", "lavfi", "-i", f"color=c=0x12131c:s=1920x1080:d={seconds}:r=30",
             "-vf", vf, "-pix_fmt", "yuv420p", "-t", str(seconds), str(out)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        return out.exists()
    except subprocess.CalledProcessError as exc:
        print(f"  title card failed: {exc.stderr.decode()[:300]}")
        return False


def main() -> int:
    load_env()
    ASSETS.mkdir(parents=True, exist_ok=True)
    key = os.environ.get("FAL_KEY", "")
    print(f"B-roll engine: {'fal.ai ' + MODEL_ID if key else 'ffmpeg title card (no FAL_KEY)'}")

    for clip in CLIPS:
        out = ASSETS / f"{clip['name']}.mp4"
        done = False
        if key:
            print(f"  {clip['name']}: requesting fal.ai clip…")
            done = fal_video(key, clip["prompt"], out)
        if not done:
            print(f"  {clip['name']}: using ffmpeg title card")
            done = title_card(clip, out)
        print(f"  {clip['name']}.mp4  {'ok' if done else 'FAILED'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
