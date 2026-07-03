#!/usr/bin/env bash
# Generate 8 platform-tuned AI backgrounds via fal gpt-image-2.
# LinkedIn = premium/clean (portrait 4:5). X = bold/edgy (landscape 16:9).
# All text-free; crisp hooks/wordmarks are composited later by sharp.
set -uo pipefail
cd "$(dirname "$0")/../../.."   # repo root
GEN="examples/refund-agent/demo/make_fal_image.py"
OUT="examples/refund-agent/demo/assets/social"
mkdir -p "$OUT"

gen() { # name size prompt
  echo ">>> $1"
  uv run --project . python "$GEN" --out "$OUT/$1.png" --size "$2" --prompt "$3" 2>&1 | tail -2
}

LI_SIZE="1088x1360"
X_SIZE="landscape_16_9"

# li_1 already generated as assets/openai/cover.png — copy it in.
cp examples/refund-agent/demo/assets/openai/cover.png "$OUT/li_1.png" 2>/dev/null && echo "li_1 <- cover.png"

gen li_2 "$LI_SIZE" "Premium minimal tech illustration, deep navy background #0f1018. A sleek glowing line/cost curve that climbs steeply and turns alarming red at its peak, with a subtle scanner highlight catching the spike. Cyan and soft amber accents, lots of negative space, high-end enterprise SaaS aesthetic, soft glow, shallow depth of field. No text, no words, no letters, no numbers."

gen li_3 "$LI_SIZE" "Premium minimal tech illustration, deep navy background #0f1018. A single glowing crystalline seed at the center emitting perfectly symmetrical repeating waves of small fault particles along faint circuit paths, conveying controlled reproducible chaos. Cyan and violet palette, orderly, elegant, generous negative space, soft glow. No text, no words, no letters, no numbers."

gen li_4 "$LI_SIZE" "Premium minimal isometric tech illustration, deep navy background #0f1018. A clean gate or checkpoint across a flowing data pipeline: one lane passes through with a calm green light, two lanes are stopped by a red barrier. Architectural, sophisticated, cyan accents, generous negative space, soft glow, enterprise aesthetic. No text, no words, no letters, no numbers."

gen x_1 "$X_SIZE" "Bold high-contrast cinematic tech illustration, dramatic dark scene, neon cyan and hot red. A confident sleek AI robot strides forward giving a thumbs up, while directly behind it an ominous red cost meter secretly skyrockets off the top of the frame. Slightly humorous, punchy, scroll-stopping, strong neon rim light, depth. No text, no words, no letters, no numbers."

gen x_2 "$X_SIZE" "Bold cyberpunk hacker aesthetic, pitch black background, intense neon green and electric red. A glitching fractured circuit board where a violent red shockwave rips through glowing data lines, digital distortion, scanlines, edgy, high energy, dramatic. No text, no words, no letters, no numbers."

gen x_3 "$X_SIZE" "Bold dynamic tech illustration, dark background, neon cyan and electric red. A lightning bolt of energy smashing into a glowing AI agent pipeline, sparks and red fault particles flying outward, high energy, cinematic, scroll-stopping, dramatic rim light. No text, no words, no letters, no numbers."

gen x_4 "$X_SIZE" "Bold playful but technical illustration, dark background, neon circuitry. A mischievous gremlin chaos-monkey made of glowing neon wires gleefully injecting red fault sparks into a cyan data pipeline, energetic, characterful, scroll-stopping, dramatic neon lighting. No text, no words, no letters, no numbers."

echo "=== done ==="; ls -la "$OUT"
