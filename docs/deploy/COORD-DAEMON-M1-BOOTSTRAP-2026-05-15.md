# M1 coord daemon — first-time bootstrap

Owner: Brian. Last touched: 2026-05-15.

Run this once on M1 to enable autonomous dispatch ↔ M1 coord. After this, the
M4 dispatch sandbox can drive M1 through the GitHub-backed queue without any
further human action.

Prereqs already done in the M1 self-host SOP
(`docs/deploy/M1-SELF-HOST-SOP-2026-05-12.md`):
- `git` works against `origin` with push rights to `coord`
- `~/dev/AI-Trader` is the working clone on `main`
- `uv` is on PATH, BW-Trader launchd agents are bootstrapped

## 1. Ensure the `coord` branch exists locally

```bash
cd ~/dev/AI-Trader
git fetch origin coord
git checkout coord            # or: git checkout -B coord origin/coord
```

If the remote branch doesn't exist yet (first ever bootstrap), create it from
`main` and push:

```bash
git checkout -b coord main
mkdir -p .coord/inbox .coord/outbox
touch .coord/inbox/.gitkeep .coord/outbox/.gitkeep
git add .coord
git commit -m "coord: initialize message queue branch"
git push -u origin coord
```

The daemon expects `.coord/inbox/` and `.coord/outbox/` to exist when it runs.

## 2. Verify the daemon runs once manually

Still on M1:

```bash
cd ~/dev/AI-Trader
COORD_REPO_ROOT=$HOME/dev/AI-Trader python3 deploy/coord-daemon/coord_daemon.py --once
```

Expected output: `no inbox tasks` (assuming the queue is empty) and exit 0.
Any traceback here means stop and debug before going further.

## 3. Install the launchd plist

```bash
cp ~/dev/AI-Trader/deploy/launchd/ai.bwstudio.bw-trader-coord-daemon.plist \
   ~/Library/LaunchAgents/ai.bwstudio.bw-trader-coord-daemon.plist

launchctl bootstrap "gui/$(id -u)" \
  ~/Library/LaunchAgents/ai.bwstudio.bw-trader-coord-daemon.plist

launchctl list ai.bwstudio.bw-trader-coord-daemon
```

`launchctl list` should show a PID (briefly, while the one-shot runs) or a
recent last-exit-status. `RunAtLoad=true` + `StartInterval=60` means the daemon
runs once now and again every minute thereafter.

## 4. Tail the log on first tick

```bash
tail -n 50 -f ~/Library/Logs/bw-trader-coord-daemon.out.log
```

Look for lines like `[coord-daemon] 2026-05-15T... no inbox tasks`. If you see
`FATAL:` or a stack trace, the daemon will keep retrying every 60 s — fix the
underlying issue and the next tick will pick up.

## 5. Hand off to dispatch

From dispatch-m4, send a no-op probe:

```bash
python3 deploy/coord-daemon/send_coord_task.py --action git_status
# prints: <task_id>

python3 deploy/coord-daemon/poll_coord_reply.py <task_id> --timeout 240
```

Expected: within ~2 minutes you see `status: "ok"` and the working tree status
echoed in `stdout`. Done.

## Disable / pause

```bash
launchctl bootout "gui/$(id -u)/ai.bwstudio.bw-trader-coord-daemon"
```

(The daemon itself is never asked to do this — only a human at the keyboard.)

## What this bootstrap deliberately does NOT automate

- Secret transfer (`.env`, Cloudflare credentials)
- Initial Cloudflare tunnel creation
- Apple Developer / signing concerns
- First-time `git push` of the `coord` branch (you do this once, above)

These are intentionally kept manual to keep blast radius small. Adding them to
the whitelist requires a security review and an explicit decision.
