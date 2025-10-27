# AI-Trader 最优决策频率设计

本文档深入分析"一天只决策一次"的局限性，并提出更合理的多时段决策方案。

---

## 🚨 问题分析：单次决策的局限性

### 当前模式的核心问题

**现状**：每天只在虚拟的"10:00"执行1次决策会话

```
09:30 - 开盘
   ↓
10:00 - AI决策（唯一的决策时点）
   ├─ 基于开盘价做所有决策
   ├─ 一次性完成买入/卖出
   └─ 输出 <FINISH_SIGNAL>
   ↓
10:00-16:00 - 市场波动（AI无法响应）
   ├─ 11:00: NVDA涨了5%  ❌ 无法止盈
   ├─ 13:00: 重大新闻发布  ❌ 无法调整
   ├─ 15:00: 尾盘跳水     ❌ 无法止损
   └─ AI处于"盲区"状态
   ↓
16:00 - 收盘（等待明天）
```

---

### 6大核心问题

#### 问题1：错过盘中机会 ⚠️⚠️⚠️

**场景**：
```
10:00 - AI买入 NVDA @ $140
11:30 - NVDA 涨到 $154（涨幅10%）
        ↓
        AI无法感知，无法止盈
        ↓
15:30 - NVDA 回落到 $142
        ↓
        错过最佳卖点，利润从10%缩水到1.4%
```

**真实数据验证**：
```python
# 从回测数据看到的模式
2025-10-22:
  - 10:00 买入2只，卖出3只
  - 但如果有14:00的决策，可能会有不同的操作

2025-10-23:
  - 10:00 买入3只，卖出1只
  - 盘中可能有更好的买入时机
```

---

#### 问题2：无法及时止损 ⚠️⚠️⚠️⚠️⚠️

**场景**：
```
10:00 - AI持有 TSLA 100股 @ $250
12:00 - 突发负面新闻，TSLA跌至 $225（-10%）
        ↓
        AI无法响应，只能眼看亏损扩大
        ↓
15:00 - TSLA继续跌至 $210（-16%）
        ↓
次日10:00 - AI才能决策（已损失16%）
```

**风险**：
- 单日最大回撤可能超过20%
- 黑天鹅事件无法应对
- 隔夜风险无法控制

---

#### 问题3：价格基准失真 ⚠️⚠️

**问题**：所有交易都用开盘价，但：

```
开盘价 vs 实际成交价的偏差：

NVDA 2025-10-15:
  - 开盘: $140.00  ← AI决策基准
  - 10:30均价: $142.50  ← 实际能买到的价格
  - 收盘: $145.00
  - 偏差: +3.6%（严重影响收益计算）

如果10:00决策，但市场已经涨了2%，
AI基于过时价格做的决策可能不合理
```

---

#### 问题4：忽略盘中趋势 ⚠️⚠️

**场景**：
```
09:30-10:00 早盘
  - 市场整体上涨1%
  - AI在10:00基于开盘价决策（偏乐观）

10:00-12:00 午盘
  - 市场反转下跌3%
  - AI无法调整，继续持有

12:00-16:00 尾盘
  - 市场继续下跌2%
  - AI仍然无法响应

结果：AI的决策基于早盘趋势，错失午盘和尾盘的信号
```

---

#### 问题5：无法应对突发事件 ⚠️⚠️⚠️⚠️

**场景案例**：

| 时间 | 事件 | AI是否响应 | 合理操作 | 实际操作 |
|------|------|-----------|---------|---------|
| 11:00 | Apple发布超预期财报 | ❌ | 立即买入AAPL | 等到明天 |
| 13:00 | Fed突然降息50bp | ❌ | 增加科技股仓位 | 等到明天 |
| 14:30 | NVDA宣布重大并购 | ❌ | 评估影响并调仓 | 等到明天 |
| 15:45 | 尾盘异常放量 | ❌ | 止盈/止损 | 等到明天 |

**后果**：
- 错过最佳进场时机（财报后30分钟涨幅最大）
- 错过避险机会（政策发布后波动最剧烈）
- 隔夜风险增加

---

#### 问题6：策略单一化 ⚠️⚠️

