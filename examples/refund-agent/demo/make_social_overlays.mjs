// Composite crisp text onto the gpt-image-2 backgrounds (which are text-free).
//   X images  → bold 2-line hook (scroll-stopper) + small wordmark
//   LinkedIn  → subtle AgentChaos wordmark + repo handle (clean)
// Raw AI outputs are preserved under assets/social/raw/.
import { readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import sharp from "sharp";

const HERE = dirname(fileURLToPath(import.meta.url));
const DIR = join(HERE, "assets", "social");
const RAW = join(DIR, "raw");
mkdirSync(RAW, { recursive: true });

const REPO = "github.com/NoraXu-0111/AgentChaos";
const C = { cyan: "#7fd1ff", white: "#f4f7ff", dim: "#aeb6c8", red: "#ff7a7a", ink: "#0b0c12" };
const SANS = "'Helvetica Neue',Helvetica,Arial,sans-serif";
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// X images: [line1 (white), line2 (cyan accent)]
const X_HOOKS = {
  x_1: ["Passed every eval.", "Still doubled its cost."],
  x_2: ["Tools never fail in dev.", "So your fallback never runs."],
  x_3: ["Break it on purpose.", "Before prod does it for you."],
  x_4: ["Chaos-test your AI agent.", "Catch the 3am pager."],
};
const LI = ["li_1", "li_2", "li_3", "li_4"];

function xOverlaySvg(w, h, l1, l2) {
  const fs = Math.round(w * 0.062);              // hook font size
  const lh = Math.round(fs * 1.18);
  const pad = Math.round(w * 0.045);
  const baseY = h - pad - Math.round(fs * 0.3);  // bottom-anchored
  const scrimH = Math.round(h * 0.5);
  const wm = Math.round(w * 0.022);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
    <defs>
      <linearGradient id="scrim" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${C.ink}" stop-opacity="0"/>
        <stop offset="1" stop-color="${C.ink}" stop-opacity="0.82"/>
      </linearGradient>
    </defs>
    <rect x="0" y="${h - scrimH}" width="${w}" height="${scrimH}" fill="url(#scrim)"/>
    <text x="${pad}" y="${baseY - lh}" font-family="${SANS}" font-weight="800"
      font-size="${fs}" fill="${C.white}" letter-spacing="-0.5"
      style="paint-order:stroke;stroke:${C.ink};stroke-width:${Math.round(fs*0.06)}px">${esc(l1)}</text>
    <text x="${pad}" y="${baseY}" font-family="${SANS}" font-weight="800"
      font-size="${fs}" fill="${C.cyan}" letter-spacing="-0.5"
      style="paint-order:stroke;stroke:${C.ink};stroke-width:${Math.round(fs*0.06)}px">${esc(l2)}</text>
    <text x="${pad}" y="${pad + wm}" font-family="${SANS}" font-weight="700"
      font-size="${wm}" fill="${C.cyan}" letter-spacing="0.5">AgentChaos</text>
  </svg>`;
}

function liOverlaySvg(w, h) {
  const wm = Math.round(w * 0.05);
  const sub = Math.round(w * 0.026);
  const pad = Math.round(w * 0.06);
  const scrimH = Math.round(h * 0.2);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
    <defs>
      <linearGradient id="s2" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${C.ink}" stop-opacity="0"/>
        <stop offset="1" stop-color="${C.ink}" stop-opacity="0.7"/>
      </linearGradient>
    </defs>
    <rect x="0" y="${h - scrimH}" width="${w}" height="${scrimH}" fill="url(#s2)"/>
    <text x="${pad}" y="${h - pad - sub - 8}" font-family="${SANS}" font-weight="800"
      font-size="${wm}" fill="${C.cyan}" letter-spacing="-0.5">AgentChaos</text>
    <text x="${pad}" y="${h - pad + sub * 0.2}" font-family="${SANS}" font-weight="500"
      font-size="${sub}" fill="${C.dim}">reliability testing for tool-using AI agents</text>
  </svg>`;
}

async function brand(name, kind) {
  const src = join(DIR, `${name}.png`);
  if (!existsSync(src)) { console.log(`  ! ${name}.png missing, skip`); return; }
  const rawCopy = join(RAW, `${name}.png`);
  if (!existsSync(rawCopy)) copyFileSync(src, rawCopy); // preserve raw once
  const buf = readFileSync(rawCopy);
  const { width: w, height: h } = await sharp(buf).metadata();
  const svg = kind === "x"
    ? xOverlaySvg(w, h, ...X_HOOKS[name])
    : liOverlaySvg(w, h);
  const out = await sharp(buf).composite([{ input: Buffer.from(svg), top: 0, left: 0 }]).png().toBuffer();
  writeFileSync(src, out);
  console.log(`  ${name}.png  (${w}x${h}, ${kind})`);
}

console.log("Branding social images:");
for (const n of LI) await brand(n, "li");
for (const n of Object.keys(X_HOOKS)) await brand(n, "x");
console.log("Done. Raw AI outputs kept in assets/social/raw/");
