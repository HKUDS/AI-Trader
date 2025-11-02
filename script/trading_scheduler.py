#!/usr/bin/env python3
"""
定时调度脚本：
在美股交易日的每个交易小时的:30自动执行：
1. 获取实时股票价格数据 (get_daily_price.py)
2. 运行模拟交易 (run_main_script_for_date.py)

美股交易时间：美东时间 9:30 - 16:00（每个交易小时）
"""

import os
import sys
import json
import subprocess
import time
from pathlib import Path
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone


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
        print(f"⚠️  交易日历文件不存在: {calendar_path}")
        return None
    
    try:
        with open(calendar_path, 'r', encoding='utf-8') as f:
            calendar_data = json.load(f)
        return calendar_data
    except Exception as e:
        print(f"❌ 加载交易日历文件失败: {e}")
        return None


def is_trading_day(date_str, calendar_data):
    """
    检查指定日期是否是交易日
    
    Args:
        date_str: 日期字符串，格式 YYYY-MM-DD
        calendar_data: 交易日历数据
        
    Returns:
        bool: 如果是交易日返回 True，否则返回 False
    """
    if calendar_data is None:
        # 如果没有交易日历，默认检查是否为工作日
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.weekday() < 5
    
    trading_days = calendar_data.get("trading_days", [])
    return date_str in trading_days


def is_trading_hour(hour_et):
    """
    检查是否是交易小时（美东时间）
    
    Args:
        hour_et: 美东时间的小时数 (0-23)
        
    Returns:
        bool: 如果在交易时间内返回 True
    """
    # 美股交易时间：9:30 - 16:00 (美东时间)
    # 由于我们在:30执行，所以检查小时数是否在 9-15 之间
    return 9 <= hour_et <= 15


def get_price_data():
    """获取实时股票价格数据"""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    get_price_script = project_root / "data" / "get_daily_price.py"
    
    if not get_price_script.exists():
        print(f"❌ get_daily_price.py 文件不存在: {get_price_script}")
        return False
    
    print("📊 开始获取实时股票价格数据...")
    
    try:
        result = subprocess.run(
            [sys.executable, str(get_price_script)],
            cwd=str(project_root),
            check=False,
            timeout=600  # 10分钟超时
        )
        
        if result.returncode == 0:
            print("✅ 成功获取股票价格数据")
            return True
        else:
            print(f"❌ 获取股票价格数据失败，返回码: {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ 获取股票价格数据超时")
        return False
    except Exception as e:
        print(f"❌ 获取股票价格数据时发生错误: {e}")
        return False


def run_trading_simulation():
    """运行模拟交易"""
    script_dir = Path(__file__).resolve().parent
    run_script = script_dir / "run_main_script_for_date.py"
    
    if not run_script.exists():
        print(f"❌ run_main_script_for_date.py 文件不存在: {run_script}")
        return False
    
    print("🤖 开始运行模拟交易...")
    
    try:
        result = subprocess.run(
            [sys.executable, str(run_script)],
            check=False,
            timeout=1800  # 30分钟超时
        )
        
        if result.returncode == 0:
            print("✅ 成功运行模拟交易")
            return True
        else:
            print(f"❌ 运行模拟交易失败，返回码: {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ 运行模拟交易超时")
        return False
    except Exception as e:
        print(f"❌ 运行模拟交易时发生错误: {e}")
        return False


def scheduled_task():
    """定时任务：在每小时的:30执行"""
    et = timezone('US/Eastern')
    now_et = datetime.now(et)
    date_str = now_et.strftime("%Y-%m-%d")
    hour_et = now_et.hour
    minute_et = now_et.minute
    
    print("=" * 60)
    print(f"🕐 定时任务触发时间: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 60)
    
    # 检查是否是交易小时
    if not is_trading_hour(hour_et):
        print(f"ℹ️  当前时间 {hour_et}:{minute_et:02d} 不在交易时间内 (9:30-16:00)，跳过")
        return
    
    # 加载交易日历
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    calendar_path = project_root / "data" / "trading_calendar" / "us_trading_days_2025Q4.json"
    calendar_data = load_trading_calendar(calendar_path)
    
    # 检查是否是交易日
    if not is_trading_day(date_str, calendar_data):
        print(f"ℹ️  日期 {date_str} 不是交易日，跳过")
        return
    
    print(f"✅ 确认是交易日 {date_str}，交易时间 {hour_et}:{minute_et:02d}")
    
    # 步骤1: 获取股票价格数据
    print("\n" + "=" * 60)
    print("步骤 1: 获取股票价格数据")
    print("=" * 60)
    price_success = get_price_data()
    
    if not price_success:
        print("⚠️  获取价格数据失败，但继续执行交易模拟")
    
    # 等待一小段时间，确保数据已保存
    time.sleep(5)
    
    # 步骤2: 运行模拟交易
    print("\n" + "=" * 60)
    print("步骤 2: 运行模拟交易")
    print("=" * 60)
    trading_success = run_trading_simulation()
    
    # 输出结果
    print("\n" + "=" * 60)
    if price_success and trading_success:
        print("🎉 所有任务执行成功")
    elif price_success:
        print("⚠️  价格数据获取成功，但交易模拟失败")
    elif trading_success:
        print("⚠️  价格数据获取失败，但交易模拟成功")
    else:
        print("❌ 所有任务执行失败")
    print("=" * 60 + "\n")


def main():
    """主函数：启动调度器"""
    print("🚀 启动美股交易定时调度器...")
    print("📅 将在每个交易日的 9:30-15:30 的每小时:30 执行任务")
    print("⏰ 使用美东时间 (US/Eastern)")
    print("\n按 Ctrl+C 停止调度器\n")
    
    # 创建调度器，使用美东时区
    et = timezone('US/Eastern')
    scheduler = BlockingScheduler(timezone=et)
    
    # 添加定时任务：每天的 9:30-15:30 的每小时:30 执行
    # 注意：是否执行取决于 scheduled_task 内部的交易日检查
    # CronTrigger: 分钟=30, 小时=9-15
    scheduler.add_job(
        scheduled_task,
        trigger=CronTrigger(
            minute=30,
            hour='9-15'  # 9:30, 10:30, ..., 15:30
        ),
        id='trading_task',
        name='美股交易定时任务',
        replace_existing=True
    )
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n\n⏹️  调度器已停止")
        scheduler.shutdown()


if __name__ == "__main__":
    main()

