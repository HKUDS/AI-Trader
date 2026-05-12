# Pionex AI Kit MCP Integration Spec

**Date:** 2026-05-12
**Branch:** `feat/pionex-ai-kit-integration`
**Author:** Brian (via Claude Code)
**Status:** Draft — Phase 3 broker integration scaffolding (read-only)

---

## Premise correction

Brian's task brief assumed BW-Trader already had a 142 LOC self-written
`service/server/brokers/pionex_client.py` with HMAC-SHA256 signing.

**This file does not exist.** The repo's broker surface today is:

| Path | What it does |
| --- | --- |
| `service/server/security/no_auto_trade.py` | Hard red-line: rejects any payload with `paper=false` (HTTP 403) and refuses all inbound broker webhooks. |
| `service/server/routes_security.py` | Mounts `/api/brokers/webhook` → 403 forever. |
| `service/server/paper_engine.py` | NT$1M paper sandbox; comment notes "future Phase 3 broker integration can reuse the same engine." |

So this PR is **greenfield**, not a rewrite. There is nothing to deprecate
or move to `legacy/`. Step 6 commit 3 ("rename existing client") is a no-op
and dropped from the plan.

---

## What Pionex AI Kit actually is

Cloned to `/Users/brian/dev/pionex-ai-kit` (`MIT` licensed, commercial-OK).

- **TypeScript / Node.js monorepo** (pnpm workspaces). No Python SDK.
- Two published npm packages:
  - `@pionex/pionex-ai-kit` — CLI for onboarding (`onboard`) and per-client
    MCP config setup (`setup --client claude-code`, etc.).
  - `@pionex/pionex-trade-mcp` — MCP server. Stdio transport. Spawned via
    `npx -y @pionex/pionex-trade-mcp`.
- **No long-running daemon model** — the MCP server is a stdio subprocess
  that lives as long as the parent agent process holds the pipe open.
- Credential priority: env vars (`PIONEX_API_KEY` / `PIONEX_API_SECRET` /
  `PIONEX_BASE_URL`) **before** `~/.pionex/config.toml`.
- Has a `--read-only` flag that "expose only read/query tools and disable
  write operations" — load-bearing for BW-Trader's no-auto-trade policy.
- Exposes `pionex_orders_new_order`, `pionex_bot_*_create`,
  `pionex_earn_dual_invest`, etc. (the writes that would cross the red
  line if reached without consent).

The `pionex-skills` package is for Brian's *personal* Claude Code install
(`npx skills add pionex-official/pionex-skills`) and is out of scope for
the BW-Trader server — skills are agent prompts, not server libraries.

---

## Three-layer impact

| Layer | Today | After this PR |
| --- | --- | --- |
| **Backend FastAPI** | No broker code at all. | `service/server/integrations/pionex_mcp_client.py` — thin Python wrapper that owns the `npx pionex-trade-mcp` subprocess and speaks JSON-RPC over stdio. Read-only by default. Write methods exist but pass through `assert_paper_only` first → 403 unless `ALLOW_LIVE_TRADING=true`. |
| **Agent (Claude / dispatch)** | Calls backend. | Two-track: (a) backend can call MCP for read-only market data inside FastAPI handlers; (b) Brian's personal agents can connect directly to the same MCP via `pionex-ai-kit setup --client claude-code` — outside this server. |
| **User-facing UI** | Talks to backend. | Unchanged. Any UI surfacing Pionex data (e.g. crypto chart) reads it via a backend route that proxies the wrapper. |

---

## Integration path decision

### Option A — pure Python rewrite (rejected)

Re-implement HMAC-SHA256 in Python. Same problem Brian wanted to avoid.

### Option B — `npm install` + Node subprocess + JSON-RPC stdio (**chosen**)

Per the task spec contingency: *"若 AI Kit Python SDK 不存在（只有 CLI /
TypeScript） → 寫 thin Python wrapper subprocess CLI."* Selected because:

1. Official MCP server is the single source of truth for signing & API
   shape; we don't fork a stale implementation.
2. `--read-only` flag is a hardware-style switch that's harder to
   accidentally bypass than a Python `if` branch.
3. Subprocess lifetime stays inside the FastAPI worker — no orphan
   daemons, no supervisor needed in v1.
4. License is MIT — drop-in.

### Option C — call AI Kit CLI per request (rejected)

`pionex-trade-cli market depth BTC_USDT` per call is 200-500ms of node
startup. MCP server keeps node warm for the lifetime of the FastAPI
worker and reuses one process across many tool calls.

---

## Wrapper design — `pionex_mcp_client.py`

### Public surface

