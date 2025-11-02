# 快速部署指南

本指南帮助你快速在 EC2 服务器上部署 AI-Trader 定时调度器。

## 前提条件

- EC2 实例已运行
- 已安装 Miniconda 或 Conda
- Python 环境路径：`/home/ec2-user/py310/bin/python`

## 快速开始（3 步）

### 1. 安装依赖

```bash
cd /home/ec2-user/AI-Trader
/home/ec2-user/py310/bin/pip install -r requirements.txt
```

### 2. 配置 systemd 服务

```bash
# 复制服务文件模板
sudo cp /home/ec2-user/AI-Trader/script/ai-trader-scheduler.service.example /etc/systemd/system/ai-trader-scheduler.service

# 编辑服务文件（如果需要修改路径）
sudo nano /etc/systemd/system/ai-trader-scheduler.service

# 设置脚本执行权限
chmod +x /home/ec2-user/AI-Trader/script/start_scheduler.sh
chmod +x /home/ec2-user/AI-Trader/script/trading_scheduler.py
chmod +x /home/ec2-user/AI-Trader/script/run_main_script_for_date.py
```

### 3. 启动服务

```bash
# 重载 systemd 配置
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start ai-trader-scheduler

# 设置开机自启
sudo systemctl enable ai-trader-scheduler

# 查看状态
sudo systemctl status ai-trader-scheduler

# 查看日志
sudo journalctl -u ai-trader-scheduler -f
```

## 验证

服务启动后，你应该看到类似以下的日志：

```
🚀 启动美股交易定时调度器...
📅 将在每个交易日的 9:30-15:30 的每小时:30 执行任务
⏰ 使用美东时间 (US/Eastern)
```

## 常用命令

```bash
# 查看服务状态
sudo systemctl status ai-trader-scheduler

# 查看实时日志
sudo journalctl -u ai-trader-scheduler -f

# 查看最新 100 行日志
sudo journalctl -u ai-trader-scheduler -n 100

# 停止服务
sudo systemctl stop ai-trader-scheduler

# 重启服务
sudo systemctl restart ai-trader-scheduler

# 禁用开机自启
sudo systemctl disable ai-trader-scheduler
```

## 故障排查

### 服务无法启动

1. **检查 Python 路径是否正确**
   ```bash
   ls -la /home/ec2-user/py310/bin/python
   ```

2. **检查项目路径是否正确**
   ```bash
   ls -la /home/ec2-user/AI-Trader/script/start_scheduler.sh
   ```

3. **检查服务日志**
   ```bash
   sudo journalctl -u ai-trader-scheduler -n 50
   ```

### Python 路径不同

如果你的 Python 路径不是 `/home/ec2-user/py310/bin/python`，请：

1. 编辑服务文件：
   ```bash
   sudo nano /etc/systemd/system/ai-trader-scheduler.service
   ```

2. 修改 `PYTHON_BIN` 环境变量：
   ```ini
   Environment="PYTHON_BIN=/your/actual/python/path"
   ```

3. 重载并重启服务：
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart ai-trader-scheduler
   ```

### 项目路径不同

如果项目不在 `/home/ec2-user/AI-Trader`，请：

1. 编辑服务文件：
   ```bash
   sudo nano /etc/systemd/system/ai-trader-scheduler.service
   ```

2. 修改所有路径为实际路径

3. 重载并重启服务

## 测试脚本

在正式部署前，可以先手动测试：

```bash
# 测试启动脚本
/home/ec2-user/AI-Trader/script/start_scheduler.sh

# 如果一切正常，按 Ctrl+C 停止，然后使用 systemd 服务
```

## 注意事项

1. **时区**：调度器使用美东时间，服务器可以设置为任意时区
2. **交易日**：只在交易日执行，非交易日会自动跳过
3. **交易时间**：仅在 9:30-15:30（美东时间）的每小时:30 执行
4. **API 限制**：注意 API 调用频率限制，避免超限

## 下一步

- 查看完整文档：`docs/DEPLOYMENT.md`
- 检查配置文件：`configs/production_config.json`
- 查看交易日历：`data/trading_calendar/`

