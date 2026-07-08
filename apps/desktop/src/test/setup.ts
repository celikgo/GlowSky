// Vitest global setup: jest-dom matchers (toBeInTheDocument, …) + DOM teardown between tests.
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach } from "vitest";
import { cleanup } from "@testing-library/react";

// jsdom under this vitest env exposes `localStorage` as a bare `{}` with no Web Storage methods,
// so the client's token store (getItem/setItem/removeItem/clear) has nothing to call. Install a
// minimal in-memory Storage so the auth wiring behaves as it does in the browser.
class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length(): number {
    return this.store.size;
  }
  clear(): void {
    this.store.clear();
  }
  getItem(key: string): string | null {
    return this.store.has(key) ? (this.store.get(key) as string) : null;
  }
  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

if (typeof localStorage.clear !== "function") {
  Object.defineProperty(globalThis, "localStorage", {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  });
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
});
