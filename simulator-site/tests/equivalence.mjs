// Proves the JavaScript port in page.html gives exactly the same answer as the original packer.cpp.
// Needs Node 18+ and g++ (MinGW on Windows).  Run:  node tests/equivalence.mjs
import { execFileSync } from "node:child_process";
import { readFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const page = readFileSync(join(here, "..", "page.html"), "utf8");
const code = page.slice(page.indexOf("/*PACKER-START*/"), page.indexOf("/*PACKER-END*/"));
const { designTrace, fitCarton } = new Function(code + "; return { designTrace, fitCarton };")();

const dir = mkdtempSync(join(tmpdir(), "packer-eq-"));
const exe = join(dir, process.platform === "win32" ? "packer.exe" : "packer");
execFileSync("g++", ["-O2", "-std=c++17", "-o", exe, join(here, "..", "..", "cpp-packer-service", "original", "packer.cpp")]);

let seed = 12345;
const rnd = (a, b) => { seed = (seed * 1103515245 + 12345) % 2147483648; return a + (seed % (b - a + 1)); };
const N = Number(process.argv[2] || 400);
let failures = 0;
for (let t = 0; t < N; t++) {
  const n = rnd(1, t % 10 === 0 ? 40 : 12);
  const big = t % 3 === 0 ? 600 : 250;
  const items = Array.from({ length: n }, () => ({ l: rnd(5, big), w: rnd(5, big), h: rnd(5, 300) }));
  if (t % 7 === 0) for (const it of items) it.l = it.w = 50;   // many equal sizes: tests stable sort + ties
  const input = `${n}\n` + items.map(i => `${i.l} ${i.w} ${i.h}`).join("\n") + "\n";
  const want = execFileSync(exe, { input }).toString().trim();
  const tr = designTrace(items), b = tr.trials[tr.best].result;
  const got = [`${b.W} ${b.L} ${b.H}`, ...items.map((_, i) => { const p = b.p[i];
    return `${i} ${p.x} ${p.y} ${p.z} ${p.l} ${p.w} ${p.h} ${p.rotated ? 1 : 0}`; })].join("\n");
  if (got !== want) { failures++; if (failures < 4) console.log("MISMATCH", JSON.stringify(items), "\nC++:\n" + want + "\nJS:\n" + got); }
}
console.log(failures ? `${failures} of ${N} baskets differ` : `All ${N} random baskets: JavaScript output identical to packer.cpp`);

// Fixed cartons: the JavaScript fitCarton() against the C++ service's fitCarton() (packer_core.cpp).
const core = join(here, "..", "..", "cpp-packer-service", "src");
const drv = join(dir, process.platform === "win32" ? "fit.exe" : "fit");
execFileSync("g++", ["-O2", "-std=c++17", "-I", core, "-o", drv, join(here, "fit_driver.cpp"), join(core, "packer_core.cpp")]);
let input = "", js = [];
for (let t = 0; t < N; t++) {
  const n = rnd(1, 8);
  const items = Array.from({ length: n }, () => ({ l: rnd(10, 220), w: rnd(10, 220), h: rnd(10, 250) }));
  const [L, W, H] = [rnd(100, 400), rnd(80, 300), rnd(60, 260)];
  input += `${L} ${W} ${H} ${n}\n` + items.map(i => `${i.l} ${i.w} ${i.h}`).join("\n") + "\n";
  const f = fitCarton(items, L, W, H);
  if (!f.fits) { js.push("nofit"); continue; }
  const a = f.attempts[f.chosen];
  js.push([a.name, a.result.W, a.result.L, a.result.H, ...items.map((_, i) => { const p = a.result.p[i]; return `${p.x},${p.y},${p.l},${p.w},${p.rotated ? 1 : 0}`; })].join(" "));
}
const cpp = execFileSync(drv, { input }).toString().trim().split("\n");
const fitFail = js.filter((line, i) => line !== cpp[i]).length;
const fitted = js.filter(l => l !== "nofit").length;
console.log(fitFail ? `${fitFail} of ${N} carton fits differ` : `All ${N} random carton fits identical to the C++ service (${fitted} fit, ${N - fitted} do not)`);
process.exit(failures || fitFail ? 1 : 0);
