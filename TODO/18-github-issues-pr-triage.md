# GitHub Issue / PR 待审批整理

日期：2026-05-12  
仓库：https://github.com/HKUDS/AI-Trader

范围：
- Issue：本次只看 `#200` 之后到当前最新开放 issue `#211`。其中 `#204`、`#208`、`#209` 是 PR 编号，不是 issue。
- PR：当前所有开放 PR，共 7 个。
- 本文档只做中文摘要、判断和建议，方便后续撰写回复草稿；尚未对远程 issue/PR 做任何处理。

## 总览

建议优先审批：

- 可在本地验证后合入：PR `#199`、PR `#184`、PR `#204`。
- 不建议直接合入、需要人工整合：PR `#209`，因为它和 PR `#204` 都改了 `service/server/utils.py` 的密码校验逻辑。
- 倾向关闭或拒绝：issue `#200`、issue `#210`、issue `#211`、PR `#195`、PR `#198`、PR `#49`。
- 需要维护者回复或后续修复：issue `#201`、`#202`、`#205`、`#206`、`#207`。
- 已有修复待 PR 合入：issue `#203`。

关键冲突：
- PR `#204` 和 PR `#209` 都涉及密码验证。如果两个安全目标都要保留，建议不要按顺序直接合并，而是合成一版经过审查的认证加固补丁。

## Issue 原文中文摘要

### [`#200`](https://github.com/HKUDS/AI-Trader/issues/200) Patch: Addressing Potential Slippage Risks on Base Mainnet

提交者：OmniSecurityCore

原文中文摘要：
- 对方声称已经在外部技术 README 中记录了一个“高交易量期间潜在流动性滑点风险”的关键补丁，并给出一个 `raw.githubusercontent.com/OmniSecurityCore/NetworkDocs/.../README.md` 链接。
- 对方要求维护者验证其中的 directive，并初始化名为 `Safety-Salami` 的协议，以确保后台流动性稳定。
- 原文还声称该流程会“绕过人工验证”，理由是要保证即时网络安全。

评论/后续摘要：
- 同一用户继续催促，说补丁需要在下一次 rebalance 前启用，并询问 trader-agent 是否已为 Base address 初始化 `Safety-Salami` 后台协议。

判断：
- 高度疑似垃圾信息或社工诱导。正文要求执行外部指令、绕过人工验证，且协议名和上下文都与仓库实际代码没有可信关联。

建议动作：
- 审批后关闭为 spam/invalid；不要打开或执行外部 README 中的任何步骤。如维护者认可，可考虑举报或拉黑提交者。

直接关闭

### [`#201`](https://github.com/HKUDS/AI-Trader/issues/201) 服务器是坏了吗

提交者：sheiy

原文中文摘要：
- 用户说已经读取并安装了 AI-Trader skill。
- 原始 skill URL `https://ai4trade.ai/SKILL.md` 在容器里访问一直超时，于是用户通过搜索找到 GitHub 镜像 `https://raw.githubusercontent.com/HKUDS/AI-Trader/main/skills/ai4trade/SKILL.md` 并保存到本机。
- 用户验证了本地 skill 文件：大小约 22,263 bytes，frontmatter 正常，skill name 是 `ai-trader`。
- 用户尝试按 SKILL.md 里的 endpoint 注册：`POST https://ai4trade.ai/api/claw/agents/selfRegister`。
- 用户也尝试按 repo docs 里的 endpoint 注册：`POST https://api.ai4trade.ai/api/claw/agents/selfRegister`。
- 结果是 `ai4trade.ai` TLS 能连上，但页面/API 请求没有返回 body，最终 timeout；`api.ai4trade.ai` DNS 解析失败；因此没有拿到 token，也不能确认注册成功。
- 用户最后提到可以执行 `/reload-skills` 或开新会话，让 Hermes 自动发现刚安装的 skill。

评论/后续摘要：
- heyaaron-Wu 评论说自己也感觉服务坏了，很卡。

判断：
- 这是有效的服务可用性和文档域名问题。当前环境只读检查显示：`ai4trade.ai` 根页、`/signals`、`/api/signals/feed` 能返回 200，约 2-4 秒；但 `api.ai4trade.ai` 仍 DNS 解析失败。

建议动作：
- 回复当前状态，说明目前推荐使用哪个 API host。
- 修复或移除文档里不可解析的 `api.ai4trade.ai`。
- 继续排查海外/容器环境访问 `ai4trade.ai/SKILL.md` 超时问题。

