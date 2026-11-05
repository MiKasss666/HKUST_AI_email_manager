# 方案 A（网页版 Dify · 设备码登录 · 可分发）

> 新增约束：
> 1. 用户使用 **网页版 Dify（cloud.dify.ai）**；
> 2. **学校提供 AI API**（不需要用户自己买 API Key）；
> 3. 登录用 **设备码（device code）**，全程在 Dify 网页里完成，**不让用户进 Azure 注册应用**；
> 4. **要分发给同学**（每个同学用各自的学校邮箱/邮箱账户）。
> 本文在 [PLAN_A_CLOUD_TWO_PLUGINS.md](PLAN_A_CLOUD_TWO_PLUGINS.md) 基础上，收敛到"可分发、低门槛"的最终形态。事实核对到 Dify Cloud 文档、`langgenius/outlook_trigger` 源码、Dify 定价页。

---

## 0. 先说结论：这组约束会改变插件拆分方式

| 约束 | 直接后果 |
|---|---|
| 设备码登录 | 授权由**我们的插件自己完成**（不是 Dify 的 OAuth 授权流），token 存在**插件 storage**里 |
| 全程在 Dify 网页完成 | 需要一个"显示设备码 → 用户去微软授权 → 回来确认"的界面。Trigger 工作流不能做 WebApp，所以用 **Human Input 节点（Dify 发邮件/表单）** 或一个极简 Setup WebApp |
| 分发给同学 | 每个同学一个自己的 Dify workspace；插件从 **GitHub 安装**（Cloud 支持）；登录沿用原程序的"微软公开客户端兜底"，**不需要注册 Entra App、不需要管理员许可** |
| "不要一个包" + 设备码 | ⚠️ **冲突点**：设备码只需登录一次，但 token 存在**单个插件的 storage**里；拆成两个插件 = 两套 storage = **要登录两次**。这是必须拍板的地方（见第 2 节） |

**我的推荐（v1）**：
- **一个插件包** `email-manager`（工具型：设备码登录 + 邮件读写 + categories + 状态 + 报告），**不含触发器**；
- **一个工作流**，起始节点用 **Schedule Trigger（每 5 分钟）**；登录用同一条工作流里的 **Human Input 分支**完成；
- 这样：**一次安装、一次设备码登录、零 Azure 操作、一个工作流**；代价是轮询间隔 1–5 分钟（不是秒级）。

> 如果"一定要实时（来邮件即触发）"，则必须再引入触发器插件，此时"一次登录"很难保住（见第 2 节的 B/C）。建议先做 v1，实时作为 v2 增量。

---

## 1. 网页版 Dify + 学校 AI API + 设备码：可行性

### 1.1 各环节的落点

| 环节 | 做法 | 依据/备注 |
|---|---|---|
| 安装插件 | 我们把插件发到 **GitHub 公开仓库 Release**；同学在 Dify → Integrations → Install → **From GitHub** 填仓库 URL | Cloud 支持 Marketplace / GitHub / 本地 `.difypkg` 三种方式；GitHub issue #25808 的故障已修复且报告者确认可用 |
| 设备码登录 | 插件内实现：`sign_in_start` 调微软 `/devicecode` 返回 `user_code` + `verification_uri_complete`；`sign_in_poll` 轮询 `/token`；成功后把 `access_token/refresh_token/expires_at` 存插件 storage | **完全照搬原程序 `core/graph.py:275-361`**：优先用可配置的 `client_id`，否则依次尝试微软自带的 3 个公开客户端（Graph CLI Tools / Azure CLI / Azure PowerShell）。**不需要注册 Entra 应用、不需要管理员同意**，每个账号首次登录时自己点"同意" |
| 登录界面（在 Dify 网页内） | 工作流的前置分支：`auth_status` 未登录 → `sign_in_start` → **Human Input 节点**（Email 投递，表单里显示设备码 + 链接）→ 用户去微软输入码 → 点 `Done` → `sign_in_poll` 存入 token | Trigger 工作流不能用 WebApp 投递，但 **Human Input 的 Email 投递可用**；Dify Cloud 自带发信能力 |
| token 刷新 | 插件每次调用 Graph 前检查 `expires_at`，过期用 refresh_token 刷新；refresh token 轮换后写回 storage；失效则重新走设备码 | 原程序 `graph.py:364-432` 的逻辑原样移植 |
| 学校 AI API | 每个同学在自己的 workspace 里把学校 API 配成 **OpenAI 兼容 Model Provider**（base_url + key），LLM 节点选它 | 需确认学校 API 从公网可达（见第 7 节问题） |
| 分发 | 仓库 = 插件源码 + Release 的 `.difypkg` + `email-manager.yml`（DSL）+ 中文安装向导；同学每人一个 workspace | Education 折扣（学校邮箱）可免费用 Yearly Professional；见配额核算 |

