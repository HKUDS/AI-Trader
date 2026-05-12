"""Adapter for the `last30days` research skill.

`last30days` ships as a Claude Code skill at
``~/.claude/plugins/marketplaces/last30days-skill/skills/last30days/scripts/last30days.py``.
It exposes a Python CLI that researches a topic across Reddit, Hacker News,
Polymarket, X, YouTube, TikTok, and a few other sources, returning a JSON
synthesis with citations.

This module shells out to that CLI rather than importing it directly: the
skill pins its own Python version (3.12+) and dependency tree, so coupling
the trader's `requirements.txt` to it would be fragile. Subprocess gives us
process isolation and lets us cap the call with a hard timeout.

Public surface is intentionally narrow:
  - `is_backend_available()` for a quick health probe (used by the
    `/api/market-intel/research/{symbol}` route to short-circuit when the
    skill isn't installed).
  - `research(topic, ...)` to actually run a query. Always returns a
    `ResearchResult` (never raises on a fetch failure) — the `status`
    field carries the error so callers can branch without exception
    handling.

The wrapper has zero behaviour tests against the live last30days CLI in
CI: we depend on `subprocess.run` returning a JSON blob, and we exercise
the parsing / failure paths against a fake binary in the unit tests.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ResearchUnavailableError(RuntimeError):
    """Raised only by `is_backend_available` callers that want to fail loud.

    The default `research()` flow never raises this — it folds availability
    into the `ResearchResult.status` field so cache writers can store a
    degraded-mode marker instead of bubbling.
    """


@dataclass
class ResearchResult:
    """Normalised return value from a research call.

    `status`:
      - "ok"            → synthesis populated, sources counted
      - "unavailable"   → backend not installed / no API key / degraded path
      - "timeout"       → subprocess hit the timeout cap
      - "error"         → backend ran but emitted invalid output

    `synthesis` is a short, citation-laced markdown string. `raw` carries
    whatever the backend returned in full so future callers can extract
    richer fields without reshaping the wrapper.
    """

    status: str
    topic: str
    synthesis: str = ""
    sources: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    raw: Optional[dict] = None

    def to_cache_payload(self) -> dict:
        """Cache-friendly representation. Drops the raw blob to keep TTL
        rows under typical Redis value limits."""
        payload = asdict(self)
        payload.pop("raw", None)
        return payload


# Discovery: the skill ships under either the marketplace cache or a user
# install directory. Probe both. The env var override is for tests and for
# operators who pin a vendored copy.
_DEFAULT_SKILL_PATHS = (
    Path.home() / ".claude/plugins/marketplaces/last30days-skill/skills/last30days/scripts/last30days.py",
    Path.home() / ".claude/plugins/cache/last30days-skill/skills/last30days/scripts/last30days.py",
    Path.home() / ".claude/skills/last30days/scripts/last30days.py",
)


def _resolve_skill_entrypoint() -> Optional[Path]:
    override = os.environ.get("LAST30DAYS_SCRIPT")
    if override:
        p = Path(override)
        return p if p.exists() else None
    for candidate in _DEFAULT_SKILL_PATHS:
        if candidate.exists():
            return candidate
    return None


def _resolve_python() -> str:
    """Pick a Python the skill can run under.

    The skill requires 3.12+, so we prefer `python3.12` / `python3.13`
    explicitly. Falls back to whatever `python3` resolves to — the skill
    will error loudly if that's too old, which is the behaviour we want
    (better than silent degraded mode for a misconfigured host).
    """
    explicit = os.environ.get("LAST30DAYS_PYTHON")
    if explicit:
        return explicit
    for candidate in ("python3.13", "python3.12", "python3"):
        path = shutil.which(candidate)
        if path:
            return path
    return "python3"


def is_backend_available() -> bool:
    """Cheap probe — does the skill script exist on disk?

    We don't actually run the script to verify (would cost a Python startup
    on every call). The downside is that a corrupted install will only be
    caught when `research()` is called and the subprocess fails.
    """
    return _resolve_skill_entrypoint() is not None


def research(
    topic: str,
    *,
    sources: Optional[list[str]] = None,
    deep: bool = False,
    timeout_seconds: float = 60.0,
) -> ResearchResult:
    """Run a single research query and return a normalised result.

    Never raises on backend failure — caller branches on `result.status`.
    The contract holds even when last30days isn't installed (returns
    `status="unavailable"`), so callers can wire this into a market-data
    pipeline without a surrounding try/except.
    """
    script = _resolve_skill_entrypoint()
    if script is None:
        logger.info("last30days not installed; returning unavailable result for %s", topic)
        return ResearchResult(
            status="unavailable",
            topic=topic,
            error="last30days skill not installed",
        )

    cmd: list[str] = [_resolve_python(), str(script), topic, "--emit", "json"]
    if sources:
        cmd.extend(["--search", ",".join(sources)])
    if deep and os.environ.get("OPENROUTER_API_KEY"):
        # Deep mode is gated on OpenRouter access — without an API key the
        # backend errors at startup, so we silently downgrade.
        cmd.append("--deep-research")
    elif deep:
        logger.info(
            "research(deep=True) requested but OPENROUTER_API_KEY not set; "
            "running standard retrieval instead"
        )

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("last30days timed out for topic=%s", topic)
        return ResearchResult(status="timeout", topic=topic, error="subprocess timed out")
    except OSError as exc:
        logger.warning("last30days exec failed for topic=%s: %s", topic, exc)
        return ResearchResult(status="unavailable", topic=topic, error=str(exc))

    if proc.returncode != 0:
        # Skill exited non-zero — captured stderr is the most useful error.
        snippet = (proc.stderr or proc.stdout or "")[:500]
        return ResearchResult(status="error", topic=topic, error=snippet)

    return _parse_emit_json(topic, proc.stdout)


def _parse_emit_json(topic: str, stdout: str) -> ResearchResult:
    """Pull synthesis + sources out of `--emit json` output.

    The exact shape is intentionally tolerated — different last30days
    versions add or rename fields, and the wrapper should be liberal in
    what it accepts so a benign skill upgrade doesn't break the trader.
    """
    if not stdout.strip():
        return ResearchResult(status="error", topic=topic, error="empty output")
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return ResearchResult(
            status="error",
            topic=topic,
            error=f"invalid JSON: {exc}",
            synthesis=stdout[:500],
        )

    synthesis = (
        data.get("synthesis")
        or data.get("summary")
        or data.get("answer")
        or ""
    )
    sources_field = data.get("sources") or data.get("citations") or data.get("results") or []
    if not isinstance(sources_field, list):
        sources_field = []

    return ResearchResult(
        status="ok",
        topic=topic,
        synthesis=str(synthesis),
        sources=[s for s in sources_field if isinstance(s, dict)],
        raw=data if isinstance(data, dict) else None,
    )
