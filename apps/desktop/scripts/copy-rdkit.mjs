// Stage the RDKit-JS runtime (loader + WASM) into public/ so Vite serves them at the
// app root and the emscripten loader can locate the .wasm next to its .js — fully
// offline, no CDN. Runs on postinstall and before dev/build.
import { copyFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../node_modules/@rdkit/rdkit/dist");
const dest = resolve(here, "../public");

const files = ["RDKit_minimal.js", "RDKit_minimal.wasm"];

mkdirSync(dest, { recursive: true });
for (const f of files) {
  const from = resolve(src, f);
  if (!existsSync(from)) {
    console.warn(`[copy-rdkit] missing ${from} — run \`pnpm install\` first`);
    process.exit(0); // don't fail install before deps exist
  }
  copyFileSync(from, resolve(dest, f));
}
console.log(`[copy-rdkit] staged ${files.join(", ")} -> public/`);
