// Build a LinkedIn carousel for AgentChaos → assets/linkedin/slide_*.png
// 1080x1350 (4:5) portrait, dark theme matching the product. Terminal "proof"
// cards are rendered native (large + legible) from the real CLI output; the two
// architecture diagrams are composited from the existing diagram PNGs.
// Local-only: SVG rasterized + composited with sharp. No Chrome/PIL.
import { writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import sharp from "sharp";

const HERE = dirname(fileURLToPath(import.meta.url));
const ASSETS = join(HERE, "assets");
const OUT = join(ASSETS, "linkedin");
mkdirSync(OUT, { recursive: true });

const W = 1080, H = 1350;
const C = {
  bg: "#0f1018", bg2: "#12131c", panel: "#1b1d2a", chrome: "#262a3d",
  stroke: "#333852", text: "#e6e9f2", dim: "#9aa1b6", faint: "#6b7188",
  cyan: "#7fd1ff", green: "#5ad48a", red: "#ff6b6b", amber: "#ffcf6b",
  blue: "#7aa2ff", purple: "#b69cff",
};
const SANS = "'Helvetica Neue',Helvetica,Arial,sans-serif";
const MONO = "'Menlo','DejaVu Sans Mono',monospace";
const REPO = "github.com/NoraXu-0111/AgentChaos";

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function text(x, y, s, o = {}) {
  const { size = 30, fill = C.text, anchor = "start", weight = "400", font = SANS, ls = "0", op = 1 } = o;
  return `<text x="${x}" y="${y}" font-size="${size}" fill="${fill}" text-anchor="${anchor}" font-weight="${weight}" font-family="${font}" letter-spacing="${ls}" opacity="${op}">${esc(s)}</text>`;
}
function rect(x, y, w, h, o = {}) {
  const { fill = "none", stroke = "none", rx = 0, sw = 0, op = 1 } = o;
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" opacity="${op}"/>`;
}

// shared page furniture: background, brand wordmark, repo, page number
function chrome(idx, total) {
  let s = rect(0, 0, W, H, { fill: C.bg });
  s += `<rect x="0" y="0" width="${W}" height="6" fill="${C.cyan}"/>`;
  // footer
  s += text(64, H - 56, "AgentChaos", { size: 30, fill: C.cyan, weight: "700" });
  s += text(W - 64, H - 56, REPO, { size: 24, fill: C.faint, anchor: "end", font: MONO });
  s += text(W - 64, H - 96, `${idx} / ${total}`, { size: 22, fill: C.faint, anchor: "end" });
  return s;
}
function kicker(s) {
  return text(64, 150, s.toUpperCase(), { size: 26, fill: C.cyan, weight: "700", ls: "3" });
}
function headline(linesArr, y0 = 220, size = 64) {
  return linesArr.map((l, i) => text(64, y0 + i * (size + 10), l, { size, weight: "800", fill: C.text })).join("");
}
function subhead(s, y, maxchars = 52) {
  // simple word-wrap
  const words = s.split(" ");
  const lines = [];
  let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > maxchars) { lines.push(cur.trim()); cur = w; }
    else cur += " " + w;
  }
  if (cur.trim()) lines.push(cur.trim());
  return lines.map((l, i) => text(64, y + i * 42, l, { size: 30, fill: C.dim })).join("");
}

// ---- native terminal card (large + legible) ----
function cardLineColor(l) {
  const t = l.trim();
  if (/^AgentChaos —|^CI GATE/.test(t)) return C.cyan;
  if (/Verdict:\s*PASS/.test(t)) return C.green;
  if (/Verdict:\s*FAIL/.test(t)) return C.red;
  if (/Merge decision:\s*BLOCKED/i.test(t)) return C.red;
  if (/\bBLOCKED\b/.test(t)) return C.red;
  if (/Exit code:\s*0\b/.test(t)) return C.green;
  if (/Exit code:\s*[1-9]/.test(t)) return C.red;
  if (/\bPASS\b/.test(t)) return C.green;
  if (/\bFAIL\b/.test(t)) return C.red;
  if (/exit 0\b/.test(t)) return C.green;
  if (/exit [1-9]\b/.test(t)) return C.red;
  if (/\[correlates\]|rag_chunks|status_code|seed 42/.test(t)) return C.amber;
  if (/^(Chaos injected:|Fallback path observed:|Metric)/.test(t)) return C.amber;
  if (/human agent will follow up/.test(t)) return C.green;
  return C.text;
}
function terminalCard(lines, x, y, w, h, title) {
  const bar = 56, padX = 40, padTop = bar + 40, padBot = 36;
  const maxCols = Math.max(30, ...lines.map((l) => l.length));
  const availW = w - 2 * padX, availH = h - padTop - padBot;
  const lh = 1.42;
  const fsW = availW / (maxCols * 0.602);
  const fsH = availH / (lines.length * lh);
  const fs = Math.max(16, Math.min(34, Math.floor(Math.min(fsW, fsH))));
  const lineH = Math.round(fs * lh);
  let s = rect(x, y, w, h, { fill: C.panel, stroke: C.stroke, sw: 2, rx: 18 });
  s += rect(x, y, w, bar, { fill: C.chrome, rx: 18 });
  s += rect(x, y + bar - 18, w, 18, { fill: C.panel });
  ["#ff5f57", "#febc2e", "#28c840"].forEach((c, i) => {
    s += `<circle cx="${x + 34 + i * 30}" cy="${y + bar / 2}" r="9" fill="${c}"/>`;
  });
  if (title) s += text(x + w / 2, y + bar / 2 + 7, title, { size: 20, fill: C.dim, anchor: "middle", font: MONO });
  lines.forEach((l, i) => {
    const ly = y + padTop + Math.round((i + 0.85) * lineH) - lineH;
    s += `<text x="${x + padX}" y="${ly}" font-size="${fs}" fill="${cardLineColor(l)}" font-family="${MONO}" xml:space="preserve">${esc(l)}</text>`;
  });
  return s;
}