### 1.2 登录方案：原版设备码 + 微软公开客户端兜底（不依赖管理员许可）

既然拿不到管理员许可，就按原程序的做法来——**不注册自己的 Entra 应用，直接借用微软自家的公开客户端做设备码**：

```text
候选 client_id 顺序（原 graph.py:275-289）：
  1) 配置里的 client_id（如果以后有学校/自建 App，可填这里）
  2) 14d82eec-204b-4c2f-b7e8-296a70dab67e  Microsoft Graph Command Line Tools
  3) 04b07795-8ddb-461a-bbee-02f9e1bf7b46  Azure CLI
  4) 1950a258-227b-4e31-a9cf-717495945fc2  Azure PowerShell
tenant：common（原默认；可配 organizations）
scopes：offline_access openid profile User.Read Mail.ReadWrite Mail.Send
```

- 逐个试 `/devicecode`，第一个成功返回的可用于整轮登录与后续 refresh（原逻辑：缓存里记下 `client_id`，refresh 时继续用它）；
- 用户只是在自己的微软账号上**同意一次委托权限**（`Mail.ReadWrite`/`Mail.Send` 属于用户可同意的委托权限，正常不需要管理员）；
- **不需要**：Azure 账号、应用注册、client secret、重定向 URI、管理员同意；
- 原程序已在你账号上跑通同样的路径，说明学校租户对这几个公开客户端的**用户同意**没有被整体禁掉；分发前只需要再拿一个同学的账号验证一次。

**已知风险（README 必须写）**：

1. 借用微软的公开客户端 ID 访问 Graph 属于"灰区"（原程序 README 也注明"仅适合自己用"）。给同学分发时建议：
   - 先按原版用兜底客户端跑通；
   - 如果学校租户以后允许注册普通应用（**可以不要管理员同意**，只要求用户同意），在插件设置里把 `client_id` 换成学校/自己的 App 即可，不用改代码；
2. 如果某个账号首次登录时提示"需要管理员批准"（租户策略禁止用户同意），这个方案对该账号无解——原程序同样会失败。这类账号只能请 IT 批准，或改用别的邮箱/自部署+学校 App；
3. 微软如果调整这 3 个公开客户端的可用性，登录会失败；插件保留 `client_id` 配置项 + 明确的错误提示，便于随时切换。

---

## 2. "不要一个包" vs "一次设备码登录"（必须拍板）

设备码的 token 存在**插件 storage**，而插件 storage 是**按插件隔离**的。拆成两个插件后：

