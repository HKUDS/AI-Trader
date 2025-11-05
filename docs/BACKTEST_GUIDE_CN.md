# 美股科技100回测快速指南

## 📊 回测说明

本指南用于在 AI-Trader 系统中回测 2025 年上半年（1月-6月）100支美股科技股的交易表现。

## 🎯 回测功能原理

### 核心机制

1. **历史时间回放**
   - 系统从配置的 `init_date` 开始，逐日模拟到 `end_date`
   - 每个交易日，AI 代理独立分析并做出交易决策

2. **防未来数据泄露**
   - 系统通过 `TODAY_DATE` 控制当前"模拟日期"
   - 查询当日数据时：只能看到**开盘价**，无法看到收盘价、最高/最低价
   - 查询历史数据时：可以看到完整的 OHLCV 数据
   - 这确保 AI 无法"偷看"未来信息

3. **交易执行流程**
   ```
   设置日期 → AI 分析市场 → 做出决策 → 记录交易 → 下一日
   ```

4. **数据存储**
   - `position.jsonl`: 每日持仓和交易动作
   - `log/{date}/log.jsonl`: AI 的完整思考和决策过程

## 🚀 快速开始

### 前置条件

1. ✅ 已获取 100 支科技股的数据文件（`daily_prices_*.json`）
2. ✅ 已配置 `.env` 文件中的 API 密钥
3. ✅ 已安装依赖：`pip install -r requirements.txt`

### 一键运行

```bash
# 赋予脚本执行权限
chmod +x scripts/run_backtest_tech100.sh

# 运行回测
bash scripts/run_backtest_tech100.sh
```

该脚本会自动完成：
- ✅ 数据格式转换（合并为 merged.jsonl）
- ✅ 启动 MCP 工具服务
- ✅ 运行 AI 交易代理回测
- ✅ 显示回测结果位置

### 手动步骤（可选）

如果需要分步执行：

#### 1️⃣ 数据准备

```bash
cd data
python3 merge_tech100_data.py
```

检查输出：
```bash
ls -lh merged.jsonl
# 应该能看到合并后的数据文件
```

#### 2️⃣ 启动 MCP 服务

```bash
cd agent_tools
python3 start_mcp_services.py
```

保持该终端运行，或使用 `nohup` 后台运行。

#### 3️⃣ 运行回测

```bash
cd ..  # 回到项目根目录
python3 main.py configs/backtest_tech100_config.json
```

## ⚙️ 配置说明

### 编辑配置文件

`configs/backtest_tech100_config.json`：

```json
{
  "date_range": {
    "init_date": "2025-01-01",  // 回测开始日期
    "end_date": "2025-06-30"     // 回测结束日期
  },
  "models": [
    {
      "name": "gpt-4o",
      "enabled": true  // 设为 true 启用该模型
    },
    {
      "name": "claude-3.7-sonnet",
      "enabled": false  // 设为 false 禁用
    }
  ],
  "agent_config": {
    "initial_cash": 10000.0  // 初始资金
  }
}
```

### 修改回测时间段

如只想测试某个月份：

```json
{
  "date_range": {
    "init_date": "2025-03-01",
    "end_date": "2025-03-31"
  }
}
```

### 同时运行多个模型

将多个模型的 `enabled` 设为 `true`，系统会依次运行：

```json
{
  "models": [
    {"name": "gpt-4o", "enabled": true},
    {"name": "claude-3.7-sonnet", "enabled": true},
    {"name": "deepseek-chat", "enabled": true}
  ]
}
```

## 📊 查看回测结果

### 持仓记录

```bash
# 查看某个模型的持仓历史
cat data/agent_data/gpt-4o-tech100-backtest/position/position.jsonl
```

示例输出：
```json
{
  "date": "2025-06-30",
  "id": 120,
  "this_action": {
    "action": "buy",
    "symbol": "AAPL",
    "amount": 10
  },
  "positions": {
    "AAPL": 20,
    "MSFT": 15,
    "CASH": 5234.56
  }
}
```

### 交易日志

```bash
# 查看某一天的完整决策过程
cat data/agent_data/gpt-4o-tech100-backtest/log/2025-06-30/log.jsonl
```

### 计算性能指标

```bash
# 运行性能分析脚本
python calculate_performance.py
```

## 🎨 可视化

启动 Web 界面查看图表：

```bash
bash scripts/start_ui.sh
# 访问 http://localhost:8888
```

## 🔧 常见问题

### Q1: 数据格式错误

**问题**：运行报错 "Data file not found"

**解决**：
```bash
# 检查 merged.jsonl 是否存在
ls -lh data/merged.jsonl

# 如不存在，重新合并
cd data
python3 merge_tech100_data.py
```

### Q2: MCP 服务未启动

**问题**：运行报错连接工具失败

**解决**：
```bash
# 检查 MCP 服务是否运行
ps aux | grep start_mcp_services

# 如未运行，启动它
cd agent_tools
python3 start_mcp_services.py
```

### Q3: API 限流

**问题**：频繁请求导致 API 限流

**解决**：
- 调整配置中的 `base_delay`（增加延迟）
- 使用更小的时间段分批回测

### Q4: 想测试自己的股票池

**问题**：不想测试这 100 支，想测试自己选择的股票

**解决**：
1. 修改 `prompts/agent_prompt.py` 中的 `all_nasdaq_100_symbols`
2. 确保你的数据文件包含这些股票

## 📈 性能评估指标

系统会计算以下指标：

- 📊 **总收益率**：(最终资产 - 初始资金) / 初始资金
- 📉 **最大回撤**：期间最大的资产下降幅度
- 📈 **夏普比率**：收益与风险的比值
- 💰 **年化收益**：标准化的年度收益率
- 🎯 **胜率**：盈利交易的比例

## 💡 优化建议

1. **多模型对比**
   - 同时启用多个 AI 模型，对比表现
   - 分析不同模型的交易风格差异

2. **时间段测试**
   - 测试不同市场环境（牛市/熊市/震荡）
   - 验证策略的稳定性

3. **参数调优**
   - 调整 `max_steps`、`initial_cash` 等参数
   - 观察对结果的影响

4. **自定义策略**
   - 修改 `prompts/agent_prompt.py` 中的系统提示词
   - 实现自己的交易策略

## 📚 相关文档

- [主要文档](../README_CN.md)
- [配置说明](../configs/README_zh.md)
- [项目架构](../README_CN.md#-项目架构)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**免责声明**：本系统仅供研究使用，不构成任何投资建议。
