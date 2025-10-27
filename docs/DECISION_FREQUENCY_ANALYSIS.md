# AI-Trader 决策频率与触发机制分析

本文档深入分析AI-Trader的决策机制，对比历史回测和实时模拟盘的不同触发策略。

---

## 📋 目录

1. [当前回测决策机制](#当前回测决策机制)
2. [决策频率实证分析](#决策频率实证分析)
3. [实时模拟盘触发策略](#实时模拟盘触发策略)
4. [定时分析 vs 事件触发](#定时分析-vs-事件触发)
5. [推荐方案](#推荐方案)

---

## 🔍 当前回测决策机制

### 核心问题回答

**Q: 一天决策几次？**

**A: 每天只触发1次决策会话，但会话内可能产生多次交易**

---

### 决策流程详解

```
┌─────────────────────────────────────────────────────────────┐
│ 每个交易日的完整流程                                          │
└─────────────────────────────────────────────────────────────┘

📅 日期: 2025-10-02 (单个交易日)
   │
   v
┌─────────────────────────────────────────────────────────────┐
│ Step 1: 启动单日交易会话 (run_trading_session)               │
│         - 每天只调用 1 次                                    │
│         - 时间点：任意（批量回测模式）                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│ Step 2: 生成系统提示词                                        │
│         - 今日日期: 2025-10-02                               │
│         - 昨日持仓: {"CASH": 10000.0, ...}                  │
│         - 今日价格: {"AAPL_price": 182.0, ...}              │
│                                                             │
│ Step 3: 发送初始查询                                         │
│         User: "Please analyze and update today's positions" │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│ Step 4: Agent 决策循环 (最多30步)                            │
│                                                             │
│   Round 1:                                                  │
│   ├─ Agent思考: "我需要分析市场并建仓"                        │
│   ├─ Tool调用: get_information("NVDA news")                │
│   └─ Tool结果: {"results": [...]}                          │
│                                                             │
│   Round 2:                                                  │
│   ├─ Agent思考: "NVDA前景好，买入10股"                       │
│   ├─ Tool调用: buy("NVDA", 10)           ← 交易1           │
│   └─ Tool结果: {"NVDA": 10, "CASH": 8580}                  │
│                                                             │
│   Round 3:                                                  │
│   ├─ Agent思考: "继续买入MSFT"                               │
│   ├─ Tool调用: buy("MSFT", 3)            ← 交易2           │
│   └─ Tool结果: {"MSFT": 3, "CASH": 7314}                   │
│                                                             │
│   Round 4:                                                  │
│   ├─ Agent思考: "买入AAPL"                                  │
│   ├─ Tool调用: buy("AAPL", 5)            ← 交易3           │
│   └─ Tool结果: {"AAPL": 5, "CASH": 6404}                   │
│                                                             │
│   ... (继续到第8次交易)                                      │
│                                                             │
│   Round N:                                                  │
│   ├─ Agent思考: "投资组合已完成"                             │
│   └─ 输出: <FINISH_SIGNAL>               ← 会话结束         │
└─────────────────────────────────────────────────────────────┘

结果: 1次决策会话 = 8次交易记录
```

---

### 关键代码位置

#### 1. 日期循环（每天调用1次）

**文件**: `base_agent.py:375-410`

```python
async def run_date_range(self, init_date: str, end_date: str):
    """运行所有交易日"""
    trading_dates = self.get_trading_dates(init_date, end_date)

    # 每个日期调用一次交易会话
    for date in trading_dates:  # ["2025-10-01", "2025-10-02", ...]
        print(f"🔄 Processing Date: {date}")

        # 每天只调用1次
        await self.run_trading_session(date)  ⬅️ 每天1次
```

#### 2. 单日交易会话（内部可多次交易）

**文件**: `base_agent.py:193-269`

```python
async def run_trading_session(self, today_date: str):
    """运行单日交易会话"""

    # 1. 生成今日系统提示词（只生成1次）
    self.agent = create_agent(
        system_prompt=get_agent_system_prompt(today_date, self.signature)
    )

    # 2. 发送初始查询（只发送1次）
    user_query = [{
        "role": "user",
        "content": f"Please analyze and update today's ({today_date}) positions."
    }]

    # 3. Agent决策循环（可能多次交易）
    current_step = 0
    while current_step < self.max_steps:  # 最多30步
        current_step += 1

        # Agent调用工具
        response = await self._ainvoke_with_retry(message)

        # 检查是否完成
        if STOP_SIGNAL in agent_response:
            break  # 结束会话

        # 提取工具结果，继续下一轮
        tool_response = extract_tool_messages(response)
        message.extend([
            {"role": "assistant", "content": agent_response},
            {"role": "user", "content": f'Tool results: {tool_response}'}
        ])
```

#### 3. 交易执行（每次buy/sell调用）

**文件**: `agent_tools/tool_trade.py:15-103`

```python
@mcp.tool()
def buy(symbol: str, amount: int):
    """买入股票"""
    # 每次buy()调用都写入一条记录
    with open(position_file_path, "a") as f:
        f.write(json.dumps({
            "date": today_date,
            "id": current_action_id + 1,
            "this_action": {"action": "buy", "symbol": symbol, "amount": amount},
            "positions": new_position
        }) + "\n")  # ⬅️ 每次交易记录1行
```

---

## 📊 决策频率实证分析

### 真实数据统计

从 `claude-3.7-sonnet` 模型的实际运行数据：

```bash
# 数据来源: data/agent_data/claude-3.7-sonnet/position/position.jsonl

2025-10-01: 1 次交易  (初始建仓)
2025-10-02: 8 次交易  (分批买入多只股票)
2025-10-03: 3 次交易  (调整仓位)
2025-10-06: 3 次交易  (周末后重新建仓)
2025-10-07: 1 次交易  (小幅调整)
2025-10-08: 4 次交易  (中等调整)
...
```

### 2025-10-02 的8次交易详情

```
10:00 AM (虚拟时间) - 启动会话
  └─ User: "Please analyze and update today's positions"

Step 1-2: 信息收集
  └─ get_information("NVDA news")
  └─ get_information("market trends")

Step 3: 交易1 - buy("NVDA", 10)
  └─ 持仓: {"NVDA": 10, "CASH": 8580}

Step 4: 交易2 - buy("MSFT", 3)
  └─ 持仓: {"NVDA": 10, "MSFT": 3, "CASH": 7314}

Step 5: 交易3 - buy("AAPL", 5)
  └─ 持仓: {"NVDA": 10, "MSFT": 3, "AAPL": 5, "CASH": 6404}

Step 6: 交易4 - buy("PLTR", 5)
Step 7: 交易5 - buy("ASML", 1)
Step 8: 交易6 - buy("AMD", 5)
Step 9: 交易7 - buy("META", 1)
Step 10: 交易8 - buy("AVGO", 4)

Step 11: Agent输出 <FINISH_SIGNAL>
  └─ 会话结束

总耗时: 约2-3分钟 (取决于API延迟和Agent思考)
```

---

### 决策机制总结

| 维度 | 当前回测模式 |
|------|------------|
| **会话触发频率** | 每天1次 |
| **触发时间点** | 批量处理时按顺序（无实际时间概念） |
| **单次会话内交易次数** | 不限制（由Agent决定，通常1-8次） |
| **最大决策步数** | 30步（max_steps配置） |
| **会话持续时间** | 2-5分钟（取决于Agent思考和API调用） |
| **交易价格** | 统一使用当天开盘价 |
| **是否跨时段** | 否，单次会话内完成所有决策 |

---

## 🚀 实时模拟盘触发策略

### 策略对比

实时模拟盘有两种核心策略：

```
┌──────────────────────────────────────────────────────────────┐
│ 策略A: 定时分析（Time-Based Trigger）                         │
└──────────────────────────────────────────────────────────────┘

特点: 固定时间点执行，类似当前回测模式

⏰ 09:30 - 市场开盘
   └─ 触发器: 无动作（等待开盘稳定）

⏰ 10:00 - 早盘分析时段
   └─ 触发器: 运行1次完整决策会话
   └─ Agent获取最新价格 → 分析 → 交易
   └─ 会话结束后等待下一个时间点

⏰ 14:00 - 午盘分析时段（可选）
   └─ 触发器: 运行1次完整决策会话

⏰ 15:45 - 尾盘分析时段（可选）
   └─ 触发器: 运行1次完整决策会话

⏰ 16:00 - 市场收盘
   └─ 触发器: 无动作（等待明天）

┌──────────────────────────────────────────────────────────────┐
│ 策略B: 事件触发（Event-Based Trigger）                        │
└──────────────────────────────────────────────────────────────┘

特点: 基于市场事件实时响应

📊 事件1: 持仓股票涨跌幅 > 5%
   └─ 触发器: 立即运行决策会话
   └─ 示例: NVDA涨了8% → 触发止盈分析

📰 事件2: 重大新闻发布
   └─ 触发器: 立即运行决策会话
   └─ 示例: Apple发布财报 → 触发持仓调整

⏰ 事件3: 固定时间点
   └─ 触发器: 作为兜底策略
   └─ 示例: 每天10:00必须检查一次

💸 事件4: 市场波动率突增
   └─ 触发器: VIX指数上涨 > 10%
   └─ 示例: 市场恐慌 → 触发风控决策
```

---

## ⚖️ 定时分析 vs 事件触发

### 详细对比表

| 维度 | 定时分析 | 事件触发 | 混合模式 |
|------|---------|---------|---------|
| **实现复杂度** | ⭐ 简单 | ⭐⭐⭐⭐ 复杂 | ⭐⭐⭐ 中等 |
| **代码修改量** | 最小（200行） | 较大（800行） | 中等（500行） |
| **响应速度** | 慢（固定间隔） | 快（实时响应） | 中（主要靠定时） |
| **交易频率** | 低（1-3次/天） | 高（不可预测） | 中（2-5次/天） |
| **API调用成本** | 低（可控） | 高（突发） | 中（基本可控） |
| **适用策略** | 日线级趋势跟踪 | 高频事件驱动 | 中长线+波动应对 |
| **风险控制** | ⭐⭐⭐ 稳定 | ⭐⭐ 不可预测 | ⭐⭐⭐⭐ 平衡 |
| **可回测性** | ⭐⭐⭐⭐⭐ 完美 | ⭐⭐ 难以复现 | ⭐⭐⭐⭐ 较好 |

---

### 方案A: 定时分析（推荐用于模拟盘）

#### 优点

✅ **实现简单**
- 最小化代码修改
- 复用现有架构
- 类似当前回测模式

✅ **成本可控**
- API调用次数固定
- 可精确预算费用
- 无突发流量

✅ **易于回测**
- 可精确复现历史决策
- 时间点固定，数据一致
- 便于策略优化

✅ **稳定可靠**
- 无并发冲突
- 无事件风暴
- 易于监控调试

#### 缺点

❌ **响应延迟**
- 错过短期机会
- 无法即时止损
- 市场突变反应慢

❌ **灵活性差**
- 固定时间点可能不合适
- 无法适应特殊情况

---

### 方案B: 事件触发

#### 优点

✅ **响应迅速**
- 实时捕捉机会
- 快速止损止盈
- 适应市场变化

✅ **策略灵活**
- 基于真实市场信号
- 个性化触发条件
- 支持复杂策略

#### 缺点

❌ **实现复杂**
- 需要实时行情订阅（WebSocket）
- 事件检测逻辑复杂
- 并发控制困难

❌ **成本不可控**
- 波动大时频繁触发
- API调用暴增
- LLM费用难以预测

❌ **难以回测**
- 事件时序难以重现
- 历史数据不完整
- 策略优化困难

❌ **可能过度交易**
- 频繁买卖增加成本
- 小波动引发无谓操作
- Agent可能"焦虑"

---

### 方案C: 混合模式（生产环境推荐）

#### 设计思路

```python
# 混合触发策略

class HybridTrigger:
    def __init__(self):
        # 定时触发（兜底）
        self.scheduled_times = ["10:00", "15:00"]  # 每天2次

        # 事件触发（可选）
        self.event_rules = [
            {"type": "price_change", "threshold": 0.05, "symbols": ["NVDA", "AAPL"]},
            {"type": "news", "keywords": ["earnings", "merger"]},
        ]

        # 限流保护
        self.max_sessions_per_day = 5
        self.min_interval = 3600  # 最小间隔1小时

    async def should_trigger(self):
        """判断是否应该触发决策"""

        # 1. 检查定时触发
        if self.is_scheduled_time():
            return True, "scheduled"

        # 2. 检查事件触发（如果启用）
        if self.event_enabled:
            for rule in self.event_rules:
                if self.check_event(rule):
                    # 检查限流
                    if self.can_trigger():
                        return True, f"event:{rule['type']}"

        return False, None

    def can_trigger(self):
        """限流检查"""
        # 今天已经触发几次
        if self.today_sessions >= self.max_sessions_per_day:
            return False

        # 距离上次触发是否超过最小间隔
        if time.time() - self.last_trigger < self.min_interval:
            return False

        return True
```

#### 优点

✅ **平衡性能和成本**
- 定时保证基本覆盖
- 事件增强响应能力
- 限流控制成本

✅ **渐进式升级**
- 初期只用定时
- 后期逐步加事件
- 灵活调整策略

✅ **风险可控**
- 最大触发次数限制
- 最小间隔保护
- 异常情况熔断

---

## 🎯 推荐方案

### 阶段1: 模拟盘初期（推荐定时分析）

**配置**:
```json
{
  "mode": "live",
  "trigger_strategy": "scheduled",
  "schedule": {
    "times": ["10:00"],  // 每天1次，美东时间10:00
    "timezone": "US/Eastern"
  },
  "session_config": {
    "max_steps": 30,
    "timeout": 300  // 5分钟超时
  }
}
```

**实现**:
```python
# main.py

async def run_scheduled_trading():
    """定时触发交易（简化版）"""
    today = datetime.now(pytz.timezone('US/Eastern'))

    # 1. 检查交易日
    if not is_trading_day(today):
        return

    # 2. 检查是否在交易时段
    if not is_market_open(today):
        return

    # 3. 检查今天是否已经交易
    if already_traded_today():
        print("⚠️  Already traded today")
        return

    # 4. 运行单次决策会话
    await run_single_day_trading(today.strftime("%Y-%m-%d"))

# 使用Cron定时任务
# 每个交易日 10:00 AM ET 运行
# 0 10 * * 1-5 cd /path && python main.py
```

**优势**:
- ✅ 代码改动最小（~200行）
- ✅ 复用现有回测架构
- ✅ 稳定可靠，易于维护
- ✅ 成本低（每天1次LLM调用）

**适用场景**:
- 模拟盘验证阶段
- 日线级别策略
- 中长期投资组合管理

---

### 阶段2: 生产环境（混合模式）

**配置**:
```json
{
  "mode": "live",
  "trigger_strategy": "hybrid",
  "schedule": {
    "times": ["10:00", "15:00"],  // 每天2次固定
    "timezone": "US/Eastern"
  },
  "event_triggers": {
    "enabled": true,
    "rules": [
      {
        "type": "price_change",
        "threshold": 0.05,  // 持仓股票涨跌5%
        "symbols": "holdings"  // 只监控持仓
      },
      {
        "type": "vix_spike",
        "threshold": 0.15  // VIX上涨15%
      }
    ],
    "limits": {
      "max_sessions_per_day": 5,
      "min_interval_seconds": 3600  // 最少1小时间隔
    }
  }
}
```

**实现**:
```python
# 新建 agent/live_trading_manager.py

class LiveTradingManager:
    def __init__(self, config):
        self.scheduled_times = config['schedule']['times']
        self.event_rules = config.get('event_triggers', {}).get('rules', [])
        self.max_sessions = config.get('event_triggers', {}).get('limits', {}).get('max_sessions_per_day', 5)

        self.today_sessions = 0
        self.last_trigger_time = None

    async def run_forever(self):
        """主循环"""
        while True:
            # 1. 检查定时触发
            should_run, reason = await self.should_trigger()

            if should_run:
                print(f"🚀 Trigger: {reason}")
                await self.execute_trading_session(reason)
                self.today_sessions += 1
                self.last_trigger_time = datetime.now()

            # 2. 每分钟检查一次
            await asyncio.sleep(60)

            # 3. 每日重置计数器
            if self.is_new_day():
                self.today_sessions = 0

    async def should_trigger(self):
        """判断是否触发"""
        # 1. 定时触发
        if self.is_scheduled_time():
            return True, "scheduled"

        # 2. 事件触发
        if self.event_enabled:
            for rule in self.event_rules:
                if await self.check_event(rule):
                    if self.can_trigger():
                        return True, f"event:{rule['type']}"

        return False, None

    def can_trigger(self):
        """限流检查"""
        if self.today_sessions >= self.max_sessions:
            return False

        if self.last_trigger_time:
            interval = (datetime.now() - self.last_trigger_time).seconds
            if interval < 3600:  # 1小时
                return False

        return True

    async def check_event(self, rule):
        """检查事件是否触发"""
        if rule['type'] == 'price_change':
            # 获取持仓股票
            holdings = get_current_holdings()

            # 获取实时价格
            current_prices = await get_realtime_prices(holdings.keys())

            # 获取基准价格（今日开盘价）
            base_prices = await get_open_prices_today(holdings.keys())

            # 计算涨跌幅
            for symbol in holdings:
                change = (current_prices[symbol] - base_prices[symbol]) / base_prices[symbol]
                if abs(change) > rule['threshold']:
                    print(f"⚡ {symbol} changed {change*100:.2f}%")
                    return True

        elif rule['type'] == 'vix_spike':
            # 检查VIX指数
            vix_current = await get_vix_index()
            vix_open = await get_vix_open_today()
            vix_change = (vix_current - vix_open) / vix_open

            if vix_change > rule['threshold']:
                print(f"⚡ VIX spiked {vix_change*100:.2f}%")
                return True

        return False
```

---

### 决策流程对比

#### 当前回测模式
```
每天1次决策会话
  └─ 10:00 (虚拟时间)
       ├─ 获取开盘价（静态数据）
       ├─ Agent思考 + 多次交易
       └─ 输出 <FINISH_SIGNAL>

结果: 1次会话，N次交易（1-8次）
```

#### 模拟盘定时模式（推荐初期）
```
每天1次决策会话
  └─ 10:00 (真实时间)
       ├─ 获取开盘价（Alpaca API）
       ├─ Agent思考 + 多次交易
       └─ 输出 <FINISH_SIGNAL>

结果: 1次会话，N次交易（1-8次）
API成本: ~$0.01/天（Claude）
```

#### 模拟盘混合模式（推荐生产）
```
每天2-5次决策会话
  ├─ 10:00 (定时触发)
  │    ├─ 获取最新价格
  │    ├─ Agent思考 + 交易
  │    └─ 结束
  │
  ├─ 13:25 (事件触发: NVDA涨6%)
  │    ├─ 获取最新价格
  │    ├─ Agent思考: "NVDA涨幅过大，止盈"
  │    ├─ sell("NVDA", 5)
  │    └─ 结束
  │
  └─ 15:00 (定时触发)
       ├─ 获取最新价格
       ├─ Agent最后检查
       └─ 结束

结果: 2-5次会话，N次交易
API成本: ~$0.02-0.05/天
```

---

## 📊 实施建议

### 第一步：模拟盘验证（1-2周）

**目标**: 验证系统稳定性

**配置**:
```json
{
  "trigger_strategy": "scheduled",
  "schedule": {"times": ["10:00"]},  // 每天1次
  "models": [{"name": "claude-3.7-sonnet", "enabled": true}]  // 单模型
}
```

**观察指标**:
- ✅ API调用成功率
- ✅ Agent决策质量
- ✅ 系统稳定性
- ✅ 成本控制

---

### 第二步：增加触发频率（2-4周）

**目标**: 测试多时段决策

**配置**:
```json
{
  "trigger_strategy": "scheduled",
  "schedule": {"times": ["10:00", "14:00", "15:30"]},  // 每天3次
}
```

**观察指标**:
- 交易频率是否合理
- 是否过度交易
- 策略收益变化

---

### 第三步：启用事件触发（1个月后）

**目标**: 增强响应能力

**配置**:
```json
{
  "trigger_strategy": "hybrid",
  "event_triggers": {
    "rules": [
      {"type": "price_change", "threshold": 0.05}
    ],
    "limits": {"max_sessions_per_day": 5}
  }
}
```

**观察指标**:
- 事件触发次数
- 响应及时性
- 成本增长

---

## 🎯 总结

### 关键结论

| 问题 | 回答 |
|------|------|
| **当前回测一天几次决策？** | 1次会话，但会话内可能多次交易（1-8次） |
| **模拟盘应该用定时还是事件？** | 初期用定时，后期可升级混合 |
| **推荐触发时间点？** | 早盘10:00（必须）+ 尾盘15:00（可选） |
| **最大触发次数限制？** | 建议5次/天（防止过度交易） |
| **实现优先级？** | 定时分析（P0） > 混合模式（P1） > 纯事件（P2） |

### 最小可行方案（MVP）

```python
# main.py - 最简实现

async def run_live_trading():
    """模拟盘模式：每天10:00运行一次"""
    today = datetime.now().strftime("%Y-%m-%d")

    # 复用现有逻辑
    await agent.run_trading_session(today)

# Cron配置
# 0 10 * * 1-5 cd /path && python main.py
```

**代码修改量**: ~50行
**工期**: 1天
**效果**: 与回测模式几乎一致，只是触发时间变为真实时间

---

**文档版本**: 1.0
**最后更新**: 2025-10-27
**作者**: AI-Trader Team
