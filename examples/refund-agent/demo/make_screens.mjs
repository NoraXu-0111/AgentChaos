// Render each caps/*.txt to a 1920x1080 dark-terminal PNG.
// Local-only: builds an SVG (monospace + window chrome + semantic coloring)
// and rasterizes it with sharp. No Chrome, no PIL.
import { readFileSync, writeFileSync, readdirSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import sharp from "sharp";

const HERE = dirname(fileURLToPath(import.meta.url));
const CAPS = join(HERE, "caps");
const ASSETS = join(HERE, "assets");
mkdirSync(ASSETS, { recursive: true });

const W = 1920, H = 1080;
const BAR = 64;                // title-bar height
const PAD_X = 56, PAD_TOP = BAR + 36, PAD_BOT = 40;

const COL = {
  bg: "#12131c",
  win: "#1b1d2a",
  bar: "#262a3d",
  text: "#cdd3e1",
  dim: "#7b8194",
  title: "#7fd1ff",
  green: "#5ad48a",
  red: "#ff6b6b",
  amber: "#ffcf6b",
  blue: "#7aa2ff",
};

function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Per-line color heuristic (caps text carries no ANSI).
function lineColor(line) {
  const t = line.trim();
  if (/^AgentChaos\b/.test(t) || /CI GATE/.test(t)) return COL.title;
  if (/Verdict:\s*PASS/.test(t)) return COL.green;
  if (/Verdict:\s*FAIL/.test(t)) return COL.red;
  if (/Merge decision:\s*BLOCKED|FAILED|did not degrade/i.test(t)) return COL.red;
  if (/\bBLOCKED\b/.test(t)) return COL.red;
  if (/exit\s*0\b|exit=0\b|YES \(deterministic\)|\bPASS\b/.test(t)) return COL.green;
  if (/exit\s*[2-9]\b|exit=[2-9]\b|\bFAIL\b|✗/.test(t)) return COL.red;
  if (/^(Why:|Metrics:|Tool sequence:|Possible contributors:|Chaos injected:|Fallback|Trace:|Seed:|Gate summary:|Run \d)/.test(t)) return COL.amber;
  if (t.startsWith("$") || t.startsWith("#")) return COL.blue;
  if (/^-+$/.test(t) || /^=+$/.test(t)) return COL.dim;
  return COL.text;
}

function render(name, body, title) {
  const lines = body.replace(/\s+$/, "").split("\n");
  const maxCols = Math.max(40, ...lines.map((l) => l.length));
  const nLines = lines.length;

  // Fit font to both width and height.
  const availW = W - 2 * PAD_X;
  const availH = H - PAD_TOP - PAD_BOT;
  const fsByW = availW / (maxCols * 0.60);
  const lh = 1.34;
  const fsByH = availH / (nLines * lh);
  const fs = Math.max(13, Math.min(30, Math.floor(Math.min(fsByW, fsByH))));
  const lineH = Math.round(fs * lh);
  const charW = fs * 0.60;

  const tspans = lines
    .map((l, i) => {
      const y = PAD_TOP + Math.round((i + 0.85) * lineH);
      const fill = lineColor(l);
      const weight = fill === COL.title ? "700" : "400";
      return `<text x="${PAD_X}" y="${y}" font-size="${fs}" fill="${fill}" font-weight="${weight}" xml:space="preserve">${esc(l)}</text>`;
    })
    .join("\n");

  const dots = ["#ff5f57", "#febc2e", "#28c840"]
    .map((c, i) => `<circle cx="${34 + i * 30}" cy="${BAR / 2}" r="9" fill="${c}"/>`)
    .join("");

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <rect width="${W}" height="${H}" fill="${COL.bg}"/>
  <rect x="24" y="24" width="${W - 48}" height="${H - 48}" rx="16" fill="${COL.win}"/>
  <rect x="24" y="24" width="${W - 48}" height="${BAR}" rx="16" fill="${COL.bar}"/>
  <rect x="24" y="${24 + BAR - 16}" width="${W - 48}" height="16" fill="${COL.win}"/>
  <g transform="translate(24,24)">${dots}</g>
  <text x="${W / 2}" y="${24 + BAR / 2 + 6}" font-size="22" fill="${COL.dim}" text-anchor="middle" font-family="monospace">${esc(title)}</text>
  <g font-family="'Menlo','DejaVu Sans Mono','Courier New',monospace">
${tspans}
  </g>
</svg>`;

  return sharp(Buffer.from(svg)).png().toBuffer().then((buf) => {
    const out = join(ASSETS, `shot_${name}.png`);
    writeFileSync(out, buf);
    console.log(`  shot_${name}.png  (${nLines} lines, fs=${fs})`);
  });
}

const titles = {
  A0_doctor: "agentchaos doctor — fidelity check",
  A1_baseline: "agentchaos run — baseline (clean)",
  A2_regression: "agentchaos run — cost regression caught",
  B1_chaos: "agentchaos run — seeded chaos, graceful fallback",
  B2_reproduce: "chaos reproducibility — same seed, same faults",
  C_gate: "CI gate — exit codes block the merge",
  C_broken: "chaos — broken fallback caught",
};

const files = readdirSync(CAPS).filter((f) => f.endsWith(".txt")).sort();
console.log("Rendering screenshots:");
for (const f of files) {
  const name = f.replace(/\.txt$/, "");
  const body = readFileSync(join(CAPS, f), "utf8");
  await render(name, body, titles[name] || name);
}
console.log("Done.");
