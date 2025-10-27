# AI-Trader 模拟盘实时交易迁移指南

本文档详细说明如何将AI-Trader系统从**历史回测模式**迁移到**模拟盘实时交易模式**。

---

## 📋 目录

1. [当前架构分析](#当前架构分析)
2. [核心差异对比](#核心差异对比)
3. [需要修改的组件](#需要修改的组件)
4. [实时价格数据源方案](#实时价格数据源方案)
5. [定时调度方案](#定时调度方案)
6. [配置更改清单](#配置更改清单)
7. [实施步骤](#实施步骤)
8. [风险与注意事项](#风险与注意事项)

---

## 🔍 当前架构分析

### 历史回测模式的核心特征

```
┌─────────────────────────────────────────────────────────────┐
│ 历史回测模式 (Current)                                       │
├─────────────────────────────────────────────────────────────┤
│ 1. 数据源：静态历史数据                                      │
│    - data/merged.jsonl (100+ MB)                            │
│    - 包含100只股票的完整历史价格                             │
│    - Alpha Vantage API (每天手动运行一次)                    │
│                                                             │
│ 2. 时间模式：循环遍历历史日期                                │
│    - init_date → end_date                                   │
│    - 顺序处理每个交易日                                      │
│    - 一次性运行完所有日期                                    │
│                                                             │
│ 3. 执行方式：批量回测                                        │
│    - python main.py configs/config.json                     │
│    - 等待所有日期处理完成后退出                              │
│                                                             │
│ 4. 价格获取：从本地文件读取                                  │
│    - get_open_prices() 读取 merged.jsonl                    │
│    - O(1) 时间复杂度，无网络延迟                            │
│                                                             │
│ 5. 交易执行：模拟记录                                        │
│    - 只写入 position.jsonl                                  │
│    - 无真实券商API调用                                       │
└─────────────────────────────────────────────────────────────┘
```

### 关键文件与数据流

| 组件 | 文件 | 作用 | 数据来源 |
|------|------|------|---------|
| **价格数据获取** | `data/get_daily_price.py` | 从Alpha Vantage API下载历史价格 | Alpha Vantage API |
| **数据合并** | `data/merge_jsonl.py` | 合并100只股票数据到merged.jsonl | 本地JSON文件 |
| **价格查询工具** | `tools/price_tools.py` | 从merged.jsonl读取指定日期价格 | `data/merged.jsonl` |
| **主控制循环** | `main.py:200-201` | 调用 `run_date_range(INIT_DATE, END_DATE)` | 配置文件 |
| **日期遍历** | `base_agent.py:349-397` | 顺序处理每个交易日 | position.jsonl最后日期 |

---

## ⚖️ 核心差异对比

### 历史回测 vs 模拟盘实时交易

| 维度 | 历史回测模式 | 模拟盘实时交易模式 |
|------|------------|------------------|
| **数据时效性** | 静态历史数据（已知未来） | 实时市场数据（未知未来） |
| **执行时机** | 批量处理所有日期 | 定时触发（每日固定时间） |
| **价格获取** | 本地文件读取 | 实时API调用 |
| **运行周期** | 一次性完成后退出 | 常驻进程/定时任务 |
| **日期控制** | 配置文件指定范围 | 系统当前日期 |
| **数据延迟** | 无延迟（离线） | 有延迟（网络+API限流） |
| **成本** | 无运行成本 | API调用费用 |
| **风险** | 无真实风险 | 模拟风险（真实市场波动） |

---

## 🛠️ 需要修改的组件

### 1. 价格数据源模块 ⭐⭐⭐⭐⭐

**当前问题**:
- `tools/price_tools.py:50-100` - 从静态 `merged.jsonl` 读取历史价格
- `data/get_daily_price.py` - 手动运行，批量下载历史数据
- 依赖本地文件，无法获取实时价格

**需要修改**:

#### 方案A：定时更新本地数据（推荐）
```python
# 新建 data/update_realtime_price.py
import schedule
import time
from get_daily_price import get_daily_price
from merge_jsonl import merge_all_jsonl

def update_today_prices():
    """每日更新最新价格数据"""
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"📊 Updating prices for {today}")

    # 1. 下载所有股票的最新价格
    for symbol in all_nasdaq_100_symbols:
        get_daily_price(symbol)
        time.sleep(12)  # Alpha Vantage API限制：5次/分钟

    # 2. 合并到 merged.jsonl
    merge_all_jsonl()
    print("✅ Price data updated")

# 每日美东时间16:30（收盘后30分钟）运行
schedule.every().day.at("16:30").do(update_today_prices)

while True:
    schedule.run_pending()
    time.sleep(60)
```

**优点**:
- ✅ 最小化代码修改
- ✅ 复用现有 `price_tools.py` 逻辑
- ✅ 离线执行，速度快

**缺点**:
- ❌ 需要额外的数据更新进程
- ❌ 仍依赖Alpha Vantage免费API（限流严格）

---

#### 方案B：实时API调用
```python
# 修改 tools/price_tools.py

def get_open_prices_realtime(today_date: str, symbols: List[str]) -> Dict[str, Optional[float]]:
    """从Alpha Vantage API实时获取开盘价"""
    results = {}
    APIKEY = os.getenv("ALPHAADVANTAGE_API_KEY")

    for symbol in symbols:
        url = f'https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={symbol}&interval=5min&apikey={APIKEY}'
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            # 提取今日开盘价
            time_series = data.get("Time Series (5min)", {})
            # 找到今天第一个5分钟K线的价格作为开盘价
            ...
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            results[f"{symbol}_price"] = None

    return results
```

**优点**:
- ✅ 真正的实时数据
- ✅ 无需本地数据存储

**缺点**:
- ❌ API限流严重（5次/分钟，100只股票需要20分钟）
- ❌ 网络不稳定风险
- ❌ 需要付费API（实时数据Alpha Vantage免费版不支持）

---

#### 方案C：使用更好的数据源（最优）

**推荐替代API**:

| API服务 | 免费额度 | 延迟 | 成本 | 推荐指数 |
|---------|---------|------|------|---------|
| **Polygon.io** | 5次/分钟 | 实时 | $99/月 | ⭐⭐⭐⭐⭐ |
| **Alpaca Markets** | 无限制 | 15分钟延迟 | 免费 | ⭐⭐⭐⭐ |
| **Yahoo Finance (非官方)** | 无限制 | 15分钟延迟 | 免费 | ⭐⭐⭐ |
| **IEX Cloud** | 50K次/月 | 实时 | $9/月起 | ⭐⭐⭐⭐ |

**Alpaca Markets示例**（推荐用于模拟盘）:
```python
# 新建 tools/alpaca_price.py
import alpaca_trade_api as tradeapi
import os

def get_alpaca_prices(symbols: List[str]) -> Dict[str, float]:
    """从Alpaca获取最新价格（15分钟延迟，免费）"""
    api = tradeapi.REST(
        os.getenv("ALPACA_API_KEY"),
        os.getenv("ALPACA_SECRET_KEY"),
        base_url='https://paper-api.alpaca.markets'  # 模拟盘API
    )

    # 获取多只股票的最新报价
    barset = api.get_bars(symbols, '1Day', limit=1)

    results = {}
    for symbol in symbols:
        bars = barset[symbol]
        if bars:
            results[f"{symbol}_price"] = bars[0].o  # 开盘价

    return results
```

**优点**:
- ✅ 免费且无限次调用
- ✅ 官方API，稳定可靠
- ✅ 支持模拟盘交易（paper trading）
- ✅ 可扩展到真实交易

**缺点**:
- ⚠️  15分钟延迟（但对日内交易影响不大）
- ⚠️  需要注册Alpaca账户

---

### 2. 主控制循环 ⭐⭐⭐⭐

**当前问题**:
- `main.py:200-201` 一次性运行整个日期范围
- `base_agent.py:349-397` 批量处理所有交易日

**需要修改**:

```python
# 修改 main.py

async def run_single_day_trading():
    """运行单日交易（模拟盘模式）"""

    # 1. 获取今天日期
    today = datetime.now().strftime("%Y-%m-%d")

    # 2. 检查是否为交易日
    if datetime.now().weekday() >= 5:  # 周末跳过
        print(f"⏭️  {today} is weekend, skipping")
        return

    # 3. 检查市场是否开盘（美东时间9:30-16:00）
    now_et = datetime.now(pytz.timezone('US/Eastern'))
    market_open = now_et.replace(hour=9, minute=30, second=0)
    market_close = now_et.replace(hour=16, minute=0, second=0)

    if now_et < market_open or now_et > market_close:
        print(f"⏰ Market is closed, skipping")
        return

    # 4. 更新今日价格数据
    await update_today_prices()

    # 5. 运行所有模型的今日交易
    for model_config in enabled_models:
        agent = create_agent(model_config)
        await agent.initialize()

        # 只运行今天一天
        await agent.run_trading_session(today)

    print(f"✅ {today} trading completed")


if __name__ == "__main__":
    # 模拟盘模式：定时任务
    schedule.every().day.at("10:00").do(lambda: asyncio.run(run_single_day_trading()))

    print("🤖 AI-Trader Live Trading Mode Started")
    print("⏰ Scheduled to run daily at 10:00 AM ET")

    while True:
        schedule.run_pending()
        time.sleep(60)
```

**关键变更**:
1. ❌ 删除 `run_date_range(INIT_DATE, END_DATE)`
2. ✅ 改为 `run_trading_session(today)` - 只运行今天
3. ✅ 添加交易日检查（周末/假期跳过）
4. ✅ 添加交易时段检查（盘前/盘后跳过）

---

### 3. 配置文件结构 ⭐⭐⭐

**当前配置** (`configs/default_config.json`):
```json
{
  "agent_type": "BaseAgent",
  "date_range": {
    "init_date": "2025-10-01",  // ❌ 模拟盘不需要
    "end_date": "2025-10-24"     // ❌ 模拟盘不需要
  },
  "models": [...],
  "agent_config": {
    "max_steps": 30,
    "initial_cash": 10000.0
  }
}
```

**模拟盘配置** (`configs/live_trading.json`):
```json
{
  "mode": "live",  // ✅ 新增：标识为实时交易模式
  "agent_type": "BaseAgent",
  "schedule": {
    "timezone": "US/Eastern",
    "trading_time": "10:00",  // 美东时间10:00执行
    "market_hours": {
      "open": "09:30",
      "close": "16:00"
    }
  },
  "data_source": {
    "provider": "alpaca",  // 或 "polygon", "alpha_vantage"
    "update_frequency": "daily",  // 每日更新一次
    "cache_enabled": true
  },
  "models": [
    {
      "name": "claude-3.7-sonnet",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-live",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 30,
    "initial_cash": 10000.0,
    "paper_trading": true  // ✅ 明确标识为模拟盘
  },
  "notifications": {  // ✅ 新增：通知配置
    "email": "your@email.com",
    "slack_webhook": "https://hooks.slack.com/...",
    "notify_on": ["trade", "error", "daily_summary"]
  }
}
```

---

### 4. 日期管理逻辑 ⭐⭐⭐

**当前逻辑** (`base_agent.py:349-397`):
```python
def get_trading_dates(self, init_date: str, end_date: str) -> List[str]:
    """计算需要处理的交易日列表"""
    # 从position.jsonl获取最后日期
    latest_date = self._get_latest_position_date()

    # 计算从latest_date+1到end_date的所有交易日
    ...
    return trading_dates
```

**模拟盘逻辑**:
```python
def should_trade_today(self) -> bool:
    """判断今天是否应该交易"""
    today = datetime.now()

    # 1. 检查是否为交易日
    if today.weekday() >= 5:
        return False

    # 2. 检查是否为节假日（需要假期日历）
    if self.is_market_holiday(today):
        return False

    # 3. 检查今天是否已经交易过
    latest_date = self._get_latest_position_date()
    if latest_date == today.strftime("%Y-%m-%d"):
        print("⚠️  Already traded today")
        return False

    return True

def is_market_holiday(self, date: datetime) -> bool:
    """检查是否为美股市场假期"""
    # 使用 pandas_market_calendars 库
    import pandas_market_calendars as mcal
    nyse = mcal.get_calendar('NYSE')
    schedule = nyse.schedule(start_date=date, end_date=date)
    return len(schedule) == 0
```

**需要安装**:
```bash
pip install pandas-market-calendars
```

---

### 5. MCP工具修改 ⭐⭐

**当前工具**:
- `tool_get_price_local.py` - 从本地merged.jsonl读取价格

**模拟盘工具**:
```python
# 新建 agent_tools/tool_get_price_realtime.py

from fastmcp import FastMCP
import os
from tools.alpaca_price import get_alpaca_prices  # 使用Alpaca实时数据

mcp = FastMCP("GetPriceRealtime")

@mcp.tool()
def get_price_realtime(symbol: str, date: str) -> Dict[str, Any]:
    """
    获取实时价格数据

    Args:
        symbol: 股票代码
        date: 日期（用于验证，实际获取最新价格）

    Returns:
        价格数据字典
    """
    # 1. 验证日期是否为今天
    today = datetime.now().strftime("%Y-%m-%d")
    if date != today:
        return {"error": f"Can only query today's price. Requested: {date}, Today: {today}"}

    # 2. 从Alpaca获取实时价格
    try:
        prices = get_alpaca_prices([symbol])

        if f"{symbol}_price" not in prices:
            return {"error": f"Symbol {symbol} not found"}

        return {
            "symbol": symbol,
            "date": today,
            "open": prices[f"{symbol}_price"],
            "source": "alpaca",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}
```

**更新MCP配置** (`base_agent.py:116-135`):
```python
def _get_default_mcp_config(self) -> List[Dict]:
    return [
        # ... 其他工具
        {
            "name": "GetPriceRealtime",  # ✅ 使用实时价格工具
            "transport": "streamable_http",
            "url": f"http://localhost:{os.getenv('GETPRICE_HTTP_PORT', '19003')}/mcp",
        },
    ]
```

---

## 📡 实时价格数据源方案

### 推荐方案：Alpaca Markets（免费模拟盘）

#### 1. 注册Alpaca账户

访问 https://alpaca.markets/ 注册Paper Trading账户（完全免费）

#### 2. 获取API密钥

```bash
# 添加到 .env 文件
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets  # 模拟盘
```

#### 3. 安装SDK

```bash
pip install alpaca-trade-api
```

#### 4. 实现价格获取模块

```python
# 新建 tools/alpaca_price.py

import alpaca_trade_api as tradeapi
import os
from datetime import datetime
from typing import List, Dict

class AlpacaPriceProvider:
    def __init__(self):
        self.api = tradeapi.REST(
            os.getenv("ALPACA_API_KEY"),
            os.getenv("ALPACA_SECRET_KEY"),
            base_url=os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        )

    def get_latest_prices(self, symbols: List[str]) -> Dict[str, float]:
        """获取多只股票的最新价格"""
        try:
            # 获取最新报价
            bars = self.api.get_bars(symbols, '1Day', limit=1).df

            results = {}
            for symbol in symbols:
                if symbol in bars.index.get_level_values(0):
                    symbol_bars = bars.loc[symbol]
                    results[f"{symbol}_price"] = float(symbol_bars['open'].iloc[-1])
                else:
                    results[f"{symbol}_price"] = None

            return results
        except Exception as e:
            print(f"Error fetching prices from Alpaca: {e}")
            return {f"{s}_price": None for s in symbols}

    def get_market_status(self) -> Dict[str, bool]:
        """获取市场状态"""
        clock = self.api.get_clock()
        return {
            "is_open": clock.is_open,
            "next_open": str(clock.next_open),
            "next_close": str(clock.next_close)
        }

# 全局实例
alpaca_provider = AlpacaPriceProvider()

def get_alpaca_prices(symbols: List[str]) -> Dict[str, float]:
    return alpaca_provider.get_latest_prices(symbols)

def check_market_open() -> bool:
    status = alpaca_provider.get_market_status()
    return status["is_open"]
```

---

## ⏰ 定时调度方案

### 方案A：Python Schedule（简单）

```python
# 修改 main.py

import schedule
import time
import asyncio

def job():
    """定时任务入口"""
    asyncio.run(run_single_day_trading())

# 每个交易日美东时间10:00执行
schedule.every().day.at("10:00").do(job)

if __name__ == "__main__":
    print("🤖 AI-Trader Live Mode Started")
    while True:
        schedule.run_pending()
        time.sleep(60)
```

**优点**: 简单易用
**缺点**: 进程需要常驻，重启后丢失状态

---

### 方案B：Cron（推荐生产环境）

```bash
# 编辑 crontab
crontab -e

# 每个交易日上午10:00运行（服务器时区需要调整）
0 10 * * 1-5 cd /data1/devin/AI-Trader && source venv/bin/activate && python main.py configs/live_trading.json >> logs/live_trading.log 2>&1
```

**优点**:
- ✅ 系统级调度，稳定可靠
- ✅ 自动重试机制
- ✅ 日志管理完善

**缺点**: 需要服务器权限

---

### 方案C：Systemd Timer（Linux推荐）

```ini
# /etc/systemd/system/ai-trader.timer
[Unit]
Description=AI-Trader Daily Trading Timer

[Timer]
OnCalendar=Mon-Fri 10:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/ai-trader.service
[Unit]
Description=AI-Trader Live Trading Service

[Service]
Type=oneshot
User=Devin
WorkingDirectory=/data1/devin/AI-Trader
ExecStart=/data1/devin/AI-Trader/venv/bin/python main.py configs/live_trading.json
```

启用：
```bash
sudo systemctl enable ai-trader.timer
sudo systemctl start ai-trader.timer
```

---

## 📝 配置更改清单

### 代码文件修改

| 文件 | 修改类型 | 优先级 | 说明 |
|------|---------|-------|------|
| `main.py` | 重写 | ⭐⭐⭐⭐⭐ | 改为单日执行模式，添加定时调度 |
| `tools/price_tools.py` | 新增函数 | ⭐⭐⭐⭐⭐ | 添加实时价格获取函数 |
| `tools/alpaca_price.py` | 新建 | ⭐⭐⭐⭐⭐ | Alpaca API集成 |
| `agent/base_agent/base_agent.py` | 修改 | ⭐⭐⭐⭐ | 添加交易日检查逻辑 |
| `agent_tools/tool_get_price_realtime.py` | 新建 | ⭐⭐⭐ | MCP实时价格工具 |
| `data/update_realtime_price.py` | 新建 | ⭐⭐⭐ | 定时价格更新脚本 |
| `configs/live_trading.json` | 新建 | ⭐⭐⭐ | 模拟盘配置文件 |

---

### 环境变量添加

```bash
# .env 文件新增

# === Alpaca Markets API (推荐) ===
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# === 运行模式 ===
TRADING_MODE=live  # 或 backtest

# === 时区设置 ===
TRADING_TIMEZONE=US/Eastern

# === 通知配置 ===
NOTIFICATION_EMAIL=your@email.com
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
```

---

### 依赖包安装

```bash
# requirements.txt 新增

alpaca-trade-api>=3.0.0
pandas-market-calendars>=4.0.0
schedule>=1.2.0
pytz>=2023.3
```

安装：
```bash
source venv/bin/activate
pip install -r requirements.txt
```

---

## 🚀 实施步骤

### Phase 1: 准备工作（1-2天）

1. **注册Alpaca账户**
   ```bash
   # 访问 https://alpaca.markets/
   # 注册Paper Trading账户
   # 获取API密钥
   ```

2. **安装依赖包**
   ```bash
   pip install alpaca-trade-api pandas-market-calendars schedule
   ```

3. **配置环境变量**
   ```bash
   # 编辑 .env
   echo "ALPACA_API_KEY=your_key" >> .env
   echo "ALPACA_SECRET_KEY=your_secret" >> .env
   ```

---

### Phase 2: 代码开发（3-5天）

4. **创建Alpaca价格模块**
   ```bash
   # 新建 tools/alpaca_price.py
   # 实现 get_alpaca_prices() 函数
   ```

5. **修改价格查询逻辑**
   ```bash
   # 修改 tools/price_tools.py
   # 添加 get_open_prices_realtime() 函数
   ```

6. **重构主控制循环**
   ```bash
   # 修改 main.py
   # 实现 run_single_day_trading() 函数
   ```

7. **添加交易日检查**
   ```bash
   # 修改 base_agent.py
   # 实现 should_trade_today() 函数
   ```

---

### Phase 3: 测试验证（2-3天）

8. **单元测试**
   ```bash
   # 测试Alpaca连接
   python tools/alpaca_price.py

   # 测试价格获取
   python -c "from tools.alpaca_price import get_alpaca_prices; print(get_alpaca_prices(['AAPL']))"
   ```

9. **集成测试**
   ```bash
   # 手动运行一次模拟盘交易
   python main.py configs/live_trading.json

   # 检查 position.jsonl 是否正确更新
   tail data/agent_data/claude-live/position/position.jsonl
   ```

10. **压力测试**
    ```bash
    # 连续运行3天，观察稳定性
    # 检查API限流情况
    # 验证错误处理机制
    ```

---

### Phase 4: 部署上线（1天）

11. **配置定时任务**
    ```bash
    # 使用Cron或Systemd Timer
    crontab -e
    # 添加定时任务
    ```

12. **配置监控告警**
    ```python
    # 实现邮件/Slack通知
    # 添加异常监控
    ```

13. **启动模拟盘**
    ```bash
    # 启动定时任务
    systemctl start ai-trader.timer

    # 查看状态
    systemctl status ai-trader.timer
    ```

---

## ⚠️ 风险与注意事项

### 1. API限流风险

**问题**: Alpha Vantage免费版限制5次/分钟

**解决**:
- ✅ 使用Alpaca（无限制）
- ✅ 实现请求队列和限流逻辑
- ✅ 添加重试机制

---

### 2. 数据延迟风险

**问题**: 15分钟延迟可能导致价格不准

**解决**:
- ✅ 模拟盘对延迟不敏感（日线级别策略）
- ✅ 在提示词中明确说明价格可能有延迟
- ✅ 升级到付费API获取实时数据

---

### 3. 市场假期处理

**问题**: 美股节假日需要特殊处理

**解决**:
```python
import pandas_market_calendars as mcal

nyse = mcal.get_calendar('NYSE')
schedule = nyse.schedule(start_date='2025-01-01', end_date='2025-12-31')

# 判断今天是否为交易日
is_trading_day = today in schedule.index
```

---

### 4. 时区问题

**问题**: 服务器时区与美东时间不一致

**解决**:
```python
import pytz

# 始终使用美东时间
eastern = pytz.timezone('US/Eastern')
now_et = datetime.now(eastern)

# 检查是否在交易时段
market_open = now_et.replace(hour=9, minute=30, second=0)
market_close = now_et.replace(hour=16, minute=0, second=0)
```

---

### 5. 错误处理

**关键场景**:
- API调用失败
- 网络超时
- 价格数据缺失
- Agent决策异常

**处理机制**:
```python
def safe_trading_execution():
    try:
        # 交易执行
        await agent.run_trading_session(today)
    except APIError as e:
        notify_admin(f"API Error: {e}")
        # 重试3次
    except NetworkError as e:
        notify_admin(f"Network Error: {e}")
        # 使用缓存数据
    except Exception as e:
        notify_admin(f"Unknown Error: {e}")
        # 跳过今日交易，记录日志
```

---

### 6. 成本控制

| 服务 | 免费额度 | 超额成本 | 月度预估 |
|------|---------|---------|---------|
| Alpaca (模拟盘) | 无限 | $0 | $0 |
| Alpha Vantage | 5次/分钟 | - | $0 |
| Polygon.io | 5次/分钟 | $99/月 | $99 |
| IEX Cloud | 50K次/月 | $0.0001/次 | ~$10 |

**建议**:
- 模拟盘阶段使用Alpaca（完全免费）
- 真实交易考虑升级Polygon.io或IEX Cloud

---

## 📊 监控指标

### 关键指标

```python
# 每日记录到日志
{
  "date": "2025-10-27",
  "trades": 5,
  "api_calls": 150,
  "api_failures": 2,
  "execution_time": "45s",
  "portfolio_value": 10588.31,
  "daily_return": 0.58,
  "errors": []
}
```

### 告警规则

- ❌ API失败率 > 10% → 发送告警
- ❌ 连续3天未交易 → 发送告警
- ❌ 账户亏损 > 20% → 发送告警
- ❌ Agent超过15步未完成 → 发送告警

---

## 🎯 总结

### 核心变更点

1. **价格数据源**: 静态文件 → Alpaca实时API
2. **运行模式**: 批量回测 → 定时单日执行
3. **日期管理**: 配置文件指定 → 系统当前日期
4. **调度方式**: 手动运行 → Cron/Systemd定时
5. **配置文件**: 添加 `mode: live` 标识

### 工作量评估

- **代码修改**: 约500-800行
- **测试验证**: 3-5天
- **总工期**: 1-2周

### 下一步

1. ✅ 选择数据源（推荐Alpaca）
2. ✅ 注册账户并获取API密钥
3. ✅ 按Phase 1-4步骤实施
4. ✅ 小规模测试（1个模型，1周）
5. ✅ 扩展到多模型并发运行

---

**文档版本**: 1.0
**最后更新**: 2025-10-27
**作者**: AI-Trader Team
