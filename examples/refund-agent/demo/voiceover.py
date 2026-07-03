#!/usr/bin/env python
"""Generate per-scene voiceover MP3s from storyboard.json.

Primary: ElevenLabs TTS (reads ELEVENLABS_API_KEY from .demo.env).
Fallback: macOS `say` → aiff → mp3 via ffmpeg, so the build never blocks.

Writes assets/vo/<scene_id>.mp3 for every scene that has a `vo` line.

Usage: uv run --project <repo_root> python examples/refund-agent/demo/voiceover.py
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent
VO_DIR = HERE / "assets" / "vo"
ENV_FILE = REPO_ROOT / ".demo.env"

# A clear, neutral narrator. "Brian" is a stable public ElevenLabs voice; if the
# account exposes a different set we fall back to the first available voice.
DEFAULT_VOICE_ID = "nPczCjzI2devNBz1zQrb"  # Brian
MODEL_ID = "eleven_multilingual_v2"


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def pick_voice(key: str) -> str:
    try:
        r = httpx.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": key},
            timeout=20,
        )
        r.raise_for_status()
        voices = r.json().get("voices", [])
        ids = {v.get("voice_id") for v in voices}
        if DEFAULT_VOICE_ID in ids:
            return DEFAULT_VOICE_ID
        if voices:
            print(f"  (default voice not on account; using {voices[0].get('name')})")
            return voices[0]["voice_id"]
    except Exception as exc:
        print(f"  voice list failed ({exc}); trying default voice id")
    return DEFAULT_VOICE_ID


def elevenlabs_tts(key: str, voice_id: str, text: str, out: Path) -> bool:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    body = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.0},
    }
    try:
        with httpx.stream(
            "POST", url,
            headers={"xi-api-key": key, "accept": "audio/mpeg",
                     "content-type": "application/json"},
            json=body, timeout=90,
        ) as resp:
            if resp.status_code != 200:
                print(f"  EL {resp.status_code}: {resp.read()[:200]!r}")
                return False
            with open(out, "wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
        return out.stat().st_size > 1000
    except Exception as exc:
        print(f"  EL error: {exc}")
        return False


def say_tts(text: str, out: Path) -> bool:
    """macOS `say` fallback → mp3."""
    aiff = out.with_suffix(".aiff")
    try:
        subprocess.run(["say", "-v", "Daniel", "-o", str(aiff), text], check=True)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(aiff), "-codec:a", "libmp3lame",
             "-b:a", "160k", str(out)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        aiff.unlink(missing_ok=True)
        return out.exists()
    except Exception as exc:
        print(f"  say fallback failed: {exc}")
        return False


def main() -> int:
    load_env()
    VO_DIR.mkdir(parents=True, exist_ok=True)
    scenes = json.loads((HERE / "storyboard.json").read_text())["scenes"]
    key = os.environ.get("ELEVENLABS_API_KEY", "")

    voice_id = pick_voice(key) if key else ""
    engine = "ElevenLabs" if key else "say (no API key)"
    print(f"Voiceover engine: {engine}")

    ok = 0
    for sc in scenes:
        text = sc.get("vo", "").strip()
        if not text:
            continue
        out = VO_DIR / f"{sc['id']}.mp3"
        done = False
        if key:
            done = elevenlabs_tts(key, voice_id, text, out)
        if not done:
            done = say_tts(text, out)
        status = "ok" if done else "FAILED"
        if done:
            ok += 1
        print(f"  {sc['id']}.mp3  {status}")

    print(f"Done: {ok}/{sum(1 for s in scenes if s.get('vo'))} scenes voiced.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