**现状**：
```
AI只能执行"一次性建仓/调仓"策略

无法实现：
  ❌ 分批建仓（早盘1/3，午盘1/3，尾盘1/3）
  ❌ 动态止盈（涨5%卖1/2，涨10%全卖）
  ❌ 追踪止损（从最高点回落3%时卖出）
  ❌ 网格交易（在价格区间内多次买卖）
```

---

## 📊 数据支撑：回测行为分析

### 真实数据统计

```python
# 分析 claude-3.7-sonnet 的17个交易日

总交易日: 17天
有卖出的天数: 15天（88.2%）
只买不卖的天数: 2天（11.8%）

平均每天操作:
  - 买入: 1.8次
  - 卖出: 1.2次
  - 总操作: 3.0次

结论：
✅ AI几乎每天都在调仓（88%有卖出）
✅ 说明策略是动态的，不是买入持有
⚠️ 但所有操作都集中在"10:00"这一个时点
```

### 操作类型分布

```
2025-10-22 (典型交易日):
  10:00 执行:
    - buy("AMZN", 1)
    - buy("PEP", 2)
    - sell("MSFT", 3)
    - sell("AAPL", 5)
    - sell("NVDA", 10)

  问题：
  ❓ 如果NVDA在13:00又涨了8%，AI能再卖吗？ → 不能
  ❓ 如果AAPL在15:00跌破支撑，AI能补仓吗？ → 不能
  ❓ 如果尾盘整体跳水，AI能清仓吗？ → 不能
```

---

## ✅ 解决方案：多时段决策框架

### 方案概览

```
┌────────────────────────────────────────────────────────┐
│ 多时段决策模式（推荐）                                  │
└────────────────────────────────────────────────────────┘

美东时间交易日程：

09:30 ━━━━━ 开盘
   ↓
10:00 ━━━━━ 决策时段1：早盘分析 ⭐⭐⭐
   ├─ 目标：基于开盘趋势建仓
   ├─ 重点：分析隔夜消息、盘前异动
   └─ 操作：建立核心仓位（50-70%资金）
   ↓
12:00 ━━━━━ 决策时段2：午盘调整 ⭐⭐
   ├─ 目标：根据上午走势调仓
   ├─ 重点：评估早盘决策效果
   └─ 操作：止盈/止损，补仓/减仓（20-30%资金）
   ↓
14:00 ━━━━━ 决策时段3：下午复盘（可选）⭐
   ├─ 目标：应对午间新闻和趋势变化
   ├─ 重点：检查是否有突发事件
   └─ 操作：微调仓位（10-20%资金）
   ↓
15:30 ━━━━━ 决策时段4：尾盘决策 ⭐⭐⭐⭐
   ├─ 目标：控制隔夜风险
   ├─ 重点：决定持仓过夜比例
   └─ 操作：止盈/止损，锁定利润
   ↓
16:00 ━━━━━ 收盘
```

---

### 方案A：双时段模式（推荐初期）

**配置**：
```json
{
  "schedule": {
    "sessions": [
      {
        "time": "10:00",
        "name": "morning",
        "strategy": "initial_position",
        "max_portfolio_change": 0.7  // 最多用70%资金
      },
      {
        "time": "15:30",
        "name": "closing",
        "strategy": "risk_control",
        "max_portfolio_change": 0.5  // 最多调整50%仓位
      }
    ]
  }
}
```

**执行流程**：
```python
# 10:00 早盘会话
系统提示词（特定化）:
"""
Current time: 10:00 AM (Market just opened)
Your task: INITIAL POSITIONING
- Analyze overnight news and pre-market moves
- Build core positions (50-70% of cash)
- Focus on high-conviction stocks
- You will have another chance at 15:30 to adjust
"""

Agent操作:
  - buy("NVDA", 10) @ $140
  - buy("AAPL", 5) @ $180
  - 使用资金: $2,300 / $10,000 (23%)

---

# 15:30 尾盘会话
系统提示词（特定化）:
"""
Current time: 15:30 PM (30 min before close)
Your task: RISK MANAGEMENT
- Review today's performance
- Current positions: NVDA +8%, AAPL -2%
- Decide overnight holdings
- Close weak positions, lock profits on strong ones
"""

Agent操作:
  - sell("NVDA", 5) @ $151 (止盈一半，锁定$55利润)
  - sell("AAPL", 5) @ $176 (止损全部，亏损$20)
  - 调整后持仓: NVDA 5股，CASH $8,455
```

