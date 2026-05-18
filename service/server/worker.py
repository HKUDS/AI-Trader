"""
Standalone background worker for AI-Trader.

Run this separately from the FastAPI process so HTTP requests are not competing
with price refreshes, profit-history compaction, and market-intel snapshots.
"""

import asyncio
import fcntl
import logging
import os
import signal
import sys
from contextlib import suppress

from database import init_database, get_database_status
from tasks import DEFAULT_BACKGROUND_TASKS, _prune_profit_history, start_background_tasks


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _renew_redis_lock(lock, timeout_seconds: int) -> None:
    interval = max(5, timeout_seconds // 3)
    while True:
        await asyncio.sleep(interval)
        try:
            lock.reacquire()
        except Exception as exc:
            logger.error("Lost worker singleton Redis lock: %s", exc)
            os._exit(1)


def _acquire_file_lock():
    lock_path = os.getenv("AI_TRADER_WORKER_LOCK_FILE", "/tmp/ai-trader-worker.lock")
    handle = open(lock_path, "w", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        logger.warning("Another AI-Trader worker is already running; lock_file=%s", lock_path)
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def _release_file_lock(handle) -> None:
    if handle is None:
        return
    with suppress(Exception):
        fcntl.flock(handle, fcntl.LOCK_UN)
    with suppress(Exception):
        handle.close()


async def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)
        except Exception:
            pass
    try:
        os.nice(int(os.getenv("AI_TRADER_WORKER_NICE", "10")))
    except Exception:
        pass

    redis_lock = None
    file_lock_handle = None
    lock_renew_task = None
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signame in ("SIGINT", "SIGTERM"):
        with suppress(Exception):
            loop.add_signal_handler(getattr(signal, signame), stop_event.set)
    tasks: list[asyncio.Task] = []
    try:
        lock_timeout_seconds = max(30, int(os.getenv("AI_TRADER_WORKER_LOCK_TIMEOUT_SECONDS", "120")))
    except Exception:
        lock_timeout_seconds = 120
    try:
        from cache import acquire_lock

        redis_lock = acquire_lock(
            "worker:singleton",
            timeout_seconds=lock_timeout_seconds,
            blocking=False,
        )
        if redis_lock is not None:
            acquired = bool(redis_lock.acquire(blocking=False))
            if not acquired:
                logger.warning("Another AI-Trader worker is already running; Redis singleton lock is held.")
                return
            lock_renew_task = asyncio.create_task(
                _renew_redis_lock(redis_lock, lock_timeout_seconds),
                name="ai-trader:worker_lock_renew",
            )
            logger.info("Acquired worker singleton lock via Redis")
        else:
            file_lock_handle = _acquire_file_lock()
            if file_lock_handle is None:
                return
            logger.info("Acquired worker singleton lock via file")
    except Exception:
        if redis_lock is not None:
            with suppress(Exception):
                redis_lock.release()
        logger.exception("Failed to acquire worker singleton lock")
        return

    try:
        init_database()
        logger.info("Worker database ready: %s", get_database_status())

        if os.getenv("AI_TRADER_BACKGROUND_TASKS") is None:
            os.environ["AI_TRADER_BACKGROUND_TASKS"] = DEFAULT_BACKGROUND_TASKS

        tasks = start_background_tasks(logger)
        if not tasks:
            logger.warning("No background tasks enabled; set AI_TRADER_BACKGROUND_TASKS to a comma-separated task list.")
            return

        if os.getenv("PROFIT_HISTORY_PRUNE_ON_WORKER_START", "false").strip().lower() in {"1", "true", "yes", "on"}:
            logger.info("Scheduling startup profit history prune")
            tasks.append(asyncio.create_task(asyncio.to_thread(_prune_profit_history), name="ai-trader:startup_profit_history_prune"))

        await stop_event.wait()
        logger.info("Worker shutdown requested")
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            with suppress(Exception):
                await asyncio.gather(*tasks, return_exceptions=True)
        if lock_renew_task is not None:
            lock_renew_task.cancel()
            with suppress(asyncio.CancelledError):
                await lock_renew_task
        if redis_lock is not None:
            with suppress(Exception):
                redis_lock.release()
        _release_file_lock(file_lock_handle)


if __name__ == "__main__":
    asyncio.run(main())
