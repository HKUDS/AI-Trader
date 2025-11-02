#!/usr/bin/env python3
"""
脚本功能：
1. 读取配置文件，获取启用的模型列表
2. 读取交易日历文件，获取所有交易日
3. 检查每个启用的 agent 已有数据的日期
4. 找出缺失的交易日数据（在今天之前）
5. 依次运行所有缺失的日期数据
"""

import os
import json
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


def load_trading_calendar(calendar_path):
    """
    加载交易日历文件

    Args:
        calendar_path: 交易日历文件路径

    Returns:
        dict: 交易日历数据，如果文件不存在则返回 None
    """
    calendar_path = Path(calendar_path)

    if not calendar_path.exists():
        print(f"❌ 交易日历文件不存在: {calendar_path}")
        return None

    try:
        with open(calendar_path, 'r', encoding='utf-8') as f:
            calendar_data = json.load(f)
        print(f"✅ 成功加载交易日历文件: {calendar_path}")
        return calendar_data
    except json.JSONDecodeError as e:
        print(f"❌ 交易日历文件 JSON 格式错误: {e}")
        return None
    except Exception as e:
        print(f"❌ 加载交易日历文件失败: {e}")
        return None


def get_trading_days_before_today(calendar_data):
    """
    获取今天之前的所有交易日

    Args:
        calendar_data: 交易日历数据字典

    Returns:
        list: 今天之前的所有交易日列表，按日期升序排序
    """
    if calendar_data is None:
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    trading_days = calendar_data.get("trading_days", [])

    # 筛选出今天之前的交易日并排序
    past_trading_days = [day for day in trading_days if day < today]
    past_trading_days.sort()

    return past_trading_days


def load_config(config_path):
    """
    加载配置文件并获取启用的模型列表

    Args:
        config_path: 配置文件路径

    Returns:
        list: 启用的模型的 signature 列表
    """
    config_path = Path(config_path)

    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"✅ 成功加载配置文件: {config_path}")
        
        # 获取启用的模型列表
        enabled_models = []
        models = config.get("models", [])
        
        for model in models:
            # enabled 默认为 True（如果未指定）
            if model.get("enabled", True):
                signature = model.get("signature")
                if signature:
                    enabled_models.append(signature)
                else:
                    name = model.get("name", "unknown")
                    print(f"⚠️  模型 {name} 启用但缺少 signature 字段，跳过")
        
        print(f"✅ 找到 {len(enabled_models)} 个启用的模型: {', '.join(enabled_models)}")
        return enabled_models
        
    except json.JSONDecodeError as e:
        print(f"❌ 配置文件 JSON 格式错误: {e}")
        return None
    except Exception as e:
        print(f"❌ 加载配置文件失败: {e}")
        return None


def get_agent_existing_dates(agent_name, agent_data_path):
    """
    获取指定 agent 已有的数据日期

    Args:
        agent_name: agent 名称（signature）
        agent_data_path: agent 数据根目录路径

    Returns:
        set: 已有的日期集合（格式：YYYY-MM-DD）
    """
    agent_path = Path(agent_data_path) / agent_name
    log_path = agent_path / "log"

    if not log_path.exists():
        print(f"⚠️  agent {agent_name} 的 log 目录不存在")
        return set()

    existing_dates = set()

    # 遍历 log 目录下的所有日期时间目录
    for date_time_dir in log_path.iterdir():
        if date_time_dir.is_dir():
            # 提取日期部分（格式：YYYY-MM-DD HH:MM:SS，取前10个字符）
            date_str = date_time_dir.name[:10]
            existing_dates.add(date_str)

    return existing_dates


def find_missing_dates_for_agent(agent_name, agent_data_path, all_trading_days):
    """
    找出指定 agent 缺失的交易日数据

    Args:
        agent_name: agent 名称
        agent_data_path: agent 数据根目录路径
        all_trading_days: 所有交易日列表

    Returns:
        list: 缺失的日期列表，按日期升序排序
    """
    existing_dates = get_agent_existing_dates(agent_name, agent_data_path)
    missing_dates = []

    for trading_day in all_trading_days:
        if trading_day not in existing_dates:
            missing_dates.append(trading_day)

    print(f"🤖 Agent {agent_name}: 已有 {len(existing_dates)} 个交易日数据，缺失 {len(missing_dates)} 个交易日数据")
    return missing_dates