**优势**：
- ✅ 早盘建仓，尾盘调整（符合交易习惯）
- ✅ 控制隔夜风险
- ✅ 代码改动小（~150行）
- ✅ API成本可控（2次/天 × $0.01 = $0.02/天）

---

### 方案B：三时段模式（推荐进阶）

**时间点**：
```
10:00 - 早盘建仓（50-60%资金）
12:00 - 午盘调整（20-30%资金）
15:30 - 尾盘风控（调整50%仓位）
```

**差异化提示词**：
```python
# prompts/session_prompts.py

MORNING_PROMPT = """
Session: MORNING (10:00 AM)
Objective: Initial positioning
Available cash: {cash}
Suggested allocation: 50-60% of total capital
Focus: High-conviction long-term plays
Risk: Moderate (you can adjust later)
"""

MIDDAY_PROMPT = """
Session: MIDDAY (12:00 PM)
Objective: Tactical adjustment
Morning positions: {morning_positions}
Morning P&L: {morning_pnl}
Suggested allocation: 20-30% additional capital
Focus: Capture mid-day momentum or correct mistakes
Risk: Low to Moderate
"""

CLOSING_PROMPT = """
Session: CLOSING (15:30 PM)
Objective: Risk control before close
Full day positions: {all_positions}
Full day P&L: {total_pnl}
Suggested action: Reduce overnight exposure
Focus: Lock profits, cut losses, manage overnight risk
Risk: Conservative (market closing soon)
"""
```

**优势**：
- ✅ 更灵活的仓位管理
- ✅ 捕捉盘中机会
- ✅ 每个时段有明确目标
- ✅ 降低单次决策压力

**成本**：
- API: 3次/天 × $0.01 = $0.03/天
- 可接受范围

---

### 方案C：四时段模式（生产环境）

**完整配置**：
```json
{
  "schedule": {
    "sessions": [
      {
        "time": "10:00",
        "name": "morning_open",
        "max_cash_usage": 0.60,
        "min_cash_reserve": 0.40
      },
      {
        "time": "12:00",
        "name": "midday_adjust",
        "max_cash_usage": 0.30,
        "min_cash_reserve": 0.20
      },
      {
        "time": "14:00",
        "name": "afternoon_check",
        "max_cash_usage": 0.15,
        "min_cash_reserve": 0.10
      },
      {
        "time": "15:30",
        "name": "closing_risk",
        "force_max_overnight_exposure": 0.80
      }
    ]
  },
  "risk_limits": {
    "max_single_position": 0.20,  // 单只股票最多20%
    "max_daily_trades": 15,        // 每天最多15笔
    "max_total_exposure": 0.95     // 最多95%仓位
  }
}
```

**一天的完整流程示例**：
```
09:30 - 开盘

10:00 - 早盘会话（6分钟）
  Agent分析隔夜新闻
  ├─ buy("NVDA", 10) @ $140  → 仓位14%
  ├─ buy("AAPL", 8) @ $180   → 仓位14.4%
  └─ 现金余额: $5,760 (57.6%)

12:00 - 午盘会话（4分钟）
  NVDA涨到$147 (+5%), AAPL跌到$178 (-1.1%)
  ├─ sell("NVDA", 5) @ $147  → 止盈一半
  ├─ buy("MSFT", 3) @ $420   → 新增仓位12.6%
  └─ 现金余额: $6,255 (62.5%)

14:00 - 下午会话（3分钟）
  Fed突然宣布利率决议，市场波动
  ├─ 检查持仓风险
  ├─ sell("AAPL", 3) @ $176  → 减少亏损仓位
  └─ 现金余额: $6,783 (67.8%)

15:30 - 尾盘会话（5分钟）
  评估全天收益，决定隔夜持仓
  ├─ NVDA 5股: +$35 (+5%)
  ├─ AAPL 5股: -$20 (-2.8%)
  ├─ MSFT 3股: +$15 (+1.2%)
  决策：
  ├─ sell("AAPL", 5) @ $176  → 止损清仓
  ├─ 持有NVDA和MSFT过夜
  └─ 隔夜仓位占比: 32% (符合风控)

16:00 - 收盘
  全天收益: +$30 (+0.3%)
  持仓: NVDA 5股, MSFT 3股
  现金: $7,663
```

