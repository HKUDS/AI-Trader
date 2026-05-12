# BW-Trader · M1 Self-Host SOP · 2026-05-12

Phase 5 改版：Render 廢，backend 改在 **M1 Mac mini** 自架（launchd + Cloudflare Tunnel）。
Vercel 還是 frontend only，Supabase 還是 DB。目標仍然是：agent 跑
`Read https://bw-trader.bw-space.com/SKILL.md and register` 走完 HKUDS 最後一哩，但不依賴付費 cloud。

> 本文是 **M4 → M1 一次交接**完整 checklist。所有命令都標清楚要在哪台跑（`# M4` / `# M1`）。

---

## A. 系統架構

```mermaid
flowchart LR
    subgraph M4["M4 Pro Max · dev host"]
        DEV[/"`~/dev/AI-Trader`<br/>fork: as84089443/AI-Trader"/]
        CC[Claude Code / Codex]
        CC --> DEV
        DEV -->|"git push"| GH
    end

    subgraph GH["GitHub"]
        FORK[as84089443/AI-Trader]
        UP[HKUDS/AI-Trader<br/>upstream]
        UP -.sync.-> FORK
    end

    subgraph M1["M1 Mac mini · prod host (LAN)"]
        REPO[/"`~/dev/AI-Trader`"/]
        API["FastAPI<br/>127.0.0.1:8788"]
        SCHED["scheduler worker<br/>(launchd KeepAlive)"]
        CFD["cloudflared tunnel<br/>(既有 tunnel, 加 ingress)"]
        API --> CFD
        SCHED -.writes.-> SB
    end

    FORK -->|"git pull on M1"| REPO
    REPO --> API
    REPO --> SCHED

    subgraph CF["Cloudflare"]
        DNS["DNS<br/>bw-trader.bw-space.com → Vercel<br/>bw-trader-api.bw-space.com → Tunnel"]
        TUN["cfargotunnel.com edge"]
    end

    CFD <--> TUN
    DNS --> TUN

    subgraph VC["Vercel (frontend only)"]
        FE["Vite SPA<br/>SKILL.md / .well-known/skill.json"]
    end

    AGENT["Claude / GPT agent"] -->|"GET /SKILL.md"| DNS
    DNS --> FE
    FE -->|"/api/* rewrite"| TUN
    TUN --> API

    subgraph SB["Supabase ap-southeast-2"]
        PG[(Postgres + RLS)]
    end
    API --> SB
```

要點：
- M4 永遠不跑 prod service，只 dev + push。
- M1 是唯一 prod runtime（FastAPI + scheduler）。
- `bw-trader.bw-space.com` 仍是 Vercel（frontend domain），**不**走 Tunnel —— 避免「frontend rewrite 指回自己」死循環。
- 新加 `bw-trader-api.bw-space.com` 走 Cloudflare Tunnel → M1 `127.0.0.1:8788`。
- Vercel `vercel.json` 的 `/api/*` rewrite 指向 **API subdomain**，不是 root。

---

## B. M1 前置（一次性，一個 work day 內）

確認 M1 已有的（推測既有，不重裝）：
- macOS（Sonoma+）
- Homebrew
- Tailscale（hostname 推測 `bwstudio-mini`，未確認的話 `tailscale status` 看一眼）
- cloudflared（已跑 NAS + Sparrow tunnel — 直接共用 tunnel）
- 1Password CLI（可選，secrets 傳輸用）

需要新裝的：

```bash
# M1
# --- Python 3.12（pyenv 路線；Homebrew 路線也可，但 launchd 路徑會比較硬）---
brew install pyenv
pyenv install 3.12.7
pyenv global 3.12.7
python3 --version   # → Python 3.12.7

# --- Node 18+（Pionex AI Kit MCP 用 npx）---
brew install node@20   # 20 LTS；18 也行，新一點省事
node --version

# --- uv（fast pip）---
curl -LsSf https://astral.sh/uv/install.sh | sh
# 安裝到 ~/.local/bin/uv，確認 PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
uv --version

# --- gh CLI ---
brew install gh
gh auth login    # 選 GitHub.com / HTTPS / paste token

# --- 確認 cloudflared 已有 ---
cloudflared --version
ls ~/.cloudflared/   # 應該已經有 cert.pem + <tunnel-id>.json + config.yml
```

