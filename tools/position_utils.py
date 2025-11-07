import os
import sys
import fcntl
import json
from pathlib import Path
from typing import Dict, Tuple

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.general_tools import get_config_value


def get_position_lock(signature: str):
    """Context manager for file-based lock to serialize position updates per signature."""
    class _Lock:
        def __init__(self, name: str):
            base_dir = Path(project_root) / "data" / "agent_data" / name
            base_dir.mkdir(parents=True, exist_ok=True)
            self.lock_path = base_dir / ".position.lock"
            # Ensure lock file exists
            self._fh = open(self.lock_path, "a+")
        def __enter__(self):
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
            return self
        def __exit__(self, exc_type, exc, tb):
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()
    return _Lock(signature)


def get_latest_position(today_date: str, signature: str) -> Tuple[Dict[str, float], int]:
    """
    获取最新持仓。从 ../data/agent_data/{signature}/position/position.jsonl 中读取。
    优先选择当天 (today_date) 中 id 最大的记录；
    若当天无记录，则回退到上一个交易日，选择该日中 id 最大的记录。

    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。
        signature: 模型名称，用于构建文件路径。

    Returns:
        (positions, max_id):
          - positions: {symbol: weight} 的字典；若未找到任何记录，则为空字典。
          - max_id: 选中记录的最大 id；若未找到任何记录，则为 -1.
    """
    from tools.price_tools import get_market_type, get_yesterday_date

    base_dir = Path(__file__).resolve().parents[1]

    # Get log_path from config, default to "agent_data" for backward compatibility
    log_path = get_config_value("LOG_PATH", "./data/agent_data")

    # Handle different path formats:
    # - If it's an absolute path (like temp directory), use it directly
    # - If it's a relative path starting with "./data/", remove the prefix and prepend base_dir/data
    # - Otherwise, treat as relative to base_dir/data
    if os.path.isabs(log_path):
        # Absolute path (like temp directory) - use directly
        position_file = Path(log_path) / signature / "position" / "position.jsonl"
    else:
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix
        position_file = base_dir / "data" / log_path / signature / "position" / "position.jsonl"

    if not position_file.exists():
        return {}, -1

    # 获取市场类型，智能判断
    market = get_market_type()

    # Step 1: 先查找当天的记录
    max_id_today = -1
    latest_positions_today: Dict[str, float] = {}

    with position_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                if doc.get("date") == today_date:
                    current_id = doc.get("id", -1)
                    if current_id > max_id_today:
                        max_id_today = current_id
                        latest_positions_today = doc.get("positions", {})
            except Exception:
                continue

    # 如果当天有记录，直接返回
    if max_id_today >= 0 and latest_positions_today:
        return latest_positions_today, max_id_today

    # Step 2: 当天没有记录，则回退到上一个交易日
    prev_date = get_yesterday_date(today_date, market=market)

    max_id_prev = -1
    latest_positions_prev: Dict[str, float] = {}

    with position_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                if doc.get("date") == prev_date:
                    current_id = doc.get("id", -1)
                    if current_id > max_id_prev:
                        max_id_prev = current_id
                        latest_positions_prev = doc.get("positions", {})
            except Exception:
                continue

    # 如果前一天也没有记录，尝试找文件中最新的记录（按日期和id排序）
    if max_id_prev < 0 or not latest_positions_prev:
        all_records = []
        with position_file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    doc = json.loads(line)
                    if doc.get("date") and doc.get("date") < today_date:
                        all_records.append(doc)
                except Exception:
                    continue

        if all_records:
            # 按日期和id排序，取最新的一条
            all_records.sort(key=lambda x: (x.get("date", ""), x.get("id", 0)), reverse=True)
            latest_positions_prev = all_records[0].get("positions", {})
            max_id_prev = all_records[0].get("id", -1)

    return latest_positions_prev, max_id_prev