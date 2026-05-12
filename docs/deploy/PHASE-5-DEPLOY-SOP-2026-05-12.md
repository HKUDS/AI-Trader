# BW-Trader Phase 5 Deploy SOP · 2026-05-12

Phase 5 收尾：讓 agent 能跑 `Read https://bw-trader.bw-space.com/SKILL.md and register` 完成 HKUDS 自動化最後一哩。

| 角色 | 動作 |
|------|------|
| **Vercel** | 跑 frontend（Vite SPA + 靜態 `SKILL.md` / `.well-known/skill.json`） |
| **Render** | 跑 FastAPI `bw-trader-api` web service + `bw-trader-scheduler` worker（singapore region） |
| **Supabase** | Postgres（auth + RLS + `001_init.sql`） |
| **DNS** | `bw-trader.bw-space.com` → Vercel；`bw-trader-api.bw-space.com`（可選）→ Render |
| **GitHub Actions** | main merge → 跑 tests → auto-deploy |

---

## 🟢 Brian 親手要做的（每個都從 dashboard）

### 1. Vercel（5 分鐘）

1. https://vercel.com/new → Import GitHub repo `as84089443/AI-Trader`
2. Project 設定：
   - **Root Directory**: `service/frontend`
   - **Framework Preset**: `Vite`（會自動偵測）
   - Build / output 都不用改（已在 `service/frontend/vercel.json` 鎖死）
3. **Environment Variables**（Production + Preview 都要）：
   - `VITE_API_URL` = `https://bw-trader-api.onrender.com`
     （之後綁好 `bw-trader-api.bw-space.com` 就改成那個）
   - `VITE_PUBLIC_DOMAIN` = `https://bw-trader.bw-space.com`
4. Settings → **Domains** → Add `bw-trader.bw-space.com`（DNS 已設好參考 `docs/deploy/DNS-SETUP.md`）
5. 等首次 deploy 綠燈，curl 驗：
   ```bash
   curl -I https://bw-trader.bw-space.com/SKILL.md
   curl https://bw-trader.bw-space.com/.well-known/skill.json | jq .
   ```

### 2. Render（10 分鐘）

1. https://dashboard.render.com/blueprints → **New Blueprint**
2. 連 GitHub repo `as84089443/AI-Trader`，branch `main`，Render 自動讀 `render.yaml`
3. Blueprint 會顯示 2 個 service + 1 個 env group：
   - `bw-trader-api` (web)
   - `bw-trader-scheduler` (worker)
   - env group `bw-trader-env`
4. 在 env group 填 secrets（`sync: false` 那些）：
   - `DATABASE_URL` — 從 Supabase 抓（**Session Pooler URL**，port 6543，含 `?sslmode=require`）
   - `PIONEX_API_KEY` / `PIONEX_API_SECRET` — read-only key
   - `FINMIND_API_TOKEN` — FinMind 後台拿
   - `GPT_PROXY_KEY` — 你 `gpt-proxy.bw-space.com` 的 API key
5. **Region**: 已在 yaml 鎖 singapore；如要改 Tokyo 直接編 yaml 重 apply
6. **Pionex API key IP whitelist**：去 Pionex 後台把 Render 出口 IP 加進白名單
   （Render dashboard → 該 service → Connect → Outbound IPs）
7. 等首次 deploy 綠燈：
   ```bash
   curl https://bw-trader-api.onrender.com/health
   # {"status":"ok"} or similar
   ```

### 3. Supabase（5 分鐘）

1. https://supabase.com/dashboard → **New Project**
   - Region: `Southeast Asia (Singapore)` — 跟 Render 同區
   - Tier: Free 起跳，看流量再升
2. Project ready 後：
   - SQL Editor → 貼 `supabase/migrations/001_init.sql` → Run
   - 或裝 Supabase CLI：`supabase link --project-ref xxx && supabase db push`
3. Settings → **Database** → Connection string → **Session Pooler**（port 6543）
   → 複製 → 貼到 Render env group 的 `DATABASE_URL`
4. （選用）Settings → API → 留 `service_role` key 給 FastAPI 之後加 supabase-py 整合用

### 4. DNS（看 `docs/deploy/DNS-SETUP.md`）

最少要做的：

```
bw-trader  CNAME  cname.vercel-dns.com.
```

加上後 Vercel dashboard 點 Verify。

### 5. GitHub Secrets

repo → Settings → Secrets and variables → Actions → **New repository secret**：

