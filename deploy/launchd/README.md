# BW-Trader · launchd plists

跑在 **M1 Mac mini** 上，把 BW-Trader backend 變成 macOS user-level service。
完整 SOP 看 `docs/deploy/M1-SELF-HOST-SOP-2026-05-12.md`。本檔只是 plist 使用手冊。

## Plist 一覽

| File | Label | Process | Port |
|------|-------|---------|------|
| `ai.bwstudio.bw-trader-api.plist` | `ai.bwstudio.bw-trader-api` | FastAPI uvicorn | `127.0.0.1:8788` |
| `ai.bwstudio.bw-trader-scheduler.plist` | `ai.bwstudio.bw-trader-scheduler` | Background scheduler | — |

兩個都是 **user-level**（`gui/$(id -u)`），不需要 sudo。Mac 重啟後使用者登入即自動拉起。

## 前置假設

- Repo clone 到 `/Users/brian/dev/AI-Trader`（路徑寫死在 plist `WorkingDirectory`）
- `uv` 裝在 `/Users/brian/.local/bin/uv`（plist `ProgramArguments[0]`）
- `.env` 在 `/Users/brian/dev/AI-Trader/.env`，`chmod 600`
- Python deps 已 `uv pip install --system -r service/requirements.txt`

路徑不同？改 plist 內絕對路徑 — launchd **不**展開 `~` 或 `$HOME`。

## 安裝 / 第一次 load

```bash
# 從 repo root 跑（M1 上）
cd ~/dev/AI-Trader
cp deploy/launchd/ai.bwstudio.bw-trader-api.plist        ~/Library/LaunchAgents/
cp deploy/launchd/ai.bwstudio.bw-trader-scheduler.plist  ~/Library/LaunchAgents/
chmod 644 ~/Library/LaunchAgents/ai.bwstudio.bw-trader-*.plist

# Bootstrap（modern syntax；舊 launchctl load 已 deprecated）
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.bwstudio.bw-trader-api.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.bwstudio.bw-trader-scheduler.plist
```

## 日常控制

| 動作 | 命令 |
|------|------|
| 看狀態 | `launchctl print gui/$(id -u)/ai.bwstudio.bw-trader-api` |
| 重啟 | `launchctl kickstart -k gui/$(id -u)/ai.bwstudio.bw-trader-api` |
| 停（不卸載） | `launchctl kill SIGTERM gui/$(id -u)/ai.bwstudio.bw-trader-api` |
| 卸載 | `launchctl bootout gui/$(id -u)/ai.bwstudio.bw-trader-api` |
| 看 log | `tail -f ~/Library/Logs/bw-trader-api.{out,err}.log` |

scheduler 同理，把 label 換掉。

## 改 plist 之後

launchd 把 plist 內容 cache 在 kernel，**改檔不會自動生效**。SOP：

```bash
launchctl bootout gui/$(id -u)/ai.bwstudio.bw-trader-api
cp deploy/launchd/ai.bwstudio.bw-trader-api.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.bwstudio.bw-trader-api.plist
```

## 行為說明

- `KeepAlive.Crashed=true + SuccessfulExit=false`：crash / non-zero exit 自動重啟，正常 `exit 0` 不重啟。debug 想看 stack trace 一次性退出，臨時改 `KeepAlive=false`。
- `ThrottleInterval`：最小重啟間隔，避免崩潰循環打爆 log。API 10s、scheduler 30s。
- `ProcessType=Interactive`（API）讓 macOS App Nap 不睡它；scheduler 用 `Background` 比較省電。
- `Nice=5`（scheduler only）：scheduler 是 background batch，讓 CPU 給 API 跟其他互動 app 優先。
- `--proxy-headers --forwarded-allow-ips *`：uvicorn 信任 Cloudflare Tunnel 帶來的 `X-Forwarded-*`，
  讓 backend log 看到真實 client IP。Tunnel 是封閉鏈路所以 `*` 安全；不要在裸公網這樣設。

## 升級 Python / uv 路徑

換 pyenv 版本或裝新 uv 後，**檢查** `which uv`、`which python`。如果路徑變了：

```bash
which uv         # 例：/Users/brian/.pyenv/shims/uv  或  /Users/brian/.local/bin/uv
```

把 plist `ProgramArguments[0]` 改成輸出值，再走「改 plist 之後」流程 reload。

## 為什麼不用 brew services

`brew services` 在背後也是寫 launchd plist，但：
- 只認 `formula` 級的 service，自家 app 要 manual plist
- 改 plist 要再 `brew services restart`，不能直接 kickstart
- macOS 14+ Apple 推薦 `bootstrap/bootout`，brew 的 wrapper 比較舊

直接寫 plist 一次學會、`Sparrow` / `hermes-bridge` / 未來其他 M1 service 全部同 pattern。