```python
class PionexMCPClient:
    """Thin Python <-> Pionex AI Kit MCP subprocess wrapper.

    Spawns `npx -y @pionex/pionex-trade-mcp --read-only` and speaks the
    MCP stdio JSON-RPC protocol (initialize -> tools/list -> tools/call).

    All write methods route through `security.assert_paper_only` first;
    they raise HTTP 403 unless `ALLOW_LIVE_TRADING=true` AND the caller
    passes an explicit user consent payload.
    """

    # Read-only
    def get_klines(self, symbol: str, interval: str = "1D", limit: int = 200) -> dict: ...
    def get_depth(self, symbol: str, limit: int = 20) -> dict: ...
    def get_tickers(self) -> dict: ...
    def get_book_tickers(self) -> dict: ...

    # Auth required, still read-only
    def get_balance(self) -> dict: ...

    # WRITE — red line; refuses without consent
    def new_order(self, payload: dict, *, user_consent: bool = False) -> dict: ...

    # Lifecycle
    def close(self) -> None: ...
```

### Transport seam

The class accepts an injectable `transport` keyword argument. In production
it's a real `MCPStdioTransport` that owns a `subprocess.Popen` of
`npx -y @pionex/pionex-trade-mcp --read-only`. In tests it's a
`FakeTransport` that responds to JSON-RPC calls from a script. This is the
only seam needed to test without spawning node.

### Red-line enforcement

Every write method does this in order:

1. `security.assert_paper_only({"paper": user_consent})` — same primitive
   the rest of the codebase uses. If `user_consent=False`, this raises
   `HTTPException(403)` before any subprocess call is made.
2. Even when consent is given, the wrapper checks `config.ALLOW_LIVE_TRADING`
   and refuses if it's false. Two locks, both have to be open.
3. Only then does the JSON-RPC `tools/call` go out.

The subprocess is *also* started with `--read-only` by default, which
means even if all the above were bypassed, the MCP server itself would
refuse the call. Three locks.

---

## Configuration

| Env var | Purpose | Default |
| --- | --- | --- |
| `PIONEX_API_KEY` | Pionex API key (read-only key recommended) | `""` (unset → public market data only) |
| `PIONEX_API_SECRET` | Pionex API secret | `""` |
| `PIONEX_BASE_URL` | Optional API base override | unset → AI Kit default |
| `PIONEX_AI_KIT_COMMAND` | Override the spawn command for the MCP server | `npx -y @pionex/pionex-trade-mcp` |
| `PIONEX_AI_KIT_READ_ONLY` | Force read-only mode on subprocess startup | `true` |

**Brian does not paste real keys into `.env.example`.** Placeholders only.

---

## Tests — `tests/test_pionex_aikit.py`

≥ 8 cases, all mocking the stdio transport (no node, no network):

1. `initialize` handshake completes and stores server capabilities.
2. `get_klines` issues a `tools/call` with `pionex_market_get_klines` and
   returns the unwrapped data field.
3. `get_depth` works on a symbol with no auth.
4. `get_balance` works when API key env var is present.
5. `get_balance` raises a clean error when no auth and the server
   responds with `requires_auth`.
6. `new_order` without `user_consent=True` raises HTTP 403 (red line)
   and never touches the transport.
7. `new_order` with `user_consent=True` but `ALLOW_LIVE_TRADING=false`
   still raises 403.
8. `new_order` with consent AND `ALLOW_LIVE_TRADING=true` reaches the
   transport (verified by spy) — the actual write is mocked to return
   a stub fill.
9. `close()` terminates the subprocess transport cleanly.

---

## Out of scope (deferred)

- **Long-running MCP supervisor** — if BW-Trader later wants a process
  manager that restarts the MCP server on crash, that's its own PR. v1
  just spawns lazily on first call and lets the parent process own it.
- **Wiring the wrapper into a FastAPI route** — this PR only ships the
  wrapper + tests. A follow-up will add `/api/market/pionex/klines` or
  similar, with the red-line dep injected.
- **`.mcpb` install for end users** — that's a personal-agent setup,
  not a server concern.
- **Skills registration** — Brian installs `pionex-skills` in his own
  Claude Code, not on the server.

---

## Risks / warnings

| Risk | Mitigation |
| --- | --- |
| Node-version mismatch on prod server (AI Kit requires Node ≥ 18). | Docs note the requirement; deploy script checks `node --version` before starting the FastAPI worker. (Out of scope for this PR — flagged for ops.) |
| `npx` install on first run is slow / racy under concurrent workers. | Pre-install with `npm install -g @pionex/pionex-trade-mcp` in the Dockerfile, then `PIONEX_AI_KIT_COMMAND=pionex-trade-mcp`. |
| MCP server hangs and the parent process inherits the pipe. | `close()` sends SIGTERM with a short timeout, then SIGKILL. Stdio reads have a per-call timeout. |
| AI Kit publishes a breaking change. | We pin a version in the spawn command at deploy time (`@pionex/pionex-trade-mcp@0.2.49`). Upgrade is a deliberate PR. |
| API key leak via env var dump. | The wrapper does not log env. Keys never appear in MCP client config files (per AI Kit's own design). |

---

## License

Pionex AI Kit is MIT — commercial use is permitted. No copyleft. The
wrapper does not vendor or modify AI Kit source; it speaks the MCP
protocol to an unmodified upstream binary spawned via `npx`.
