"""
ThematicAgent - 主题集中交易策略
基于DeepSeek的成功策略实现，核心特点：
1. 主题集中投资（AI/半导体）
2. 动态权重再平衡
3. 高仓位运作（98%+）
4. 积极止盈策略
"""

import os
import sys
from typing import Dict, List, Optional, Any

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from agent.base_agent.base_agent import BaseAgent


class ThematicAgent(BaseAgent):
    """
    主题集中交易Agent

    策略核心：
    - 聚焦AI/半导体主题（可自定义）
    - 单股最大权重20%
    - 保持98%以上仓位
    - 定期再平衡
    """

    # AI/半导体主题股票池
    THEME_STOCKS = {
        "ai_semiconductor": [
            "NVDA",   # NVIDIA - AI芯片领导者
            "AMD",    # AMD - GPU/CPU制造商
            "MSFT",   # Microsoft - AI应用
            "GOOGL",  # Google - AI研究
            "ASML",   # ASML - 半导体设备
            "AVGO",   # Broadcom - 半导体基础设施
            "QCOM",   # Qualcomm - 移动芯片
            "AMAT",   # Applied Materials - 半导体设备
            "ARM",    # ARM - 芯片设计
            "INTC",   # Intel - 芯片制造
            "MU",     # Micron - 内存芯片
            "TSM",    # TSMC - 芯片代工（如果有）
        ],
        "tech_giants": [
            "MSFT", "AAPL", "GOOGL", "AMZN", "META"
        ],
        "cloud_computing": [
            "MSFT", "AMZN", "GOOGL", "ORCL", "CRM"
        ]
    }

    def __init__(
        self,
        signature: str,
        basemodel: str,
        theme: str = "ai_semiconductor",
        max_stock_weight: float = 0.20,
        min_cash_ratio: float = 0.01,
        **kwargs
    ):
        """
        初始化ThematicAgent

        Args:
            signature: Agent标识
            basemodel: AI模型路径
            theme: 投资主题 ("ai_semiconductor", "tech_giants", "cloud_computing")
            max_stock_weight: 单股最大权重（默认20%）
            min_cash_ratio: 最小现金比例（默认1%）
            **kwargs: 其他BaseAgent参数
        """
        super().__init__(signature, basemodel, **kwargs)

        self.theme = theme
        self.max_stock_weight = max_stock_weight
        self.min_cash_ratio = min_cash_ratio

        # 获取主题股票列表
        if theme in self.THEME_STOCKS:
            self.theme_stocks = self.THEME_STOCKS[theme]
        else:
            print(f"⚠️ 主题 '{theme}' 不存在，使用默认主题 'ai_semiconductor'")
            self.theme_stocks = self.THEME_STOCKS["ai_semiconductor"]

        # 过滤：只保留在NASDAQ 100中的股票
        self.theme_stocks = [s for s in self.theme_stocks if s in self.DEFAULT_STOCK_SYMBOLS]

        print(f"🎯 主题: {theme}")
        print(f"📊 主题股票池 ({len(self.theme_stocks)}只): {', '.join(self.theme_stocks)}")
        print(f"⚖️ 单股最大权重: {max_stock_weight*100:.0f}%")
        print(f"💵 最小现金比例: {min_cash_ratio*100:.0f}%")

    def get_strategy_description(self) -> str:
        """获取策略描述"""
        return f"""
## 主题集中交易策略

**投资主题**: {self.theme}
**目标股票池**: {', '.join(self.theme_stocks)}

**策略规则**:
1. 🎯 **主题聚焦**: 优先投资主题股票池中的标的
2. ⚖️ **权重管理**: 单股权重不超过{self.max_stock_weight*100:.0f}%，超限时减仓
3. 💪 **高仓位**: 保持{(1-self.min_cash_ratio)*100:.0f}%以上仓位
4. 🔄 **动态再平衡**: 及时止盈超涨股票，加仓优质标的
5. 📊 **分散配置**: 持有8-12只股票，避免过度集中

**交易纪律**:
- ✅ 优先买入主题股票池中的标的
- ✅ 当某只股票权重超过{self.max_stock_weight*100:.0f}%时，卖出部分锁定利润
- ✅ 将止盈资金再投资到权重较低的优质标的
- ✅ 保持现金比例在{self.min_cash_ratio*100:.0f}%-{self.min_cash_ratio*100*3:.0f}%之间
- ❌ 避免频繁交易（每日不超过5次操作）
"""

    def __str__(self) -> str:
        return f"ThematicAgent(signature='{self.signature}', theme='{self.theme}', stocks={len(self.theme_stocks)})"

    def __repr__(self) -> str:
        return self.__str__()


if __name__ == "__main__":
    # 测试代码
    agent = ThematicAgent(
        signature="test-thematic",
        basemodel="anthropic/claude-3.7-sonnet",
        theme="ai_semiconductor",
        max_stock_weight=0.20,
        min_cash_ratio=0.01
    )

    print("\n" + "="*60)
    print(agent)
    print("="*60)
    print(agent.get_strategy_description())