如果 cloudflared 沒裝：

```bash
# M1
brew install cloudflared
cloudflared tunnel login     # 開 browser 授權
# 這一步如果你 NAS / Sparrow 已經跑很久了，跳過 —— 你已經 logged in
```

---

## C. M1 第一次 clone + setup

```bash
# M1
mkdir -p ~/dev && cd ~/dev
gh repo clone as84089443/AI-Trader
cd AI-Trader
git remote add upstream https://github.com/HKUDS/AI-Trader
git remote -v
# origin    git@github.com:as84089443/AI-Trader.git
# upstream  https://github.com/HKUDS/AI-Trader

# Python deps（只裝 backend，不裝 frontend —— Vercel 跑那邊）
cd service
uv pip install --system -r requirements.txt
cd ..
```

> **不要** 在 M1 上 `cd service/frontend && npm install`。前端 Vercel 全包了。

---

## D. Secrets 安全 transfer（不過 chat、不過 git）

`.env` 不能 commit、不能貼到 Slack / chat 工具。從 M4 傳到 M1 選一個方法（按推薦順序）：

### D-1. Tailscale scp（最推薦）

兩台都在 Tailnet，流量 wireguard 加密，不出 Tailnet：

```bash
# M4
# 先確認 M1 的 Tailscale hostname
tailscale status | grep mini
# 假設叫 bwstudio-mini

# 確認 .env 沒 commit
cd /Users/brian/dev/AI-Trader
git check-ignore -v .env   # 應該回 .gitignore:某行:.env

# scp 過去（用 Tailscale IP 也可，hostname 比較好記）
scp .env brian@bwstudio-mini:~/dev/AI-Trader/.env

# 對方權限收緊 + verify
ssh brian@bwstudio-mini '
  cd ~/dev/AI-Trader
  chmod 600 .env
  ls -l .env       # 應該 -rw------- brian staff
  git check-ignore -v .env   # 確認 .gitignore 有 cover
  wc -l .env       # 行數比對 M4 那邊
'
```

### D-2. AirDrop

兩台 Apple ID 一樣 / 已配對 → Finder 拖 `.env` 過去 → 同上 `chmod 600` + `git check-ignore` 驗。

### D-3. 1Password Document

如果你有 1Password：
1. M4 上新增 Document `.env` → upload 檔案
2. M1 上 `op document get "bw-trader .env" --out-file ~/dev/AI-Trader/.env`
3. `chmod 600 .env`

### D-4. USB（最 paranoid）

實體拷貝 → AES 加密 sparse bundle 也行。

### D-5. Smoke test（無論用哪個方法）

```bash
# M1
cd ~/dev/AI-Trader
# 確認檔案不會被 git tracked
git status --ignored | grep -F '.env' || echo "WARN: .env not visible in status, double-check .gitignore"
git check-ignore -v .env

# 確認 Python 讀得到（不印 value，只印 key 數量）
python3 -c "
from dotenv import dotenv_values
d = dotenv_values('.env')
print(f'loaded {len(d)} keys')
for k in sorted(d):
    print(f'  - {k} = {\"***\" if d[k] else \"\"}')
"

# 確認 server import OK（不會真正啟動）
cd service
uv run python -c "from server.main import app; print('app loaded:', app.title if hasattr(app, \"title\") else app)"
cd ..
```

不通的話，**先**修 .env / requirements，不要往下做 launchd。

---

## E. launchd plist templates

兩個 service：

| Label | 用途 | Port |
|-------|------|------|
| `ai.bwstudio.bw-trader-api` | FastAPI uvicorn web | `127.0.0.1:8788` |
| `ai.bwstudio.bw-trader-scheduler` | Background scheduler worker | — |

### E-1. Port 衝突先檢

