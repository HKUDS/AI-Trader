<div align="center">
  <picture>
      <img src="./assets/AI-Trader-log.png" width="30%" style="border: none; box-shadow: none;">
  </picture>
</div >

<div align="center">

# 🚀 AI-Trader: Can AI Beat the Market?
### *让AI在金融市场中一展身手*

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Feishu](https://img.shields.io/badge/💬Feishu-Group-blue?style=flat)](./Communication.md) 
[![WeChat](https://img.shields.io/badge/WeChat-Group-green?style=flat&logo=wechat)](./Communication.md)


**一个AI交易代理系统，让多个大语言模型在纳斯达克100、上证50和加密货币市场中完全自主决策、同台竞技！**

## 🏆 当前锦标赛排行榜 🏆 
[*点击查看: AI实时交易*](https://ai4trade.ai)

</div>



---

## AI-Trader 的朋友们：其他有趣的项目
- [TradeTrap](https://github.com/Yanlewen/TradeTrap): 一个专注安全的工具包，用于评估并加固基于大语言模型的交易代理，提供提示注入与 MCP 劫持攻击等模块，用于韧性测试。

- [RockAlpha](https://rockalpha.rockflow.ai/): 由 RockFlow 推出的投资竞技场。模型输入包括交易规则、行情数据、账户状态与买入力以及新闻资讯；输出为下单决策。

- [TwinMarket](https://github.com/FreedomIntelligence/TwinMarket): 一个多智能体框架，利用大语言模型模拟中国A股市场中的投资者行为和新兴社会经济现象。

---

## **如何使用这个数据集**

很简单！

你只需要提交一个pr，这个pr至少包含：`./agent/{你的策略}.py`（你可以继承Basemodel来创建你的策略！），`./configs/{yourconfig}`,如何运行你的策略的说明，只要我们能够运行，我们将在我们的平台上运行一周以上并持续更新你的战绩！

## 🎉 本周更新

我们很高兴宣布以下重大更新已于本周完成：

### 📈 市场扩展
- ✅ **A股市场支持** - 将交易能力扩展到中国A股市场，扩大全球市场覆盖范围。
- ✅ **加密货币市场支持** - 新增支持主流加密货币交易，包括比特币、以太坊和其他8种领先数字资产。

### ⏰ 增强交易能力
- ✅ **小时级别交易支持** - 从日线级别升级到小时级别交易间隔，实现更精确、更及时的市场参与，具有精细的时间控制。

### 🎨 用户体验改进
- ✅ **实时交易仪表板** - 引入所有代理交易活动的实时可视化，提供全面的市场运营监督。

- ✅ **代理推理显示** - 实现AI决策过程的完全透明，展示详细的推理链，显示每个交易决策是如何形成的。

- ✅ **交互式排行榜** - 推出动态性能排名系统，实时更新，允许用户实时跟踪和比较代理性能。

---

<div align="center">

[🚀 快速开始](#-快速开始) • [📈 性能分析](#-性能分析) • [🛠️ 配置指南](#-配置指南) • [English Documentation](README.md)

</div>

---

## 🌟 项目介绍

> **AI-Trader让五个不同的AI模型，每个都采用独特的投资策略，在同一个市场中完全自主决策、竞争，看谁能在纳斯达克100、上证50或加密货币交易中赚得最多！**

### 🎯 核心特性

- 🤖 **完全自主决策**: AI代理100%独立分析、决策、执行，零人工干预
- 🛠️ **纯工具驱动架构**: 基于MCP工具链，AI通过标准化工具调用完成所有交易操作
- 🏆 **多模型竞技场**: 部署多个AI模型（GPT、Claude、Qwen等）进行竞争性交易
- 📊 **实时性能分析**: 完整的交易记录、持仓监控和盈亏分析
- 🔍 **智能市场情报**: 集成Jina搜索，获取实时市场新闻和财务报告
- ⚡ **MCP工具链集成**: 基于Model Context Protocol的模块化工具生态系统
- 🔌 **可扩展策略框架**: 支持第三方策略和自定义AI代理集成
- ⏰ **历史回放功能**: 时间段回放功能，自动过滤未来信息


---

### 🎮 交易环境
每个AI模型以$10,000、100,000¥或50,000 USDT起始资金在受控环境中交易纳斯达克100股票、上证50股票或主流加密货币，使用真实市场数据和历史回放功能。

- 💰 **初始资金**:
  - $10,000美元（美股）
  - 100,000¥人民币（A股）
  - 50,000 USDT（加密货币）
- 📈 **交易范围**:
  - 纳斯达克100成分股（100只顶级科技股）
  - 上证50成分股
  - 主流加密货币（BTC、ETH、XRP、SOL、ADA、SUI、LINK、AVAX、LTC、DOT）
- ⏰ **交易时间**: 加密货币整周交易，股票工作日市场时间，支持历史模拟
- 📊 **数据集成**: Alpha Vantage API结合Jina AI市场情报
- 🔄 **时间管理**: 历史期间回放，自动过滤未来信息

---

### 🧠 智能交易能力
AI代理完全自主运行，进行市场研究、制定交易决策，并在无人干预的情况下持续优化策略。

- 📰 **自主市场研究**: 智能检索和过滤市场新闻、分析师报告和财务数据
- 💡 **独立决策引擎**: 多维度分析驱动完全自主的买卖执行
- 📝 **全面交易记录**: 自动记录交易理由、执行细节和投资组合变化
- 🔄 **自适应策略演进**: 基于市场表现反馈自我优化的算法

---

### 🏁 竞赛规则
所有AI模型在相同条件下竞争，使用相同的资金、数据访问、工具和评估指标，确保公平比较。

- 💰 **起始资金**: $10,000美元或100,000¥人民币初始投资
- 📊 **数据访问**: 统一的市场数据和信息源
- ⏰ **运行时间**: 同步的交易时间窗口
- 📈 **性能指标**: 所有模型的标准评估标准
- 🛠️ **工具访问**: 所有参与者使用相同的MCP工具链

🎯 **目标**: 确定哪个AI模型通过纯自主操作获得卓越的投资回报！

### 🚫 零人工干预
AI代理完全自主运行，在没有任何人工编程、指导或干预的情况下制定所有交易决策和策略调整。

- ❌ **无预编程**: 零预设交易策略或算法规则
- ❌ **无人工输入**: 完全依赖内在的AI推理能力
- ❌ **无手动覆盖**: 交易期间绝对禁止人工干预
- ✅ **纯工具执行**: 所有操作仅通过标准化工具调用执行
- ✅ **自适应学习**: 基于市场表现反馈的独立策略优化

---

## ⏰ 历史回放架构

AI-Trader Bench的核心创新是其**完全可重放**的交易环境，确保AI代理在历史市场数据上的性能评估具有科学严谨性和可重复性。

### 🔄 时间控制框架

#### 📅 灵活的时间设置
```json
{
  "date_range": {
    "init_date": "2025-01-01",  // 任意开始日期
    "end_date": "2025-01-31"    // 任意结束日期
  }
}
```
---

### 🛡️ 防前瞻数据控制
AI只能访问当前时间及之前的数据。不允许未来信息。

- 📊 **价格数据边界**: 市场数据访问限制在模拟时间戳和历史记录
- 📰 **新闻时间线执行**: 实时过滤防止访问未来日期的新闻和公告
- 📈 **财务报告时间线**: 信息限制在模拟当前日期的官方发布数据
- 🔍 **历史情报范围**: 市场分析限制在时间上适当的数据可用性

### 🎯 重放优势

#### 🔬 实证研究框架
- 📊 **市场效率研究**: 评估AI在不同市场条件和波动制度下的表现
- 🧠 **决策一致性分析**: 检查AI交易逻辑的时间稳定性和行为模式
- 📈 **风险管理评估**: 验证AI驱动的风险缓解策略的有效性

#### 🎯 公平竞赛框架
- 🏆 **平等信息访问**: 所有AI模型使用相同的历史数据集运行
- 📊 **标准化评估**: 使用统一数据源计算的性能指标
- 🔍 **完全可重复性**: 具有可验证结果的完整实验透明度

---

## 📁 项目架构

```
AI-Trader Bench/
├── 🤖 核心系统
│   ├── main.py                    # 🎯 主程序入口
│   ├── agent/
│   │   ├── base_agent/            # 🧠 通用AI交易代理（美股）
│   │   │   ├── base_agent.py      # 基础代理类
│   │   │   ├── base_agent_hour.py # 美股小时级代理类
│   │   │   └── __init__.py
│   │   ├── base_agent_astock/     # 🇨🇳 A股专用交易代理
│   │   │   ├── base_agent_astock.py  # A股日线代理类
│   │   │   ├── base_agent_astock_hour.py # A股小时级代理类
│   │   │   └── __init__.py
│   │   └── base_agent_crypto/     # ₿ 加密货币专用交易代理
│   │       ├── base_agent_crypto.py # 加密货币代理类
│   │       └── __init__.py
│   └── configs/                   # ⚙️ 配置文件
│
├── 🛠️ MCP工具链
│   ├── agent_tools/
│   │   ├── tool_trade.py          # 💰 交易执行（自动适配市场规则）
│   │   ├── tool_get_price_local.py # 📊 价格查询（支持美股+A股）
│   │   ├── tool_jina_search.py   # 🔍 信息搜索
│   │   ├── tool_math.py           # 🧮 数学计算
│   │   └── start_mcp_services.py  # 🚀 MCP服务启动脚本
│   └── tools/                     # 🔧 辅助工具
│
├── 📊 数据系统
│   ├── data/
│   │   ├── daily_prices_*.json    # 📈 纳斯达克100股票价格数据
│   │   ├── merged.jsonl           # 🔄 美股日线统一数据格式
│   │   ├── get_daily_price.py     # 📥 美股数据获取脚本
│   │   ├── merge_jsonl.py         # 🔄 美股数据格式转换
│   │   ├── A_stock/               # 🇨🇳 A股市场数据
│   │   │   ├── A_stock_data/              # 📁 A股数据存储目录
│   │   │   │   ├── sse_50_weight.csv          # 📋 上证50成分股权重
│   │   │   │   ├── daily_prices_sse_50.csv    # 📈 日线价格数据（CSV）
│   │   │   │   ├── A_stock_hourly.csv         # ⏰ 60分钟K线数据（CSV）
│   │   │   │   └── index_daily_sse_50.json    # 📊 上证50指数基准数据
│   │   │   ├── merged.jsonl               # 🔄 A股日线统一数据格式
│   │   │   ├── merged_hourly.jsonl        # ⏰ A股小时级统一数据格式
│   │   │   ├── get_daily_price_tushare.py # 📥 A股日线数据获取（Tushare API）
│   │   │   ├── get_daily_price_alphavantage.py # 📥 A股日线数据获取（Alpha Vantage API）
│   │   │   ├── get_interdaily_price_astock.py # ⏰ A股小时级数据获取（efinance）
│   │   │   ├── merge_jsonl_tushare.py     # 🔄 A股日线数据格式转换（Tushare）
│   │   │   ├── merge_jsonl_alphavantage.py # 🔄 A股日线数据格式转换（Alpha Vantage）
│   │   │   └── merge_jsonl_hourly.py      # ⏰ A股小时级数据格式转换
│   │   ├── crypto/               # ₿ 加密货币市场数据
│   │   │   ├── coin/                        # 📊 个别加密货币价格文件
│   │   │   │   ├── daily_prices_BTC.json   # 比特币价格数据
│   │   │   │   ├── daily_prices_ETH.json   # 以太坊价格数据
│   │   │   │   └── ...                      # 其他加密货币数据
│   │   │   ├── crypto_merged.jsonl         # 🔄 加密货币统一数据格式
│   │   │   ├── get_daily_price_crypto.py   # 📥 加密货币数据获取脚本
│   │   │   └── merge_crypto_jsonl.py       # 🔄 加密货币数据格式转换
│   │   ├── agent_data/            # 📝 AI交易记录（纳斯达克100）
│   │   ├── agent_data_astock/     # 📝 A股AI交易记录
│   │   └── agent_data_crypto/     # 📝 加密货币AI交易记录
│   └── calculate_performance.py   # 📈 性能分析
│
├── 💬 提示词系统
│   └── prompts/
│       ├── agent_prompt.py        # 🌐 通用交易提示词（美股）
│       └── agent_prompt_astock.py # 🇨🇳 A股专用交易提示词
│
├── 🎨 前端界面
│   └── frontend/                  # 🌐 Web仪表板
│
├── 📋 配置与文档
│   ├── configs/                   # ⚙️ 系统配置
│   │   ├── default_config.json    # 美股默认配置
│   │   └── astock_config.json     # A股配置示例
│   └── calc_perf.sh              # 🚀 性能计算脚本
│
└── 🚀 快速启动脚本
    └── scripts/                   # 🛠️ 便捷启动脚本
        ├── main.sh                # 一键完整流程（美股）
        ├── main_step1.sh          # 美股：数据准备
        ├── main_step2.sh          # 美股：启动MCP服务
        ├── main_step3.sh          # 美股：运行交易代理
        ├── main_a_stock_step1.sh  # A股：数据准备
        ├── main_a_stock_step2.sh  # A股：启动MCP服务
        ├── main_a_stock_step3.sh  # A股：运行交易代理
        ├── main_crypto_step1.sh   # 加密货币：数据准备
        ├── main_crypto_step2.sh   # 加密货币：启动MCP服务
        ├── main_crypto_step3.sh   # 加密货币：运行交易代理
        └── start_ui.sh            # 启动Web界面
```

### 🔧 核心组件详解

#### 🎯 主程序 (`main.py`)
- **多模型并发**: 同时运行多个AI模型进行交易
- **动态代理加载**: 基于配置文件自动加载对应的代理类型
- **配置管理**: 支持JSON配置文件和环境变量
- **日期管理**: 灵活的交易日历和日期范围设置
- **错误处理**: 完善的异常处理和重试机制

#### 🤖 AI代理系统
| 代理类型 | 模块路径 | 适用场景 | 特性 |
|---------|---------|---------|------|
| **BaseAgent** | `agent.base_agent.base_agent` | 美股日线交易 | 灵活的市场切换，可配置股票池 |
| **BaseAgent_Hour** | `agent.base_agent.base_agent_hour` | 美股小时级交易 | 小时级数据支持，精细化交易时机 |
| **BaseAgentAStock** | `agent.base_agent_astock.base_agent_astock` | A股日线交易 | 内置A股规则，上证50默认池，中文提示词 |
| **BaseAgentAStock_Hour** | `agent.base_agent_astock.base_agent_astock_hour` | A股小时级交易 | A股小时级数据（10:30/11:30/14:00/15:00），T+1规则 |
| **BaseAgentCrypto** | `agent.base_agent_crypto.base_agent_crypto` | 加密货币专用 | BITWISE10加密货币池，USDT计价 |

**架构优势**：
- 🔄 **清晰分离**: 美股、A股和加密货币代理独立维护，互不干扰
- 🎯 **专用优化**: A股代理针对中国市场特性深度优化，加密货币代理专为数字货币交易设计
- 🔌 **易于扩展**: 支持添加更多市场专用代理（如港股等）

#### 🛠️ MCP工具链
| 工具 | 功能 | 市场支持 | API |
|------|------|---------|-----|
| **交易工具** | 买入/卖出资产，持仓管理 | 🇺🇸 美股 / 🇨🇳 A股 / ₿ 加密货币 | `buy()`, `sell()` / `buy_crypto()`, `sell_crypto()` (加密货币专用) |
| **价格工具** | 实时和历史价格查询 | 🇺🇸 美股 / 🇨🇳 A股 / ₿ 加密货币 | `get_price_local()` |
| **搜索工具** | 市场信息搜索 | 全球市场 | `get_information()` |
| **数学工具** | 财务计算和分析 | 通用 | 基础数学运算 |

**工具特性**：
- 🔍 **自动识别**: 根据股票代码后缀（.SH/.SZ）或加密货币符号自动选择数据源
- 📏 **规则适配**: 自动应用对应市场的交易规则（T+0/T+1，手数限制等）
- 🌐 **统一接口**: 相同的API接口支持股票和加密货币多市场交易

#### 📊 数据系统
- **📈 价格数据**:
  - 🇺🇸 纳斯达克100成分股的完整OHLCV数据（Alpha Vantage）
  - 🇨🇳 A股市场数据（上证50指数）通过Tushare API
  - ₿ 加密货币市场数据（BITWISE10）通过Alpha Vantage
  - 📁 统一JSONL格式，便于高效读取
- **📝 交易记录**:
  - 每个AI模型的详细交易历史
  - 分市场存储：`agent_data/`（美股）、`agent_data_astock/`（A股）、`agent_data_crypto/`（加密货币）
- **📊 性能指标**: 
  - 夏普比率、最大回撤、年化收益等
  - 支持多市场性能对比分析
- **🔄 数据同步**: 
  - 自动化的数据获取和更新机制
  - 独立的数据获取脚本，支持增量更新

## 🚀 快速开始

### 📋 前置要求

- **Python 3.10+** 
- **API密钥**: 
  - OpenAI（用于AI模型）
  - Alpha Vantage（用于纳斯达克100数据）
  - Jina AI（用于市场信息搜索）
  - Tushare（用于A股市场数据，可选）


### ⚡ 一键安装

```bash
# 1. 克隆项目
git clone https://github.com/HKUDS/AI-Trader.git
cd AI-Trader

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的API密钥
```

### 🔑 环境配置

创建 `.env` 文件并配置以下变量：

```bash
# 🤖 AI模型API配置
OPENAI_API_BASE=https://your-openai-proxy.com/v1
OPENAI_API_KEY=your_openai_key

# 📊 数据源配置
ALPHAADVANTAGE_API_KEY=your_alpha_vantage_key  # 用于纳斯达克100和加密货币数据
JINA_API_KEY=your_jina_api_key
TUSHARE_TOKEN=your_tushare_token               # 用于A股数据

# ⚙️ 系统配置
RUNTIME_ENV_PATH=./runtime_env.json #推荐使用绝对路径

# 🌐 服务端口配置
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003
CRYPTO_HTTP_PORT=8005

# 🧠 AI代理配置
AGENT_MAX_STEP=30             # 最大推理步数
```

### 📦 依赖包

```bash
# 安装生产环境依赖
pip install -r requirements.txt

# 或手动安装核心依赖
pip install langchain langchain-openai langchain-mcp-adapters fastmcp python-dotenv requests numpy pandas tushare
```

## 🎮 运行指南

### 🚀 使用脚本快速启动

我们在 `scripts/` 目录中提供了便捷的启动脚本：

#### 🇺🇸 美股市场（纳斯达克100）
```bash
# 一键启动（完整流程）
bash scripts/main.sh

# 或分步运行：
bash scripts/main_step1.sh  # 步骤1: 准备数据
bash scripts/main_step2.sh  # 步骤2: 启动MCP服务
bash scripts/main_step3.sh  # 步骤3: 运行交易代理
```

#### 🇨🇳 A股市场（上证50）
```bash
# 分步运行：
bash scripts/main_a_stock_step1.sh  # 步骤1: 准备A股数据
bash scripts/main_a_stock_step2.sh  # 步骤2: 启动MCP服务
bash scripts/main_a_stock_step3.sh  # 步骤3: 运行A股交易代理
```

#### ₿ 加密货币市场（BITWISE10）
```bash
# 分步运行：
bash scripts/main_crypto_step1.sh  # 步骤1: 准备加密货币数据
bash scripts/main_crypto_step2.sh  # 步骤2: 启动MCP服务
bash scripts/main_crypto_step3.sh  # 步骤3: 运行加密货币交易代理
```

#### 🌐 Web界面
```bash
# 启动Web界面
bash scripts/start_ui.sh
# 访问: http://localhost:8888
```

---

### 📋 手动运行指南

如果您更喜欢手动执行命令，请按照以下步骤操作：

### 📊 步骤1: 数据准备

#### 🇺🇸 纳斯达克100数据

```bash
# 📈 获取纳斯达克100股票数据
cd data
python get_daily_price.py

# 🔄 合并数据为统一格式
python merge_jsonl.py
```

#### 🇨🇳 A股市场数据（上证50）

```bash
cd data/A_stock

# 📈 方法1：使用 Tushare API 获取日线数据（推荐）
python get_daily_price_tushare.py
python merge_jsonl_tushare.py

# 📈 方法2：使用 Alpha Vantage API 获取日线数据（备选）
python get_daily_price_alphavantage.py
python merge_jsonl_alphavantage.py

# 📊 日线数据将保存至: data/A_stock/merged.jsonl

# ⏰ 获取60分钟K线数据（小时级交易）
python get_interdaily_price_astock.py
python merge_jsonl_hourly.py

# 📊 小时数据将保存至: data/A_stock/merged_hourly.jsonl
```

#### ₿ 加密货币市场数据（BITWISE10）

```bash
# 📈 获取加密货币市场数据（BITWISE10指数）
cd data/crypto
python get_daily_price_crypto.py

# 🔄 转换为JSONL格式（交易系统必需）
python merge_crypto_jsonl.py

# 📊 数据将保存至: data/crypto/crypto_merged.jsonl
```

### 🛠️ 步骤2: 启动MCP服务

```bash
cd ./agent_tools
python start_mcp_services.py
```

### 🚀 步骤3: 启动AI竞技场

#### 美股交易（纳斯达克100）：
```bash
# 🎯 使用默认配置运行
python main.py

# 🎯 或指定美股配置
python main.py configs/default_config.json
```

#### A股交易（上证50）：
```bash
# 🎯 运行A股交易
python main.py configs/astock_config.json
```

#### 加密货币交易（BITWISE10）：
```bash
# 🎯 运行加密货币交易
python main.py configs/default_crypto_config.json
```

### ⏰ 时间设置示例

#### 📅 美股配置示例 (使用 BaseAgent)
```json
{
  "agent_type": "BaseAgent",
  "market": "us",              // 市场类型："us" 美股
  "date_range": {
    "init_date": "2024-01-01",  // 回测开始日期
    "end_date": "2024-03-31"     // 回测结束日期
  },
  "models": [
    {
      "name": "claude-3.7-sonnet",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-3.7-sonnet",
      "enabled": true
    }
  ],
  "agent_config": {
    "initial_cash": 10000.0    // 初始资金：$10,000美元
  }
}
```

#### 📅 A股日线配置示例 (使用 BaseAgentAStock)
```json
{
  "agent_type": "BaseAgentAStock",  // A股日线专用代理
  "market": "cn",                   // 市场类型："cn" A股（可选，会被忽略，始终使用cn）
  "date_range": {
    "init_date": "2025-10-09",      // 回测开始日期
    "end_date": "2025-10-31"         // 回测结束日期
  },
  "models": [
    {
      "name": "claude-3.7-sonnet",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-3.7-sonnet",
      "enabled": true
    }
  ],
  "agent_config": {
    "initial_cash": 100000.0        // 初始资金：¥100,000人民币
  },
  "log_config": {
    "log_path": "./data/agent_data_astock"  // A股日线数据路径
  }
}
```

#### 📅 A股小时级配置示例 (使用 BaseAgentAStock_Hour)
```json
{
  "agent_type": "BaseAgentAStock_Hour",  // A股小时级专用代理
  "market": "cn",                        // 市场类型："cn" A股（可选，会被忽略，始终使用cn）
  "date_range": {
    "init_date": "2025-10-09 10:30:00",  // 回测开始时间（小时级）
    "end_date": "2025-10-31 15:00:00"    // 回测结束时间（小时级）
  },
  "models": [
    {
      "name": "claude-3.7-sonnet",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-3.7-sonnet-astock-hour",
      "enabled": true
    }
  ],
  "agent_config": {
    "initial_cash": 100000.0        // 初始资金：¥100,000人民币
  },
  "log_config": {
    "log_path": "./data/agent_data_astock_hour"  // A股小时级数据路径
  }
}
```

> 💡 **提示**: A股小时级交易时间点为：10:30、11:30、14:00、15:00（每天4个时间点）

#### 📅 加密货币配置示例 (使用 BaseAgentCrypto)
```json
{
  "agent_type": "BaseAgentCrypto",  // 加密货币专用代理
  "market": "crypto",               // 市场类型："crypto" 加密货币
  "date_range": {
    "init_date": "2025-01-01",     // 回测开始日期
    "end_date": "2025-01-31"       // 回测结束日期
  },
  "models": [
    {
      "name": "claude-3.7-sonnet",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-3.7-sonnet",
      "enabled": true
    }
  ],
  "agent_config": {
    "initial_cash": 50000.0       // 初始资金：50,000 USDT
  },
  "log_config": {
    "log_path": "./data/agent_data_crypto" // 加密货币数据路径
  }
}
```

> 💡 **提示**: `BaseAgentCrypto` 将使用UTC 00:00的价格作为买入/卖出价格，市场应设置为 `"crypto"`。

> 💡 **提示**: 使用 `BaseAgentCrypto` 时，`market` 参数会被自动设置为 `"crypto"`，无需手动指定。

> 💡 **提示**: 使用 `BaseAgentAStock` 时，`market` 参数会被自动设置为 `"cn"`，无需手动指定。

### 📈 启动Web界面

```bash
cd docs
python3 -m http.server 8000
# 访问 http://localhost:8000
```

或者使用启动脚本：

```bash
# 启动Web界面
bash scripts/start_ui.sh
# 访问: http://localhost:8888
```

---

## 📈 性能分析

### 🏆 竞技规则

| 规则项 | 美股 | A股（中国） | 加密货币 |
|--------|------|------------|----------|
| **💰 初始资金** | $10,000 | ¥100,000 | 50,000 USDT |
| **📈 交易标的** | 纳斯达克100 | 上证50 | BITWISE10顶级加密货币 |
| **🌍 市场** | 美国股市 | 中国A股市场 | 全球加密货币市场 |
| **⏰ 交易时间** | 工作日 | 工作日 | 整周 |
| **💲 价格基准** | 开盘价 | 开盘价 | 开盘价 |
| **📝 记录方式** | JSONL格式 | JSONL格式 | JSONL格式 |

## ⚙️ 配置指南

### 📋 配置文件结构

```json
{
  "agent_type": "BaseAgent",
  "market": "us",
  "date_range": {
    "init_date": "2025-01-01",
    "end_date": "2025-01-31"
  },
  "models": [
    {
      "name": "claude-3.7-sonnet",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-3.7-sonnet",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 30,
    "max_retries": 3,
    "base_delay": 1.0,
    "initial_cash": 10000.0
  },
  "log_config": {
    "log_path": "./data/agent_data"
  }
}
```

### 🔧 配置参数说明

| 参数 | 说明 | 可选值 | 默认值 |
|------|------|--------|--------|
| `agent_type` | AI代理类型 | "BaseAgent"（通用）<br>"BaseAgentAStock"（A股专用）<br>"BaseAgentCrypto"（加密货币专用） | "BaseAgent" |
| `market` | 市场类型 | "us"（美股）<br>"cn"（A股）<br>"crypto"（加密货币）<br>注：使用BaseAgentAStock时自动设为"cn"，使用BaseAgentCrypto时自动设为"crypto" | "us" |
| `max_steps` | 最大推理步数 | 正整数 | 30 |
| `max_retries` | 最大重试次数 | 正整数 | 3 |
| `base_delay` | 操作延迟(秒) | 浮点数 | 1.0 |
| `initial_cash` | 初始资金 | 浮点数 | $10,000（美股）<br>¥100,000（A股）<br>50,000 USDT（加密货币） |

#### 📋 代理类型说明

| 代理类型 | 适用市场 | 交易频率 | 特点 |
|---------|---------|---------|------|
| **BaseAgent** | 美股 | 日线 | • 通用交易代理<br>• 通过 `market` 参数切换市场<br>• 灵活配置股票池 |
| **BaseAgent_Hour** | 美股 | 小时级 | • 美股小时级交易<br>• 更精细的交易时机控制<br>• 支持盘中交易决策 |
| **BaseAgentAStock** | A股 | 日线 | • 专为A股日线优化<br>• 内置A股交易规则（一手100股、T+1）<br>• 默认上证50股票池<br>• 人民币计价 |
| **BaseAgentAStock_Hour** | A股 | 小时级 | • A股小时级交易（10:30/11:30/14:00/15:00）<br>• 支持盘中4个时间点交易<br>• 继承所有A股交易规则<br>• 数据源：merged_hourly.jsonl |
| **BaseAgentCrypto** | 加密货币 | 日线 | • 专为加密货币优化<br>• 默认BITWISE10指数成分池<br>• USDT计价<br>• 支持整周交易 |

#### 🪙 加密货币交易特点

加密货币交易具有以下独特特点：

- **整周交易**: 不同于股票市场，加密货币市场支持整周交易
- **高波动性**: 价格波动剧烈，既带来高风险也提供高收益机会
- **多资产组合**: 支持同时交易多种主流加密货币
- **开盘价定价**: 基于全球交易所的开盘价格数据
- **USDT 计价**: 使用稳定币 USDT 作为计价单位，减少汇率波动影响

### 📊 数据格式

#### 💰 持仓记录 (position.jsonl)
```json
{
  "date": "2025-01-20",
  "id": 1,
  "this_action": {
    "action": "buy",
    "symbol": "AAPL", 
    "amount": 10
  },
  "positions": {
    "AAPL": 10,
    "MSFT": 0,
    "CASH": 9737.6
  }
}
```

#### 📈 价格数据 (merged.jsonl)
```json
{
  "Meta Data": {
    "2. Symbol": "AAPL",
    "3. Last Refreshed": "2025-01-20"
  },
  "Time Series (Daily)": {
    "2025-01-20": {
      "1. buy price": "255.8850",
      "2. high": "264.3750", 
      "3. low": "255.6300",
      "4. sell price": "262.2400",
      "5. volume": "90483029"
    }
  }
}
```

### 📁 文件结构

```
data/agent_data/
├── claude-3.7-sonnet/
│   ├── position/
│   │   └── position.jsonl      # 📝 持仓记录
│   └── log/
│       └── 2025-01-20/
│           └── log.jsonl       # 📊 交易日志
├── gpt-4o/
│   └── ...
└── qwen3-max/
    └── ...
```

## 🔌 第三方策略集成

AI-Trader Bench采用模块化设计，支持轻松集成第三方策略和自定义AI代理。

### 🛠️ 集成方式

#### 1. 自定义AI代理
```python
# 创建新的AI代理类
class CustomAgent(BaseAgent):
    def __init__(self, model_name, **kwargs):
        super().__init__(model_name, **kwargs)
        # 添加自定义逻辑
```

#### 2. 注册新代理
```python
# 在 main.py 中注册
AGENT_REGISTRY = {
    "BaseAgent": {
        "module": "agent.base_agent.base_agent",
        "class": "BaseAgent"
    },
    "BaseAgentAStock": {
        "module": "agent.base_agent_astock.base_agent_astock",
        "class": "BaseAgentAStock"
    },
    "CustomAgent": {  # 新增自定义代理
        "module": "agent.custom.custom_agent",
        "class": "CustomAgent"
    },
}
```

#### 3. 配置文件设置
```json
{
  "agent_type": "CustomAgent",
  "models": [
    {
      "name": "your-custom-model",
      "basemodel": "your/model/path",
      "signature": "custom-signature",
      "enabled": true
    }
  ]
}
```

### 🔧 扩展工具链

#### 添加自定义工具
```python
# 创建新的MCP工具
@mcp.tools()
class CustomTool:
    def __init__(self):
        self.name = "custom_tool"
    
    def execute(self, params):
        # 实现自定义工具逻辑
        return result
```

## 🚀 路线图

### 🌟 未来计划
- [x] **🇨🇳 A股支持** - ✅ 上证50指数数据集成已完成
- [x] **₿ 加密货币支持** - ✅ 主流加密货币交易支持已完成
- [ ] **📊 收盘后统计** - 自动收益分析
- [ ] **🔌 策略市场** - 添加第三方策略分享平台
- [ ] **🎨 炫酷前端界面** - 现代化Web仪表板
- [ ] **📈 更多策略** - 技术分析、量化策略
- [ ] **⏰ 高级回放** - 支持分钟级时间精度和实时回放
- [ ] **🔍 智能过滤** - 更精确的未来信息检测和过滤


## 📞 支持与社区

- **💬 讨论**: [GitHub Discussions](https://github.com/HKUDS/AI-Trader/discussions)
- **🐛 问题**: [GitHub Issues](https://github.com/HKUDS/AI-Trader/issues)

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源协议。

## 🙏 致谢

感谢以下开源项目和服务：
- [LangChain](https://github.com/langchain-ai/langchain) - AI应用开发框架
- [MCP](https://github.com/modelcontextprotocol) - Model Context Protocol
- [Alpha Vantage](https://www.alphavantage.co/) - 美股金融数据API
- [Tushare](https://tushare.pro/) - A股市场数据API
- [efinance](https://github.com/Micro-sheep/efinance) - A股小时级数据获取
- [Jina AI](https://jina.ai/) - 信息搜索服务

## 👥 管理员

<div align="center">

<a href="https://github.com/TianyuFan0504">
  <img src="https://avatars.githubusercontent.com/TianyuFan0504?v=4" width="80" height="80" alt="TianyuFan0504" style="border-radius: 50%; margin: 5px;"/>
</a>
<a href="https://github.com/yangqin-jiang">
  <img src="https://avatars.githubusercontent.com/yangqin-jiang?v=4" width="80" height="80" alt="yangqin-jiang" style="border-radius: 50%; margin: 5px;"/>
</a>
<a href="https://github.com/yuh-yang">
  <img src="https://avatars.githubusercontent.com/yuh-yang?v=4" width="80" height="80" alt="yuh-yang" style="border-radius: 50%; margin: 5px;"/>
</a>
<a href="https://github.com/Hoder-zyf">
  <img src="https://avatars.githubusercontent.com/Hoder-zyf?v=4" width="80" height="80" alt="Hoder-zyf" style="border-radius: 50%; margin: 5px;"/>
</a>

</div>

## 🤝 贡献

<div align="center">
  我们感谢所有贡献者的宝贵贡献。
</div>

<div align="center">
  <a href="https://github.com/HKUDS/AI-Trader/graphs/contributors">
    <img src="https://contrib.rocks/image?repo=HKUDS/AI-Trader" style="border-radius: 15px; box-shadow: 0 0 20px rgba(0, 217, 255, 0.3);" />
  </a>
</div>

## 免责声明

AI-Trader项目所提供的资料仅供研究之用，并不构成任何投资建议。投资者在作出任何投资决策之前，应寻求独立专业意见。任何过往表现未必可作为未来业绩的指标。阁下应注意，投资价值可能上升亦可能下跌，且并无任何保证。AI-Trader项目的所有内容仅作研究之用，并不构成对所提及之证券／行业的任何投资推荐。投资涉及风险。如有需要，请寻求专业咨询。

---

<div align="center">

**🌟 如果这个项目对你有帮助，请给我们一个Star！**

[![GitHub stars](https://img.shields.io/github/stars/HKUDS/AI-Trader?style=social)](https://github.com/HKUDS/AI-Trader)
[![GitHub forks](https://img.shields.io/github/forks/HKUDS/AI-Trader?style=social)](https://github.com/HKUDS/AI-Trader)

**🤖 让AI在金融市场中完全自主决策、一展身手！**  
**🛠️ 纯工具驱动，零人工干预，真正的AI交易竞技场！** 🚀

</div>

---

## ⭐ Star 历史

*社区增长轨迹*

<div align="center">
  <a href="https://star-history.com/#HKUDS/AI-Trader&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=HKUDS/AI-Trader&type=Date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=HKUDS/AI-Trader&type=Date" />
      <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=HKUDS/AI-Trader&type=Date" style="border-radius: 15px; box-shadow: 0 0 30px rgba(0, 217, 255, 0.3);" />
    </picture>
  </a>
</div>

---

<p align="center">
  <em> ❤️ 感谢访问 ✨ AI-Trader!</em><br><br>
  <img src="https://visitor-badge.laobi.icu/badge?page_id=HKUDS.AI-Trader&style=for-the-badge&color=00d4ff" alt="Views">
</p>
