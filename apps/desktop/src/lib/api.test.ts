import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, getToken, setToken } from "./api";

/** A minimal Response stand-in for the client's `request`/`download`/`tryRefresh` paths. */
function res(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: `HTTP ${status}`,
    headers: { get: (k: string) => headers[k.toLowerCase()] ?? null },
    json: async () => body,
    blob: async () => new Blob([]),
  } as unknown as Response;
}

const TOKEN = { access_token_expires_in: 900, refresh_token_expires_in: null, tenant_scoped: true };

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("tool invocation wiring", () => {
  it("posts args to /tools/{name} and returns output + provenance", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(res(200, { output: { target: "CCO" }, provenance: { duration_ms: 3 } }));
    vi.stubGlobal("fetch", fetchMock);

    const out = await api.runTool("retrosynthesize", { canonical_smiles: "CCO" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/tools/retrosynthesize");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ args: { canonical_smiles: "CCO" } });
    expect(out.output).toEqual({ target: "CCO" });
  });

  it("includes the seed in the body only when one is given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(200, { output: {}, provenance: {} }));
    vi.stubGlobal("fetch", fetchMock);

    await api.runTool("matched_pairs", { smiles_list: ["CCO"] }, 7);

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ args: { smiles_list: ["CCO"] }, seed: 7 });
  });

  it("raises an ApiError carrying the server's detail on a failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(500, { detail: "boom" })));

    const err = await api.runTool("sar_transforms", { smiles_list: [] }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 500, message: "boom" });
  });
});

describe("auth wiring", () => {
  it("stores the access token after login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(res(200, { access_token: "tok123", refresh_token: "r1", ...TOKEN })),
    );

    await api.login("a@b.com", "pw");
    expect(getToken()).toBe("tok123");
  });

  it("silently refreshes and replays once on a 401", async () => {
    setToken("expired");
    localStorage.setItem("glowsky_refresh_token", "r1");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(res(401, { detail: "expired" })) // first /tools call
      .mockResolvedValueOnce(res(200, { access_token: "fresh", refresh_token: "r2", ...TOKEN })) // /auth/refresh
      .mockResolvedValueOnce(res(200, { output: 42, provenance: {} })); // replayed /tools call
    vi.stubGlobal("fetch", fetchMock);

    const out = await api.runTool("retrosynthesize", { canonical_smiles: "CCO" });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect((fetchMock.mock.calls[1][0] as string)).toContain("/auth/refresh");
    expect(getToken()).toBe("fresh");
    expect(out.output).toBe(42);
  });
});