```bash
# M1
lsof -nP -iTCP:8788 -sTCP:LISTEN
# 應該無輸出。若被佔（例如 reef-lounge 也用 8788）→ 改 8789、8889、9788 ⋯ 任挑一個
# 改了之後：
#   1. plist ProgramArguments 裡的 --port 改
#   2. ~/.cloudflared/config.yml 的 service URL 改
#   3. 本 SOP 內所有 8788 一起改
```

### E-2. Plist 檔案

templates 在 repo `deploy/launchd/`：
- `deploy/launchd/ai.bwstudio.bw-trader-api.plist`
- `deploy/launchd/ai.bwstudio.bw-trader-scheduler.plist`
- `deploy/launchd/README.md`

### E-3. 安裝到 LaunchAgents

```bash
# M1
cd ~/dev/AI-Trader

# 複製到 LaunchAgents（不要直接 symlink — launchd 不愛 symlink 跨 volume）
cp deploy/launchd/ai.bwstudio.bw-trader-api.plist        ~/Library/LaunchAgents/
cp deploy/launchd/ai.bwstudio.bw-trader-scheduler.plist  ~/Library/LaunchAgents/

# 確認權限
chmod 644 ~/Library/LaunchAgents/ai.bwstudio.bw-trader-*.plist

# bootstrap（首次載入）
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.bwstudio.bw-trader-api.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.bwstudio.bw-trader-scheduler.plist

# 確認狀態
launchctl print gui/$(id -u)/ai.bwstudio.bw-trader-api | head -30
launchctl print gui/$(id -u)/ai.bwstudio.bw-trader-scheduler | head -30
```

### E-4. 日常控制

```bash
# Restart
launchctl kickstart -k gui/$(id -u)/ai.bwstudio.bw-trader-api
launchctl kickstart -k gui/$(id -u)/ai.bwstudio.bw-trader-scheduler

# Stop（不卸載）
launchctl kill SIGTERM gui/$(id -u)/ai.bwstudio.bw-trader-api

# 完全 unload（要重新編 plist 後 reload 才這樣）
launchctl bootout gui/$(id -u)/ai.bwstudio.bw-trader-api

# 看 log
tail -f ~/Library/Logs/bw-trader-api.out.log ~/Library/Logs/bw-trader-api.err.log
tail -f ~/Library/Logs/bw-trader-scheduler.out.log ~/Library/Logs/bw-trader-scheduler.err.log
```

> Plist 內 `KeepAlive.SuccessfulExit = false` 表示「正常退出不要重啟，異常退出才重啟」。debug 期間想立刻看 stack trace，可暫時改 `KeepAlive = false`。

---

## F. Cloudflare Tunnel 設定

策略：**共用 既有 tunnel**（NAS / Sparrow 那條），加一條 ingress rule 給 `bw-trader-api.bw-space.com`。
不另開 tunnel 是為了少維護一份 credentials。

### F-1. 找既有 tunnel

```bash
# M1
cloudflared tunnel list
# 應該看到 NAME / ID / CREATED / CONNECTIONS
# 找 sparrow / NAS 那條的 ID → 記下來，下面叫 <TUNNEL_ID>

cat ~/.cloudflared/config.yml
# 應該已經有 tunnel: + credentials-file: + ingress:
```

### F-2. 加 ingress rule

編 `~/.cloudflared/config.yml`，在 `ingress:` 最尾的 `- service: http_status:404` **之前**插入：

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /Users/brian/.cloudflared/<TUNNEL_ID>.json

ingress:
  # 既有的別動 —— 例：
  - hostname: sparrow.bw-space.com
    service: http://127.0.0.1:<sparrow-port>
  - hostname: nas.bw-space.com
    service: http://<nas-lan-ip>:<nas-port>

  # ↓↓↓ 新加 ↓↓↓
  - hostname: bw-trader-api.bw-space.com
    service: http://127.0.0.1:8788
    originRequest:
      connectTimeout: 10s
      noTLSVerify: true   # 本機 http，沒 TLS

  # 一定要保留在最尾
  - service: http_status:404
```

### F-3. validate + restart

```bash
# M1
cloudflared tunnel ingress validate
# OK: validation succeeded

