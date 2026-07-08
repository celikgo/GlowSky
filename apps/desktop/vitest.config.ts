/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Standalone test config (kept apart from vite.config.ts so the heavy Ketcher CJS pre-bundling and
// node-polyfill shims the app build needs don't run under the tests). The client logic under test
// talks to a mocked backend and mocks the RDKit WASM hook, so a plain jsdom env is enough.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    clearMocks: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
