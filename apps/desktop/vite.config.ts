import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { nodePolyfills } from "vite-plugin-node-polyfills";

// Tauri expects a fixed dev-server port and ignores VITE_-prefixed env leakage.
// https://v2.tauri.app/start/frontend/vite/
export default defineConfig({
  plugins: [
    react(),
    // Ketcher (the 2D structure editor) is authored for a webpack/CRA world and reaches for
    // Node globals (`process`, `Buffer`, `global`). Shim just those so it runs in the browser;
    // its Indigo WASM engine loads via Vite's native `new Worker(new URL(..., import.meta.url))`
    // pattern, so no extra worker/wasm config is needed. Modules off — we only need the globals.
    nodePolyfills({ globals: { process: true, Buffer: true, global: true }, protocolImports: false }),
  ],
  clearScreen: false,
  // One stray `process.env.NODE_DEBUG` read in ketcher-react isn't covered by the globals shim;
  // pin it to undefined so it doesn't throw. (A blanket `process.env` replace would clobber the
  // NODE_ENV that React's dev/prod build depends on — so target only this key.)
  define: { "process.env.NODE_DEBUG": "undefined" },
  build: {
    // Ketcher's ESM build embeds conditional CommonJS `require()` calls (e.g.
    // `typeof window !== 'undefined' ? require('raphael') : undefined`). Rollup's commonjs plugin
    // skips require() inside ES modules by default, so they survive to runtime as `require is not
    // defined` and crash the editor on open. transformMixedEsModules rewrites those to imports.
    commonjsOptions: { transformMixedEsModules: true },
  },
  // Pre-bundle Ketcher's CJS deps (raphael/ajv/acorn/…) so the dev server resolves them the same
  // way the production build does.
  optimizeDeps: { include: ["ketcher-react", "ketcher-core", "ketcher-standalone"] },
  server: {
    port: 1420,
    strictPort: true,
    watch: {
      // Don't watch the Rust shell from the web dev server.
      ignored: ["**/src-tauri/**"],
    },
  },
});
