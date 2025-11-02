#!/usr/bin/env python3
"""
脚本功能：
为当前日期和时间运行模拟交易脚本
该脚本会在交易日的每个交易小时被调用
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime


def run_main_script_for_today(config_path):
    """
    为今天运行 main.py 交易脚本
    
    Args:
        config_path: 配置文件路径
        
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

    # 获取当前日期和时间（美东时间）
    from pytz import timezone
    import pytz
    
    # 获取美东时间
    et = timezone('US/Eastern')
    now_et = datetime.now(et)
    
    # 格式化为 YYYY-MM-DD HH:MM:SS
    date_str = now_et.strftime("%Y-%m-%d")
    time_str = now_et.strftime("%Y-%m-%d %H:00:00")  # 使用整点时间

    # 设置环境变量来覆盖配置文件中的日期
    env = os.environ.copy()
    env["INIT_DATE"] = time_str
    env["END_DATE"] = time_str

    print(f"📅 执行交易日期: {date_str}")
    print(f"🕐 执行交易时间: {time_str}")
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
            print(f"✅ 成功执行日期 {date_str} 时间 {time_str}")
            return True
        else:
            print(f"❌ 执行日期 {date_str} 时间 {time_str} 失败，返回码: {result.returncode}")
            return False

    except Exception as e:
        print(f"❌ 执行日期 {date_str} 时间 {time_str} 时发生错误: {e}")
        return False


def main():
    """主函数"""
    # 获取脚本所在目录和项目根目录
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    # 配置文件路径
    config_path = project_root / "configs" / "production_config.json"

    # 检查配置文件是否存在
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        sys.exit(1)

    print("🚀 开始执行当日交易脚本...")
    
    # 运行主脚本
    success = run_main_script_for_today(config_path)
    
    if success:
        print("🎉 交易脚本执行成功")
        sys.exit(0)
    else:
        print("❌ 交易脚本执行失败")
        sys.exit(1)


if __name__ == "__main__":
    main()