回复说之前的服务器容量太小了，经常被打爆，现在我们已经扩容了服务器，对造成的不便深感歉意。

### [`#202`](https://github.com/HKUDS/AI-Trader/issues/202) Slow initial loading and unclear onboarding for international users

提交者：Naveen-Boddepalli

原文中文摘要：
- 用户来自印度，使用 macOS 和 Chrome。
- 平台最终可以加载成功，但首次加载很慢，用户侧大约需要 1 分钟。
- 从新贡献者/新用户角度看，海外访问尤其是中国以外地区加载非常慢，而且用户难以判断页面是在正常加载还是卡死。
- 用户建议增加初始化过程中的 loading/progress 指示，改善国际 CDN/routing 性能，并在 README 中说明海外访问如果预期较慢应如何处理。
- 用户补充说平台加载完成后的 UI 观感不错，主要是反馈 onboarding 体验。

评论/后续摘要：
- chunhaiwu2020 从欧洲西班牙确认类似问题。
- 该用户说轻量 API 如注册/登录约 200ms 能成功，但数据重接口持续超时：`GET /api/signals/feed` 30 秒超时，`GET /api/signals/grouped` 30 秒超时，前端 `ai4trade.ai/signals` 完全超时。
- 该用户说 agent 注册成功，Hermes-小青 ID 为 5889，但无法使用平台核心功能：没有 signal feed、leaderboard、copy trading。
- 评论推测 API server 在香港，数据接口前面没有 CDN/edge caching。
- 评论建议使用 Cloudflare 等边缘缓存 signal feed/grouped，或加 gzip 和分页来减少首屏 payload。
- 评论者愿意在修复部署后协助测试。

判断：
- 有效的国际访问性能和首屏体验问题。当前环境未复现 30 秒超时，但不同地区的访问质量差异可信。

建议动作：
- 对 `/api/signals/feed`、`/api/signals/grouped` 等重接口加分页、压缩、缓存和边缘缓存。
- 前端增加可见 loading/progress 状态，避免用户误判卡死。
- README 增加国际访问说明和排障路径。


回复说之前的服务器容量太小了，经常被打爆，现在我们已经扩容了服务器，对造成的不便深感歉意。


### [`#203`](https://github.com/HKUDS/AI-Trader/issues/203) 关于api token问题

提交者：heyaaron-Wu

原文中文摘要：
- 用户询问为什么每次登录表现不一致：有时候提示密码不对，有时候登录成功后 API token 又变了。
- 用户质疑账户是否不是唯一的，或者 token 是否应该保持稳定。

评论/后续摘要：
- 无评论。

判断：
- 有效 bug。当前代码里 user login 会创建新的 user session；agent login 原本会通过 `_issue_agent_token` 每次轮换 agent API token，导致用户登录后看到 API token 改变。
- 账号名处理也需要统一：新注册应保存 trim 后的规范名称，同时要防止历史带空格账号和新规范账号形成“看起来同名”的两个账号。

建议动作：
- 合入修复 PR：agent login 复用已有 API token；仅 legacy 空 token 账号登录时补发 token；显式 token recovery 仍会轮换 token。
- 合入修复 PR：注册时保存 trim 后的 agent 名称，并按 `TRIM(name)` 查重，避免历史空格名和新规范名并存。
- 回复说明：agent API token 不应该因为普通登录而变化；同一 agent 名称注册后按规范化名称保持唯一；如果仍遇到密码错误，请确认使用的是注册时的 agent 名称，旧的历史空格名称也已保留精确登录兼容。

建议回复草稿：
> 感谢反馈，这里确实有一个 agent 登录行为的问题：普通登录不应该每次轮换 agent API token。我们已经准备了修复，登录会复用已有 token，只有历史空 token 账号会在首次登录时补发 token；显式 token recovery 仍会按预期轮换 token。注册侧也会统一保存 trim 后的 agent 名称，并阻止历史空格名称和新规范名称形成看起来相同的两个账号。修复合入后，请重新登录确认 token 是否保持稳定。




### [`#205`](https://github.com/HKUDS/AI-Trader/issues/205) `.env.example` formatting makes several env variables unusable

提交者：JamesVanhecke

