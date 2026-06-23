import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  clearAuth,
  getToken,
  setToken,
  type Credential,
  type ProviderInfo,
  type RouteInfo,
} from "../lib/api";

const TASK_LABELS: Record<string, string> = {
  reasoning: "Reasoning",
  fast_triage: "Fast triage",
  codegen: "Code generation",
};

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : "Backend offline. Is `make run` up?";
}

export function SettingsScreen() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [creds, setCreds] = useState<Credential[]>([]);
  const [routes, setRoutes] = useState<RouteInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  // draft input state
  const [keyDraft, setKeyDraft] = useState<Record<string, string>>({});
  const [urlDraft, setUrlDraft] = useState<Record<string, string>>({});
  const [routeDraft, setRouteDraft] = useState<Record<string, { provider: string; model: string }>>({});

  // platform access token (the only credential the backend accepts)
  const [tokenDraft, setTokenDraft] = useState(getToken());
  const [tokenSaved, setTokenSaved] = useState(getToken());

  // login form (email + password → carbon-auth via the backend proxy)
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);
  const [loginMsg, setLoginMsg] = useState<string | null>(null);

  async function load() {
    try {
      const [ps, cs, rs] = await Promise.all([
        api.listProviders(),
        api.listCredentials(),
        api.getRoutes(),
      ]);
      setProviders(ps);
      setCreds(cs);
      setRoutes(rs);
      setRouteDraft(
        Object.fromEntries(rs.map((r) => [r.task_class, { provider: r.provider, model: r.model }])),
      );
    } catch (e) {
      setError(errMsg(e));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const credFor = (provider: string) => creds.find((c) => c.provider === provider);

  async function saveKey(provider: string, needsUrl: boolean) {
    const key = (keyDraft[provider] ?? "").trim();
    if (!key) return;
    try {
      await api.addCredential(provider, key, needsUrl ? urlDraft[provider] : undefined);
      setKeyDraft((d) => ({ ...d, [provider]: "" }));
      await load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function removeKey(id: string) {
    try {
      await api.deleteCredential(id);
      await load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function saveRoute(taskClass: string) {
    const d = routeDraft[taskClass];
    if (!d?.provider.trim() || !d?.model.trim()) return;
    try {
      await api.setRoute(taskClass, d.provider.trim(), d.model.trim());
      await load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function revertRoute(taskClass: string) {
    try {
      await api.clearRoute(taskClass);
      await load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  function saveToken() {
    const t = tokenDraft.trim();
    setToken(t);
    setTokenSaved(t);
    load(); // re-fetch now that requests are authenticated
  }

  function clearToken() {
    clearAuth();
    setTokenDraft("");
    setTokenSaved("");
    setLoginMsg(null);
  }

  async function doLogin() {
    setLoggingIn(true);
    setLoginMsg(null);
    setError(null);
    try {
      const t = await api.login(email.trim(), password);
      setTokenDraft(t.access_token);
      setTokenSaved(t.access_token);
      setPassword("");
      if (!t.tenant_scoped) {
        setLoginMsg(
          "Signed in, but your account has no single tenant — paste a tenant-scoped token below.",
        );
      }
      load(); // re-fetch now that requests are authenticated
    } catch (e) {
      setLoginMsg(
        e instanceof ApiError && e.status === 401
          ? "Invalid email or password."
          : e instanceof ApiError && e.status === 502
            ? "Identity service unreachable."
            : errMsg(e),
      );
    } finally {
      setLoggingIn(false);
    }
  }

  return (
    <div className="settings">
      {error ? <div className="design__error">{error}</div> : null}

      {/* Platform access — log in with carbon-auth credentials (proxied through the backend). */}
      <div className="section-title">Platform access</div>
      <p className="settings__note">
        Sign in with your <strong>nakitte-carbon-auth</strong> account. Glowsky proxies the login to
        carbon-auth and stores the returned token locally — your password is never stored. The
        session refreshes silently when the access token expires.
      </p>
      <section className="card settings__group">
        <div className="settings__row">
          <div className="settings__rowlabel">
            <span className="settings__provider">Account</span>
            <span className={`chip ${tokenSaved ? "chip--success" : ""}`}>
              {tokenSaved ? "signed in" : "signed out"}
            </span>
          </div>
          {tokenSaved ? (
            <div className="settings__addline">
              <button className="btn btn--ghost settings__btn" onClick={clearToken}>
                Sign out
              </button>
            </div>
          ) : (
            <div className="settings__loginform">
              <input
                className="input"
                type="email"
                placeholder="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <input
                className="input"
                type="password"
                placeholder="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && email.trim() && password && doLogin()}
              />
              <button
                className="btn settings__btn"
                onClick={doLogin}
                disabled={loggingIn || !email.trim() || !password}
              >
                {loggingIn ? <span className="spinner" /> : null}
                Sign in
              </button>
            </div>
          )}
          {loginMsg ? <div className="settings__loginmsg">{loginMsg}</div> : null}
        </div>

        {/* Advanced: paste a token directly (e.g. a tenant-scoped token for multi-tenant users). */}
        <details className="settings__advanced">
          <summary>Paste a token directly</summary>
          <div className="settings__addline">
            <input
              className="input mono"
              type="password"
              placeholder="Bearer JWT from nakitte-carbon-auth"
              value={tokenDraft}
              onChange={(e) => setTokenDraft(e.target.value)}
            />
            <button className="btn settings__btn" onClick={saveToken} disabled={!tokenDraft.trim()}>
              Save
            </button>
          </div>
        </details>
      </section>

      {/* Provider keys */}
      <div className="section-title">Provider keys (BYO-LLM)</div>
      <p className="settings__note">
        Keys are encrypted at rest and never shown again — only a masked hint. Set
        per-task models below to route work to a connected provider.
      </p>
      <section className="card settings__group">
        {providers.map((p) => {
          const cred = credFor(p.id);
          return (
            <div className="settings__row" key={p.id}>
              <div className="settings__rowlabel">
                <span className="settings__provider">{p.label}</span>
                <span className="mono settings__providerid">{p.id}</span>
              </div>
              {cred ? (
                <div className="settings__credline">
                  <span className="chip chip--success">connected</span>
                  <span className="chip mono">{cred.hint}</span>
                  {cred.base_url ? <span className="chip mono">{cred.base_url}</span> : null}
                  <button className="btn btn--ghost settings__btn" onClick={() => removeKey(cred.id)}>
                    Remove
                  </button>
                </div>
              ) : (
                <div className="settings__addline">
                  <input
                    className="input mono"
                    type="password"
                    placeholder={`${p.label} API key`}
                    value={keyDraft[p.id] ?? ""}
                    onChange={(e) => setKeyDraft((d) => ({ ...d, [p.id]: e.target.value }))}
                  />
                  {p.needs_base_url ? (
                    <input
                      className="input mono"
                      placeholder="base URL (e.g. http://localhost:11434/v1)"
                      value={urlDraft[p.id] ?? ""}
                      onChange={(e) => setUrlDraft((d) => ({ ...d, [p.id]: e.target.value }))}
                    />
                  ) : null}
                  <button
                    className="btn settings__btn"
                    onClick={() => saveKey(p.id, p.needs_base_url)}
                    disabled={!(keyDraft[p.id] ?? "").trim()}
                  >
                    Save
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </section>

      {/* Model routing */}
      <div className="section-title">Model routing</div>
      <p className="settings__note">
        Which “provider/model” handles each task class. An override applies to your org;
        otherwise the server default (often the offline mock) is used.
      </p>
      <section className="card settings__group">
        {routes.map((r) => {
          const d = routeDraft[r.task_class] ?? { provider: r.provider, model: r.model };
          return (
            <div className="settings__row" key={r.task_class}>
              <div className="settings__rowlabel">
                <span className="settings__provider">{TASK_LABELS[r.task_class] ?? r.task_class}</span>
                <span className={`chip ${r.source === "override" ? "chip--accent" : ""}`}>
                  {r.source}
                </span>
              </div>
              <div className="settings__addline">
                <input
                  className="input mono settings__provinput"
                  placeholder="provider"
                  value={d.provider}
                  onChange={(e) =>
                    setRouteDraft((rd) => ({
                      ...rd,
                      [r.task_class]: { ...d, provider: e.target.value },
                    }))
                  }
                />
                <input
                  className="input mono"
                  placeholder="model"
                  value={d.model}
                  onChange={(e) =>
                    setRouteDraft((rd) => ({
                      ...rd,
                      [r.task_class]: { ...d, model: e.target.value },
                    }))
                  }
                />
                <button className="btn settings__btn" onClick={() => saveRoute(r.task_class)}>
                  Save
                </button>
                {r.source === "override" ? (
                  <button
                    className="btn btn--ghost settings__btn"
                    onClick={() => revertRoute(r.task_class)}
                  >
                    Revert
                  </button>
                ) : null}
              </div>
            </div>
          );
        })}
      </section>
    </div>
  );
}
