#!/usr/bin/env python3
"""
加密货币模型表现评估脚本
Evaluate all crypto trading models' performance
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd
from datetime import datetime

# 添加项目根目录到路径（文件现在在 data/crypto 目录下）
project_root = Path(__file__).resolve().parents[2]  # data/crypto -> AI-Trader 需要向上两级
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tools.result_tools import calculate_and_save_metrics, get_available_date_range
from tools.general_tools import get_config_value


def get_crypto_models(data_dir: str = "data/agent_data_crypto") -> List[str]:
    """
    获取所有可用的加密货币模型

    Args:
        data_dir: 数据目录路径（相对于 data/crypto 目录）

    Returns:
        模型名称列表
    """
    base_dir = Path(__file__).resolve().parents[2]  # data/crypto -> AI-Trader 需要向上两级
    crypto_data_dir = base_dir / data_dir

    if not crypto_data_dir.exists():
        print(f"❌ 目录不存在: {crypto_data_dir}")
        return []

    models = []
    for item in crypto_data_dir.iterdir():
        if item.is_dir() and not item.name.startswith("__"):
            # 检查是否有 position 目录
            position_dir = item / "position"
            if position_dir.exists():
                position_file = position_dir / "position.jsonl"
                if position_file.exists():
                    models.append(item.name)

    return sorted(models)


def evaluate_model(model_name: str, market: str = "crypto") -> Dict[str, Any]:
    """
    评估单个模型的表现

    Args:
        model_name: 模型名称
        market: 市场类型

    Returns:
        评估结果字典
    """
    print(f"🔍 评估模型: {model_name}")

    try:
        # 获取可用日期范围
        start_date, end_date = get_available_date_range(model_name)
        if not start_date or not end_date:
            return {
                "model_name": model_name,
                "error": "无法获取数据日期范围",
                "status": "❌ 数据错误"
            }

        # 计算指标（不打印详细报告）
        metrics = calculate_and_save_metrics(
            signature=model_name,
            start_date=start_date,
            end_date=end_date,
            market=market,
            print_report=False
        )

        if "error" in metrics:
            return {
                "model_name": model_name,
                "error": metrics["error"],
                "status": "❌ 计算错误"
            }

        # 添加基本信息
        result = {
            "model_name": model_name,
            "status": "✅ 成功",
            "trading_days": metrics.get("total_trading_days", 0),
            "start_date": metrics.get("start_date", ""),
            "end_date": metrics.get("end_date", ""),
            "cumulative_return": metrics.get("cumulative_return", 0.0),
            "annualized_return": metrics.get("annualized_return", 0.0),
            "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
            "max_drawdown": metrics.get("max_drawdown", 0.0),
            "volatility": metrics.get("volatility", 0.0),
            "win_rate": metrics.get("win_rate", 0.0),
            "profit_loss_ratio": metrics.get("profit_loss_ratio", 0.0),
        }

        # 添加投资组合价值信息
        portfolio_values = metrics.get("portfolio_values", {})
        if portfolio_values:
            sorted_dates = sorted(portfolio_values.keys())
            initial_value = portfolio_values[sorted_dates[0]]
            final_value = portfolio_values[sorted_dates[-1]]

            result.update({
                "initial_value": initial_value,
                "final_value": final_value,
                "value_change": final_value - initial_value,
                "value_change_percent": ((final_value - initial_value) / initial_value) if initial_value > 0 else 0.0
            })

        return result

    except Exception as e:
        return {
            "model_name": model_name,
            "error": str(e),
            "status": "❌ 异常"
        }


def print_comparison_table(results: List[Dict[str, Any]]) -> None:
    """
    打印对比表格

    Args:
        results: 评估结果列表
    """
    if not results:
        print("❌ 没有可用的评估结果")
        return

    print("\n" + "="*100)
    print("📊 加密货币交易模型性能对比表")
    print("="*100)

    # 过滤出成功的结果
    successful_results = [r for r in results if "error" not in r]
    failed_results = [r for r in results if "error" in r]

    if not successful_results:
        print("❌ 没有成功评估的模型")
        return

    # 创建DataFrame
    df = pd.DataFrame(successful_results)

    # 选择要显示的列
    display_columns = [
        "model_name",
        "trading_days",
        "cumulative_return",
        "annualized_return",
        "sharpe_ratio",
        "max_drawdown",
        "volatility",
        "win_rate",
        "profit_loss_ratio"
    ]

    df_display = df[display_columns].copy()

    # 格式化显示
    df_display["cumulative_return"] = df_display["cumulative_return"].apply(lambda x: f"{x:.2%}")
    df_display["annualized_return"] = df_display["annualized_return"].apply(lambda x: f"{x:.2%}")
    df_display["sharpe_ratio"] = df_display["sharpe_ratio"].apply(lambda x: f"{x:.4f}")
    df_display["max_drawdown"] = df_display["max_drawdown"].apply(lambda x: f"{x:.2%}")
    df_display["volatility"] = df_display["volatility"].apply(lambda x: f"{x:.2%}")
    df_display["win_rate"] = df_display["win_rate"].apply(lambda x: f"{x:.2%}")
    df_display["profit_loss_ratio"] = df_display["profit_loss_ratio"].apply(lambda x: f"{x:.4f}")

    # 重命名列
    df_display.columns = [
        "模型名称",
        "交易天数",
        "累计收益率",
        "年化收益率",
        "夏普比率",
        "最大回撤",
        "波动率",
        "胜率",
        "盈亏比"
    ]

    print(df_display.to_string(index=False))

    # 显示排名
    print("\n" + "="*60)
    print("🏆 模型排名")
    print("="*60)

    # 按不同指标排名
    metrics_ranking = {
        "累计收益率": ("cumulative_return", False),
        "夏普比率": ("sharpe_ratio", False),
        "最大回撤": ("max_drawdown", True),  # 越小越好
        "胜率": ("win_rate", False)
    }

    for metric_name, (column, ascending) in metrics_ranking.items():
        print(f"\n📈 {metric_name}排名:")
        sorted_df = df.sort_values(by=column, ascending=ascending)
        for i, (_, row) in enumerate(sorted_df.iterrows(), 1):
            if metric_name == "最大回撤":
                print(f"  {i:2d}. {row['model_name']:20s} {row[column]:.2%}")
            else:
                print(f"  {i:2d}. {row['model_name']:20s} {row[column]:.2%}")

    # 显示失败的模型
    if failed_results:
        print(f"\n❌ 评估失败的模型 ({len(failed_results)} 个):")
        for result in failed_results:
            print(f"  - {result['model_name']}: {result['error']}")


def save_summary_report(results: List[Dict[str, Any]], filename: str = None) -> None:
    """
    保存汇总报告

    Args:
        results: 评估结果列表
        filename: 输出文件名
    """
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"crypto_models_evaluation_{timestamp}.json"

    # 保存到当前目录 (data/crypto)
    output_path = Path(__file__).parent / filename

    # 准备保存的数据
    save_data = {
        "evaluation_time": datetime.now().isoformat(),
        "total_models": len(results),
        "successful_evaluations": len([r for r in results if "error" not in r]),
        "failed_evaluations": len([r for r in results if "error" in r]),
        "market": "crypto",
        "results": results
    }

    import json
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)

    print(f"\n💾 汇总报告已保存到: {output_path}")


def main():
    """主函数"""
    print("🚀 开始评估加密货币交易模型...")
    print(f"📅 评估时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 设置环境变量（相对于项目根目录）
    os.environ['LOG_PATH'] = './data/agent_data_crypto'

    # 获取所有模型
    models = get_crypto_models()

    if not models:
        print("❌ 未找到任何加密货币模型")
        print("请检查 data/agent_data_crypto 目录下是否有模型数据")
        return

    print(f"📋 找到 {len(models)} 个模型: {', '.join(models)}")
    print()

    # 评估所有模型
    results = []
    for i, model in enumerate(models, 1):
        print(f"[{i}/{len(models)}] ", end="")
        result = evaluate_model(model, market="crypto")
        results.append(result)

    print(f"\n✅ 评估完成! 成功: {len([r for r in results if 'error' not in r])}, 失败: {len([r for r in results if 'error' in r])}")

    # 打印对比表格
    print_comparison_table(results)

    # 保存汇总报告
    save_summary_report(results)

    print("\n🎉 评估报告生成完成!")


if __name__ == "__main__":
    main()