# 🎯 独立风险/机会信号检测器

一个可单独运行的交易信号检测工具，基于DeepSeek成功策略（+10.61%收益）的实战经验开发。

## 📋 功能特性

### 🔴 风险信号检测

| 风险类型 | 检测内容 | 触发条件 |
|---------|---------|---------|
| **市场风险** | 市场暴跌、波动率飙升 | 跌幅>3.5%, VIX>30 |
| **持仓风险** | 单股权重过高 | 权重>20% |
| **现金风险** | 现金比例异常 | <1% 或 >3% |
| **新闻风险** | 贸易战、政策变化 | 情绪指数>0.7 |

### 💡 机会信号识别

| 机会类型 | 识别标准 | 置信度 |
|---------|---------|--------|
| **超跌机会** | 主题股暴跌>5% | 极高 🔥 |
| **回调买入** | 主题股回调2-5% | 高 ⭐ |
| **权重不足** | 核心股权重<8% | 中等 💫 |
| **强势突破** | 上涨>3%且权重低 | 中等 💫 |

---

## 🚀 快速开始

### 1. 基础使用

```bash
# 分析今日市场信号
python signal_detector/detector_runner.py

# 分析指定日期
python signal_detector/detector_runner.py --date 2025-10-24

# 分析DeepSeek的持仓（基于实际数据）
python signal_detector/detector_runner.py --date 2025-10-24 --model deepseek-chat-v3.1
```

### 2. 高级用法

```bash
# 指定投资主题
python signal_detector/detector_runner.py --date 2025-10-24 --theme ai_semiconductor

# 可选主题:
#   - ai_semiconductor (AI/半导体)
#   - tech_giants (科技巨头)
#   - cloud (云计算)

# 保存报告
python signal_detector/detector_runner.py --date 2025-10-24 --output my_report.json

# 使用自定义配置
python signal_detector/detector_runner.py --config my_config.json
```

---

## 📊 输出示例

### 风险警告示例

```
⚠️ 风险警告 (3项):
   🔴 极高风险: 1项
   🟠 高风险: 2项

   1. 🔴 MARKET_CRASH [极高风险]
      描述: 市场暴跌 -3.6%
      建议: 立即减仓50%+，大幅提高现金比例至20%+
      评分: 90/100

   2. 🟠 POSITION_OVERWEIGHT_HIGH [高风险]
      描述: NVDA 权重过高 25.0%
      建议: 卖出部分，降低至15-18%
      评分: 75/100

   3. 🟡 HIGH_CASH [中等风险]
      描述: 现金比例偏高 5.2%
      建议: 考虑买入优质标的
      评分: 50/100
```

### 机会识别示例

```
💡 买入机会 (5个):
   🔥 高置信度机会: 2个

   1. 🔥 NVDA - OVERSOLD [极高置信度]
      价格: $182.23 (-5.80%)
      建议: 强烈买入
      原因: 主题股超跌5.8%，抄底机会
      评分: 95/100

   2. ⭐ AMD - PULLBACK [高置信度]
      价格: $118.50 (-3.20%)
      建议: 逢低买入
      原因: 主题股回调3.2%，买入机会
      评分: 75/100

   3. 💫 ASML - UNDERWEIGHT [中等置信度]
      价格: $1,020.00 (+0.50%)
      建议: 加仓至10-15%
      原因: 主题核心股权重仅5.2%，配置不足
      评分: 55/100
```

---

## 🎯 实战案例

### 案例1：2025-10-10 贸易战威胁日

```bash
python signal_detector/detector_runner.py --date 2025-10-10 --model deepseek-chat-v3.1
```

**实际输出**：
```
⚠️ 风险警告:
   🔴 MARKET_CRASH - 市场暴跌 -3.6%
   建议: 立即减仓50%+

   🟠 HIGH_VOLATILITY - VIX波动率 28.5
   建议: 减少仓位，增加防御性资产
```

**DeepSeek实际操作**：
- ✅ 卖出NVDA 5股（减仓50%）
- ✅ 增加PEP、AEP防御性资产
- ✅ 现金比例提至17.3%

**结果**：成功避免进一步下跌


### 案例2：2025-10-16 恐慌后反弹

```bash
python signal_detector/detector_runner.py --date 2025-10-16 --model deepseek-chat-v3.1
```

**实际输出**：
```
💡 买入机会:
   🔥 NVDA - OVERSOLD (-5.8%)
   价格: $182.23
   建议: 强烈买入
   评分: 95/100
```

**DeepSeek实际操作**：
- ✅ 买入NVDA 2股 @ $182.23
- ✅ 买入AMD加仓

**结果**：赚取$11/股价差（5.8%）

---

## 📁 文件结构

```
signal_detector/
├── signal_engine.py      # 核心检测引擎
├── detector_runner.py    # 独立运行程序
├── README.md            # 使用文档（本文件）
├── reports/             # 报告输出目录
│   └── signal_report_2025-10-24.json
└── configs/             # 配置文件目录
    └── custom_config.json
```

---

## ⚙️ 配置说明

### 自定义配置文件

创建 `custom_config.json`:

```json
{
  "max_single_weight": 0.20,
  "critical_weight": 0.25,
  "min_cash_ratio": 0.01,
  "max_cash_ratio": 0.03,

  "risk_thresholds": {
    "market_drop": {
      "critical": -0.035,
      "high": -0.025,
      "medium": -0.015
    },
    "position_concentration": {
      "critical": 0.30,
      "high": 0.25,
      "medium": 0.20
    }
  },

  "opportunity_thresholds": {
    "oversold": -0.05,
    "pullback": -0.02,
    "strong_momentum": 0.03
  }
}
```