| 拆分方式 | 登录次数 | 用户成本 | 我们维护成本 | 实时性 |
|---|---|---|---|---|
| **A. 单插件（推荐 v1）**：工具型插件（登录+读写+状态+报告）+ **Schedule Trigger 轮询** | **1 次设备码** | 最低 | 低（1 个包） | 1–5 分钟 |
| **B. 双插件（实时）**：`email-manager-tools`（设备码）+ **官方 `outlook_trigger`**（Dify Cloud 自带 OAuth） | 1 次设备码 + 1 次 OAuth 点击 | 中；需确认 Cloud 是否为 Outlook Trigger 提供默认 OAuth（这样也不用建 Entra App） | 中（1 个自研包） | 事件驱动 |
| **C. 双插件（全自研设备码）**：tools + trigger 各做一次设备码 | **2 次设备码** | 高 | 高（2 个包） | 事件驱动 |
| **D. 双插件（trigger 用自研 OAuth）** | 1 次设备码 + 1 次 OAuth + 用户建 Entra App | 高（与"不碰 Azure"冲突） | 中 | 事件驱动 |

**所以**：
- 如果"不要一个包"是**硬要求**，并且要**实时** → 选 **B**（前提：Cloud 给官方 Outlook Trigger 提供默认 OAuth，或你能接受同学各自建 Entra App）；
- 如果"不要一个包"只是**不想维护一个合并插件**，而可以接受 v1 先做单插件 + 轮询 → 选 **A**，后续再增量上 B；
- **C/D 不建议**：要么两次登录，要么把 Azure 步骤重新推给同学。

> 我的建议：**v1 选 A**（单插件 + 5 分钟轮询 + 一次设备码登录），把"实时"作为 v2 用 B 的方式增量加。这样第一版就能发给同学用。

---

## 3. v1（方案 A）架构

### 3.1 交付物

| # | 交付物 | 说明 |
|---|---|---|
| 1 | 插件 `email-manager`（单包，GitHub Release `.difypkg`） | 设备码登录 + 邮件读写 + categories 写回 + 状态 + 报告/告警发送；**无触发器** |
| 2 | 工作流 `email-manager.yml`（DSL） | 一个工作流：Schedule Trigger + 登录分支 + 主流程（采集/控制/报告/判级/写回/推进/告警） |
| 3 | 安装向导 README（中文） | 学生视角：注册 → Education 折扣 → 配学校 AI API → 装插件 → 导入 DSL → 填环境变量 → 运行 → 设备码登录 → 打开 Schedule |
| 4 | 运维/故障排查文档 | token 失效、学校租户限制、Graph 限流、日志排查 |

### 3.2 插件工具

| 工具 | 用途 |
|---|---|
| `auth_status` | 返回是否已登录、账号 UPN、token 是否可刷新 |
| `sign_in_start` | 调 `/devicecode`，返回 `user_code`、`verification_uri`（含 code 的完整链接）、`expires_in` |
| `sign_in_poll` | 轮询 token；成功则把 access/refresh/expires_at 写入 storage 并返回账号信息 |
| `sign_out` | 清除 token（换账号/撤销） |
| `collect` | 头部列表 → 跳过报告/`sum`/已分类/ignored/旧邮件 → 候选取正文并截断 → 同时返回待处理 `sum` 指令与待补 `Sum` 报告 |
| `collect_recent` | 出总结报告时读取已分级邮件（官方插件不返回 categories，必须自研） |
| `apply` | 合并写 categories（保留用户自定义标签）+ S 紧急打红旗 + 单封错误隔离 |
| `tag` | 给报告/指令邮件打 `Sum` |
| `send_report` | 发 HTML 报告 / 告警邮件 |
| `state_get` / `state_lock` / `state_unlock` / `state_advance` | 状态 KV（last_seen / ignored / failed_rounds / lock / paused / last_catchup_date / last_report_at） |
| `check` | 只读自检：token、`/me`、最近一封邮件、AI 由 Dify 侧负责 |

- 所有业务失败返回 `{success, transient, error}`；写操作不自动重试；GET 遇 429/5xx 按 `Retry-After` 退避（原 `graph.py:196-248`）。
- storage 申请 10MB；token 与状态都在 workspace 级（**每个同学自己的 workspace**，天然隔离）。
- 插件 manifest 声明 `network.domains: [graph.microsoft.com, login.microsoftonline.com]`。

