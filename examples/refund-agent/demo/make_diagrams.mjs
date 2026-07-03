// Three explainer diagrams → assets/diagram_*.png (1920x1080), dark theme to
// match the terminal screenshots. Hand-built SVG rasterized with sharp.
import { writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import sharp from "sharp";

const HERE = dirname(fileURLToPath(import.meta.url));
const ASSETS = join(HERE, "assets");
mkdirSync(ASSETS, { recursive: true });

const W = 1920, H = 1080;
const C = {
  bg: "#12131c", panel: "#1b1d2a", stroke: "#3a3f57",
  text: "#e6e9f2", dim: "#9aa1b6",
  cyan: "#7fd1ff", green: "#5ad48a", red: "#ff6b6b", amber: "#ffcf6b",
  blue: "#7aa2ff", purple: "#b69cff",
};
const FONT = "'Helvetica Neue',Arial,sans-serif";
const MONO = "'Menlo','DejaVu Sans Mono',monospace";

function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

function box(x, y, w, h, opts = {}) {
  const { fill = C.panel, stroke = C.stroke, rx = 16, sw = 2 } = opts;
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
}
function text(x, y, s, opts = {}) {
  const { size = 30, fill = C.text, anchor = "middle", weight = "400", font = FONT, ls = "0" } = opts;
  return `<text x="${x}" y="${y}" font-size="${size}" fill="${fill}" text-anchor="${anchor}" font-weight="${weight}" font-family="${font}" letter-spacing="${ls}">${esc(s)}</text>`;
}
// Multi-line centered text inside a box.
function lines(cx, cy, arr, opts = {}) {
  const { size = 28, gap = 38 } = opts;
  const start = cy - ((arr.length - 1) * gap) / 2;
  return arr.map((l, i) => text(cx, start + i * gap + size * 0.34, l.t ?? l, { size, ...(l.o || {}), ...opts })).join("");
}
function arrow(x1, y1, x2, y2, opts = {}) {
  const { color = C.dim, sw = 3, dash = "" } = opts;
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${sw}" marker-end="url(#arr)" ${dash ? `stroke-dasharray="${dash}"` : ""}/>`;
}
function defs() {
  return `<defs>
    <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 z" fill="${C.dim}"/>
    </marker>
  </defs>`;
}
function frame(title, sub) {
  return `${box(24, 24, W - 48, H - 48, { rx: 22, fill: C.panel, stroke: C.stroke })}
    <rect x="24" y="24" width="${W - 48}" height="${H - 48}" rx="22" fill="${C.bg}" stroke="${C.stroke}" stroke-width="2"/>
    ${text(W / 2, 96, title, { size: 46, weight: "700", fill: C.cyan })}
    ${sub ? text(W / 2, 146, sub, { size: 26, fill: C.dim }) : ""}`;
}
function svg(inner) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <rect width="${W}" height="${H}" fill="${C.bg}"/>${defs()}${inner}</svg>`;
}
async function save(name, inner) {
  await sharp(Buffer.from(svg(inner))).png().toBuffer().then((b) => {
    writeFileSync(join(ASSETS, `${name}.png`), b);
    console.log(`  ${name}.png`);
  });
}

// ---------- Diagram A: AgentChaos in the dev loop / CI gate ----------
async function diagramA() {
  const bw = 300, bh = 120, y = 300;
  const xs = [120, 540, 960];
  let s = frame("Where AgentChaos fits", "a reliability gate in your agent CI — never scores answer quality");
  // dev → PR → gate
  const labels = [
    ["Change", "prompt · model · retrieval", C.amber],
    ["Open PR", "", C.blue],
    ["AgentChaos", "runs your scenarios", C.cyan],
  ];
  xs.forEach((x, i) => {
    s += box(x, y, bw, bh, { stroke: labels[i][2] });
    s += text(x + bw / 2, y + (labels[i][1] ? 50 : 70), labels[i][0], { size: 34, weight: "700", fill: labels[i][2] });
    if (labels[i][1]) s += text(x + bw / 2, y + 88, labels[i][1], { size: 24, fill: C.dim });
  });
  s += arrow(xs[0] + bw, y + bh / 2, xs[1], y + bh / 2);
  s += arrow(xs[1] + bw, y + bh / 2, xs[2], y + bh / 2);

  // gate splits to PASS / FAIL
  const gx = xs[2] + bw;
  const passY = 180, failY = 470;
  const rx = 1420, rw = 360, rh = 110;
  s += box(rx, passY, rw, rh, { stroke: C.green });
  s += text(rx + rw / 2, passY + 45, "exit 0 → PASS", { size: 30, weight: "700", fill: C.green, font: MONO });
  s += text(rx + rw / 2, passY + 82, "merge · deploy", { size: 24, fill: C.dim });
  s += box(rx, failY, rw, rh + 40, { stroke: C.red });
  s += text(rx + rw / 2, failY + 42, "exit 2 / 3 / 4 → FAIL", { size: 28, weight: "700", fill: C.red, font: MONO });
  s += text(rx + rw / 2, failY + 80, "block the merge", { size: 24, fill: C.dim });
  s += text(rx + rw / 2, failY + 116, "cost · fallback · crash", { size: 22, fill: C.dim });
  s += arrow(gx, y + 30, rx, passY + rh / 2, { color: C.green });
  s += arrow(gx, y + 90, rx, failY + 40, { color: C.red });

  // feedback loop fail → change
  s += arrow(rx + rw / 2, failY + rh + 40, rx + rw / 2, 760, { color: C.red, dash: "8 8" });
  s += arrow(rx + rw / 2, 760, xs[0] + bw / 2, 760, { color: C.red, dash: "8 8" });
  s += arrow(xs[0] + bw / 2, 760, xs[0] + bw / 2, y + bh, { color: C.red, dash: "8 8" });
  s += text((xs[0] + bw / 2 + rx) / 2, 745, "fix before it ships", { size: 24, fill: C.red });
  await save("diagram_devloop", s);
}

// ---------- Diagram B: chaos-proxy architecture ----------
async function diagramB() {
  let s = frame("Seeded chaos proxy", "deterministic fault injection between the agent and its tools");
  const y = 380, bh = 160;
  const A = [180, 460], P = [780, 460], T = [1560, 460];
  // Agent
  s += box(A[0], y, 360, bh, { stroke: C.blue });
  s += lines(A[0] + 180, y + bh / 2, [
    { t: "Refund agent", o: { size: 34, weight: "700", fill: C.blue } },
    { t: "real HTTP tool calls", o: { size: 24, fill: C.dim } },
  ]);
  // Proxy
  s += box(P[0], y - 30, 380, bh + 60, { stroke: C.purple, sw: 3 });
  s += lines(P[0] + 190, y + bh / 2 - 10, [
    { t: "Chaos proxy", o: { size: 36, weight: "700", fill: C.purple } },
    { t: "inject 503 · latency", o: { size: 24, fill: C.amber } },
    { t: "forward survivors", o: { size: 24, fill: C.green } },
  ]);
  s += box(P[0] + 70, y + bh + 44, 240, 50, { stroke: C.amber, rx: 25 });
  s += text(P[0] + 190, y + bh + 76, "seed = 42", { size: 28, weight: "700", fill: C.amber, font: MONO });
  // Tools
  s += box(T[0], y, 280, bh, { stroke: C.green });
  s += lines(T[0] + 140, y + bh / 2, [
    { t: "Tools", o: { size: 34, weight: "700", fill: C.green } },
    { t: "get_order …", o: { size: 24, fill: C.dim, font: MONO } },
  ]);
  // arrows
  s += arrow(A[0] + 360, y + bh / 2, P[0], y + bh / 2);
  s += arrow(P[0] + 380, y + bh / 2, T[0], y + bh / 2);
  s += text((A[0] + 360 + P[0]) / 2, y + bh / 2 - 18, "TOOLS_BASE_URL", { size: 20, fill: C.dim, font: MONO });
  s += text((P[0] + 380 + T[0]) / 2, y + bh / 2 - 18, "survivors", { size: 20, fill: C.green, font: MONO });

  // trace output below
  const ty = 760;
  s += box(560, ty, 800, 150, { stroke: C.stroke });
  s += text(960, ty + 44, "→ append-only JSONL trace", { size: 28, weight: "700", fill: C.cyan, font: MONO });
  s += text(960, ty + 88, "chaos_injected · tool_response · agent_turn", { size: 22, fill: C.dim, font: MONO });
  s += text(960, ty + 124, "same seed → same faults → reproducible verdict", { size: 22, fill: C.green });
  s += arrow(P[0] + 190, y + bh + 100, 960, ty, { color: C.purple, dash: "6 6" });
  await save("diagram_proxy", s);
}

// ---------- Diagram C: "why cost changed" cause detection ----------
async function diagramC() {
  let s = frame("Cost regression → root cause", "AgentChaos correlates metric deltas with what changed in the trace");
  // baseline vs current panels
  const py = 240, ph = 300, pw = 560;
  s += box(140, py, pw, ph, { stroke: C.dim });
  s += text(140 + pw / 2, py + 50, "baseline", { size: 30, weight: "700", fill: C.dim });
  s += text(140 + pw / 2, py + 120, "input tokens   1850", { size: 30, fill: C.text, font: MONO });
  s += text(140 + pw / 2, py + 175, "cost        $0.0004", { size: 30, fill: C.text, font: MONO });
  s += text(140 + pw / 2, py + 245, "rag_chunks       5", { size: 30, fill: C.amber, font: MONO });

  s += box(1220, py, pw, ph, { stroke: C.red });
  s += text(1220 + pw / 2, py + 50, "current", { size: 30, weight: "700", fill: C.red });
  s += text(1220 + pw / 2, py + 120, "input tokens   3530", { size: 30, fill: C.red, font: MONO });
  s += text(1220 + pw / 2, py + 175, "cost        $0.0006", { size: 30, fill: C.red, font: MONO });
  s += text(1220 + pw / 2, py + 245, "rag_chunks      12", { size: 30, fill: C.amber, font: MONO });

  // delta chip in middle
  s += box(800, py + 80, 320, 140, { stroke: C.red, rx: 18 });
  s += text(960, py + 130, "Δ cost", { size: 26, fill: C.dim });
  s += text(960, py + 180, "+68.2%", { size: 48, weight: "700", fill: C.red, font: MONO });
  s += arrow(140 + pw, py + ph / 2, 800, py + 150);
  s += arrow(1220, py + 150, 800 + 320, py + 150, { color: C.red });

  // cause box
  const cy = 660, ch = 280;
  s += box(360, cy, 1200, ch, { stroke: C.cyan, sw: 3 });
  s += text(960, cy + 60, "Possible contributors", { size: 32, weight: "700", fill: C.cyan });
  s += text(960, cy + 130, "metadata.rag_chunks  5 → 12   [correlates]", { size: 32, fill: C.amber, font: MONO });
  s += text(960, cy + 185, "input_tokens grew +90.8% (+1680)", { size: 28, fill: C.text, font: MONO });
  s += text(960, cy + 235, "per-model cost gpt-4o-mini +68.2%", { size: 28, fill: C.text, font: MONO });
  s += arrow(960, py + 220, 960, cy, { color: C.cyan, dash: "6 6" });
  await save("diagram_cause", s);
}

console.log("Rendering diagrams:");
await diagramA();
await diagramB();
await diagramC();
console.log("Done.");
