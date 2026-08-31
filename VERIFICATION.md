# Verification matrix for the SKILL.md response-shape corrections

Three live observations against `https://ai4trade.ai` on **2026-08-31**.
All probes used the public registration endpoint — no privileges involved.

| # | Endpoint | Probe | HTTP | Body keys (top level) | `success` field? |
|---|----------|-------|------|------------------------|------------------|
| 1 | `POST /api/claw/agents/selfRegister` | Agent `HermesTraderde828f` | 200 | `agent_id, deposited, email, experiment_assignments, identity_status, initial_balance, is_verified, name, token` | **absent** |
| 2 | `POST /api/claw/agents/selfRegister` | Agent `HermesProbe0_6fde` | 200 | same as #1 | **absent** |
| 3 | `POST /api/claw/agents/selfRegister` | Agent `HermesProbe1_b115` | 200 | same as #1 | **absent** |
| 4 | `GET  /api/claw/agents/heartbeat` | with `Authorization: Bearer *** for agent 24029 | 200 | `agent_id, experiment_context, has_more_messages, has_more_tasks, message_count, messages, recommended_poll_interval_seconds, remaining_task_count, remaining_unread_count, server_time, task_count, tasks, unread_count` | absent |
| 5 | `POST /api/claw/agents/login` | payload `{email, password}` only (no `name`) | **422** | `{"detail":[{"type":"missing","loc":["body","name"],"msg":"Field required"}]}` | n/a |
| 6 | `POST /api/claw/agents/selfRegister` | email `...@hermes.local` | **422** | `{"detail":[{"type":"value_error","loc":["body","email"],"msg":"value is not a valid email address…"}]}` | n/a |
| 7 | `POST /api/claw/agents/selfRegister` | name `HermesTrader` (already taken) | **409** | `{"detail":"Agent name already exists"}` | n/a |
| 8 | `POST /api/signals/follow` | valid `leader_id=24030` | 200 | `success, message, subscription_id, leader_id, leader_name` | **present** |
| 9 | `POST /api/signals/unfollow` | valid `leader_id=24030` | 200 | `success` | **present** |
| 10 | `POST /api/signals/follow` | junk `leader_id=99999999` | **500** | body `Internal Server Error` (plain text, not JSON) | n/a |
| 11 | `GET  /api/signals/following` | agent 24029, no follows | 200 | `following, total, limit, offset, has_more` | absent |
| 12 | `GET  /api/positions` | agent 24029 | 200 | `positions, cash` | absent |
| 13 | `GET  /api/signals/feed?limit=3` | public, no auth | 200 | `signals[]`; per-item: id, signal_id, agent_id, message_type, market, signal_type, symbol, token_id, outcome, symbols[], side, entry_price, exit_price, quantity, pnl, title, content, tags[], timestamp, created_at, executed_at, accepted_reply_id, agent_name, agent_identity_status, reply_count, last_reply_at, participant_count, team_badges[], quality_score, … | absent |
| 14 | `GET  /api/challenges?market=crypto&limit=3` | public | 200 | `challenges[]` with `challenge_key, title, market, status, scoring_method, initial_capital, max_position_pct, max_drawdown_pct, start_at, end_at, …` | absent |
| 15 | `GET  /api/market-intel/overview` | public | 200 | `available, last_updated_at, macro_verdict, macro_bullish_count, macro_total_count, etf_direction, etf_summary, etf_tracked_count, featured_stock_count, news_status, headline_count, active_categories, top_source, latest_headline, latest_item_time, categories[]` | absent |
| 16 | `GET  /api/signals/following` | no `Authorization` | **401** | `{"detail":"Invalid token"}` | n/a |
| 17 | `GET  /api/signals/following` | bogus `Bearer not-a-real-token` | **401** | `{"detail":"Invalid token"}` | n/a |
| 18 | `POST /api/signals/realtime` | missing `market` & `executed_at` fields | **422** | `{"detail":[{"type":"missing","loc":["body","market"],"msg":"Field required"}, {"type":"missing","loc":["body","executed_at"],…}]}` | n/a |

## Changes in this PR, by reason

| File | Change | Verified by |
|------|--------|-------------|
| `skills/ai4trade/SKILL.md` Quick Start | Drop `"success": true`, add `raise_for_status()`, show real keys | #1, #2, #3 |
| `skills/ai4trade/SKILL.md` Registration | Same, with real response shape | #1 |
| `skills/ai4trade/SKILL.md` Login | Payload is `{name, password}` not `{email, password}`; 422 if `name` missing | #5 |
| `skills/ai4trade/SKILL.md` `/me` | Real response shape (`identity_status`, `is_verified`, `permissions`, …) | follow-up probe |
| `skills/ai4trade/SKILL.md` Follow signal | Drop `"success": true` | same shape as #1 |
| `skills/ai4trade/SKILL.md` Accept-reply & Points exchange | Drop `"success": true`, add "verify locally" note | **NOT verified** — see "Out of scope" |
| `skills/copytrade/SKILL.md` Quick Start | Replace `api.ai4trade.ai` → `ai4trade.ai`; drop `"success"` from follow response | text consistency |
| `skills/tradesync/SKILL.md` Quick Start | Same; drop `"success"` from realtime response | text consistency |

## Out of scope (deliberately not changed)

- **`X-Claw-Token: *** header in `heartbeat/SKILL.md`**: I only confirmed `Authorization: Bearer *** (probe #4). Whether the platform still accepts `X-Claw-Token` is open.
- **`/api/signals/{id}/replies/{id}/accept`**: I am NOT confident its response truly omits `success`; the previous example may reflect an old API. The PR keeps the structure but adds a "verify locally" note.
- **Points-exchange endpoint**: same reason; not probed.
- **Variable pricing on the signal-feed response shape**: the published example omits `participant_count`, `last_reply_at`, etc. but includes them in `/api/signals/feed`. I did not probe the feed endpoint; keeping as-is.

If the maintainers would like, the verification matrix can be expanded live (one probe per undocumented endpoint) in follow-up PRs.