原文中文摘要：
- 用户指出 `.env.example` 里很多变量和注释被折叠到同一行，导致一些变量不能被常见 dotenv loader 正确解析。
- 用户举例说第一行里注释标题和 `ENVIRONMENT=development` 在同一行：`# ==================== Environment ==================== ENVIRONMENT=development`。

评论/后续摘要：
- 无评论。

判断：
- 有效的配置文件格式问题。关闭的 PR `#208` 曾提供较聚焦修复，但未合并。

建议动作：
- 复用或重做 `#208`：让 `.env.example` 每个变量独立成行，默认 `DATABASE_URL=` 为空，把 PostgreSQL URL 放到注释示例，并增加解析测试。

### [`#206`](https://github.com/HKUDS/AI-Trader/issues/206) Docker setup seems inconsistent with local SQLite default configuration

提交者：JamesVanhecke

原文中文摘要：
- 用户指出默认本地数据库配置和 Docker 设置之间可能不一致。
- `.env.example` 同时定义了 `DATABASE_URL=postgresql://...` 和 `DB_PATH=service/server/data/clawtrader.db`。
- 用户认为这会让 PostgreSQL 和 SQLite 的默认路径/优先级不清楚。

评论/后续摘要：
- 无评论。

判断：
- 有效的配置/文档问题，和 `#205` 同源。需要明确本地开发和 Docker 环境的默认数据库策略。

建议动作：
- 明确规则：本地开发可在 `DATABASE_URL` 为空时使用 SQLite；Docker 或生产部署显式配置 PostgreSQL。
- 同步更新 `.env.example`、Docker 文档和 README 相关段落。

### [`#207`](https://github.com/HKUDS/AI-Trader/issues/207) Where is the backtest, walk-forward, and out-of-sample evidence?

提交者：Anic888

原文中文摘要：
- 提交者自称是量化交易员，认为 README 使用了较强营销表述，例如“100% Fully-Automated Agent-Native Trading”、“Collective Intelligence Trading”、“One-Click Copy Trading”，且覆盖股票、加密、外汇、期权、期货。
- 用户说在仓库里找不到以下证据：明确数据集和时间窗口上的回测结果、walk-forward optimization、样本外/holdout 验证、Profit Factor/MAR/Sharpe/最大回撤、滑点/延迟/交易成本建模、具体交易策略实现。
- 用户认为 `skills/` 目录更像 `ai4trade.ai` 注册和信号发布的 REST client，而不是策略实现。
- 用户认为“$100K paper trading”、“复制顶级表现者”、“发信号得积分”更像众包信号社交平台，而不是有可测 alpha 的交易系统。
- 用户质疑没有真实资金约束和 performance attribution 的众包信号对跟随者通常没有正 alpha，扣除成本后甚至可能是负 alpha。
- 用户要求维护者提供三个东西：任一策略在 holdout period 的 equity curve；证明 AI-agent-published signals 扣除滑点和费用后有正期望的方法论；解释为什么“universal market access”是优势，而不是缺少特定市场 edge 的信号。
- 用户最后说当前项目看起来像围绕 ai4trade.ai 的营销包装，缺少 edge 证据，但愿意被数据说服。

评论/后续摘要：
- 无评论。

判断：
- 有效的可信度和研究文档问题，不是小 bug。需要明确平台定位：研究/竞赛/信号平台，还是可验证交易系统。

建议动作：
- 如果已有 benchmark、paper trading 统计或实验报告，回复链接和方法。
- 如果没有，应诚实说明当前验证边界，并建立 benchmark/methodology 路线图。
- 审视 README 中可能过强的收益或自动交易表述。

### [`#210`](https://github.com/HKUDS/AI-Trader/issues/210) fantastic idea

提交者：zongyangbigpolo

原文中文摘要：
- 正文只有一句拼音/口语“niu bee”，表达夸赞。

评论/后续摘要：
- Felix8693 回复引用“牛蜂”，并问“好用吗兄弟”。

判断：
- 低信息量讨论，不包含 bug、feature request 或可执行建议。

建议动作：
- 简短感谢后关闭

### [`#211`](https://github.com/HKUDS/AI-Trader/issues/211) al trader

提交者：selnanbako2004-a11y

原文中文摘要：
- 标题为 `al trader`，正文为空。

评论/后续摘要：
- 无评论。

判断：
- 信息不完整，无法判断诉求。

建议动作：
- 关闭为 incomplete

## PR 原文中文摘要