def run_main_script_for_date(config_path, date_str):
    """
    为指定日期调用 main.py 运行交易脚本

    Args:
        config_path: 配置文件路径
        date_str: 要运行的日期字符串，格式为 YYYY-MM-DD

    Returns:
        bool: 如果执行成功返回 True，否则返回 False
    """
    # 获取项目根目录
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    main_script = project_root / "main.py"

    if not main_script.exists():
        print(f"❌ main.py 文件不存在: {main_script}")
        return False

    # 设置环境变量来覆盖配置文件中的日期
    env = os.environ.copy()
    env["INIT_DATE"] = date_str
    env["END_DATE"] = date_str

    print(f"📅 执行交易日期: {date_str}")
    print(f"📄 使用配置文件: {config_path}")

    try:
        # 调用 main.py，传递配置文件路径
        result = subprocess.run(
            [sys.executable, str(main_script), str(config_path)],
            env=env,
            cwd=str(project_root),
            check=False
        )

        if result.returncode == 0:
            print(f"✅ 成功执行日期 {date_str}")
            return True
        else:
            print(f"❌ 执行日期 {date_str} 失败，返回码: {result.returncode}")
            return False

    except Exception as e:
        print(f"❌ 执行日期 {date_str} 时发生错误: {e}")
        return False


def main():
    """主函数"""
    # 获取脚本所在目录和项目根目录
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    # 交易日历文件路径
    calendar_path = project_root / "data" / "trading_calendar" / "us_trading_days_2025Q4.json"

    # 配置文件路径
    config_path = project_root / "configs" / "production_config.json"

    # agent 数据目录路径
    agent_data_path = project_root / "data" / "agent_data"

    print("🚀 开始检查缺失的交易数据...")

    # 加载交易日历
    calendar_data = load_trading_calendar(calendar_path)
    if calendar_data is None:
        print("❌ 无法加载交易日历，程序退出")
        sys.exit(1)

    # 获取今天之前的所有交易日
    past_trading_days = get_trading_days_before_today(calendar_data)
    if not past_trading_days:
        print("ℹ️  今天之前没有交易日，程序退出")
        sys.exit(0)

    print(f"📅 今天之前共有 {len(past_trading_days)} 个交易日")

    # 检查配置文件是否存在
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        sys.exit(1)

    # 加载配置文件，获取启用的模型列表
    enabled_models = load_config(config_path)
    if enabled_models is None:
        print("❌ 无法加载配置文件，程序退出")
        sys.exit(1)

    if not enabled_models:
        print("⚠️  配置文件中没有启用的模型，程序退出")
        sys.exit(0)

    # 收集所有需要执行的日期
    all_missing_dates = set()

    for agent_name in enabled_models:
        print(f"\n🔍 检查 agent: {agent_name}")
        missing_dates = find_missing_dates_for_agent(agent_name, agent_data_path, past_trading_days)

        if missing_dates:
            print(f"📋 缺失日期: {', '.join(missing_dates)}")
            # 将缺失的日期添加到集合中
            all_missing_dates.update(missing_dates)
        else:
            print("✅ 该 agent 数据完整")

    if not all_missing_dates:
        print("\n🎉 所有启用的 agent 数据都已完整，无需执行")
        sys.exit(0)

    # 转换为排序列表
    missing_dates_list = sorted(list(all_missing_dates))

    print(f"\n📊 总共需要执行 {len(missing_dates_list)} 个交易日")
    print(f"📅 缺失的交易日: {', '.join(missing_dates_list)}")

    # 执行所有缺失的日期
    success_count = 0
    total_count = len(missing_dates_list)

    print("\n🚀 开始执行缺失数据...")
    print("=" * 60)

    for i, date_str in enumerate(missing_dates_list, 1):
        print(f"\n[{i}/{total_count}] 执行交易日: {date_str}")

        # 为所有启用的 agent 执行该日期的数据
        # main.py 会根据配置文件中的 enabled=true 模型来决定运行哪些 agent
        success = run_main_script_for_date(config_path, date_str)

        if success:
            success_count += 1
        else:
            print(f"⚠️  日期 {date_str} 执行失败，但继续处理其他日期")

    print("\n" + "=" * 60)
    print(f"📊 执行完成: 成功 {success_count}/{total_count}")

    if success_count == total_count:
        print("🎉 所有任务执行成功")
        sys.exit(0)
    else:
        print(f"⚠️  {total_count - success_count} 个任务执行失败")
        sys.exit(1)


if __name__ == "__main__":
    main()

