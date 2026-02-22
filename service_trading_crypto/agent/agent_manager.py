"""
AgentManager: 从 IndicatorManager 的 output_queue 读取 SnapshotProcessedV1，
构建 prompt、调用模型进行分析，将 SnapshotProcessedV2 写入 output_queue。
"""

import logging
import threading
import time

from queue import Empty, Queue
from typing import Any, Dict, Literal, Optional
from service_trading_crypto.indicators import MarketSnapshot, SnapshotProcessedV1, SnapshotProcessedV2
from service_trading_crypto.agent.data.agent_result import hold_result
from service_trading_crypto.agent.prompt.realtime_prompt import get_realtime_system_prompt

logger = logging.getLogger(__name__)

AgentType = Literal["default", "llm"]


class AgentManager:
    """
    从 input_queue（IndicatorManager 的 output_queue）读取 SnapshotProcessedV1，
    解析为快照 -> 构建 prompt -> 调用模型 -> 输出分析结果 SnapshotProcessedV2 到 output_queue。
    """

    def __init__(
        self,
        input_queue: Queue,
        output_queue: Optional[Queue] = None,
        agent_type: AgentType = "default",
        symbol: str = "BTC-USDT",
        trigger_interval_seconds: float = 60.0,
        trigger_on_candle: bool = True,
        model_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.input_queue = input_queue
        self.output_queue = output_queue or Queue()
        self.agent_type = agent_type
        self.symbol = symbol
        self.trigger_interval_seconds = max(0.1, trigger_interval_seconds)
        self.trigger_on_candle = trigger_on_candle
        self.model_config = model_config or {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_snapshot: Optional[SnapshotProcessedV1] = None

    def _unwrap_single(self, snap: SnapshotProcessedV1) -> MarketSnapshot:
        """将 SnapshotProcessedV1 转为单个 MarketSnapshot（单 channel 取唯一，多 channel 取最后一个）。"""
        if not snap.compose_snapshot:
            raise ValueError("SnapshotProcessedV1 has empty compose_snapshot")
        if len(snap.compose_snapshot) == 1:
            return next(iter(snap.compose_snapshot.values()))
        return next(reversed(snap.compose_snapshot.values()))

    def _build_prompt(self, snapshot: MarketSnapshot) -> str:
        """根据 MarketSnapshot 构建给模型的 prompt。"""
        positions: Dict[str, float] = self.model_config.get("positions") or {}
        return get_realtime_system_prompt(
            ts=snapshot.ts,
            symbol=self.symbol,
            open_=snapshot.open,
            high=snapshot.high,
            low=snapshot.low,
            close=snapshot.close,
            volume=snapshot.volume,
            indicators=snapshot.indicators,
            positions=positions,
        )

    def _run_model(self, prompt: str, snapshot: MarketSnapshot) -> Dict[str, Any]:
        """
        调用模型进行分析。default：仅打日志并返回 hold；llm：使用 model_config 中的 OpenAI 兼容 API 调 LLM。
        返回的 dict 含 action、reason、snapshot_ts、confidence、metadata。
        """
        if self.agent_type == "llm":
            try:
                raw = self._invoke_llm(prompt, snapshot.ts)
                return self._normalize_agent_result(raw, snapshot.ts)
            except Exception as e:
                logger.exception("LLM agent error: %s", e)
                return self._default_result(snapshot)
        return self._default_result(snapshot)

    def _invoke_llm(self, prompt: str, snapshot_ts: str) -> Dict[str, Any]:
        """使用 model_config（openai_base_url、openai_api_key、basemodel）调用 OpenAI 兼容接口。"""
        try:
            from openai import OpenAI
            base_url = self.model_config.get("openai_base_url") or "https://api.deepseek.com"
            api_key = self.model_config.get("openai_api_key") or ""
            model = self.model_config.get("basemodel", "deepseek-chat")
            client = OpenAI(base_url=base_url, api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            text = (resp.choices[0].message.content or "").strip()
            return self._parse_llm_response(text, snapshot_ts)
        except Exception as e:
            logger.exception("LLM invoke error: %s", e)
            return {"action": "hold", "reason": f"llm_error:{e}", "snapshot_ts": snapshot_ts, "confidence": 0.0, "metadata": {}}

    def _parse_llm_response(self, text: str, snapshot_ts: str) -> Dict[str, Any]:
        """从模型回复文本解析出 action/reason 等。"""
        t = text.lower()
        if "buy" in t or "long" in t:
            action = "buy"
        elif "sell" in t or "short" in t:
            action = "sell"
        else:
            action = "hold"
        return {
            "action": action,
            "reason": text[:500] if text else "no_content",
            "snapshot_ts": snapshot_ts,
            "confidence": 0.5,
            "metadata": {"raw_preview": text[:200]},
        }

    def _normalize_agent_result(self, raw: Dict[str, Any], snapshot_ts: str) -> Dict[str, Any]:
        """确保 agent 返回的 dict 至少包含 action、reason、snapshot_ts，兼容 AgentResult。"""
        return {
            "action": raw.get("action", "hold"),
            "reason": raw.get("reason", ""),
            "snapshot_ts": raw.get("snapshot_ts", snapshot_ts),
            "confidence": raw.get("confidence", 0.0),
            "metadata": raw.get("metadata", {}),
        }

    def _default_result(self, snapshot: MarketSnapshot) -> Dict[str, Any]:
        """Default 模式：打日志并返回 hold。"""
        logger.info(
            "Agent snapshot: ts=%s close=%.2f indicators=%s",
            snapshot.ts,
            snapshot.close,
            list(snapshot.indicators.keys()),
        )
        return hold_result(snapshot.ts, reason="default")

    def _analyze(self, snap: SnapshotProcessedV1) -> Dict[str, Any]:
        """对 SnapshotProcessedV1 进行分析：unwrap -> 构建 prompt -> 调用模型。"""
        snapshot = self._unwrap_single(snap)
        prompt = self._build_prompt(snapshot)
        logger.debug("Prompt length: %d chars", len(prompt))
        return self._run_model(prompt, snapshot)

    def _run_loop(self) -> None:
        last_trigger_time = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            while True:
                try:
                    snap = self.input_queue.get(timeout=0.2)
                    if not isinstance(snap, SnapshotProcessedV1):
                        continue
                    self._last_snapshot = snap
                    if self.trigger_on_candle:
                        try:
                            # result = self._analyze(snap)
                            # self.output_queue.put_nowait(
                            #     SnapshotProcessedV2(snapshot_processed=snap, agent_result=result or {})
                            # )

                            self.output_queue.put_nowait(
                                SnapshotProcessedV2(snapshot_processed_v1=snap, agent_result={})
                            )
                        except Exception as e:
                            logger.exception("Agent analyze error: %s", e)
                except Empty:
                    break

            if now - last_trigger_time >= self.trigger_interval_seconds and self._last_snapshot is not None:
                last_trigger_time = now
                try:
                    # result = self._analyze(self._last_snapshot)
                    # self.output_queue.put_nowait(
                    #     SnapshotProcessedV2(
                    #         snapshot_processed=self._last_snapshot, agent_result=result or {},
                    #     )
                    # )
                    self.output_queue.put_nowait(
                        SnapshotProcessedV2(
                            snapshot_processed_v1=self._last_snapshot, agent_result={},
                        )
                    )
                except Exception as e:
                    logger.exception("Agent interval analyze error: %s", e)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(
            "AgentManager started: agent_type=%s symbol=%s interval=%.1fs on_candle=%s",
            self.agent_type,
            self.symbol,
            self.trigger_interval_seconds,
            self.trigger_on_candle,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._thread = None
        logger.info("AgentManager stopped")
