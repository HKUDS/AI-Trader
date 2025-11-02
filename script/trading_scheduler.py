#!/usr/bin/env python3
"""
定时调度脚本：
在美股交易日的每个交易小时的:30自动执行：
0. 确保 MCP 服务正在运行 (start_mcp_services.py)
1. 获取实时股票价格数据 (get_daily_price.py)
2. 运行模拟交易 (run_main_script_for_date.py)

美股交易时间：美东时间 9:30 - 16:00（每个交易小时）
"""

import os
import sys
import json
import subprocess
import time
import socket
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


def check_port_open(port):
    """
    检查指定端口是否开放
    
    Args:
        port: 端口号
        
    Returns:
        bool: 如果端口开放返回 True
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        return result == 0
    except:
        return False


def check_mcp_services_running(verbose=False):
    """
    检查所有 MCP 服务是否正在运行
    
    Args:
        verbose: 是否打印详细日志
        
    Returns:
        bool: 如果所有服务都在运行返回 True
    """
    # MCP 服务端口配置
    ports = {
        'math': int(os.getenv('MATH_HTTP_PORT', '8000')),
        'search': int(os.getenv('SEARCH_HTTP_PORT', '8001')),
        'trade': int(os.getenv('TRADE_HTTP_PORT', '8002')),
        'price': int(os.getenv('GETPRICE_HTTP_PORT', '8003'))
    }
    
    all_running = True
    for service_name, port in ports.items():
        if not check_port_open(port):
            if verbose:
                print(f"⚠️  {service_name} 服务未运行 (端口 {port})")
            all_running = False
    
    return all_running


def start_mcp_services():
    """
    启动 MCP 服务（后台运行）
    
    Returns:
        bool: 如果启动成功返回 True
    """
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    mcp_script = project_root / "agent_tools" / "start_mcp_services.py"
    
    if not mcp_script.exists():
        print(f"❌ start_mcp_services.py 文件不存在: {mcp_script}")
        return False
    
    print("🔧 检查 MCP 服务状态...")
    
    # 首先检查服务是否已经在运行（静默检查）
    if check_mcp_services_running(verbose=False):
        print("✅ MCP 服务已在运行")
        return True
    
    print("ℹ️  MCP 服务未运行，需要启动")
    
    print("🚀 启动 MCP 服务...")
    
    try:
        # 以后台方式启动 MCP 服务
        # 注意：start_mcp_services.py 是一个阻塞脚本，我们需要在后台运行
        # 使用 devnull 避免缓冲问题，并允许服务正常输出到日志文件
        import subprocess as sp
        devnull = open(os.devnull, 'w')
        
        process = subprocess.Popen(
            [sys.executable, str(mcp_script)],
            cwd=str(project_root / "agent_tools"),
            stdout=devnull,
            stderr=sp.STDOUT,
            start_new_session=True,  # 创建新会话，使进程独立
            close_fds=True  # 关闭文件描述符
        )
        devnull.close()
        
        # 等待服务启动
        print("⏳ 等待 MCP 服务启动...")
        time.sleep(5)
        
        # 检查进程是否还在运行
        if process.poll() is not None:
            print(f"⚠️  MCP 服务进程已退出，返回码: {process.poll()}")
            return False
        
        # 检查服务是否成功启动（通过端口检查）
        if check_mcp_services_running():
            print("✅ MCP 服务启动成功")
            # 保存进程 ID，以便后续可能需要停止
            mcp_pid_file = project_root / ".mcp_services.pid"
            try:
                with open(mcp_pid_file, 'w') as f:
                    f.write(str(process.pid))
            except Exception as e:
                print(f"⚠️  无法保存 MCP 进程 ID: {e}")
            return True
        else:
            print("⚠️  MCP 服务可能未完全启动，但进程仍在运行")
            print("⚠️  将在下次任务执行前再次检查")
            return False
            
    except Exception as e:
        print(f"❌ 启动 MCP 服务时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def ensure_mcp_services_running():
    """
    确保 MCP 服务正在运行，如果未运行则启动
    
    Returns:
        bool: 如果服务运行中返回 True
    """
    # 在任务执行时，使用详细模式检查服务状态
    if check_mcp_services_running(verbose=True):
        return True
    
    # 如果服务未运行，尝试启动
    return start_mcp_services()


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
    
    # 步骤0: 确保 MCP 服务正在运行
    print("\n" + "=" * 60)
    print("步骤 0: 确保 MCP 服务正在运行")
    print("=" * 60)
    mcp_success = ensure_mcp_services_running()
    
    if not mcp_success:
        print("❌ MCP 服务启动失败，无法继续执行交易任务")
        print("=" * 60 + "\n")
        return
    
    # 等待一小段时间，确保服务完全就绪
    time.sleep(2)
    
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
    try:
        print("🚀 启动美股交易定时调度器...")
        print("📅 将在每个交易日的 9:30-15:30 的每小时:30 执行任务")
        print("⏰ 使用美东时区 (US/Eastern)")
        print("\n" + "=" * 60)
        print("步骤 0: 启动 MCP 服务")
        print("=" * 60)
        
        # 在调度器启动时启动 MCP 服务（添加异常处理）
        try:
            if not start_mcp_services():
                print("⚠️  MCP 服务启动可能失败，但调度器将继续运行")
                print("⚠️  将在每次任务执行前再次尝试启动服务")
        except Exception as e:
            print(f"⚠️  启动 MCP 服务时出现异常: {e}")
            print("⚠️  调度器将继续运行，将在每次任务执行前再次尝试启动服务")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("✅ 调度器初始化完成")
        print("=" * 60)
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
        except Exception as e:
            print(f"\n❌ 调度器运行时发生错误: {e}")
            import traceback
            traceback.print_exc()
            scheduler.shutdown()
            raise
    
    except Exception as e:
        print(f"\n❌ 启动调度器时发生严重错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