### 3.3 一个工作流的结构

```text
[Schedule Trigger: */5 * * * *]
  → auth_status
      ├─ 未登录: sign_in_start → Human Input(Email 表单：显示设备码+链接) → sign_in_poll
      │            ├─ 成功 → Output（提示已登录，下轮自动开始工作）
      │            └─ 超时/取消 → Output（下轮重试，重新发码）
      └─ 已登录:
           state_get → paused?→Output
           state_lock(owner={{sys.workflow_run_id}}, ttl=300) → 抢不到 → Output skipped
           collect(catchup=今天没补过, max_items=30)
             ├─ controls.sum_commands 非空 → tag → 报告分支（collect_recent → Code 分批 → LLM 要点 → Code HTML → send_report → tag(报告) → advance）
             ├─ controls.reports 非空 → tag → advance
             ├─ candidates 空 → advance → unlock → Output idle
             └─ 有候选 → Code 分批(20+10) → LLM #1 → Code 校验+确定性兜底
                        → If 第二批 → LLM #2 → Code
                        → If 失败 → Iteration 逐封补判
                        → apply → advance → (gave_up/连续错误 → send_report 告警 + state_set paused)
                        → unlock → Output stats
```

- 登录分支让"在 Dify 网页里完成设备码登录"成立：同学只需要打开 Dify 发的表单邮件（或工作流 Human Input 表单），复制设备码到微软页面，授权后回来点 Done。
- 登录分支平时不会触发（已登录直接跳过）；token 失效时会自动再次发起。
- **防刷屏**：在 `state` 里记 `auth_prompted_at` / 待用设备码；同一个设备码有效期（约 15 分钟）内不重复发邮件；设备码过期后下一轮再发新码。不要在未登录时每 5 分钟发一封邮件。
- Human Input 超时设 **20–30 分钟**（必须小于 `WORKFLOW_MAX_EXECUTION_TIME=3600s`；若实测暂停时间计入，则更短或调大上限）。
- 所有分支最终都 `state_unlock`，避免锁泄漏。

### 3.4 环境变量（每个同学填自己的）

`EMAIL`、`NAME`、`STUDENT_ID`、`SCHOOL_DOMAINS`、`FACULTY`、`FACULTY_KEYWORDS`、`COURSES`、`DORM_KEYWORDS`、`URGENT_DAYS`、`CATCHUP_DAYS`、`SUMMARY_DAYS`、`BATCH_SIZE(20)`、`RECIPIENT`、`LANGUAGE`、`DRY_RUN`、`AI_MODEL`、`TENANT`（默认 `common`）、`CLIENT_ID`（默认空 = 用微软公开客户端兜底；以后有学校/自建 App 时填这里）。

### 3.5 一轮到底发生了什么（逻辑总览，便于讲解/答辩）

把整个工作流想成一台**每 3–5 分钟醒来一次的自动值班员**，每轮只做 5 件事：

**① 先确认"能干活"**
- 没登录 → 走设备码登录分支（发一次表单邮件，拿到 token 就继续；这轮到此为止）；
- `paused=true` → 直接结束（连续出错后自动暂停，等人处理）；
- 抢不到运行锁 → 直接结束（说明上一轮还没跑完，防止重复处理）。

**② 去邮箱里"看有什么要做的"（插件 `collect` 一次搞定）**
- 只拉邮件头（不下载正文）→ 跳过：自家报告、`sum` 指令、已经打过我们标签的、之前判过"非学校"的、比上次基线更旧的；
- 返回三样东西：
  - `candidates`：要判级的邮件（最多 30 封，含截断后的正文头 400 字 + 尾 300 字）；
  - `controls`：还没处理的 `sum` 指令邮件、还没打 `Sum` 标签的自家报告；
  - `newest/oldest`：本轮扫描到的最新/最旧邮件 ID（用来推进基线）。
