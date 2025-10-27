# AI-Trader 决策流程与提示词详解

本文档详细说明AI模型在AI-Trader系统中的完整决策流程，以及如何通过提示词和MCP工具实现自主交易。

---

## 📋 目录

1. [整体架构流程](#整体架构流程)
2. [系统提示词机制](#系统提示词机制)
3. [MCP工具调用流程](#mcp工具调用流程)
4. [单日交易会话流程](#单日交易会话流程)
5. [完整决策示例](#完整决策示例)

---

## 🏗️ 整体架构流程

### 流程图

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. 主程序启动 (main.py)                                         │
│    - 加载配置文件 configs/default_config.json                    │
│    - 遍历所有启用的模型 (models[].enabled = true)               │
│    - 为每个模型创建独立的BaseAgent实例                           │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       v
┌─────────────────────────────────────────────────────────────────┐
│ 2. Agent初始化 (BaseAgent.__init__)                             │
│    - 连接到4个MCP服务 (端口19000-19003)                         │
│    - 创建LangChain agent with ChatOpenAI                        │
│    - 初始化模型参数 (max_steps=30, max_retries=3)               │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       v
┌─────────────────────────────────────────────────────────────────┐
│ 3. 日期循环 (BaseAgent.run_for_dates())                         │
│    - 计算交易日期范围 (从position.jsonl最后日期到end_date)       │
│    - 过滤掉周末，只处理交易日                                    │
│    - 按日期顺序逐日执行交易会话                                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       v
┌─────────────────────────────────────────────────────────────────┐
│ 4. 每日交易会话 (BaseAgent.run_trading_session())               │
│    ┌──────────────────────────────────────────────────────────┐│
│    │ 4.1 生成系统提示词 (get_agent_system_prompt())           ││
│    │     - 注入今日日期                                        ││
│    │     - 注入昨日持仓                                        ││
│    │     - 注入昨日收盘价                                      ││
│    │     - 注入今日开盘价                                      ││
│    └──────────────────────────────────────────────────────────┘│
│    ┌──────────────────────────────────────────────────────────┐│
│    │ 4.2 发送初始用户查询                                     ││
│    │     "Please analyze and update today's positions."       ││
│    └──────────────────────────────────────────────────────────┘│
│    ┌──────────────────────────────────────────────────────────┐│
│    │ 4.3 Agent决策循环 (最多30步)                             ││
│    │     ┌────────────────────────────────────────────┐      ││
│    │     │ a) Agent思考并调用工具                      │      ││
│    │     │    - 可能调用多个工具获取信息               │      ││
│    │     │    - 工具返回结果                           │      ││
│    │     └────────────────────────────────────────────┘      ││
│    │     ┌────────────────────────────────────────────┐      ││
│    │     │ b) 将工具结果反馈给Agent                    │      ││
│    │     │    - 格式: "Tool results: {结果内容}"       │      ││
│    │     └────────────────────────────────────────────┘      ││
│    │     ┌────────────────────────────────────────────┐      ││
│    │     │ c) Agent继续思考或输出停止信号              │      ││
│    │     │    - 如果输出 <FINISH_SIGNAL> 则结束        │      ││
│    │     │    - 否则继续下一轮工具调用                 │      ││
│    │     └────────────────────────────────────────────┘      ││
│    └──────────────────────────────────────────────────────────┘│
│    ┌──────────────────────────────────────────────────────────┐│
│    │ 4.4 记录日志                                             ││
│    │     - 路径: data/agent_data/{signature}/log/{date}/     ││
│    │     - 格式: log.jsonl (每条消息一行JSON)                 ││
│    └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 系统提示词机制

### 提示词模板

系统提示词定义在 `prompts/agent_prompt.py:32-66`，每天动态生成。

#### 完整提示词内容

```python
agent_system_prompt = """
You are a stock fundamental analysis trading assistant.

Your goals are:
- Think and reason by calling available tools.
- You need to think about the prices of various stocks and their returns.
- Your long-term goal is to maximize returns through this portfolio.
- Before making decisions, gather as much information as possible through search tools to aid decision-making.

Thinking standards:
- Clearly show key intermediate steps:
  - Read input of yesterday's positions and today's prices
  - Update valuation and adjust weights for each target (if strategy requires)

Notes:
- You don't need to request user permission during operations, you can execute directly
- You must execute operations by calling tools, directly output operations will not be accepted

Here is the information you need:

Today's date:
{date}

Yesterday's closing positions (numbers after stock codes represent how many shares you hold, numbers after CASH represent your available cash):
{positions}

Yesterday's closing prices:
{yesterday_close_price}

Today's buying prices:
{today_buy_price}

When you think your task is complete, output
{STOP_SIGNAL}
"""
```

### 提示词参数动态注入

**函数**: `get_agent_system_prompt(today_date: str, signature: str)` (agent_prompt.py:68-83)

**注入的动态参数**:

| 参数 | 来源函数 | 说明 | 示例 |
|------|---------|------|------|
| `{date}` | 直接传入 | 今天的交易日期 | `"2025-10-15"` |
| `{positions}` | `get_today_init_position()` | 昨日收盘时的持仓状态 | `{"AAPL": 10, "MSFT": 5, "CASH": 8500.0, ...}` |
| `{yesterday_close_price}` | `get_yesterday_open_and_close_price()` | 昨日各股票的收盘价 | `{"AAPL_price": 180.5, "MSFT_price": 420.3, ...}` |
| `{today_buy_price}` | `get_open_prices()` | 今日各股票的开盘价（买入价） | `{"AAPL_price": 182.0, "MSFT_price": 422.5, ...}` |
| `{STOP_SIGNAL}` | 常量 | 停止信号字符串 | `"<FINISH_SIGNAL>"` |

### 提示词生成时机

**调用位置**: `base_agent.py:206-210`

```python
async def run_trading_session(self, today_date: str) -> None:
    # 每天开始交易前重新生成系统提示词
    self.agent = create_agent(
        self.model,
        tools=self.tools,
        system_prompt=get_agent_system_prompt(today_date, self.signature),
    )
```

**关键特性**:
- ✅ **每日重新生成** - 确保日期和价格数据始终是当天的
- ✅ **时间隔离** - Agent不记得昨天的对话，只基于系统提示词中的信息
- ✅ **防止未来信息泄露** - 所有价格数据都截止到当前交易日

---

## 🛠️ MCP工具调用流程

### 可用工具列表

AI Agent可以调用以下6个MCP工具：

| 工具名称 | 服务 | 端口 | 功能描述 | 文件位置 |
|---------|------|------|---------|---------|
| `get_price_local` | GetPrice | 19003 | 查询本地价格数据库中的历史价格 | `tool_get_price_local.py` |
| `get_information` | Search | 19001 | 使用Jina AI搜索互联网信息 | `tool_jina_search.py` |
| `add` | Math | 19000 | 计算加法 | `tool_math.py` |
| `multiply` | Math | 19000 | 计算乘法 | `tool_math.py` |
| `buy` | Trade | 19002 | 执行买入操作 | `tool_trade.py` |
| `sell` | Trade | 19002 | 执行卖出操作 | `tool_trade.py` |

### 工具详细说明

#### 1. `get_price_local(symbol: str, date: str)`

**功能**: 查询指定股票在指定日期的价格数据

**参数**:
- `symbol`: 股票代码，如 `"AAPL"`
- `date`: 日期字符串，格式 `"YYYY-MM-DD"`

**返回**:
```json
{
  "date": "2025-10-15",
  "open": 182.0,
  "high": 185.5,
  "low": 181.2,
  "close": 184.3,
  "volume": 52847600
}
```

**典型用途**:
- 查询历史价格趋势
- 计算股票涨跌幅
- 分析技术指标

---

#### 2. `get_information(query: str)`

**功能**: 搜索互联网获取实时信息（新闻、公司动态、行业分析）

**参数**:
- `query`: 搜索查询字符串，如 `"Apple Q3 earnings report 2025"`

**返回**:
```json
{
  "results": [
    {
      "title": "Apple Reports Strong Q3 Earnings",
      "content": "Apple Inc. reported revenue of $94.9B...",
      "url": "https://example.com/article"
    }
  ]
}
```

**典型用途**:
- 获取公司财报信息
- 了解行业动态
- 搜索宏观经济新闻
- 基本面分析

**API**: 使用Jina AI Reader API

---

#### 3. `add(a: float, b: float)` / `multiply(a: float, b: float)`

**功能**: 数学计算工具

**典型用途**:
- 计算投资组合总价值
- 计算持仓市值 (股数 × 价格)
- 计算收益率

---

#### 4. `buy(symbol: str, amount: int)`

**功能**: 执行股票买入操作

**参数**:
- `symbol`: 股票代码
- `amount`: 买入数量（整数，必须 > 0）

**执行逻辑**:
1. 验证股票代码有效性
2. 获取今日开盘价
3. 计算所需现金 = 开盘价 × 数量
4. 检查现金余额是否充足
5. 更新持仓：
   - `CASH -= 所需现金`
   - `持仓[symbol] += amount`
6. 写入 `position.jsonl` 记录交易

**返回**:
- 成功: 新的持仓字典
- 失败: `{"error": "错误信息", ...}`

**错误处理**:
- ❌ 现金不足 → 返回错误，不执行交易
- ❌ 股票代码不存在 → 返回错误
- ✅ 交易成功 → 立即持久化到文件

**文件位置**: `tool_trade.py:15-103`

---

#### 5. `sell(symbol: str, amount: int)`

**功能**: 执行股票卖出操作

**参数**:
- `symbol`: 股票代码
- `amount`: 卖出数量（整数，必须 > 0）

**执行逻辑**:
1. 验证股票代码有效性
2. 获取今日开盘价（卖出价）
3. 检查持仓数量是否充足
4. 更新持仓：
   - `CASH += 开盘价 × 数量`
   - `持仓[symbol] -= amount`
5. 写入 `position.jsonl` 记录交易

**返回**:
- 成功: 新的持仓字典
- 失败: `{"error": "错误信息", ...}`

**错误处理**:
- ❌ 持仓不足 → 返回错误
- ❌ 股票代码不存在 → 返回错误
- ✅ 交易成功 → 立即持久化到文件

**文件位置**: `tool_trade.py:106-180`

---

### 工具调用流程示例

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Agent思考                                            │
│ "I need to check Apple's current price and recent news"     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│ Step 2: 并行调用工具                                         │
│ Tool Call 1: get_price_local("AAPL", "2025-10-15")         │
│ Tool Call 2: get_information("Apple stock news October")   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│ Step 3: MCP服务返回结果                                      │
│ Tool Result 1: {"close": 184.3, "volume": 52847600, ...}   │
│ Tool Result 2: {"results": [{"title": "...", ...}]}        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│ Step 4: 系统将结果反馈给Agent                                │
│ User Message: "Tool results: [结果1] [结果2]"                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│ Step 5: Agent基于结果继续思考                                │
│ "Price is up 2.5%, good news. I'll buy 10 shares."         │
│ Tool Call: buy("AAPL", 10)                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│ Step 6: 交易执行并持久化                                     │
│ - 更新 position.jsonl                                        │
│ - 返回新持仓给Agent                                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│ Step 7: Agent完成决策                                        │
│ "Portfolio updated. <FINISH_SIGNAL>"                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 单日交易会话流程

### 详细步骤分解

**代码位置**: `base_agent.py:193-269`

#### Phase 1: 初始化 (Lines 200-217)

```python
# 1. 设置日志文件
log_file = self._setup_logging(today_date)
# 路径: data/agent_data/{signature}/log/{date}/log.jsonl

# 2. 重新生成系统提示词
self.agent = create_agent(
    self.model,
    tools=self.tools,
    system_prompt=get_agent_system_prompt(today_date, self.signature),
)

# 3. 构造初始用户查询
user_query = [{"role": "user", "content": f"Please analyze and update today's ({today_date}) positions."}]
message = user_query.copy()

# 4. 记录初始消息到日志
self._log_message(log_file, user_query)
```

---

#### Phase 2: 决策循环 (Lines 219-259)

```python
current_step = 0
while current_step < self.max_steps:  # 默认 max_steps = 30
    current_step += 1

    # 1. 调用Agent（带重试机制）
    response = await self._ainvoke_with_retry(message)

    # 2. 提取Agent的文本响应
    agent_response = extract_conversation(response, "final")

    # 3. 检查停止信号
    if STOP_SIGNAL in agent_response:  # "<FINISH_SIGNAL>"
        print("✅ Received stop signal, trading session ended")
        self._log_message(log_file, [{"role": "assistant", "content": agent_response}])
        break

    # 4. 提取工具调用结果
    tool_msgs = extract_tool_messages(response)
    tool_response = '\n'.join([msg.content for msg in tool_msgs])

    # 5. 构造新消息（Agent响应 + 工具结果）
    new_messages = [
        {"role": "assistant", "content": agent_response},
        {"role": "user", "content": f'Tool results: {tool_response}'}
    ]

    # 6. 将新消息添加到对话历史
    message.extend(new_messages)

    # 7. 记录到日志
    self._log_message(log_file, new_messages[0])
    self._log_message(log_file, new_messages[1])
```

**循环终止条件**:
- ✅ Agent输出 `<FINISH_SIGNAL>`
- ❌ 达到最大步数 (30步)
- ❌ 发生异常错误

---

#### Phase 3: 后处理 (Lines 261-269)

```python
async def _handle_trading_result(self, today_date: str) -> None:
    # 检查是否有交易发生（通过 IF_TRADE 标志）
    if_trade = get_config_value("IF_TRADE")
    if if_trade:
        # 重置交易标志
        write_config_value("IF_TRADE", False)
        print("✅ Trading completed")
    else:
        print("ℹ️  No trades executed today")
```

**IF_TRADE 标志说明**:
- 当 `buy()` 或 `sell()` 成功执行时，工具会设置 `IF_TRADE = True`
- 用于区分"主动不交易"和"执行了交易"

---

## 💡 完整决策示例

### 示例场景

**日期**: 2025-10-15
**模型**: claude-3.7-sonnet
**昨日持仓**: `{"AAPL": 10, "MSFT": 5, "NVDA": 0, "CASH": 8500.0, ...}`

---

### Step-by-Step 决策过程

#### 🎬 会话开始

**系统提示词** (动态生成):
```
You are a stock fundamental analysis trading assistant.

Your goals are:
- Think and reason by calling available tools.
- You need to think about the prices of various stocks and their returns.
...

Today's date:
2025-10-15

Yesterday's closing positions:
{"AAPL": 10, "MSFT": 5, "NVDA": 0, "CASH": 8500.0, ...}

Yesterday's closing prices:
{"AAPL_price": 184.3, "MSFT_price": 422.5, ...}

Today's buying prices:
{"AAPL_price": 182.0, "MSFT_price": 420.0, ...}

When you think your task is complete, output
<FINISH_SIGNAL>
```

**用户查询**:
```
Please analyze and update today's (2025-10-15) positions.
```

---

#### 🤖 Step 1: Agent初步分析

**Agent响应**:
```
I need to analyze the current market situation and portfolio performance.
Let me start by checking recent news and price trends for my holdings.

Tool calls:
1. get_information("Apple stock news October 2025")
2. get_information("Microsoft earnings Q3 2025")
3. get_price_local("NVDA", "2025-10-14")
```

**工具返回**:
```json
Tool results:
1. {"results": [{"title": "Apple unveils new AI features", "content": "..."}]}
2. {"results": [{"title": "Microsoft beats earnings expectations", "content": "..."}]}
3. {"date": "2025-10-14", "close": 145.2, "volume": 48520000}
```

---

#### 🤖 Step 2: Agent分析并决策

**Agent响应**:
```
Based on the information:
- Apple has positive news about AI features, but stock price is down 1.2% today (182.0 vs 184.3)
- Microsoft beat earnings, showing strong fundamentals, price also down slightly
- NVIDIA has been trending up, currently at 145.2

My strategy:
1. Hold current AAPL and MSFT positions (good long-term prospects)
2. Add NVDA exposure due to strong AI sector momentum

Calculating available cash and position sizing...

Tool calls:
1. multiply(145.2, 20)  # Cost for 20 NVDA shares
2. buy("NVDA", 20)
```

**工具返回**:
```json
Tool results:
1. 2904.0
2. {"AAPL": 10, "MSFT": 5, "NVDA": 20, "CASH": 5596.0, ...}
```

---

#### 🤖 Step 3: Agent确认完成

**Agent响应**:
```
Portfolio successfully updated:
- Maintained AAPL: 10 shares
- Maintained MSFT: 5 shares
- Added NVDA: 20 shares (cost: $2,904)
- Remaining cash: $5,596

Portfolio is well-diversified across tech leaders in cloud, devices, and AI infrastructure.
No further actions needed for today.

<FINISH_SIGNAL>
```

---

#### ✅ 会话结束

**日志记录** (data/agent_data/claude-3.7-sonnet/log/2025-10-15/log.jsonl):
```jsonl
{"role": "user", "content": "Please analyze and update today's (2025-10-15) positions."}
{"role": "assistant", "content": "I need to analyze the current market situation..."}
{"role": "user", "content": "Tool results: ..."}
{"role": "assistant", "content": "Based on the information..."}
{"role": "user", "content": "Tool results: 2904.0\n{\"NVDA\": 20, ...}"}
{"role": "assistant", "content": "Portfolio successfully updated...<FINISH_SIGNAL>"}
```

**持仓记录** (data/agent_data/claude-3.7-sonnet/position/position.jsonl):
```jsonl
...
{"date": "2025-10-15", "id": 42, "this_action": {"action": "buy", "symbol": "NVDA", "amount": 20}, "positions": {"AAPL": 10, "MSFT": 5, "NVDA": 20, "CASH": 5596.0, ...}}
```

---

## 🔑 关键设计要点

### 1. 时间隔离

**问题**: 如何防止AI看到"未来"的数据？

**解决方案**:
- ✅ 每天重新生成系统提示词，只包含截止到当天的数据
- ✅ Agent不保留跨天的记忆（每天创建新的agent实例）
- ✅ `get_price_local()` 工具只能查询历史数据，无法访问未来价格

---

### 2. 工具驱动决策

**问题**: 如何确保AI做出的决策能真实执行？

**解决方案**:
- ✅ 提示词明确要求：**"You must execute operations by calling tools"**
- ✅ 只有通过 `buy()` / `sell()` 工具的操作才会被持久化
- ✅ 工具内置验证逻辑（现金检查、持仓检查）

---

### 3. 自主性与约束

**自主性**:
- ✅ "You don't need to request user permission"
- ✅ Agent可以自由调用任意工具
- ✅ Agent决定买卖时机和数量

**约束**:
- ❌ 最多30步必须完成决策
- ❌ 不能做空（持仓不能为负）
- ❌ 不能借贷（现金不能为负）
- ❌ 只能交易NASDAQ 100股票

---

### 4. 可重复性

**问题**: 如何确保实验可复原？

**解决方案**:
- ✅ 所有对话记录到 `log.jsonl`
- ✅ 所有交易记录到 `position.jsonl` (append-only)
- ✅ 系统提示词中包含确定性的价格数据
- ⚠️  注意: 同一个LLM在相同输入下可能产生不同输出（温度参数）

---

## 📚 相关文件索引

| 文件 | 行数范围 | 功能说明 |
|------|---------|---------|
| `prompts/agent_prompt.py` | 32-66 | 系统提示词模板 |
| `prompts/agent_prompt.py` | 68-83 | 提示词生成函数 |
| `agent/base_agent/base_agent.py` | 193-269 | 交易会话主流程 |
| `agent/base_agent/base_agent.py` | 137-159 | MCP工具初始化 |
| `agent_tools/tool_trade.py` | 15-103 | buy() 工具实现 |
| `agent_tools/tool_trade.py` | 106-180 | sell() 工具实现 |
| `agent_tools/tool_get_price_local.py` | 25-100 | 价格查询工具 |
| `agent_tools/tool_jina_search.py` | 217-250 | 信息搜索工具 |
| `main.py` | 153-220 | 主控制循环 |

---

**文档版本**: 1.0
**最后更新**: 2025-10-27
**作者**: AI-Trader Team
