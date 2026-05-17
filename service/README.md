# AI-Trader Server - Private Implementation

This directory contains the proprietary server implementation for AI-Trader.

## Contents

- `main.py` - Full FastAPI backend implementation

## Database backends

AI-Trader supports two database backends, selected by environment variable:

- **SQLite (default for local development)** — used when `DATABASE_URL` is empty.
  The database file path comes from `DB_PATH` (default:
  `service/server/data/clawtrader.db`).
- **PostgreSQL (recommended for Docker / production)** — used when
  `DATABASE_URL` is set. When `DATABASE_URL` is set it takes precedence over
  `DB_PATH`.

Example for local SQLite development (the default, no extra setup required):

```
# .env
DATABASE_URL=
DB_PATH=service/server/data/clawtrader.db
```

Example for PostgreSQL (Docker / production):

```
# .env
DATABASE_URL=postgresql://ai_trader:change-me@127.0.0.1:5432/ai_trader
```

## Deployment

See deployment documentation for production setup.