---

## 🎯 推荐实施方案

### 阶段性升级路径

#### 第1周：单时段（当前）
```
10:00 - 单次决策
成本: $0.01/天
目标: 系统验证
```

#### 第2-4周：双时段
```
10:00 - 早盘建仓
15:30 - 尾盘风控
成本: $0.02/天
目标: 验证多时段逻辑
```

#### 第5-8周：三时段
```
10:00 - 早盘
12:00 - 午盘
15:30 - 尾盘
成本: $0.03/天
目标: 优化仓位管理
```

#### 第9周+：四时段
```
10:00, 12:00, 14:00, 15:30
成本: $0.04/天
目标: 生产级运行
```

---

## 📊 效果对比预测

### 单时段 vs 多时段

| 指标 | 单时段(10:00) | 双时段(10:00+15:30) | 三时段 | 四时段 |
|------|--------------|-------------------|-------|-------|
| **止盈能力** | ⭐ 差 | ⭐⭐⭐ 好 | ⭐⭐⭐⭐ 很好 | ⭐⭐⭐⭐⭐ 优秀 |
| **止损速度** | ⭐ 延迟1天 | ⭐⭐⭐ 延迟5.5h | ⭐⭐⭐⭐ 延迟3.5h | ⭐⭐⭐⭐ 延迟1.5h |
| **隔夜风险** | ⭐ 高（无控制） | ⭐⭐⭐⭐ 低（尾盘减仓） | ⭐⭐⭐⭐ 低 | ⭐⭐⭐⭐⭐ 很低 |
| **实现复杂度** | ⭐ 简单 | ⭐⭐ 较简单 | ⭐⭐⭐ 中等 | ⭐⭐⭐⭐ 复杂 |
| **API成本** | $0.01/天 | $0.02/天 | $0.03/天 | $0.04/天 |
| **预期夏普** | 0.8-1.0 | 1.2-1.5 | 1.5-1.8 | 1.8-2.2 |
| **最大回撤** | -15% | -10% | -8% | -6% |

---

## 🔧 实现代码框架

### 多时段系统提示词生成

```python
# prompts/session_prompts.py

def get_session_system_prompt(
    today_date: str,
    session_name: str,  # "morning", "midday", "afternoon", "closing"
    signature: str
) -> str:
    """生成特定时段的系统提示词"""

    # 基础信息
    base_info = {
        "date": today_date,
        "positions": get_today_init_position(today_date, signature),
        "yesterday_close": get_yesterday_close_price(today_date),
        "today_price": get_current_price(today_date, session_name),  # 关键：不同时段用不同价格
    }

    # 时段特定指令
    session_configs = {
        "morning": {
            "time": "10:00 AM",
            "objective": "Initial positioning based on overnight news",
            "cash_allocation": "50-60% of total capital",
            "risk_profile": "Moderate",
            "focus": "High-conviction long-term positions",
            "reminder": "You will have opportunities to adjust at 12:00 and 15:30"
        },
        "midday": {
            "time": "12:00 PM",
            "objective": "Tactical adjustment based on morning performance",
            "cash_allocation": "20-30% of remaining capital",
            "risk_profile": "Low to Moderate",
            "focus": "Momentum plays or error correction",
            "reminder": "Last major adjustment before closing session at 15:30"
        },
        "afternoon": {
            "time": "14:00 PM",
            "objective": "Review and fine-tune before close",
            "cash_allocation": "10-15% of remaining capital",
            "risk_profile": "Low",
            "focus": "React to afternoon news or trend changes",
            "reminder": "Final adjustment at 15:30 for overnight risk"
        },
        "closing": {
            "time": "15:30 PM",
            "objective": "Manage overnight risk",
            "cash_allocation": "Can adjust up to 50% of positions",
            "risk_profile": "Conservative",
            "focus": "Lock profits, cut losses, reduce exposure",
            "reminder": "Market closes in 30 minutes - be decisive"
        }
    }

    session_config = session_configs[session_name]

    # 计算当前会话的盈亏
    session_pnl = calculate_session_pnl(today_date, session_name, signature)

    prompt = f"""
You are a stock trading assistant - {session_config['time']} Session

Today's date: {today_date}
Session: {session_name.upper()}
Objective: {session_config['objective']}

Current positions: {base_info['positions']}
Current prices: {base_info['today_price']}
Session P&L: {session_pnl}

Trading guidelines for this session:
- Cash allocation: {session_config['cash_allocation']}
- Risk profile: {session_config['risk_profile']}
- Focus: {session_config['focus']}
- Note: {session_config['reminder']}

When finished, output <FINISH_SIGNAL>
"""

    return prompt
```