// ---- rounded embedded image (for diagrams) ----
async function roundedImage(path, w, h, radius) {
  const buf = await sharp(path).resize(w, h, { fit: "contain", background: C.bg2 }).png().toBuffer();
  const mask = Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><rect width="${w}" height="${h}" rx="${radius}" fill="#fff"/></svg>`
  );
  return sharp(buf).composite([{ input: mask, blend: "dest-in" }]).png().toBuffer();
}

async function save(name, svg, composites = []) {
  let img = sharp(Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${svg}</svg>`)).png();
  if (composites.length) img = img.composite(composites);
  const out = join(OUT, `${name}.png`);
  writeFileSync(out, await img.toBuffer());
  console.log(`  ${name}.png`);
}

// ============================ SLIDES ============================
const TOTAL = 8;

async function s1_hero() {
  let s = chrome(1, TOTAL);
  s += text(64, 360, "OPEN SOURCE · PYTHON · CI-NATIVE", { size: 26, fill: C.cyan, weight: "700", ls: "3" });
  s += text(64, 500, "AgentChaos", { size: 128, fill: C.cyan, weight: "800", ls: "-1" });
  s += text(64, 575, "reliability testing for tool-using AI agents", { size: 40, fill: C.text, weight: "600" });
  s += subhead("Catch cost and reliability regressions in CI — before they ever hit production.", 660);
  // accent chips (sized to fit within the 64px side margins)
  const chips = [["▸ profile cost", C.green], ["✗ catch regressions", C.red], ["↻ seeded chaos", C.amber]];
  const chipFs = 25, chipCW = 15.3, gap = 20;
  let cx = 64;
  const cy = 800;
  for (const [label, col] of chips) {
    const w = Math.round(40 + label.length * chipCW);
    s += rect(cx, cy, w, 66, { fill: C.panel, stroke: col, sw: 2, rx: 33 });
    s += text(cx + w / 2, cy + 44, label, { size: chipFs, fill: col, anchor: "middle", weight: "600", font: MONO });
    cx += w + gap;
  }
  // mini terminal teaser
  s += terminalCard(
    ["$ agentchaos run scenario.yaml --baseline base.jsonl", "", "Verdict: FAIL   cost +68.2%   exit 2"],
    64, 930, W - 128, 210, "agentchaos"
  );
  return save("slide_1_hero", s);
}

async function s2_problem() {
  let s = chrome(2, TOTAL);
  s += kicker("the problem");
  s += headline(["Agents break in ways", "evals never catch"], 240, 62);
  const bullets = [
    ["Cost silently doubles", "after a prompt or model change"],
    ["A flaky tool 503s", "and the agent retries 12× — $4 in model calls"],
    ["Retrieval returns 12 chunks", "instead of 5, blowing the context budget"],
    ["The tool-failure fallback", "was never tested — tools never fail in dev"],
  ];
  let y = 480;
  for (const [a, b] of bullets) {
    s += rect(64, y - 34, 8, 8 + 64, { fill: C.red, rx: 4 });
    s += text(104, y, a, { size: 36, fill: C.text, weight: "700" });
    s += text(104, y + 44, b, { size: 30, fill: C.dim });
    y += 150;
  }
  return save("slide_2_problem", s);
}

