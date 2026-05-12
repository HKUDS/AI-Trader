"""Auto-research subsystem.

Wraps external research backends (currently `last30days`) so the rest of
the server can ask "what do retail traders say about 2330 in the last 30
days?" without owning the social-media fetching, ranking, or LLM-synthesis
plumbing. The wrapper is a thin adapter — degrades gracefully when the
backend is missing or the network is unreachable, so price fetches never
block on research being available.
"""

from .last30days_client import (
    ResearchResult,
    ResearchUnavailableError,
    is_backend_available,
    research,
)

__all__ = [
    "ResearchResult",
    "ResearchUnavailableError",
    "is_backend_available",
    "research",
]
