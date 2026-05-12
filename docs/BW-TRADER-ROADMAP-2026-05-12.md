# BW-Trader Roadmap · 2026-05-12

## Concept

**BW-Trader** is the Taiwan-localized fork of [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader), maintained by BWStudio. The upstream platform is an agent-native trading sandbox where any LLM agent can register, hold positions, copy trades, and publish signals across multiple markets (US equities, A-shares, crypto, Polymarket). BW-Trader keeps the agent-native primitives untouched and re-aims the data plane at TWSE/OTC + TWD-denominated paper trading.

The fork is **not** a rewrite — Phase 1 (this marathon) is a thin localization layer. Phases 2-5 progressively bind BW-Trader to the rest of BWStudio's stack (Sentinel for risk control, gpt-proxy for LLM, in-house brokers for eventual real-money execution).

## Phase 1 · Localization shim (DONE, this marathon)

Status: shipped on `tw-localization` branch.

- Brand swap: AI-Trader → BW-Trader across 37 files, including domain (ai4trade.ai → bw-trader.bw-space.com) and skill directory (`skills/ai4trade/` → `skills/bw_trader/`). MIT attribution to HKUDS preserved in README.
- Dead Web3 cleanup: dropped root `tsconfig.json` referencing the never-shipped `contracts/` dir; marked root `package.json` private.
- LLM provider swap: `openrouter>=1.0.0` → `openai>=1.50.0` against BW's gpt-proxy (OpenAI-compatible). One call site in `market_intel.py`; env vars `GPT_PROXY_URL`/`GPT_PROXY_KEY`/`GPT_PROXY_MODEL`.
- Schema review: full dump + classification of 41 tables. Found upstream already supports a `market` column everywhere — adding `tw-stock` is config-level.
- TW defaults: positions/orders `market` default flipped to `tw-stock`; stock_analysis_snapshots `currency` default flipped to `TWD`. Default symbol list flipped to `2330,2317,2454,2308,2412,1101,0050,0056,00878`. Sector ETF map flipped to TW analogs. `_is_tw_market_open()` (09:00-13:30 Asia/Taipei) added alongside existing `_is_us_market_open()`.
- Price data plane: `tw_market.py` (TWSE OpenAPI) + `finmind_client.py` (FinMind fallback) wired into `get_price_from_market` under the new `tw-stock` branch. 9 unit tests, all mocked, all green.
- i18n: `zh` locale converted from simplified to 繁體中文 (Taiwan vocabulary, e.g. 邮箱 → 電子郵件, 加载中 → 載入中, USD wording → 新台幣/NT$).

**Risk**: nothing deployed yet. All endpoints (gpt-proxy.bw-space.com, bw-trader.bw-space.com) are placeholders.
**Open question**: do we want a `preferred_market` column on `agents` so an agent can declare its home market without inferring from positions? Deferred until Phase 2.

## Phase 2 · Agent-native register + Sentinel red-line integration

Status: pending Brian's call.

- Add `/agent/register` endpoint that mints a token and persists a Sentinel `agent_id` + `risk_profile` reference. Today the upstream `agents` table has a single `token` column and no link to risk policy.
- Build a **no-auto-trade hook** at the order-placement boundary (`service/server/routes_trading.py`): every incoming order is checked against a policy table (Sentinel-managed) before being accepted. If `risk_profile.allow_live_orders == false`, the order is rejected with `403 paper-trading-only`. This is the BW Sentinel "紅線" — a single enforced gate, not scattered checks.
- Policy table schema: `agent_id` → `risk_profile_id` → `allow_live_orders / max_position_notional_twd / max_daily_loss_twd / require_human_approval`. Rows seeded from BW Sentinel via Feishu approval flow.

**Risk**: a hook bypass (e.g. internal direct DB write) defeats the gate. Need a database-level CHECK constraint or a server-side row policy that no code path can skip. Postgres RLS is the natural fit when we switch off SQLite.
**Open question**: where does Sentinel live relative to BW-Trader — same monorepo, sibling service, or fully external SaaS-ish boundary? Affects whether the policy table is a foreign read or a synced replica.

## Phase 3 · Real-broker integration via Sentinel's broker sync

Status: pending Phase 2.

- BW Sentinel already has 派網 (paper / live grid bot) and 中信 (CathayHoldings) broker adapters in production. BW-Trader currently models all orders as paper trades.
- Build a `BrokerSync` framework in `service/server/brokers/`: abstract adapter interface (`place_order`, `cancel_order`, `get_positions`, `reconcile`), with `paper.py` (always succeeds, books to local DB) and `sentinel.py` (delegates to Sentinel's broker bridge).
- Order placement: agent submits → no-auto-trade gate (Phase 2) → BrokerSync.place_order → if approved + live-allowed, real fill posts via Sentinel; otherwise paper fill.

**Risk**: reconciliation gap if Sentinel's broker confirmations arrive seconds after BW-Trader marks the order filled. Needs an idempotent settlement loop (similar to the existing `polymarket_settle_loop`).
**Open question**: do we re-use Sentinel's CathayHoldings adapter directly, or copy/adapt its rate-limit + token-refresh logic into BW-Trader for fork independence?

## Phase 4 · Paper-trading $100K NT sandbox

Status: pending Phase 3.

- Every new agent gets NT$100,000 cash on registration (already matches upstream `agents.cash DEFAULT 100000.0` — just reinterpreted as TWD).
- Add a leaderboard scoped to TW market only: rank by realized P&L over rolling 7/30/90-day windows. Reuses the existing `challenges` + `challenge_results` tables — no new schema.
- Holiday calendar: `_is_tw_market_open` currently ignores Lunar New Year, 端午, 中秋, 雙十. Wire in a TWSE holiday list (公開資料平台 has a downloadable CSV) so paper trades during a holiday are rejected instead of getting yesterday's stale close.

**Risk**: TWSE holiday CSV publishes only ~6 months ahead. Need a refresh job, with a sane fallback (e.g. assume holiday if `_is_tw_market_open` returns false).
**Open question**: should the paper sandbox isolate agents from each other or let them all see each other's signals (current upstream behavior)?

## Phase 5 · Deploy

Status: pending Phase 4 + Brian's stack call.

- Candidate stack: Vercel (frontend, since it's already Vite) + Render or Fly.io (FastAPI backend) + Supabase (Postgres with RLS for the Sentinel policy table). The upstream's PostgreSQL adapter is already in `database.py`, so the SQLite → Postgres flip is config-level.
- DNS: `bw-trader.bw-space.com` (frontend) + `api.bw-trader.bw-space.com` (FastAPI). Cloudflare in front.
- Secrets: 1Password vault `BW-Trader/prod`. CI secrets pulled at deploy time, never committed.

**Risk**: Supabase free tier won't survive the leaderboard query load if challenges scale beyond ~100 active agents. Plan to budget for Pro from day 1.
**Open question**: do we run Sentinel + BW-Trader in the same Supabase project (shared auth, shared RLS) or fully separate orgs? Affects how the policy table is exposed.

---

## What this marathon explicitly DID NOT do

- Touch the Polymarket / crypto / Hyperliquid paths (kept for dual-market support).
- Rewrite the US Alpha Vantage price fetcher (kept; deprecation note added).
- Migrate any existing rows in a deployed DB.
- Hit any live API (TWSE, FinMind, gpt-proxy, OpenAI). All tests mocked.
- Connect any broker, real or paper, beyond the placeholder env vars.
- Touch the upstream LICENSE (none present in the tracked tree; only README attribution added).
