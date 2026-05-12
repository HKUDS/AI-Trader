"""Thin Python wrapper around the official Pionex AI Kit MCP server.

Pionex AI Kit (https://github.com/pionex-official/pionex-ai-kit) ships its
trading tools as a TypeScript MCP server published to npm as
`@pionex/pionex-trade-mcp`. There is no Python SDK, so this module owns a
subprocess of `npx -y @pionex/pionex-trade-mcp` and speaks the MCP stdio
JSON-RPC protocol directly.

Why a subprocess rather than reimplementing HMAC in Python:
  * The official MCP server is the single source of truth for Pionex
    request signing and tool shape. We do not fork a stale copy.
  * The server's own `--read-only` flag is a process-level switch that
    disables write tools at the source. We rely on it as the outermost
    red-line lock.

Red-line model (three locks, all must be open before a write reaches Pionex):
  1. `security.assert_paper_only` rejects callers that did not pass
     explicit user consent (`paper=true` semantics inverted: write
     methods require `user_consent=True`).
  2. `config.ALLOW_LIVE_TRADING` must be true at the process level.
  3. The MCP subprocess itself must have been started without
     `--read-only`. The default is read-only.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from typing import Any, Dict, List, Optional, Protocol

import config
from security import assert_paper_only

logger = logging.getLogger(__name__)


JSONRPC_VERSION = "2.0"
DEFAULT_COMMAND = ["npx", "-y", "@pionex/pionex-trade-mcp"]
DEFAULT_READ_TIMEOUT_SECONDS = 30.0


class PionexMCPError(RuntimeError):
    """Raised when the MCP subprocess returns an error envelope or the
    transport reports a protocol-level failure.

    Distinct from `HTTPException(403)` raised by the red-line guard —
    callers can tell whether they hit a Pionex API error vs. a BW-Trader
    policy refusal.
    """


class Transport(Protocol):
    """Minimal duck-type for the MCP stdio transport.

    Implementations send a single JSON-RPC request line and return the
    parsed response. The production implementation is
    `MCPStdioSubprocessTransport`; tests inject a fake.
    """

    def request(self, payload: Dict[str, Any]) -> Dict[str, Any]: ...

    def close(self) -> None: ...


class MCPStdioSubprocessTransport:
    """Owns the lifetime of an MCP server subprocess and its stdio pipes.

    The transport is intentionally minimal: one outstanding request at a
    time, line-delimited JSON. The MCP spec allows more elaborate
    multiplexing but BW-Trader does not need it — Pionex tool calls are
    independent and we call them serially from FastAPI handlers.
    """

    def __init__(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        read_timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS,
    ) -> None:
        self._command = command
        self._env = env
        self._read_timeout = read_timeout_seconds
        self._proc: Optional[subprocess.Popen[str]] = None
        self._lock = threading.Lock()

    def _ensure_started(self) -> subprocess.Popen[str]:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        logger.info("pionex-mcp: spawning subprocess: %s", " ".join(self._command))
        self._proc = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self._env,
            bufsize=1,
        )
        return self._proc

    def request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            proc = self._ensure_started()
            assert proc.stdin is not None and proc.stdout is not None
            try:
                proc.stdin.write(json.dumps(payload) + "\n")
                proc.stdin.flush()
            except BrokenPipeError as exc:
                raise PionexMCPError(
                    f"pionex-mcp subprocess pipe closed before write: {exc}"
                ) from exc

            line = proc.stdout.readline()
            if not line:
                stderr_tail = ""
                if proc.stderr is not None:
                    try:
                        stderr_tail = proc.stderr.read() or ""
                    except Exception:  # pragma: no cover — defensive
                        stderr_tail = ""
                raise PionexMCPError(
                    "pionex-mcp subprocess closed stdout without a response."
                    + (f" stderr: {stderr_tail.strip()}" if stderr_tail else "")
                )
            try:
                return json.loads(line)
            except json.JSONDecodeError as exc:
                raise PionexMCPError(
                    f"pionex-mcp returned non-JSON line: {line!r}"
                ) from exc

    def close(self) -> None:
        with self._lock:
            if self._proc is None:
                return
            if self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None


class PionexMCPClient:
    """High-level wrapper that exposes the Pionex tools BW-Trader cares about.

    The class is safe to construct without any Pionex credentials present;
    only `get_balance` and the write methods require auth, and the wrapper
    returns a `PionexMCPError` rather than crashing at startup.
    """

    def __init__(
        self,
        *,
        transport: Optional[Transport] = None,
        command: Optional[List[str]] = None,
        read_only: Optional[bool] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        if transport is not None:
            self._transport: Transport = transport
            self._owns_transport = False
        else:
            resolved_cmd = list(command) if command else list(self._resolve_command())
            resolved_read_only = (
                read_only
                if read_only is not None
                else _env_truthy("PIONEX_AI_KIT_READ_ONLY", default=True)
            )
            if resolved_read_only and "--read-only" not in resolved_cmd:
                resolved_cmd.append("--read-only")
            resolved_env = self._build_env(env)
            self._transport = MCPStdioSubprocessTransport(resolved_cmd, env=resolved_env)
            self._owns_transport = True

        self._msg_id = 0
        self._initialized = False
        self._server_info: Dict[str, Any] = {}

    @staticmethod
    def _resolve_command() -> List[str]:
        override = os.getenv("PIONEX_AI_KIT_COMMAND", "").strip()
        if override:
            return override.split()
        return list(DEFAULT_COMMAND)

    @staticmethod
    def _build_env(extra: Optional[Dict[str, str]]) -> Dict[str, str]:
        # Carry the parent env through (PATH is needed to find `npx`) but
        # also forward Pionex credentials explicitly so a future refactor
        # that scrubs env still keeps the integration working.
        merged: Dict[str, str] = dict(os.environ)
        for key in ("PIONEX_API_KEY", "PIONEX_API_SECRET", "PIONEX_BASE_URL"):
            value = os.getenv(key)
            if value:
                merged[key] = value
        if extra:
            merged.update(extra)
        return merged

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "id": self._next_id(),
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        response = self._transport.request(payload)
        if "error" in response and response["error"]:
            err = response["error"]
            raise PionexMCPError(
                f"pionex-mcp rpc error ({method}): "
                f"{err.get('code')} {err.get('message', '')}"
            )
        return response.get("result", {}) or {}

    def initialize(self) -> Dict[str, Any]:
        if self._initialized:
            return self._server_info
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "bw-trader", "version": "0.1.0"},
                "capabilities": {},
            },
        )
        self._server_info = result
        self._initialized = True
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        self.initialize()
        result = self._rpc("tools/list")
        return list(result.get("tools", []))

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.initialize()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            structured = result.get("structuredContent") or {}
            raise PionexMCPError(
                f"pionex tool {name} returned error: "
                f"{structured.get('code') or 'UNKNOWN'} "
                f"{structured.get('message') or result.get('content')}"
            )
        structured = result.get("structuredContent") or {}
        # The MCP server wraps payloads as {tool, ok, data, capabilities, ts}.
        if isinstance(structured, dict) and "data" in structured:
            return structured["data"]
        return structured

    # -- Read-only convenience -------------------------------------------------

    def get_klines(self, symbol: str, *, interval: str = "1D", limit: int = 200) -> Any:
        return self.call_tool(
            "pionex_market_get_klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )

    def get_depth(self, symbol: str, *, limit: int = 20) -> Any:
        return self.call_tool(
            "pionex_market_get_depth",
            {"symbol": symbol, "limit": limit},
        )

    def get_tickers(self) -> Any:
        return self.call_tool("pionex_market_get_tickers", {})

    def get_book_tickers(self) -> Any:
        return self.call_tool("pionex_market_get_book_tickers", {})

    def get_balance(self) -> Any:
        """Read-only but requires auth — returns the spot account balance."""
        return self.call_tool("pionex_account_get_balance", {})

    # -- Write surface (red line) ---------------------------------------------

    def new_order(
        self,
        payload: Dict[str, Any],
        *,
        user_consent: bool = False,
    ) -> Any:
        """Place a spot order on Pionex.

        Three locks must all be open for the call to reach the exchange:
          1. `user_consent=True` (this method's keyword).
          2. `config.ALLOW_LIVE_TRADING` set to true at process level.
          3. The MCP subprocess started without `--read-only`.

        Without any one of (1) or (2) the call raises HTTPException(403)
        via `assert_paper_only`. Without (3) the upstream MCP server
        itself refuses the tool call.
        """
        # Lock 1: explicit user consent. The keyword default refuses by
        # design — a caller must opt in, the way the rest of the codebase
        # treats `paper=true` as the safe default.
        assert_paper_only({"paper": user_consent})

        # Lock 2: process-level kill switch. Belt-and-suspenders: even if
        # a caller passes `user_consent=True`, the deploy config still has
        # final say.
        if not config.ALLOW_LIVE_TRADING:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Live trading disabled at process level "
                    "(ALLOW_LIVE_TRADING=false). Server policy refuses to "
                    "forward orders even with explicit user consent."
                ),
            )

        return self.call_tool("pionex_orders_new_order", payload)

    # -- Lifecycle -------------------------------------------------------------

    def close(self) -> None:
        if self._owns_transport:
            self._transport.close()


def _env_truthy(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