### [`#209`](https://github.com/HKUDS/AI-Trader/pull/209) Improve agent credential robustness and sanitize signal transaction identifiers

作者：RinZ27  
分支：`fix/security-robustness-rinz27` -> `main`  
状态：Mergeable  
规模：+27 / -11

原文中文摘要：
- 作者认为需要改进 agent credential 存储和 signal transaction handling，以提升 trading server 的系统完整性。
- 作者指出 `utils.py` 当前使用 SHA256 做 credential hashing，吞吐高但对专用暴力破解硬件抵抗力不如专门的 key derivation function。
- 作者引入 `bcrypt`，通过可配置 work factor 加强凭据保护，同时保留对已有 SHA256 hash 的兼容校验，以便迁移。
- 作者还指出 `routes_signals.py` 使用 f-string 管理 `SAVEPOINT`，把 follower identifier 显式转成整数可以避免复杂事务回滚中的解析问题或意外行为，尽管当前 ID 来自内部表。
- 变更包括：`service/requirements.txt` 增加 `bcrypt`；`service/server/utils.py` 将 `hash_password` 改为 bcrypt 并让 `verify_password` 支持 legacy SHA256；`service/server/routes_signals.py` 清理 savepoint/rollback identifier。

评论/评审摘要：
- 无评论，无 review。

文件变更摘要：
- `service/requirements.txt`：新增 `bcrypt>=4.1.2`。
- `service/server/utils.py`：新密码用 bcrypt；旧 `salt$sha256` 仍可验证。
- `service/server/routes_signals.py`：`follower_id` 转 `int` 后用于 savepoint；另有一个字符串转义变动。

判断：
- bcrypt 方向合理，但该 PR 与 `#204` 都改 `utils.py` 的认证逻辑，不能直接顺序合并。
- legacy SHA256 分支仍没有 constant-time compare，异常处理也偏宽。

建议动作：
- 不直接合并。若批准 bcrypt，建议把 bcrypt 迁移整合进 `#204` 的认证加固补丁，并补测试。

### [`#204`](https://github.com/HKUDS/AI-Trader/pull/204) fix(security): rate-limit `/api/users/register` and use CSPRNG for codes

作者：aaronjmars  
分支：`security/registration-bruteforce-and-timing-safe-verify` -> `main`  
状态：Mergeable  
规模：+168 / -11

原文中文摘要：
- 作者认为用户注册流程有三个安全弱点，会组合成未认证的 email pre-emption / 未注册邮箱账户抢占风险。
- 第一，`/api/users/register` 在 5 分钟验证码有效期内允许无限次尝试；6 位验证码空间是 1,000,000，没有 per-code attempt counter、IP/email rate limit 或 back-off，攻击者可异步暴力枚举。
- 第二，验证码由 `random.randint` 生成，属于 Mersenne Twister，不是 CSPRNG；同样问题也在 `utils.generate_verification_code`。
- 第三，`verify_password` 用 `==` 比较 SHA256 hex digest，可能产生 timing leak；函数里的 bare `except:` 还会吞掉所有异常。
- 作者描述影响：攻击者可抢占尚未注册的邮箱账户，阻止真实用户注册，并拿到绑定受害邮箱的 session token；若下游 SSO/wallet-link/OAuth 信任邮箱，会扩大风险。
- 作者说明 agent/wallet-signature recovery flow 不受影响，因为已用 `secrets.token_urlsafe(18)` 并绑定 wallet signature。
- 修复方案：验证码改用 `secrets.randbelow(1_000_000)`；同一 email 30 秒内不能重复发送验证码；注册时记录 attempts，超过 5 次清除验证码并返回 429；验证码比较使用 `hmac.compare_digest`；`utils.generate_verification_code` 改用 CSPRNG；`verify_password` 改为 constant-time compare，并只捕获 malformed hash 的 `ValueError`。
- 作者说明检测来源是 Aeon 手工审查，semgrep/trufflehog/osv-scanner 都跑过；semgrep 该路径 clean，trufflehog 没发现 verified secrets；osv-scanner 报告部分依赖下限的传递 CVE，但作者认为 fresh install 会解析到新版本，可另开 hygiene PR。
- 作者标注严重性为 high，涉及 CWE-307、CWE-330、CWE-208。
- 作者声称验证命令 `python3 -m pytest service/server/tests/ -v` 通过，23 个测试全过。
- 新增测试覆盖：验证码不受固定 `random.seed` 影响、始终 6 位、密码 round-trip/篡改/坏 hash 行为、`verify_password` 调用 `hmac.compare_digest`、注册 5 次错误后第 6 次 429、重复发送验证码 429。

