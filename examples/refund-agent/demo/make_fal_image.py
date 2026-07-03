#!/usr/bin/env python
"""Generate images via fal.ai (default: openai/gpt-image-2) using FAL_KEY.

No OpenAI key needed — fal proxies the model. Reads FAL_KEY from .demo.env.

Usage:
  uv run --project <root> python examples/refund-agent/demo/make_fal_image.py \
      --prompt "..." --out assets/openai/cover.png --size 1088x1360

--size accepts a preset (square_hd, portrait_4_3, portrait_16_9, landscape_4_3,
landscape_16_9, square) or WxH (multiples of 16).
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent
ENV_FILE = REPO_ROOT / ".demo.env"
MODEL = "openai/gpt-image-2"
SUBMIT = f"https://queue.fal.run/{MODEL}"

DEFAULT_PROMPT = (
    "A clean, premium tech illustration for an open-source developer tool called "
    "AgentChaos. Deep navy background (#12131c). Glowing cyan and purple "
    "circuit/data-flow lines forming an abstract AI agent pipeline; a few data "
    "packets glitch and turn red to suggest injected faults / chaos testing; on "
    "one path a calm green checkmark of light forms, suggesting a passing CI gate. "
    "Minimal, high-end, lots of negative space, soft depth of field, modern "
    "vector-poster aesthetic. No text, no words, no letters."
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


def parse_size(s: str):
    if "x" in s.lower():
        w, h = s.lower().split("x")
        return {"width": int(w), "height": int(h)}
    return s  # preset name


def generate(key: str, prompt: str, size, out: Path, quality: str, fmt: str) -> bool:
    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    payload = {
        "prompt": prompt,
        "image_size": size,
        "quality": quality,
        "num_images": 1,
        "output_format": fmt,
    }
    try:
        r = httpx.post(SUBMIT, headers=headers, json=payload, timeout=60)
        if r.status_code not in (200, 201):
            print(f"submit {r.status_code}: {r.text[:300]}")
            return False
        d = r.json()
        req_id = d.get("request_id")
        status_url = d.get("status_url") or f"{SUBMIT}/requests/{req_id}/status"
        result_url = d.get("response_url") or f"{SUBMIT}/requests/{req_id}"

        deadline = time.time() + 240
        while time.time() < deadline:
            s = httpx.get(status_url, headers=headers, timeout=30)
            st = s.json().get("status") if s.status_code == 200 else None
            if st == "COMPLETED":
                break
            if st in ("FAILED", "ERROR"):
                print(f"job failed: {s.text[:300]}")
                return False
            time.sleep(3)
        else:
            print("timed out")
            return False

        res = httpx.get(result_url, headers=headers, timeout=60).json()
        images = res.get("images") or []
        if not images or not images[0].get("url"):
            print(f"no image url: {str(res)[:300]}")
            return False
        url = images[0]["url"]
        img = httpx.get(url, timeout=120).content
        out.write_bytes(img)
        return out.stat().st_size > 1000
    except Exception as exc:
        print(f"error: {exc}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--out", default=str(HERE / "assets" / "openai" / "cover.png"))
    ap.add_argument("--size", default="1088x1360")  # ~4:5, multiples of 16
    ap.add_argument("--quality", default="high")
    ap.add_argument("--format", default="png")
    args = ap.parse_args()

    load_env()
    key = os.environ.get("FAL_KEY", "")
    if not key:
        print("✗ FAL_KEY not found in .demo.env")
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Generating with {MODEL} ({args.size}, {args.quality}) → {out}")
    ok = generate(key, args.prompt, parse_size(args.size), out, args.quality, args.format)
    print("ok" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
