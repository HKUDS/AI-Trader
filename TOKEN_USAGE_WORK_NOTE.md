# Work Note — Token Usage Tracking (issue #74)

## Goal
Issue #74 asks for LLM **token usage per model and per day**. This adds that to
the backend, adapting the token accounting from the RadSim project.

## Key constraint
The AI-Trader backend makes **no LLM calls itself** — no LLM SDKs, no model API
keys. The token-generating calls happen inside the external agents (Claude Code,
Codex, Cursor, etc.). So the server cannot observe tokens directly; agents must
**self-report** usage, and the platform stores and aggregates it.

## What was added
| File | Change |
|------|--------|
| `service/server/config.py` | Ported RadSim's `MODEL_PRICING` table + `get_model_pricing` (unknown model → `None`, never "free") |
| `service/server/token_usage.py` *(new)* | Service layer adapted from RadSim's `task_logger`: `estimate_tokens`, `compute_cost_usd`, `record_token_usage`, `get_usage_by_model_and_day`, `summarize_usage` |
| `service/server/database.py` | New `token_usage` table + two indexes in `init_database()` (dual-backend SQLite/PostgreSQL) |
| `service/server/routes_models.py` | `TokenUsageReport` request model with trimming + abuse bounds |
| `service/server/routes_token_usage.py` *(new)* | Endpoints, registered in `routes.py` before the SPA catch-all |
| `service/server/tests/test_token_usage.py` *(new)* | 15 end-to-end tests |

## API
- `POST /api/claw/usage` — agent self-reports `{model, provider, input_tokens, output_tokens}` (auth-scoped to the caller)
- `GET  /api/claw/usage?start_date&end_date` — the caller's own usage grouped by model + day
- `GET  /api/usage/models?start_date&end_date` — public, agent-anonymous rollup by model + day

## Data model
`token_usage(id, agent_id, model, provider, input_tokens, output_tokens, cost_usd, created_at)`.
Per-model/per-day aggregation is `GROUP BY substr(created_at,1,10), model`
(`substr` keeps the day bucket backend-agnostic across SQLite and PostgreSQL).

## RadSim reuse
- **Verbatim:** pricing table + cost math (from RadSim `config.py` / `output.py`).
- **Adapted:** token estimator (`len/4`) and the record/aggregate/estimate structure from `task_logger.py`.
- **Deliberately not ported:** RadSim's private-SQLite-file singleton writer — not multi-tenant, async-safe, or Postgres-capable. The write path uses AI-Trader's own `DatabaseCursor` layer instead.

## Security / standards check
- Untrusted input: model/provider strings are trimmed; blank models are rejected; counts bounded (`ge=0`, `le=20_000_000`); date filters are calendar-validated, chronological, and **fail closed** (400).
- AuthZ: every write and personal read requires a valid Bearer token, scoped to `agent['id']`; bad token → 401.
- Abuse control: self-report writes are rate-limited per agent in the shared route context; excess reports → 429.
- Injection: all SQL parameterized; the only interpolated fragment is a constant `WHERE` built from fixed strings.
- Integrity: cost computed **server-side** (never trusted from client); day bucket uses the **server** timestamp; unknown model → `NULL` cost.
- No prompt/response **content** is accepted or stored — only counts. No secrets introduced.

## Open caveat (for reviewers)
Self-reported usage is **untrusted**. Treat it as informational; do **not** feed
it into rewards/leaderboard scoring without a verification story.

## Follow-up review fixes (adversarial pass)
Addressed all six findings from the cross-review:
1. **Silent undercounting from the write rate limit** — added `POST /api/claw/usage/batch` (up to `MAX_REPORTS_PER_BATCH=500` records) that counts as **one** write, so a busy agent reports many calls without dropping usage.
2. **Public overview uncached / full-scan** — `GET /api/usage/models` now uses the repo's short cache (`token_usage_overview_cache`, 60s TTL, Redis + in-process).
3. **No idempotency** — optional `client_event_id` per report + a `UNIQUE(agent_id, client_event_id)` index; a repeated key returns the stored row (`deduplicated: true`) instead of double-counting.
4. **Rate-limit state leak** — idle agents are pruned from `token_usage_rate_limit_state` once it exceeds `TOKEN_USAGE_RATE_LIMIT_MAX_AGENTS=10000`.
5. **Non-sargable date filter** — bounds now compare the raw `created_at` column (`>= start`, `< day_after(end)`) so the `(agent_id, created_at)` / `(model, created_at)` indexes serve the range; the day bucket still uses `substr`.
6. **Day timezone** — documented as **UTC**; responses now include `"timezone": "UTC"`.

Standards check: ruff clean on all changed files (pre-existing `config.py` E402 untouched); no dependencies added (no `pip-audit` needed).

## Tests
```
tests/test_token_usage.py ......................  22 passed
tests/  (full server suite)                       143 passed, 2 skipped — 0 regressions
```
Run: `cd service/server && python3 -m pytest tests/test_token_usage.py -v`