# Reload tunnel — 看你怎麼跑：
# 如果是 launchctl 起的（macOS service install 後常見）：
launchctl kickstart -k gui/$(id -u)/com.cloudflare.cloudflared
# 或 system service：
sudo launchctl kickstart -k system/com.cloudflare.cloudflared

# 確認 tunnel 起來
cloudflared tunnel info <TUNNEL_ID>
```

---

## G. DNS 更新（Cloudflare dashboard）

> Brian 親手 dashboard 做，**不要**讓 agent 改 DNS。

兩筆 record 共存：

| Host | Type | Target | Proxy |
|------|------|--------|-------|
| `bw-trader` | CNAME | `cname.vercel-dns.com.` | **灰雲（DNS only）** — Vercel 要直連發 cert |
| `bw-trader-api` | CNAME | `<TUNNEL_ID>.cfargotunnel.com` | **橘雲（Proxied）** — CF Tunnel 必須走 proxy |

Tunnel ID 從 `cloudflared tunnel list` 拿。或 dashboard：
**Zero Trust** → **Networks** → **Tunnels** → 點 tunnel → top-right 顯示 UUID。

驗證：

```bash
# M4 / 任何電腦
dig bw-trader.bw-space.com +short
# → cname.vercel-dns.com. + 76.76.21.x

dig bw-trader-api.bw-space.com +short
# → 100.x.x.x（Cloudflare anycast 範圍，proxied 才會這樣）

curl -fsS https://bw-trader-api.bw-space.com/health
# → {"status":"ok","timestamp":"2026-05-12T..."}
```

---

## H. Vercel frontend API rewrite 更新

`service/frontend/vercel.json` 的 rewrite target 改：

```diff
- { "source": "/api/(.*)", "destination": "https://bw-trader-api.onrender.com/api/$1" },
- { "source": "/ws/(.*)",  "destination": "https://bw-trader-api.onrender.com/ws/$1" }
+ { "source": "/api/(.*)", "destination": "https://bw-trader-api.bw-space.com/api/$1" },
+ { "source": "/ws/(.*)",  "destination": "https://bw-trader-api.bw-space.com/ws/$1" }
```

> ⚠️ **不要**改成 `https://bw-trader.bw-space.com/api/$1` —— 因為 `bw-trader.bw-space.com` 就是 Vercel
> 自己的 domain，rewrite 指回自己會無限 loop / 503。所以一定要 **獨立 API subdomain**。

merge 進 main → Vercel auto-deploy → `bw-trader.bw-space.com/api/health` 透 rewrite 打到 M1。

---

## I. 第一次 deploy 跑起來（M1 端）

```bash
# M1
cd ~/dev/AI-Trader
git pull origin main

cd service
uv pip install --system -r requirements.txt
cd ..

# Verify .env loaded
python3 -c "from dotenv import dotenv_values; d=dotenv_values('.env'); print('keys:', len(d))"

# Bootstrap launchd（如果還沒）
cp deploy/launchd/ai.bwstudio.bw-trader-*.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.bwstudio.bw-trader-api.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.bwstudio.bw-trader-scheduler.plist

# Smoke test（依序）
sleep 5

# 1. local
curl -fsS http://127.0.0.1:8788/health
# → {"status":"ok",...}

# 2. via Cloudflare Tunnel
curl -fsS https://bw-trader-api.bw-space.com/health
# → 同上

# 3. via Vercel rewrite（merge & deploy 後）
curl -fsS https://bw-trader.bw-space.com/api/health   # 注意：rewrite 是 /api/* → backend /api/*，所以 backend 那邊 /health 走 /api/health？看 routes 定義
# 若 backend /health 不在 /api 下，frontend 改打 https://bw-trader-api.bw-space.com/health 即可

# 4. SKILL.md（agent 入口）
curl -fsS -I https://bw-trader.bw-space.com/SKILL.md | head -5
# HTTP/2 200, content-type: text/markdown
```

> **注意**：目前 backend health route 在 `/health`（不是 `/api/health`，見 `service/server/routes_market.py:88`）。
> 如果你想讓 frontend rewrite 也能 cover health，要嘛在 backend 加 `/api/health` alias，要嘛 agent 直接打 API subdomain。