async function s3_devloop() {
  let s = chrome(3, TOTAL);
  s += kicker("where it fits");
  s += headline(["A reliability gate", "in your agent CI"], 240, 62);
  s += subhead("Runs your scenarios on every PR. Passes clean changes; blocks regressions by exit code. Never scores answer quality.", 410);
  const iw = W - 128, ih = Math.round(iw * 1080 / 1920);
  const img = await roundedImage(join(ASSETS, "diagram_devloop.png"), iw, ih, 18);
  s += rect(64, 560, iw, ih, { stroke: C.stroke, sw: 2, rx: 18 });
  return save("slide_3_devloop", s, [{ input: img, left: 64, top: 560 }]);
}

async function s4_cost() {
  let s = chrome(4, TOTAL);
  s += kicker("01 · cost regression");
  s += headline(["Catch cost", "regressions in CI"], 240, 62);
  s += subhead("Fails the run when cost, latency, or tokens regress past your budget.", 410);
  s += terminalCard([
    "AgentChaos — refund-rag-cost-regression",
    "",
    "Verdict: FAIL",
    "",
    "  Metric         Baseline   Current      Δ  Status",
    "  Cost            $0.0004    $0.0006  +68.2%  FAIL",
    "  Input tokens       1850       3530  +90.8%  FAIL",
    "",
    "Exit code: 2",
  ], 64, 560, W - 128, 520, "agentchaos run");
  return save("slide_4_cost", s);
}

async function s5_cause() {
  let s = chrome(5, TOTAL);
  s += kicker("02 · root cause");
  s += headline(["It names the cause,", "not just the delta"], 240, 62);
  s += subhead("Correlates every metric delta with what actually changed in the trace — down to the metadata.", 410);
  const iw = W - 128, ih = Math.round(iw * 1080 / 1920);
  const img = await roundedImage(join(ASSETS, "diagram_cause.png"), iw, ih, 18);
  s += rect(64, 560, iw, ih, { stroke: C.stroke, sw: 2, rx: 18 });
  return save("slide_5_cause", s, [{ input: img, left: 64, top: 560 }]);
}

async function s6_chaos() {
  let s = chrome(6, TOTAL);
  s += kicker("03 · seeded chaos");
  s += headline(["Inject faults,", "prove the fallback"], 240, 62);
  s += subhead("Deterministic 503s between agent and tools. Same seed → same faults → reproducible in CI.", 410);
  s += terminalCard([
    "AgentChaos — refund-chaos-get-order",
    "",
    "Verdict: PASS",
    "",
    "Chaos injected:",
    "  get_order: status_code = 503   (seed 42)",
    "",
    "Fallback path observed:",
    '  "...a human agent will follow up."',
    "",
    "Exit code: 0",
  ], 64, 540, W - 128, 580, "agentchaos run --chaos");
  return save("slide_6_chaos", s);
}

async function s7_gate() {
  let s = chrome(7, TOTAL);
  s += kicker("04 · the ci gate");
  s += headline(["One gate.", "Exit codes block", "the merge."], 240, 60);
  s += subhead("A drop-in CI step. Distinct exit codes tell you exactly why a change is unsafe to ship.", 470);
  s += terminalCard([
    "CI GATE — three checks, one decision",
    "",
    "  clean ............... exit 0   PASS",
    "  cost regression ..... exit 2   BLOCKED",
    "  chaos (broken) ...... exit 4   BLOCKED",
    "",
    "Merge decision: BLOCKED",
    "  2 of 3 checks failed — fix before merging.",
  ], 64, 620, W - 128, 470, "ci");
  return save("slide_7_gate", s);
}

async function s8_cta() {
  let s = chrome(8, TOTAL);
  s += text(64, 380, "AgentChaos", { size: 96, fill: C.cyan, weight: "800", ls: "-1" });
  s += text(64, 450, "reliability testing for tool-using AI agents", { size: 36, fill: C.text, weight: "600" });
  s += subhead("Open source. Record runs, profile cost, inject seeded chaos, and gate every PR.", 540);
  // install chip
  s += rect(64, 660, W - 128, 110, { fill: C.panel, stroke: C.stroke, sw: 2, rx: 16 });
  s += text(96, 728, "$ pip install agentchaos-reliability", { size: 38, fill: C.green, font: MONO, weight: "600" });
  // repo
  s += rect(64, 820, W - 128, 110, { fill: C.panel, stroke: C.cyan, sw: 2, rx: 16 });
  s += text(96, 888, REPO, { size: 36, fill: C.cyan, font: MONO });
  s += text(64, 1030, "★ Star it · try it on your agent · break it on purpose", { size: 32, fill: C.dim, weight: "600" });
  return save("slide_8_cta", s);
}

console.log("Rendering LinkedIn carousel (1080x1350):");
await s1_hero();
await s2_problem();
await s3_devloop();
await s4_cost();
await s5_cause();
await s6_chaos();
await s7_gate();
await s8_cta();
console.log("Done → assets/linkedin/");
