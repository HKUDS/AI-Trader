# DNS 設定 · `bw-trader.bw-space.com`

把 `bw-trader.bw-space.com` 指到 Vercel，把 `bw-trader-api.bw-space.com`（選用）指到 Render。

## 1. Frontend · Vercel

在你的 DNS provider（Cloudflare / Route53 / Google Domains 等）：

```
Record type:  CNAME
Host:         bw-trader
Target:       cname.vercel-dns.com.
TTL:          300 (5 min) 起跳，穩定後可拉長
Proxied (CF): 關閉（Vercel 需直連發 cert）
```

Vercel dashboard：

1. BW-Trader project → Settings → Domains → **Add `bw-trader.bw-space.com`**
2. Vercel 會自動偵測到 CNAME，等 cert 自動發放（< 1 min）
3. Verify 之後設成 Primary domain，舊的 `*.vercel.app` 自動 301 redirect

驗證：

```bash
dig bw-trader.bw-space.com +short
# 應該回 cname.vercel-dns.com. 然後一串 76.76.21.x

curl -I https://bw-trader.bw-space.com/SKILL.md
# HTTP/2 200, content-type: text/markdown
```

## 2. Backend API · Render（可選 subdomain）

預設用 `bw-trader-api.onrender.com` 就能跑，但建議綁自己的 subdomain 讓 agent 看到的 URL 一致。

```
Record type:  CNAME
Host:         bw-trader-api
Target:       bw-trader-api.onrender.com.
TTL:          300
Proxied (CF): 關閉
```

Render dashboard：

1. `bw-trader-api` service → Settings → Custom Domains → **Add `bw-trader-api.bw-space.com`**
2. Render 自動發 cert（Let's Encrypt）
3. 等 status 變 `Verified`（通常 1-3 min）

API 綁 subdomain 後，要記得回 frontend `vercel.json` 把 rewrite target 改成新網址，或設環境變數 `VITE_API_URL=https://bw-trader-api.bw-space.com`。

驗證：

```bash
curl -I https://bw-trader-api.bw-space.com/health
# HTTP/2 200
```

## 3. CNAME flattening / Cloudflare 注意事項

- 主 domain `bw-space.com` 若用 Cloudflare，記得 `bw-trader` 那一筆**關掉 proxy**（灰雲），否則 Vercel cert 拿不到。
- 拿到 cert 之後**可以**再打開 proxy，但要記得設 SSL mode 為 `Full (strict)`。

## 4. 同場加映 · `*.bw-space.com` wildcard

如果 `bw-space.com` 已經有 wildcard CNAME（`*  CNAME  cname.vercel-dns.com.`），那 `bw-trader.bw-space.com` 直接生效，不用另開一筆。確認方式：

```bash
dig '*.bw-space.com' CNAME +short
```

## 5. 回滾

- 改 CNAME 回原本的（或直接刪除這筆 record）
- Vercel domain 從 dashboard remove
- TTL 300 的話 5 分鐘內全球回滾完畢