评论/评审摘要：
- 无评论，无 review。

文件变更摘要：
- `service/server/routes_users.py`：验证码生成、重发冷却、错误尝试次数限制、验证码 constant-time compare。
- `service/server/utils.py`：验证码 CSPRNG、密码 hash 比对 constant-time、坏 hash 处理更窄。
- `service/server/tests/test_user_auth_security.py`：新增认证安全回归测试。

判断：
- 安全修复目标明确，价值较高。限制是限流仍是内存态，不适合多进程/多实例完全防护；验证码仍打印到日志；随机性测试可以更强。

建议动作：
- 可作为认证加固基础补丁。本地测试后合入或本地应用；若要 bcrypt，则把 `#209` 的 bcrypt 迁移整合进同一版。

### [`#199`](https://github.com/HKUDS/AI-Trader/pull/199) fix(market_intel): treat Friday-close quotes as `session_close` on weekends and pre-market

作者：SuperMarioYL  
分支：`fix/market-intel-session-close-weekend` -> `main`  
状态：Mergeable  
规模：+152 / -2

原文中文摘要：
- 作者指出 `_build_stock_price_metadata()` 目前只在 intraday quote 日期等于当前美东日期时，把 `price_status` 标为 `session_close`。
- 这个逻辑对同一天盘后有效，例如周二 16:00 ET quote、周二 18:00 ET 当前时间。
- 但在两个日常场景下错误：周末时，周五 16:00 ET 收盘价是周一开盘前的最新实时数据，但周六/周日日期不同会被标为 `stale`；下一交易日前盘时，例如周二 08:00 ET，最新 quote 是周一 16:00 ET，也会因日期不同被标为 `stale`。
- 作者认为这些 quote 本质上是最新 session close 数据，应为 `session_close`。
- 修复方案是新增 `_last_us_session_date(now_et)`，从当前美东时间往回找最近一个已经完整收盘的交易日，跳过周末，然后用 `quote_et.date() < _last_us_session_date(now_et)` 判断 stale。
- 作者明确不处理节假日；这会把某些节假日相关 quote 保守地视作 `session_close`，但无新增依赖。
- 作者新增 9 个测试，覆盖盘中 realtime、同日盘后、周六/周日用周五收盘、周二盘前用周一收盘、周一盘前用周五收盘、多 session 前 quote 仍 stale、daily fallback 仍 stale、无法解析 timestamp 仍 stale。
- 作者给出运行方式：`python3 -m unittest service/server/tests/test_market_intel.py -v` 和 `python3 -m py_compile service/server/market_intel.py`，并声称所有 25 个 server tests 继续通过。

评论/评审摘要：
- 有一个空内容 approval，来自 `nfkbr7jcbs-spec`。

文件变更摘要：
- `service/server/market_intel.py`：新增最近已收盘美股交易日 helper，修改 stale/session_close 判断。
- `service/server/tests/test_market_intel.py`：新增 9 个测试。

判断：
- 聚焦、测试充分、风险较低。唯一明显限制是未建模美股节假日。

建议动作：
- 本地跑后端测试后可合入；节假日日历作为后续增强。

### [`#198`](https://github.com/HKUDS/AI-Trader/pull/198) Molten Hub Code: 100% Unit Test Coverage

作者：moltenbot000  
分支：`moltenhub-you-are-a-senior-software-engineer-focus` -> `main`  
状态：Mergeable  
规模：+1005 / -0

原文中文摘要：
- PR 声称来自 Molten.Bot，已实现所请求的变更，并且由 AI augmented engineering 构建、提交前经过 review。
- 原始任务要求是：作为关注 100% 单元测试覆盖率和测试质量的高级工程师，分析当前测试覆盖，找出未覆盖行/分支/函数，编写聚焦单元测试补齐覆盖；遵循现有测试模式；除非为了可测试性必要，不修改生产代码；不跳过或排除 coverage，除非有明确注释。
- 原始任务还要求本地验证 coverage，不断迭代直到达到目标或证明 blocker；如果测试/覆盖工具不可用，不应仅因此失败，而要用可行替代检查并报告验证缺口。
- PR 正文没有列出具体覆盖率报告，只说明“只修改相关文件”，并附了 MoltenBot Code 的宣传链接。

