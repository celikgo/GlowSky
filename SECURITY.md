# Security Policy

Glowsky holds two things that are worth stealing: **other people's LLM API keys**, and
**unpublished chemistry**. A leaked provider key is somebody else's money and somebody
else's account. A leaked structure can be a research programme. Both are handled by
this repository, so please read the reporting section before the boasting section.

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Report privately through GitHub's [private vulnerability
reporting](https://github.com/celikgo/GlowSky/security/advisories/new) on this
repository. That channel is preferred because it keeps the report, the fix and the
advisory in one place and lets you be credited automatically.

Please include: what an attacker gains, the steps to reproduce, the affected version or
commit, and the configuration you ran (self-hosted or not, which `GLOWSKY_*` settings,
which database). A proof of concept helps enormously and does not need to be weaponised.

**What to expect.** This is a single-maintainer project, not a vendor with a security
team, and saying so is more useful than publishing response times nobody is on call to
meet. You should get an acknowledgement within a few days. Fixes for credential-exposure
and cross-tenant issues take priority over everything else in the project. If a report
turns out to be a design limitation rather than a bug, you will get a straight answer
saying so, and it will be documented rather than quietly closed.

Please give a reasonable window to ship a fix before disclosing publicly. If you do not
hear back, escalate by opening a public issue that says only that you sent a private
report and got no reply — with no details of the vulnerability itself.

## Supported versions

| Version | Supported |
|---|---|
| `main` | Yes |
| Tagged releases | The most recent tag only |
| Anything older | No |

Glowsky is early access and there is no long-term-support branch. Fixes land on `main`
and go out in the next tag.

## What is in scope

Anything that would let someone:

- **read or exfiltrate a stored BYO-LLM provider key**, in any form — through the API,
  the logs, an error message, a trace, an export, or the database;
- **cross a tenant boundary** — read or write another org's projects, molecules,
  libraries, runs, jobs or credentials;
- **bypass the role gate** — perform a write as a `viewer`, or act without a valid
  platform JWT;
- **escape the container-tool sandbox** — reach the host, the Docker socket, the
  network, or another tool's data from inside a tool container;
- **be a confused deputy** — get the agent to exfiltrate data or invoke tools it should
  not, via prompt injection through imported files, tool output, or chat content;
- **poison the deterministic core** — get an unvalidated or model-generated structure
  persisted, displayed, or exported as if it had passed the validation firewall.

The last one is a security issue here even though it looks like a correctness issue.
The premise of this project is that the molecule is never a model-generated string; a
path that defeats that is an attack on the product's only real guarantee.

## Known limitations — please do not report these as vulnerabilities

These are documented, deliberate, and already written down in
[`docs/07-security-privacy.md`](docs/07-security-privacy.md), which tags every control
as shipped / partial / planned. Reporting them is not useful; **finding a way to exploit
one of them beyond its stated blast radius is**, and that is worth reporting.

- **There is no key rotation.** `GLOWSKY_SECRET_KEY` is a single Fernet key with no
  `MultiFernet` fallback. Changing it makes every stored credential permanently
  undecryptable. Anyone holding both the database and that key can decrypt every stored
  provider key.
- **Encryption at rest is one process-wide key.** No envelope encryption, no per-tenant
  data keys, no KMS. The `KeyStore` seam exists; the implementation does not.
- **TLS is a deployment responsibility.** The app terminates no TLS and encrypts no
  disk. Put it behind a reverse proxy and encrypt the volume.
- **Tool arguments are not validated server-side.** `ToolSpec.input_schema` is
  advertised to the model but not enforced before dispatch, so a malformed call surfaces
  as a handler `TypeError` (HTTP 422) rather than a schema rejection.
- **The structure firewall is narrower than its name.** It runs only for tools declaring
  `emits_structures=True` and inspects only dict keys literally named `smiles`.
- **`egress: allowlist` on a container tool means no network at all.** The
  allowlist-honouring proxy is not built, so the runtime fails closed — and the
  downgrade is silent.
- **There is no Postgres row-level security.** Tenant isolation is enforced in the
  application layer on every read and write path. RLS is planned as defence in depth.
- **Self-hosting is single-tenant by construction.** If you run one instance for
  multiple untrusted orgs, you are relying entirely on those application-layer checks.

## What this project does enforce, and where it is tested

Each of these is gated by [`.github/workflows/security.yml`](.github/workflows/security.yml)
on every pull request — they are claims with tests behind them, not assurances.

- **The secret guard fails safe.** `GLOWSKY_ENVIRONMENT` defaults to `production`, and a
  production instance with no `GLOWSKY_SECRET_KEY` **refuses to boot** rather than fall
  back to the deterministic development key — which is public by construction, because
  it is in this repository. Tested in `tests/test_settings.py`.
- **The deployment refuses to start unconfigured too.** The compose files declare the
  secret as `${GLOWSKY_SECRET_KEY:?...}`, so `docker compose up` stops rather than
  starting an instance that would encrypt real keys under the dev key. Asserted in both
  directions by `.github/workflows/docker.yml`.
- **Keys are never returned after entry.** Storing a credential returns a masked hint
  only; the plaintext is never logged and never sent back. Tested in
  `tests/test_settings.py`.
- **Every request is authenticated.** There is no auth bypass flag and no local
  credential store: every request carries a platform JWT or gets a 401.
- **Writes require a writer.** `/agent/design`, `/agent/chat` and their WebSocket
  variants execute tools and persist rows, so a `viewer` is refused — 403 on REST, an
  error frame on the socket. Tested in `tests/test_rbac_agent.py`.
- **Cross-tenant reads return 404, never 403**, so existence is never confirmed across
  orgs. Tested in `tests/test_auth.py`.
- **Container tools are off by default** and require both
  `GLOWSKY_ENABLE_CONTAINER_TOOLS=true` and `GLOWSKY_TOOLS_DIR`.
- **Dependencies are audited** (`pip-audit`, `pnpm audit`) and the **full git history is
  secret-scanned** (`gitleaks`) on every pull request.

## Running Glowsky safely

- **Set `GLOWSKY_SECRET_KEY` to a real Fernet key** and back it up somewhere you will
  still have it later. There is no rotation path; losing it orphans every stored
  credential.
- **Never set `GLOWSKY_ENVIRONMENT` to a dev value in a real deployment.** That is the
  one switch that enables the public development key.
- **Do not commit `.env`.** It is gitignored, and CI fails if it appears.
- **Only enable container tools on a host you trust.** The opt-in
  `docker-compose.tools.yml` overlay mounts the Docker socket into the worker, which is
  root-equivalent on that host. Use it single-tenant.
- **Terminate TLS in front of it**, and encrypt the volume.
- **Your keys go to your providers.** Glowsky sends completions to whichever
  provider/model the active route names. It makes no other outbound calls — no
  telemetry, no analytics, no crash reporting, nothing phones home. Use the `local`
  provider to keep everything inside your own boundary.

## Credentials in this repository

The string `glowsky-dev-secret-do-not-use-in-production` in
`services/core/crypto.py` is a **deliberately public** development passphrase. It is not
a leak. It is public precisely so that `validate_secret_config()` can refuse to let any
non-development environment fall back to it. Anything encrypted under it should be
treated as plaintext.