### 主控制循环修改

```python
# main.py

async def run_live_trading_multi_session():
    """多时段模拟盘交易"""
    today = datetime.now(pytz.timezone('US/Eastern'))
    today_str = today.strftime("%Y-%m-%d")

    # 定义会话时间表
    sessions = [
        {"time": "10:00", "name": "morning"},
        {"time": "12:00", "name": "midday"},
        {"time": "14:00", "name": "afternoon"},
        {"time": "15:30", "name": "closing"},
    ]

    for session in sessions:
        session_time = datetime.strptime(f"{today_str} {session['time']}", "%Y-%m-%d %H:%M")
        session_time = pytz.timezone('US/Eastern').localize(session_time)

        # 等待到会话时间
        wait_until(session_time)

        # 运行该时段的交易会话
        print(f"🔔 Starting {session['name']} session at {session['time']}")

        await agent.run_session(
            date=today_str,
            session_name=session['name']
        )

        print(f"✅ {session['name']} session completed")

# 使用Cron每天早上9:00启动，然后内部等待各个时段
# 0 9 * * 1-5 cd /path && python main.py
```

---

## 💡 关键设计原则

### 1. 时段差异化

每个时段有不同的：
- ✅ **目标**：建仓 vs 调整 vs 风控
- ✅ **价格**：开盘价 vs 实时价 vs 收盘前价
- ✅ **资金限制**：60% vs 30% vs 15%
- ✅ **风险偏好**：激进 vs 中性 vs 保守

### 2. 资金分配控制

```python
# 防止早盘all-in
MAX_CASH_USAGE = {
    "morning": 0.60,   # 最多60%
    "midday": 0.30,    # 额外30%
    "afternoon": 0.15, # 额外15%
    "closing": 1.0     # 可以调整全部仓位
}
```

### 3. 仓位连续性

```python
# 每个时段都能看到上一时段的结果
midday_positions = get_latest_position(today, signature)
# 包含morning时段的所有交易结果
```

### 4. 限流保护

```python
# 防止单日过度交易
MAX_TRADES_PER_SESSION = {
    "morning": 8,
    "midday": 5,
    "afternoon": 3,
    "closing": 5
}
# 总计：最多21笔/天
```

---

## 🎯 总结

### 核心观点

**问题**：一天只分析一次确实不合理

**原因**：
1. ❌ 错过盘中止盈机会（NVDA涨10%无法卖）
2. ❌ 无法及时止损（突发负面新闻无法应对）
3. ❌ 价格基准失真（全用开盘价）
4. ❌ 忽略盘中趋势（市场反转无法调整）
5. ❌ 无法应对突发事件（财报/政策）
6. ❌ 策略单一化（无法分批建仓）

**解决方案**：多时段决策

| 方案 | 时段数 | 成本 | 推荐阶段 |
|------|-------|------|---------|
| 双时段 | 10:00 + 15:30 | $0.02/天 | 初期验证 ⭐⭐⭐⭐⭐ |
| 三时段 | +12:00 | $0.03/天 | 进阶优化 ⭐⭐⭐⭐ |
| 四时段 | +14:00 | $0.04/天 | 生产环境 ⭐⭐⭐ |

**立即行动**：
- ✅ 第1步：实现双时段（10:00早盘 + 15:30尾盘）
- ✅ 代码量：~200行
- ✅ 工期：2-3天
- ✅ 效果：大幅提升风控能力

---

**文档版本**: 1.0
**最后更新**: 2025-10-27
**作者**: AI-Trader Team