- 网络/429/5xx → 返回 `transient`，本轮不写回、不推进，下一轮重试。

**③ 有控制邮件 → 先办控制邮件（对应原程序"先打标签再出报告"）**
- `sum` 指令：先给指令邮件打 `Sum`（"已处理"标志，防重复）→ 读出最近 N 天已分级邮件 →
  - 没有邮件 → 不发报告；
  - 有 → 每 20 封一批让 AI 写一句话要点（截断时先收下完整的，缺的留空）→ 拼 HTML（按 S→A→B→C 分组）→ 发给自己 → 报告主题带中英标记；
- 自己的报告缺标签：补打 `Sum`；
- 最后推进基线、解锁、结束。

**④ 没有控制邮件、也没有候选 → 空跑结束**（只花 1 次触发，不调 AI）

**⑤ 有候选 → 判级并写回（核心）**
1. Code 把 30 封分成 20 + 10 两批，拼提示词（规则文本来自环境变量：课程、学院、学校域名、紧急天数、姓名/学号）；
2. LLM 判级，要求返回每封的 `entryid + 级别 + 截止日期 + 是否学校邮件`；
3. Code 校验：**条数必须正好等于本批**，并按 `entryid` 对齐（不按顺序，防错位）；不合规的批次整批作废；
4. 失败的批次 → **逐封再判一次**（这是"递归对半拆"的替代：不再拆 3 层，坏一批就退化成单封，仍失败就留空不猜）；
5. Code 确定性兜底（只升不降）：发件域名命中学校域名 → 强制算学校邮件；命中我参与的课程 / 我的学院 → 至少 A 级；S + 截止日在 N 天内 → 加急红旗；
6. `apply` 写回：非学校邮件不写、只计 skipped 并记住 ID；学校邮件只替换 `S/A/B/C` 这 4 个标签（用户自己打的标签保留）+ S 加急打红旗；单封失败不影响其他封；
7. `advance` 推进基线：全部成功 → 基线推到本轮最旧一封；有失败且未满 3 轮 → **基线不动**（下轮只重试失败的）；连续 3 轮失败 → 放弃并推进，同时发告警邮件；
8. 解锁、输出统计（read / ok / failed / skipped / S A B C 各多少）。

**贯穿始终的"幂等"三保险**：
- 写进邮件的 `S/A/B/C/Sum` 标签本身就是"已处理"标记（读邮件头就能看到）→ 崩溃在"写完邮箱、还没推进基线"之间，下一轮也不会重复处理；
- "判过不是学校"的邮件不贴标签，所以另存一份 ignored ID 名单，避免每轮重复送 AI；
- 报告靠"`Sum` 标签 + 主题标记 + last_report_at"三重去重，不会重复出报告。

**和原程序的对应关系**：`collect`≈原 `graph._collect`；控制分支≈原 `watcher.plan_tick/_tag_reports/_run_commands`；判级≈原 `classifier.classify`（拆分策略有损）；`apply`≈原 `apply_verdicts + merge_categories`；`advance`≈原 `advance_policy`；报告≈原 `summarizer`；告警/暂停≈原 `_on_error`。

### 3.6 手动发指令：邮件 `sum` 之外，还能在 Dify 里点一下

默认语义（与原程序一致）：**只有收到 `sum` 指令邮件才出总结**。但"发指令"可以不止一种方式：

| 方式 | 怎么做 | 优点 | 代价 |
|---|---|---|---|
| **A. `sum` 指令邮件（默认，保留）** | 给自己发主题 `sum` / `sum sa` / `sum sabc` | 零配置，手机上就能发 | 要发一封邮件 |
| **B. Webhook Trigger（推荐加）** | 同一个工作流再挂一个 Webhook Trigger；用户打开一个带 token 的 URL/书签就出总结 | 仍然只有**一个工作流**；可扩展成 classify / check / resume 指令 | +0.5 天；URL 要保管好 |
| **C. 控制台 WebApp（可选）** | 另发一个 User Input 小应用，页面上放"出总结/立即分类/自检"按钮 | 体验最像原程序的 GUI | **多一个应用**（主引擎仍是一个工作流） |
| **D. 定时自动总结（可选）** | 在 Schedule 分支判断"到点了且今天还没发过" → 自动出报告 | 不用任何指令 | 改变原语义；每次都要花钱/写日志 |

