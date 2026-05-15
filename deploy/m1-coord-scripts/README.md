# M1 coord scripts

Scripts here are reachable from the coord daemon via the `run_script` action.

Constraints enforced by the daemon:

- Script name must match `^[a-z0-9][a-z0-9-]{0,63}$`
- Resolved path must stay inside `deploy/m1-coord-scripts/`
- 10-minute timeout per script

Add new scripts here, not under arbitrary paths. Anything that needs secrets or
human approval (initial bootstrap, key transfer, prod migrations) must remain
manual — it does not belong here.