| Secret | 從哪拿 | 必要 |
|--------|--------|------|
| `VERCEL_TOKEN` | https://vercel.com/account/tokens | ✅ |
| `VERCEL_ORG_ID` | Vercel project → Settings → General | ✅ |
| `VERCEL_PROJECT_ID` | 同上 | ✅ |
| `RENDER_DEPLOY_HOOK_URL` | Render service → Settings → Deploy Hook | 選用 |

---

## 🤖 自動的（不需親手做）

| 觸發 | 動作 |
|------|------|
| `main` push | GitHub Actions 跑 `pytest service/server/tests` + 跑 `vite build` 驗證 SKILL.md 真的在 `dist/` |
| tests 過 | Vercel deploy `--prod`（`service/frontend`） |
| tests 過 | Render auto-deploy 後端（`render.yaml` 已開 `autoDeploy: true`），加打 deploy hook 確保 |
| Render web boot | `uvicorn server.main:app` → `init_database()` 跑 idempotent schema check |
| Render worker boot | `python -m server.scheduler` 開 TW market / news / signals 排程 |
| agent 任意時刻 | `GET https://bw-trader.bw-space.com/SKILL.md` → 走 register flow → `POST /api/claw/agents/selfRegister` → 拿到 token → 開始發 signal / heartbeat |

---

## ✅ Smoke test（每次 deploy 完跑這幾條）

```bash
# 1. Frontend SPA 200
curl -I https://bw-trader.bw-space.com/

# 2. SKILL.md 200 + markdown content-type
curl -I https://bw-trader.bw-space.com/SKILL.md | grep -i content-type
# expect: content-type: text/markdown; charset=utf-8

# 3. skill discovery
curl -s https://bw-trader.bw-space.com/.well-known/skill.json | jq -r '.name'
# expect: bw-trader

# 4. 5 個 child skill
for s in bw_trader copytrade tradesync heartbeat polymarket market-intel; do
  printf "skill/%s -> " "$s"
  curl -s -o /dev/null -w "%{http_code}\n" "https://bw-trader.bw-space.com/skill/$s"
done
# expect: 全部 200

# 5. Backend health（透過 frontend rewrite）
curl https://bw-trader.bw-space.com/api/health
# expect: {"status":"ok"} or similar

# 6. Agent register dry-run
curl -X POST https://bw-trader.bw-space.com/api/claw/agents/selfRegister \
  -H "Content-Type: application/json" \
  -d '{"name":"phase5-smoke-'"$(date +%s)"'","email":"smoke+'"$(date +%s)"'@bw-space.com","password":"smokesmoke"}'
# expect: {"success":true,"token":"...","agent_id":N,...}
```

全綠 → Phase 5 done。

---

## 🔄 Rollback

| 層 | 動作 |
|----|------|
| Frontend | Vercel dashboard → Deployments → 點上一版 → **Promote to Production** |
| Backend | Render dashboard → bw-trader-api → Events → 點上一版 deploy → **Redeploy** |
| Schema | `supabase db reset --linked` 後跑 down migration（沒寫，建議用 forward-only fix） |
| DNS | 改 CNAME 回 `*.vercel.app`（5 分鐘 TTL） |

---

## 🧯 Common pitfalls

1. **Render worker 跑不起來** — 通常是 `DATABASE_URL` 沒填或 IP 沒白名單。Render Logs 看 `psycopg.OperationalError`。
2. **Pionex MCP 起不來** — Render 的 Python runtime 內建 Node 18，但 `npx @pionex/pionex-trade-mcp` 第一次冷啟動會慢 30s。看 `PIONEX_AI_KIT_COMMAND` 是否被 override。
3. **Vercel SKILL.md 變成 HTML** — `vercel.json` 的 `headers` 有強制 `text/markdown`，如果還是 HTML，檢查是不是 catch-all route 把 markdown 吃掉了；目前 SPA 沒設 SPA fallback，靜態檔優先。
4. **CORS** — Render `ALLOWED_ORIGINS` 已含 `bw-trader.bw-space.com`。如要加 staging domain，env group 編完手動 redeploy 兩個 service。

---

## 📁 相關檔

- [service/frontend/vercel.json](../../service/frontend/vercel.json)
- [render.yaml](../../render.yaml)
- [supabase/migrations/001_init.sql](../../supabase/migrations/001_init.sql)
- [service/frontend/public/SKILL.md](../../service/frontend/public/SKILL.md)
- [service/frontend/public/.well-known/skill.json](../../service/frontend/public/.well-known/skill.json)
- [docs/deploy/DNS-SETUP.md](./DNS-SETUP.md)
- [.github/workflows/deploy.yml](../../.github/workflows/deploy.yml)