**方案 B 的具体做法（推荐）**：

1. 工作流里加 **Webhook Trigger** 节点（和 Schedule Trigger 并列，Dify 支持一个工作流多个触发器；分支共享下游时用 Variable Aggregator 汇合）；Dify Cloud 会给出公网 URL；
2. Trigger 配置：`POST`（或 `GET`）+ query 参数 `token`、`action`、`letters`、`days`，其中 `token` 设为 required；
3. 第一个 Code 节点校验 `token == {{env.WEBHOOK_TOKEN}}`，不匹配直接结束（防止拿到 URL 的人消耗 AI）；
4. 按 `action` 分支：
   - `sum`：跳过采集/判级，直接 `collect_recent → LLM 要点 → Code HTML → send_report → tag`；
   - `classify`：立即跑一轮完整分类（等于原程序的 Categorize 按钮）；
   - `check`：返回登录状态 + 邮箱连通性；
   - `resume`：清除 `paused`；
5. 用户用法：浏览器书签 `https://…/triggers/webhook/xxx?token=…&action=sum&letters=sa`；或一个静态 HTML 按钮页（三个按钮 POST 到该 URL）；或 Dify 里"Test Run"手动发一次；
6. 返回 200 只代表"已触发"，总结是异步生成的——结果看 Dify 运行日志或邮箱。

> 建议：**A + B 都保留**。A 作为手机上的快捷方式，B 作为电脑上"点一下"的入口；C 等有同学反馈"想要按钮界面"再做。

---

## 4. 网页版 Dify 配额与成本（分发视角）

| 项目 | Sandbox | Professional | **Education（学生免费 Yearly Pro）** |
|---|---|---|---|
| Trigger Events | 3,000 | 20,000/月 | 20,000/月 |
| **每 5 分钟轮询** = 288 次/天 ≈ **8,640 次/月** | 超 | 占用 43% | 占用 43% |
| 每封新邮件额外触发的 Graph/LLM | 只在有候选时发生 | — | — |
| AI 调用 | 用**学校 AI API**（自建 Model Provider）→ 不消耗 Dify AI credits | 同 | 同 |
| Apps | 5 | 50 | 50 |

- 分发建议：同学用**学校邮箱**注册 cloud.dify.ai → 申请 **Education 折扣**（免费 Yearly Professional）→ 20k Trigger Events/月足够 3–5 分钟轮询 + 兜底；
- **「5 分钟延迟」的含义**：邮件本身立刻进收件箱；只是"打 S/A/B/C 标签、发报告"要等到下一次定时运行。等一次 = 0–5 分钟（平均约 2.5 分钟，最坏接近 5 分钟）。文件在两次运行之间到达的会**在同一轮里一起批处理**，不会逐封排队叠加。
- 轮询间隔与配额（Education Pro 20,000 Trigger Events/月）：

| 间隔 | 每天运行 | 每月 Trigger Events | 最坏延迟 | 结论 |
|---|---|---|---|---|
| 1 分钟 | 1,440 | 43,200 | 1 分钟 | 超配额 ❌ |
| 2 分钟 | 720 | 21,600 | 2 分钟 | 略超 ❌ |
| **3 分钟** | **480** | **14,400** | **3 分钟** | **配额内，想快就选它 ✅** |
| **5 分钟（默认）** | **288** | **8,640** | **5 分钟** | 配额宽裕 ✅ |
| 10 分钟 | 144 | 4,320 | 10 分钟 | 最省，但慢 |
- 学校 AI API 若只限校园网，Cloud 调不到 → 需要学校提供公网可达 endpoint，或退回自部署（见第 7 节问题）。