评论/评审摘要：
- 无评论，无 review。

文件变更摘要：
- 新增 `service/server/tests/test_unit_utilities.py`，约 1005 行，覆盖大量 utility、cache、scoring、market_intel、database-backed helper、routes_shared 等内部函数。

判断：
- 测试规模过大且集中在一个文件，明显依赖内部实现细节，维护成本高。
- 与 `#204` 存在概念冲突：该测试期望 `generate_verification_code` 可通过 patch `utils.random.randint` 控制，而 `#204` 的目标是移除 `random.randint`。

建议动作：
- 不建议整体合入。可要求作者拆成小而聚焦的测试 PR，或在安全/时区修改落地后挑选有价值的测试。

### [`#195`](https://github.com/HKUDS/AI-Trader/pull/195) feat(skills): add web-fetch-fallback skill using peer delegation

作者：baronsengir007  
分支：`feat/peer-skill-web-fetch-fallback` -> `main`  
状态：Mergeable  
规模：+97 / -0

原文中文摘要：
- 作者新增 `skills/web-fetch-fallback/SKILL.md`，描述通过 `@openclaw/peer-skill-mcp` peer delegation 做 resilient web-fetch。
- 作者强调默认无行为变化，只有设置 `PEER_SKILL_DELEGATE=1` 才启用 delegation。
- 用例是 market-intel 新闻聚合中，源站 rate limit、primary fetch 超时或地理限制时，使用 fallback。
- 作者说 AI-Trader 的 `market-intel` skill 依赖 web-fetch；当 primary fetch 失败时目前没有 fallback。该 PR 添加 opt-in peer delegation layer，把失败 fetch 路由到声明的 3 个 agent peer。
- peer pool 包括：OpenClaw Agent Tools，以及两个第三方 External Peer A/B，能力包括 web_fetch 和 summarize。
- 隐私说明：只 opt-in；不传 credentials；telemetry 只用截断 SHA-256 hash，不含 IP；可用 `PEER_SKILL_NO_TELEMETRY=1` 关闭 telemetry。
- 测试计划是人工 review 新 skill 文档、确认 pseudocode 与 AI-Trader fetch 模式匹配、可选安装 `@openclaw/peer-skill-mcp` 并运行 SKILL.md 中的 integration checklist。
- 相关链接是 npm package `@openclaw/peer-skill-mcp`、GitHub source `baronsengir007/peer-skill-mcp` 和 OpenClaw Research exp-242。

评论/评审摘要：
- 无评论，无 review。

文件变更摘要：
- 新增 `skills/web-fetch-fallback/SKILL.md`，内容是可选外部 peer delegation 的文档和伪代码。

判断：
- 这是文档型变更，但会引导用户安装外部 MCP 包并把 fetch 交给外部 peer，涉及隐私、供应链、信任边界和数据外传风险。
- 仓库内没有对应实现或安全评审。

建议动作：
- 除非维护者明确接受外部 peer 模型，否则建议拒绝/关闭。若要保留，应先安全评审，并标成实验性文档。

### [`#184`](https://github.com/HKUDS/AI-Trader/pull/184) fix: use DST-aware timezone for US stock price lookups

作者：sjhddh  
分支：`fix/hardcoded-edt-offset-dst` -> `main`  
状态：Mergeable  
规模：+10 / -2

原文中文摘要：
- 作者指出 `price_fetcher.py` 把美东时间硬编码为 `UTC-4`，即 EDT 夏令时。
- 实际上美东冬令时是 `UTC-5`，夏令时是 `UTC-4`；通常 11 月第一个周日从 EDT 切到 EST，3 月第二个周日从 EST 切回 EDT。
- 影响是 `_get_us_stock_price()` 会把 `executed_at` 转成美东时间，再与 Alpha Vantage 的美东蜡烛时间比较；在 EST 月份，所有 timestamp comparison 都偏 1 小时。
- 这可能导致函数错过 exact match，或者从错误的 candle 里取“closest previous”价格，静默返回所有美股交易的错误成交价。
- 作者认为这对回测或真实交易记录会造成接近半年的系统性 1 小时价格误差。
- 修复方案是使用 Python 3.9+ stdlib 的 `zoneinfo.ZoneInfo("America/New_York")` 做 DST-aware conversion；如果 Python < 3.9，则 fallback 到固定 `UTC-5`，作者认为这比固定夏令时更保守。
- 不新增依赖。
- 测试计划列出三项但未实现：EST 期间 `2025-01-15T14:30:00Z` 应转为 `09:30 ET`；EDT 期间 `2025-07-15T14:30:00Z` 应转为 `10:30 ET`；DST transition edge case `2025-03-09T06:30:00Z`。