---

## J. 日常更新流程（M4 dev → M1 prod）

### 標準路徑（PR-based）

```bash
# === M4 ===
cd /Users/brian/dev/AI-Trader
git checkout main && git pull
git checkout -b feat/xxx
# ... 改 code、commit ...
git push -u origin feat/xxx
gh pr create --fill
# CI 過 + review OK 後
gh pr merge --squash --delete-branch

# === M1（手動或 cron）===
ssh brian@bwstudio-mini   # 或直接 console
~/dev/AI-Trader/deploy/m1-redeploy.sh
```

### Hotfix 路徑（直推 main，僅緊急）

```bash
# M4
git checkout main
# ...
git push
# M1
~/dev/AI-Trader/deploy/m1-redeploy.sh
```

### m1-redeploy.sh

repo 內 `deploy/m1-redeploy.sh`，wrap 成一行：pull → install → restart → health check。
script 失敗會 `set -e` 中止，不會把壞版本留在 prod。

---

## K. 故障排除

### K-1. launchd service 不起

```bash
launchctl print gui/$(id -u)/ai.bwstudio.bw-trader-api
# 看 state / last exit status / last exit reason
# state = running    → 跑著
# state = waiting    → 等 KeepAlive 重試
# last exit code ≠ 0 → 看 err.log

tail -n 200 ~/Library/Logs/bw-trader-api.err.log
```

常見：
- `command not found: uv` → plist `ProgramArguments[0]` 路徑要絕對 `/Users/brian/.local/bin/uv`
- `ModuleNotFoundError: server` → `WorkingDirectory` 要設 `service/`，不是 repo root
- `address already in use` → port 撞，回 §E-1

### K-2. Cloudflare Tunnel 不通

```bash
# Tunnel 還活著？
cloudflared tunnel info <TUNNEL_ID>
# CONNECTIONS 至少 1 個 active

# Ingress 對嗎？
cloudflared tunnel ingress validate
cloudflared tunnel ingress url https://bw-trader-api.bw-space.com
# → http://127.0.0.1:8788

# 直接打本機通嗎？
curl -fsS http://127.0.0.1:8788/health
```

### K-3. DNS 沒生效

```bash
dig bw-trader-api.bw-space.com +short
# 等 5 min TTL，或 dashboard 把 TTL 設 60
# 還不通 → flush cache：sudo dscacheutil -flushcache
```

### K-4. Supabase 連不到

```bash
# M1
psql "$DATABASE_URL" -c 'SELECT now();'
# 通 → DB OK
# 不通 → 檢查 Supabase Pooler URL 是否 IP allowlist（Brian 走 Session Pooler 應該不需要）
# 或 .env 裡 DATABASE_URL 是否還是 Render 那條（已舊）
```

### K-5. 整體健診一鍵跑

```bash
# M1
bash ~/dev/AI-Trader/deploy/m1-redeploy.sh --health-only
# （見 script，--health-only 只跑驗證不重啟）
```

---

## 附錄 · 廢棄但保留

- `render.yaml`：暫不刪，當未來 cloud fallback 留著。標 `# DEPRECATED 2026-05-12 — backend moved to M1 self-host. Kept as cold-standby blueprint.`
- `docs/deploy/PHASE-5-DEPLOY-SOP-2026-05-12.md`：保留歷史，文首加 note 指向本 SOP。
- `docs/deploy/DNS-SETUP.md`：保留 Vercel CNAME 那段，「API subdomain」段過時，改看本 SOP §G。

---

## 附錄 · 回滾到 Render（萬一）

1. M1 兩個 launchd `launchctl bootout`。
2. Render dashboard → Blueprint deploy `render.yaml` → 補回 secrets。
3. Cloudflare DNS：`bw-trader-api` CNAME 改回 `bw-trader-api.onrender.com.`（灰雲）。
4. `vercel.json` rewrite target 改回 `bw-trader-api.onrender.com`，merge。
5. M1 上的 `.env` 留著沒事。