---

## 5. 同学安装流程（README 要写的 8 步）

1. 用**学校邮箱**注册 cloud.dify.ai → Settings > Billing 申请 **Education 折扣**（免费 Yearly Pro）；
2. 在 Model Provider 里添加**学校 AI API**（OpenAI 兼容：base_url / key / model 名）；
3. Integrations → Install → **From GitHub** → 填插件仓库 URL（或上传 `.difypkg`）→ 同意权限；
4. Studio → Import DSL → 导入 `email-manager.yml`；
5. 填应用环境变量（第 3.4 节）；
6. 发布工作流 → 打开 Schedule Trigger（`*/5`）；
7. 等第一轮运行：Dify 会发一封 **Human Input 表单邮件**（或在工作流日志里看到设备码）→ 打开微软设备登录页 → 输入码 → **首次会看到微软的权限同意页（应用名显示 Microsoft Graph Command Line Tools 等）→ 点接受** → 回来点 **Done**；
8. 下一轮自动开始分类；之后收件箱里的新学校邮件会在 5 分钟内被分类，`sum` 指令邮件触发报告。

> 同学不需要：Azure 账号操作、注册 Entra 应用、自己买 AI API、装 Python/桌面程序。

---

## 6. P0 验证清单（必须先做，半天）

| # | 验证 | 通过标准 | 失败退路 |
|---|---|---|---|
| 1 | **同学账号**首次设备码登录：3 个微软公开客户端里至少 1 个能返回设备码，且用户同意页可通过（不需要管理员） | 非管理员账号也能授权 `Mail.ReadWrite/Mail.Send`；登录后 `/me` 通 | 换另一个公开客户端；仍不行则该校账号被策略限制（原程序也过不了），只能请 IT 或换账号 |
| 2 | 插件在网页版 Dify 从 GitHub 安装 | 安装成功、工具节点出现 | 本地 `.difypkg` 上传；或 Marketplace（需审核） |
| 3 | Human Input 在 Trigger 工作流里 Email 投递可用 | 表单邮件能收到、链接能打开、提交后流程继续 | 改成"Setup WebApp（User Input 应用）+ 主工作流"两个应用（多一个，但登录体验更好） |
| 4 | Human Input 暂停是否计入 3600s | 实测：暂停 10 分钟后仍能恢复 | 调大 `WORKFLOW_MAX_EXECUTION_TIME`；或缩短超时 |
| 5 | 设备码 token 刷新/轮换在插件 storage 中正常 | 跨 1 小时/跨天仍能调用 Graph | 重新登录分支兜底 |
| 6 | 学校 AI API 从 Dify Cloud 可达 | LLM 节点能返回结果 | 换公网可达 endpoint；或改自部署 |
| 7 | 5 分钟轮询的 Trigger Events 计数 | Dify 用量面板数字 = 预期 | 改 10 分钟；或改成实时方案 B |
| 8 | PATCH categories 生效 | 邮箱里出现 S/A/B/C 标签 | 检查 scope/租户策略 |

---

## 7. 分发与多用户设计要点

