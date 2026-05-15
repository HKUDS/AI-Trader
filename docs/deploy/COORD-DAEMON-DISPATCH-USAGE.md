# Dispatch-side coord daemon usage

Owner: Brian. Last touched: 2026-05-15.

This is how the M4 dispatch sandbox drives M1 once the coord daemon is live.

## Prereqs in the dispatch shell

- cwd is inside a working clone of `as84089443/AI-Trader`
- `origin` is the fork with push rights
- `coord` branch already exists on origin (M1 bootstrap step 1 done)

The helpers do not modify the dispatch's current branch — they use a temporary
git worktree to write the inbox file, push, and clean up.

## Queue a task

```bash
python3 deploy/coord-daemon/send_coord_task.py \
  --action health_check \
  --params '{"url": "http://127.0.0.1:8788/api/health"}'
```

Stdout is a single UUID — the task id. Capture it:

```bash
task_id=$(python3 deploy/coord-daemon/send_coord_task.py --action git_status)
echo "$task_id"
```

## Wait for the reply

```bash
python3 deploy/coord-daemon/poll_coord_reply.py "$task_id" --timeout 240
```

Exit codes:
- `0` — reply found, status `ok`
- `3` — reply found, status `denied` / `fail` / `timeout`
- `4` — no reply within `--timeout`

The reply JSON is printed to stdout on exit 0 or 3.

## Common actions

```bash
# Pull the latest main on M1
send_coord_task.py --action git_pull

# Re-install Python deps on M1
send_coord_task.py --action uv_pip_install

# Kick the API service
send_coord_task.py --action launchctl_kickstart \
  --params '{"label": "ai.bwstudio.bw-trader-api"}'

# Public health probe (must end in bw-space.com)
send_coord_task.py --action health_check \
  --params '{"url": "https://bw-trader-api.bw-space.com/health"}'

# Full redeploy via canonical script
send_coord_task.py --action run_script \
  --params '{"name": "m1-redeploy"}'

# Full local + public health sweep
send_coord_task.py --action run_script \
  --params '{"name": "health-all"}'
```

## What dispatch CANNOT do via the queue

Anything not in the whitelist. If you try, you get back `status: denied` and a
`stderr` explaining why. Notably:

- No arbitrary shell — there is no `run_command` action
- No `git push --force`, no `reset --hard`
- No `launchctl bootout` / `unload`
- No `run_script` outside `deploy/m1-coord-scripts/`
- No `health_check` against arbitrary URLs

If you need a new capability, add it to `deploy/coord-daemon/whitelist.py` in a
reviewed PR — do not try to smuggle commands through existing actions.

## Failure handling

- `denied` — the dispatch is wrong (typo, bad params, expired). Fix locally.
- `fail` — the action ran but the underlying command exited non-zero. Read
  `stderr` for the cause; treat like any production failure.
- `timeout` — action exceeded its whitelist timeout. Means something on M1 is
  stuck (typically deps install or git pull on a flaky link).
- No reply at all — daemon may be down. Sit-rep:
  - Brian SSH into M1 directly
  - `launchctl list ai.bwstudio.bw-trader-coord-daemon`
  - `tail ~/Library/Logs/bw-trader-coord-daemon.err.log`

## Auditability

Every task and every reply is a git commit on the `coord` branch. The full
history of M4↔M1 coord lives in `git log coord`. Don't squash this branch.
