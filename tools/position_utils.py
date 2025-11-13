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

def get_latest_position_robust(today_date: str, signature: str) -> Tuple[Dict[str, float], int]:
    """
    获取截止到指定日期的最新持仓记录。

    算法：
    1. 找到 position.jsonl 文件。
    2. 遍历文件中的每一行。
    3. 查找所有日期小于或等于 (<=) today_date 的记录。
    4. 在这些有效记录中，找到日期 "最晚" (latest) 的记录。
    5. 如果 "最晚" 日期有多条记录，选择 "id" 最大的那一条。
    
    **并未假设周末不可交易，但是能修复bug:周日周一开始模拟，无法找到周日的持仓（bug直接返回cash=0）**

    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表查询截止日期。
        signature: 模型名称，用于构建文件路径。

    Returns:
        (positions, max_id):
          - positions: {symbol: amount} 的字典；若未找到任何记录，则为空字典。
          - max_id: 选中记录的最大 id；若未找到任何记录，则为 -1.
    """
    
    # --- 1. 定位文件 (与原代码逻辑一致) ---
    base_dir = Path(__file__).resolve().parents[1]
    log_path = get_config_value("LOG_PATH", "./data/agent_data")

    if os.path.isabs(log_path):
        position_file = Path(log_path) / signature / "position" / "position.jsonl"
    else:
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix
        position_file = base_dir / "data" / log_path / signature / "position" / "position.jsonl"

    if not position_file.exists():
        # 模拟 "首次运行" (test5) 场景
        return {}, -1

    # --- 2. 查找 "最晚日期" 和 "最大ID" ---
    
    latest_valid_doc = None
    max_valid_date_str = None  # 用于跟踪找到的 "最晚" 日期

    try:
        with position_file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                
                try:
                    doc = json.loads(line)
                    doc_date_str = doc.get("date")
                    doc_id = doc.get("id", -1)

                    # 3. 检查日期是否有效，且是否在查询日期之前（或当天）
                    #    (这会正确处理 test7: 未来数据保护)
                    if not doc_date_str or doc_date_str > today_date:
                        continue
                        
                    # 4. 比较并更新 "最晚" 记录
                    if max_valid_date_str is None:
                        # 这是我们找到的第一个有效记录
                        max_valid_date_str = doc_date_str
                        latest_valid_doc = doc
                    elif doc_date_str > max_valid_date_str:
                        # 找到了一个日期更晚的记录 (test2, test4)
                        max_valid_date_str = doc_date_str
                        latest_valid_doc = doc
                    elif doc_date_str == max_valid_date_str:
                        # 日期相同，比较 ID (test6)
                        if doc_id > latest_valid_doc.get("id", -1):
                            latest_valid_doc = doc
                    # else: doc_date_str < max_valid_date_str (忽略旧数据)
                            
                except json.JSONDecodeError:
                    # 忽略损坏的行
                    continue
                except Exception:
                    # 忽略其他可能的行错误
                    continue
                    
    except FileNotFoundError:
        # 再次检查，以防文件在 exists() 和 open() 之间被删除
        return {}, -1
    except Exception as e:
        # 处理读取文件时的其他IO错误
        print(f"Error reading position file {position_file}: {e}", file=sys.stderr)
        return {}, -1

    # --- 3. 返回最终结果 ---
    if latest_valid_doc:
        # 找到了符合条件的最新记录
        return latest_valid_doc.get("positions", {}), latest_valid_doc.get("id", -1)
    else:
        # 文件存在，但没有找到任何 date <= today_date 的有效记录
        return {}, -1

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
    import warnings
    warnings.warn("get_latest_position 已被弃用，请使用 get_latest_position_robust 以获得更健壮的行为。", DeprecationWarning)
    
    return get_latest_position_robust(today_date, signature)
    
    
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

    # 🔧 CRITICAL FIX: 改进 fallback 逻辑 - 查找小于等于指定日期的最新记录
    if max_id_prev < 0 or not latest_positions_prev:
        latest_valid_doc = None
        max_valid_date_str = None

        with position_file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    doc = json.loads(line)
                    doc_date_str = doc.get("date")

                    # 修复点：查找小于或等于 (<=) 查询日期的最新记录
                    if doc_date_str and doc_date_str <= today_date:
                        # 找到这些有效记录中，日期最新的那一条
                        if max_valid_date_str is None or doc_date_str >= max_valid_date_str:
                            # 如果日期相同，保留ID更大的记录
                            if max_valid_date_str == doc_date_str and latest_valid_doc:
                                if doc.get("id", -1) > latest_valid_doc.get("id", -1):
                                    latest_valid_doc = doc
                            else:
                                max_valid_date_str = doc_date_str
                                latest_valid_doc = doc
                except json.JSONDecodeError:
                    continue
                except Exception:
                    continue

        # 使用找到的最新有效记录
        if latest_valid_doc:
            latest_positions_prev = latest_valid_doc.get("positions", {})
            max_id_prev = latest_valid_doc.get("id", -1)

    return latest_positions_prev, max_id_prev