| 主题 | 结论 |
|---|---|
| 每个同学的数据隔离 | 每人**自己的 Dify workspace**（Education Pro），插件 storage 天然按 workspace 隔离；不要让大家共用同一个 workspace，否则 token 会互相覆盖 |
| 学校 AI API 的 Key | 如果是一个共享 Key，风险是额度/滥用；建议学校给每人独立 Key 或限制额度（这属于学校侧策略，不是 Dify 能解决的） |
| 插件升级 | GitHub Release 升版本；Dify 里点升级；DSL 版本号写进 README 与工作流检查节点 |
| 隐私 | 插件会读/发邮件；token 存在 Dify Cloud 的插件存储。README 里写明数据流向（Dify Cloud + 学校 AI API + Microsoft Graph），**OpenAI 兼容接口如果由学校提供，邮件正文会发给学校 AI 服务**，需告知同学 |
| 撤销/毕业 | `sign_out` 工具或直接卸载插件/撤销微软授权；毕业换邮箱时重新登录 |
| 支持成本 | 同学们会遇到的问题集中在：设备码过期、学校租户拒绝同意、AI API 配置、轮询延迟。README + FAQ 先写好；建议群里置顶 |
| 后续 Marketplace | 等稳定、用户变多再考虑上架（需要公开源码、英文 README、PRIVACY.md、风险分级、审核）；Cloud 直接 GitHub 安装已够用 |

---

## 8. 实时版（v2 / 方案 B）增量

如果 v1 跑稳后要"来邮件即触发"：
1. 新增第二个包 `email-manager-trigger`（fork 官方 `outlook_trigger`：只订阅 `created`、事件瘦身、去重窗口清理、10MB storage）；
2. 登录：触发器订阅创建需要 OAuth/凭据。**两条路**：
   - 用 Cloud 给官方 Outlook Trigger 提供的**默认 OAuth**（若有）→ 一键授权，无需 Entra App；我们的 trigger fork 无法用默认客户端，所以这一步可能必须用**官方插件**；
   - 或 trigger 包沿用工具包的**公共客户端 OAuth**（P0 验证 Dify 是否支持 public client 无 secret 的授权码流程；不支持就要用户建 Entra App → 与"不碰 Azure"冲突）。
3. 工作流在现有 DS L上加 **Integration Trigger**，与 Schedule Trigger 用 Variable Aggregator 汇合；Schedule 降为每天 1–2 次兜底；
4. Trigger Events 消耗从"轮询 8.6k/月"降为"每封邮件 1 次"，更省。

> 结论：v2 的实时能力取决于"Cloud 是否给 Outlook Trigger 默认 OAuth"这一条；P0 里可以顺手验证。

---

## 9. 实施计划（v1）

| 阶段 | 内容 | 工作量 |
|---|---|---|
| P0 | 第 6 节 8 条（重点是同学账号设备码同意、Human Input 邮件、Cloud 配额、学校 AI API 可达） | 0.5–1d |
| P1 | 插件：设备码登录 + token 刷新 + Graph 底座 + collect/apply/tag/send/state（fork 官方 outlook 作为底座） | 3–4d |
| P2 | 一个工作流 DSL：Schedule + 登录分支 + 主流程 + 报告 + 告警 | 1.5–2d |
| P3 | Golden Set 对照 + 写回/故障注入验收 | 1d |
| P4 | 分发：GitHub Release、中文安装向导、FAQ、隐私说明、版本校验 | 1d |
| 合计 | | **7–9d** |

---

## 10. 待确认问题

1. "不要一个包"是**硬要求**吗？在"设备码 + 一次登录"的前提下，**单插件 + 5 分钟轮询**是最干净的第一版；如果必须两个包并且要实时，就只能走 B（依赖 Cloud 默认 OAuth 或同学自建 Entra App）。
2. **学校 AI API** 是公网可达的 OpenAI 兼容 endpoint 吗？有没有给每个学生的独立 Key？模型名/限流是什么？
3. 你的账号已经用原程序设备码登录成功过吗？有没有第二个同学的账号可以立刻验一次"首次用户同意"？（这决定分发前是否需要准备账号白名单/说明）
4. 可接受的延迟：**5 分钟**（推荐，省配额）还是 10 分钟/1 分钟？
5. 分发规模：先给几个同学试用，还是一个班/一个学院？（决定要不要写更细的 FAQ、要不要上 Marketplace）
6. 是否需要保留"手动立即跑一次"？（Trigger 工作流没有按钮，可以再加一个保护口令的 Webhook Trigger 作为 Run now 入口）
