# BW-Trader Schema Review · 2026-05-12

**Source**: `service/server/database.py:340-1361` (`init_database()`).
**Dump**: [BW-TRADER-SCHEMA-DUMP-2026-05-12.sql](./BW-TRADER-SCHEMA-DUMP-2026-05-12.sql)
**Backend**: SQLite by default (`DB_PATH=service/server/data/bw_trader.db`), PostgreSQL when `DATABASE_URL` is set. No prod DB ever lived here — schema review only.

## Table inventory (41 tables)

### Tier A · Trading core (need TW awareness)

| Table | TW-sensitive columns | Decision |
|---|---|---|
| `agents` | `cash REAL DEFAULT 100000.0` | **Keep as-is.** Default cash 100000 maps cleanly to NT$100,000 — Brian wants $100K NT paper trading. Currency is implicit per-agent, not per-row. |
| `positions` | `market TEXT NOT NULL DEFAULT 'us-stock'`, `symbol`, `wallet_address` (line 670 ALTER) | **Add `tw-stock` as a valid market value.** Change default to `'tw-stock'` for new fork installs. Keep `us-stock` / `a-stock` / `crypto` / `polymarket` enums. |
| `orders` | `market TEXT NOT NULL` (line 220 default `'us-stock'`), `symbol` | **Same as positions** — flip default to `'tw-stock'`. |
| `listings` | `market`, `symbols TEXT (JSON)` | **Same**, but listings are user-published so default doesn't bind hard — UI default is what matters. |
| `signals` | `market TEXT NOT NULL`, `symbol`, `token_id` (polymarket) | No default — caller specifies. Just need UI to default to TW. |
| `signal_replies` | inherits via FK | No change. |
| `subscriptions` | `market` | No default. |
| `polymarket_settlements` | `market_slug`, `symbol`, prediction-market-specific | **Keep as-is, US-denominated.** Polymarket is a USD prediction market; if BW-Trader ever exposes Polymarket to TW users we'd hold USD-denominated positions side-by-side — not a fork-time concern. |
| `signal_sequence` | sequence counter only | No change. |

### Tier B · Market-intel snapshots (price + currency surface)

| Table | TW-sensitive columns | Decision |
|---|---|---|
| `stock_analysis_snapshots` | `market TEXT NOT NULL`, `symbol`, **`currency TEXT DEFAULT 'USD'`** | **Flip default `'USD'` → `'TWD'`.** Most TW caller-rows will get `'TWD'`, so default matches reality. Keep column nullable-flexibly so US-stock rows can override. |
| `market_news_snapshots` | category + payload (JSON blob) | No currency leakage — JSON payload internal. |
| `macro_signal_snapshots` | snapshot key + JSON | No change. |
| `etf_flow_snapshots` | snapshot_key + JSON | **Watch the JSON payload** — upstream code populates US ETF tickers (SPY/QQQ/IWM). Commit 6 handles call-site swap to TW ETFs (0050/00878/0056); schema itself is generic enough to stay. |

### Tier C · Identity, governance, points (currency-agnostic)

No changes — these tables don't care about market or currency:
- `users`, `user_tokens`, `rate_limits`
- `points_transactions` (BW internal point ledger, dimensionless)
- `agent_reward_ledger` (same — points/reputation)
- `agent_messages`, `agent_tasks`
- `arbitrators`, `dispute_votes`
- `experiment_events`, `experiments`, `experiment_assignments`

### Tier D · Competition / team mission (currency-agnostic if NT$ adopted globally)

- `challenges`, `challenge_participants`, `challenge_submissions`, `challenge_trades`, `challenge_results`
- `team_missions`, `teams`, `team_mission_participants`, `team_members`, `team_messages`, `team_submissions`, `team_contributions`, `team_results`
- `signal_predictions`, `signal_quality_scores`

If we adopt NT$ globally per-fork, these don't need column changes — just consistent interpretation of the existing numeric fields (`profit`, `reward_value`, etc.) as TWD.

### Tier E · Bookkeeping (no change)

- `profit_history` — `total_value`, `cash`, `position_value`, `profit` are all REAL, currency-implicit. Per-agent interpretation.

## Recommended schema diff (deferred; not applied this commit)

```sql
-- 1. positions / orders / listings default flip (only affects new rows; existing data unaffected)
-- For NEW fork installs, change DEFAULT 'us-stock' → DEFAULT 'tw-stock' in init_database().
-- For migration from an existing US install: add explicit market='tw-stock' on TW positions, don't ALTER DEFAULT.

-- 2. stock_analysis_snapshots currency default
ALTER TABLE stock_analysis_snapshots ALTER COLUMN currency SET DEFAULT 'TWD';
-- (SQLite: rewrite the CREATE TABLE block in init_database)

-- 3. (optional) add agents.preferred_market TEXT DEFAULT 'tw-stock' so multi-market agents
--    can declare their home market without inferring from positions.
```

**These are not yet applied** — Commit 5 ships the dump + review only. Commit 6 handles the in-place flip for new installs (init_database default change is a 2-line edit) but does NOT migrate any existing rows. Cross-market agents stay supported.

## Surprises worth flagging

1. **`market` column already exists everywhere it matters.** Upstream HKUDS already supports US + A-stock + crypto + polymarket via the `market` field. Adding `tw-stock` is config-level, not schema-level. **This is the biggest find** — schema work for TW localization is much smaller than expected.
2. **No `currency` column on positions/orders/listings.** Currency is implicit per-market. If we ever support a TW user holding US positions, we'd need to add it. Flag for Phase 2.
3. **`polymarket_settlements` is USD-locked by reality of the upstream prediction market.** Don't try to TWD-ize it; if exposed, just convert on display.
4. **Web3 hangover**: `positions` and `agents` have `wallet_address` columns (line 357, 670-ALTER). Not related to TW; just an HKUDS feature for crypto markets. Leave alone — Brian's prompt says don't kill polymarket / crypto.
5. **`profit_history` has 4 separate REAL columns** (`total_value`, `cash`, `position_value`, `profit`) — currency-agnostic but means a multi-currency rollup would need a flatten step. Phase 2 concern.

## Touched-in-Commit-6 plan

- `init_database` line 220: `DEFAULT 'us-stock'` → `DEFAULT 'tw-stock'` (positions)
- `init_database` line 670 ALTER: same flip
- `init_database` line 653: `DEFAULT 'USD'` → `DEFAULT 'TWD'` (stock_analysis_snapshots.currency)
- Nothing else schema-side this marathon. Phase 2 (Commit-set after this) can add a `preferred_market` column to agents if Brian wants explicit declaration.