使用配置：
```bash
python signal_detector/detector_runner.py --config custom_config.json
```

---

## 🔧 API使用

### Python脚本中使用

```python
from signal_detector.signal_engine import SignalEngine

# 创建引擎
engine = SignalEngine()

# 准备数据
market_data = {
    'market_change': -0.028,
    'vix': 26.5,
    'current_prices': {'NVDA': 180.50, 'MSFT': 420.00},
    'previous_prices': {'NVDA': 189.00, 'MSFT': 425.00}
}

portfolio = {
    'positions': {'NVDA': 50, 'MSFT': 10},
    'cash': 500.0,
    'total_value': 12500.0
}

# 生成信号
signals = engine.generate_daily_signals(
    market_data,
    portfolio,
    theme_stocks=['NVDA', 'AMD']
)

# 处理结果
for risk in signals['risk_signals']:
    print(f"风险: {risk['description']}")

for opp in signals['opportunity_signals']:
    print(f"机会: {opp['symbol']} - {opp['action']}")
```

---

## 📈 信号评分系统

### 风险评分 (0-100)

| 分数范围 | 风险等级 | 建议操作 |
|---------|---------|---------|
| 90-100 | 🔴 极高 | 立即减仓50%+ |
| 70-89 | 🟠 高 | 适度减仓30% |
| 50-69 | 🟡 中等 | 停止买入，观望 |
| 0-49 | 🟢 低 | 正常操作 |

### 机会评分 (0-100)

| 分数范围 | 置信度 | 建议操作 |
|---------|--------|---------|
| 90-100 | 🔥 极高 | 强烈买入 |
| 75-89 | ⭐ 高 | 逢低买入 |
| 60-74 | 💫 中等 | 小幅加仓 |
| 0-59 | ✨ 低 | 观望 |

---

## 🎓 实战建议

### 1. 每日检查流程

```bash
# 步骤1: 早盘前分析（9:00 AM）
python signal_detector/detector_runner.py --date today

# 步骤2: 检查风险警告
# 如果出现🔴极高风险 → 立即准备减仓

# 步骤3: 识别机会
# 如果出现🔥高置信度机会 → 准备买入

# 步骤4: 盘中监控（可选）
# 每小时运行一次，监控风险变化
```

### 2. 回测历史信号

```bash
# 分析DeepSeek在关键日期的信号
python signal_detector/detector_runner.py --date 2025-10-10 --model deepseek-chat-v3.1
python signal_detector/detector_runner.py --date 2025-10-16 --model deepseek-chat-v3.1
python signal_detector/detector_runner.py --date 2025-10-23 --model deepseek-chat-v3.1

# 对比信号与实际操作，验证准确性
```

### 3. 批量分析

```bash
# 创建批量分析脚本
for date in 2025-10-{02..24}; do
    echo "分析 $date"
    python signal_detector/detector_runner.py --date $date --output reports/$date.json
done
```

---

## 🔍 故障排除

### 常见问题

**Q: 提示"No module named 'dotenv'"**
```bash
# 解决：安装依赖
pip install python-dotenv
```

**Q: 找不到价格数据**
```bash
# 解决：确保数据文件存在
ls data/merged.jsonl
# 如果不存在，运行数据获取脚本
cd data && python get_daily_price.py && python merge_jsonl.py
```

**Q: 模型数据不存在**
```bash
# 解决：检查模型数据目录
ls data/agent_data/deepseek-chat-v3.1/position/
# 如果不存在，先运行主交易程序生成数据
python main.py
```

---

## 📝 输出格式

### JSON报告格式

```json
{
  "risk_signals": [
    {
      "signal_type": "MARKET_CRASH",
      "level": "极高",
      "score": 90,
      "description": "市场暴跌 -3.6%",
      "action": "立即减仓50%+",
      "details": {"market_change": -0.036},
      "timestamp": "2025-10-10T09:30:00"
    }
  ],
  "opportunity_signals": [
    {
      "symbol": "NVDA",
      "opportunity_type": "OVERSOLD",
      "confidence": "极高",
      "score": 95,
      "price": 182.23,
      "price_change": -0.058,
      "action": "强烈买入",
      "reason": "主题股超跌5.8%，抄底机会",
      "details": {"is_theme": true, "current_weight": 0.06},
      "timestamp": "2025-10-16T09:30:00"
    }
  ],
  "summary": {
    "timestamp": "2025-10-24T09:30:00",
    "total_risks": 3,
    "critical_risks": 1,
    "high_risks": 2,
    "total_opportunities": 5,
    "high_confidence_opportunities": 2,
    "portfolio_value": 10968.03,
    "cash_ratio": 0.0053
  }
}
```

---

## 🚀 未来计划

- [ ] 添加实时WebSocket数据源
- [ ] 集成邮件/短信告警
- [ ] Web可视化Dashboard
- [ ] 历史信号回测分析
- [ ] 机器学习信号优化
- [ ] 多市场支持（A股、港股）

---

## 📞 支持

如有问题或建议，请联系：
- 📧 Email: your-email@example.com
- 💬 GitHub Issues: [提交问题](https://github.com/your-repo/issues)

---

## 📄 许可证

MIT License

---

**免责声明**: 本工具仅供参考，不构成投资建议。投资有风险，入市需谨慎。