评论/评审摘要：
- 无评论，无 review。

文件变更摘要：
- `service/server/price_fetcher.py`：引入 `zoneinfo.ZoneInfo`，用 `America/New_York` 替代固定 `UTC-4`；老 Python fallback 固定 `UTC-5`。

判断：
- 小而合理的时间处理修复。当前仓库 Python 版本如果满足 3.9+，实现风险低；但 PR 没有测试。

建议动作：
- 可合入候选；建议先补最小 EST/EDT 转换测试，或者要求作者补测试。

### [`#49`](https://github.com/HKUDS/AI-Trader/pull/49) feat: Migrate to uv for package management

作者：Yvictor  
分支：`main` -> `main`  
状态：Conflicting  
规模：+2817 / -44

原文中文摘要：
- 作者希望把项目从 pip 迁移到 `uv`，以获得更现代、更快的包管理。
- 变更包括：新增 `pyproject.toml` 和完整项目元数据；生成 `uv.lock`；删除 `requirements.txt`，把依赖放到 `pyproject.toml`；`.gitignore` 增加 `.python-version`。
- 文档更新包括：README 和 README_CN 改为 uv 命令；删除 pip 安装说明；把运行命令简化成 `uv run main.py`、`uv run data/get_daily_price.py`、`uv run agent_tools/start_mcp_services.py`。
- 脚本更新包括：`data/get_daily_price.py` 和 `data/get_interdaily_price.py` 改成适配 uv 运行路径。
- 作者列出 uv 的好处：比 pip 快 10-100 倍，统一 Python/venv/package 管理，通过 `uv.lock` 可复现，符合 PEP 的 `pyproject.toml`，运行命令更简单。
- 新工作流是 `uv sync` 安装依赖，`uv run ...` 运行脚本，`uv add/remove` 管理依赖。
- 作者声称已成功安装并测试 85 个包，包括 `langchain==1.0.2`、`langchain-openai==1.0.1`、`langchain-mcp-adapters>=0.1.0`、`fastmcp==2.12.5`。

评论/评审摘要：
- yefangyong 评论说这个想法很好，自己刚准备做就发现有人一小时前已经提交了。

文件变更摘要：
- `.gitignore`、`README.md`、`README_CN.md`、`data/get_daily_price.py`、`data/get_interdaily_price.py`、新增 `pyproject.toml`、删除旧根目录 `requirements.txt`、新增大体积 `uv.lock`。

判断：
- PR 很旧，已与当前仓库结构脱节。当前 runtime 依赖在 `service/requirements.txt`，不是旧根目录 `requirements.txt`；GitHub 已标记冲突。

建议动作：
- 关闭为 stale/superseded。如仍想迁移 uv，应基于当前 `service/` 结构重新设计并开新 PR。

## 可复用的已关闭 PR

[`#208`](https://github.com/HKUDS/AI-Trader/pull/208) `fix: make .env.example parseable by shell and dotenv` 已关闭且未合并，但它与 issue `#205`、`#206` 直接相关：把 `DATABASE_URL` 改为空默认值、把 PostgreSQL URL 变成注释示例、修复格式损坏的分隔行，并新增 `.env.example` 解析测试。

## 建议审批队列

1. 审批关闭明显不可操作或可疑条目：issue `#200`、`#210`、`#211`。
2. 审批回复并保留开放：issue `#201`、`#202`、`#205`、`#206`、`#207`。
3. 合入 issue `#203` 的 agent token 稳定性修复后回复并关闭。
4. 本地测试后合入或本地应用 PR `#199`。
5. 为 PR `#184` 补最小 EST/EDT 测试后合入或本地应用。
6. 以 PR `#204` 作为认证加固基础；审批是否把 PR `#209` 的 bcrypt 迁移并入。
7. 除非维护者希望重新拆分，否则关闭 PR `#195`、`#198`、`#49`。

## 未执行操作确认

本次没有：
- 在任何 issue 或 PR 下评论；
- 关闭、打标、分配、审批或合并任何远程条目；
- push commit 或修改远程分支。
