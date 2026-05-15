# Coord daemon protocol

Status: scaffold, not yet running on M1 (see bootstrap SOP).
Owner: Brian. Last touched: 2026-05-15.

## What this is

A GitHub-backed message queue between the M4 dispatch sandbox (which cannot SSH
into M1 or reach the Tailnet) and the M1 mac mini (which runs the BW-Trader
services). All transport is `git push` / `git pull` against this fork; the M1
side runs a launchd-driven daemon that polls every 60 s.

```
  dispatch-m4                   github.com/as84089443/AI-Trader               M1 daemon
  ───────────                   ──────────────────────────────                ─────────
  send_coord_task.py  ──push──▶  coord branch  .coord/inbox/<id>.json
                                                  │
                                                  ▼ (60s tick)
                                              fetch + read
                                                  │
                                                  ▼
                                            execute via whitelist
                                                  │
                                                  ▼ commit + push
  poll_coord_reply.py ◀─fetch──   coord branch  .coord/outbox/<id>.json
```

Latency floor: ~60 seconds (StartInterval). Real round trip: 1–3 minutes
including push propagation.

## Channels

Branch: `coord`, separate from `main`. Never merges into main.

Layout on the `coord` branch:

```
.coord/
  README.md        ← short pointer to this doc
  inbox/           ← dispatch writes tasks here
    <task_id>.json
  outbox/          ← M1 writes replies here
    <task_id>.json
```

## Inbox task schema

```json
{
  "task_id":   "uuid v4",
  "timestamp": "2026-05-15T14:00:00Z",
  "expires_at":"2026-05-15T14:30:00Z",
  "from":      "dispatch-m4",
  "to":        "m1",
  "action":    "git_pull",
  "params":    {},
  "nonce":     "random hex"
}
```

Required: `task_id`, `from`, `to`, `action`, `nonce` (non-empty strings).
`to` must equal `"m1"`. `params` may be omitted or `{}`. Expired tasks are
written as `denied` replies.

## Outbox reply schema

```json
{
  "task_id":      "...",
  "action":       "git_pull",
  "ack_at":       "2026-05-15T14:00:30Z",
  "completed_at": "2026-05-15T14:00:35Z",
  "exit_code":    0,
  "stdout":       "...truncated to 8 KiB...",
  "stderr":       "...truncated to 8 KiB...",
  "status":       "ok|fail|timeout|denied"
}
```

`status` mapping:
- `ok` — exit_code 0
- `fail` — exit_code != 0
- `timeout` — action exceeded its whitelist timeout
- `denied` — schema invalid, action unknown, or params failed validation

## Whitelist

Source of truth: `deploy/coord-daemon/whitelist.py`. Current actions:

| action | params | what it does | timeout |
|---|---|---|---|
| `git_pull` | none | `git pull --ff-only origin main` | 60s |
| `git_status` | none | `git status --short` | 10s |
| `uv_pip_install` | none | `uv pip install -r service/requirements.txt` | 300s |
| `launchctl_kickstart` | `{label}` | `launchctl kickstart -k gui/<uid>/<label>` (label must start `ai.bwstudio.`) | 30s |
| `launchctl_bootstrap` | `{plist_path}` | `launchctl bootstrap gui/<uid> <plist>` (path under `~/Library/LaunchAgents/ai.bwstudio.*`) | 30s |
| `launchctl_list` | `{label}` | `launchctl list <label>` | 10s |
| `health_check` | `{url}` | `curl -fsS -m 10 <url>` (loopback or `*.bw-space.com` only) | 15s |
| `run_script` | `{name}` | runs `deploy/m1-coord-scripts/<name>.sh` (slug-only) | 600s |

## Hard limits (do not relax without security review)

- No arbitrary shell command. Every action is a fixed argv builder; user input
  never reaches a shell.
- No destructive git (`push --force`, `reset --hard`, `clean -fdx`).
- No `launchctl bootout` / `unload`.
- `run_script` resolves to a real-path check that must stay inside
  `deploy/m1-coord-scripts/`.
- Secrets never echo into `stdout` — they live in env vars on M1; the daemon
  captures stdout/stderr but the whitelist commands do not print env contents.
- All stdout/stderr truncated to 8 KiB.

## Failure modes

- **Push race**: two consecutive runs both try to push. The second loses; its
  reply file already exists in the worktree but didn't make it upstream — the
  next tick will rediscover (or, more likely, the inbox file was deleted and
  the reply lingers locally until the next tick pushes it).
- **Daemon crash**: launchd respawns next minute. fail-loud logging goes to
  `~/Library/Logs/bw-trader-coord-daemon.err.log`.
- **Network outage**: `git fetch` returns non-zero; daemon logs and exits.
  Next tick retries.
- **Tunnel down**: `health_check` returns curl exit 22/28; status `fail`,
  stderr captured. Dispatch sees the failure and can escalate.

## Operational entry points

- Dispatch-side: `deploy/coord-daemon/send_coord_task.py`,
  `deploy/coord-daemon/poll_coord_reply.py`.
- M1-side: launchd label `ai.bwstudio.bw-trader-coord-daemon`, plist in
  `deploy/launchd/`.
- First-time M1 bootstrap: `docs/deploy/COORD-DAEMON-M1-BOOTSTRAP-2026-05-15.md`.
- Dispatch usage: `docs/deploy/COORD-DAEMON-DISPATCH-USAGE.md`.
