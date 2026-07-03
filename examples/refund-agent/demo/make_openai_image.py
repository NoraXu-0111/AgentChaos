#!/usr/bin/env python
"""Generate images with OpenAI's gpt-image-1 (reads OPENAI_API_KEY from .demo.env).

Usage:
  uv run --project <root> python examples/refund-agent/demo/make_openai_image.py \
      --prompt "..." --out assets/openai/cover.png --size 1024x1536

Defaults to a LinkedIn-cover prompt for AgentChaos if no --prompt is given.
"""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent
ENV_FILE = REPO_ROOT / ".demo.env"
MODEL = "gpt-image-1"

DEFAULT_PROMPT = (
    "A clean, modern tech illustration for a developer-tool brand called "
    "AgentChaos. Dark navy background (#12131c), glowing cyan and purple "
    "circuit/data-flow lines, a few packets turning red and breaking to suggest "
    "faults and chaos testing, a subtle green checkmark of light forming on one "
    "path to suggest a passing CI gate. Minimal, high-end, no text, lots of "
    "negative space, soft depth of field, vector-poster feel."
)


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def generate(key: str, prompt: str, size: str, out: Path, quality: str) -> bool:
    body = {
        "model": MODEL,
        "prompt": prompt,
        "size": size,        # 1024x1024 | 1024x1536 | 1536x1024 | auto
        "quality": quality,  # low | medium | high | auto
        "n": 1,
    }
    try:
        r = httpx.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=180,
        )
        if r.status_code != 200:
            print(f"OpenAI {r.status_code}: {r.text[:400]}")
            return False
        data = r.json()["data"][0]
        b64 = data.get("b64_json")
        if not b64:
            url = data.get("url")
            if url:
                img = httpx.get(url, timeout=120).content
                out.write_bytes(img)
                return out.stat().st_size > 1000
            print(f"no image in response: {str(data)[:200]}")
            return False
        out.write_bytes(base64.b64decode(b64))
        return out.stat().st_size > 1000
    except Exception as exc:
        print(f"error: {exc}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--out", default=str(HERE / "assets" / "openai" / "cover.png"))
    ap.add_argument("--size", default="1024x1536")
    ap.add_argument("--quality", default="high")
    args = ap.parse_args()

    load_env()
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        print("✗ OPENAI_API_KEY not found. Add it to .demo.env first.")
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Generating with {MODEL} ({args.size}, {args.quality}) → {out}")
    ok = generate(key, args.prompt, args.size, out, args.quality)
    print("ok" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
