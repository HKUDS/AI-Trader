"""
Standalone background worker for AI-Trader.

Run this separately from the FastAPI process so HTTP requests are not competing
with price refreshes, profit-history compaction, and market-intel snapshots.
"""

import asyncio
import logging
import os

from database import init_database, get_database_status
from tasks import DEFAULT_BACKGROUND_TASKS, _prune_profit_history, start_background_tasks


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    init_database()
    logger.info("Worker database ready: %s", get_database_status())

    if os.getenv("AI_TRADER_BACKGROUND_TASKS") is None:
        os.environ["AI_TRADER_BACKGROUND_TASKS"] = DEFAULT_BACKGROUND_TASKS

    if os.getenv("PROFIT_HISTORY_PRUNE_ON_WORKER_START", "true").strip().lower() in {"1", "true", "yes", "on"}:
        await asyncio.to_thread(_prune_profit_history)

    tasks = start_background_tasks(logger)
    if not tasks:
        logger.warning("No background tasks enabled; set AI_TRADER_BACKGROUND_TASKS to a comma-separated task list.")
        return

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
