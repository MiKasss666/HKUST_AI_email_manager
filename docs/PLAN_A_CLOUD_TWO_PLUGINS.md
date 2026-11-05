# 方案 A（网页版 Dify 版）：两个插件 + 一个工作流

> 需求更新：**用户使用网页版 Dify（Dify Cloud）**；**不合并成一个插件包**——拆成两个可独立安装的插件；所有逻辑仍然放在 **一个 Dify 工作流**里。
> 前置阅读：[DIFY_MIGRATION_ADVICE.md](DIFY_MIGRATION_ADVICE.md)、[PLAN_A_SINGLE_WORKFLOW.md](PLAN_A_SINGLE_WORKFLOW.md)（插件工具规格、状态/失败语义、移植清单继续适用）。
> 本文替换上一版"单插件包"的分发与部署部分。事实依据：Dify 官方 Cloud 文档、`langgenius/outlook` 1.0.1、`langgenius/outlook_trigger` 1.0.3 源码、Dify Cloud 定价页。

---

## 0. 结论

可以做到"**装两个插件 + 导入一个工作流**"就能在网页版 Dify 上跑起来。关键结论：

1. **网页版 Dify 支持安装 GitHub 插件和本地 `.difypkg`**（Integrations → Install → GitHub / Local Package File），**不一定需要上架 Marketplace**。之前有段时间 Cloud 装不上（GitHub issue #25808），现已修复并由报告者确认。→ 分发方式：**GitHub 仓库 + Release**，用户填仓库 URL 安装。
2. **网页版 Dify 的触发器回调地址是公网的**：官方 Outlook Trigger 可以在 Cloud 上直接创建 Graph 订阅，**用户不需要自己搞内网穿透/Tunnel**。这是 Cloud 相对自部署的最大便利。
3. **Cloud 支持一个工作流里放多个触发器**，官方文档明确："If their branches share downstream nodes, add a Variable Aggregator to converge them." → 一个工作流同时挂 **Outlook 事件触发器（实时）** + **Schedule Trigger（兜底/补分类）** 是被官方支持的。
4. **必须拆成两个插件**（符合"不要一个包"）：
   - **插件 A `email-manager-tools`**：读写邮件 + 状态（categories 写回、KV、报告发送、采集）——fork 官方 `outlook` 工具插件，加 3 类能力；
   - **插件 B `email-manager-trigger`**：新邮件触发器——fork 官方 `outlook_trigger`，修掉 4 个已知坑。
   - 备选：插件 B 直接用 Marketplace 的官方 `outlook_trigger`（少维护一个包，但接受它的 4 个坑，见 3.2）。
5. **注意 Cloud 的配额**：触发器事件和 AI 调用都计费/限量（见第 5 节）。学生可申请 **Dify for Education：免费 Yearly Professional**（20,000 trigger events/月），AI 用**自己的模型 API Key**（如 DeepSeek）绕开 200 一次性 AI credits 的限制。

---

## 1. 网页版 Dify 的关键事实（直接影响设计）

| 事实 | 出处 | 影响 |
|---|---|---|
| 安装来源：Marketplace / **GitHub（公开仓库 URL + 版本）** / **本地 `.difypkg`** | Cloud 文档 "Install Integrations" | 自研插件不用上架 Marketplace；GitHub Release 即可分发 |
| GitHub 安装时 `manifest.yaml` 的 `author` 必须等于仓库 owner | 插件发布文档 | 命名/仓库归属要提前定 |
| Cloud 触发器回调是公网地址（Dify 托管） | Cloud Trigger 文档 | 事件驱动无需用户自建 Tunnel |
| 一个工作流可挂多个 Integration Trigger；共享下游节点时用 Variable Aggregator 汇合 | Cloud Integration Trigger 文档 | "两个触发器 + 一个工作流"官方支持 |
| Sandbox：**200 AI credits、5 Apps、3,000 Trigger Events**、30 天日志 | Cloud 定价页 | 只适合试用；长期跑要升级 |
| Professional：**5,000 AI credits/月、20,000 Trigger Events/月、50 Apps** | Cloud 定价页 | 事件驱动方案的主推档位 |
| **Dify for Education**：学生可免费用 Yearly Professional；但 AI credits 仍是 200 一次性（用自己模型 Key 即可） | Cloud Billing 文档 | HKUST 学生邮箱可申请，等于 0 成本拿到 20k triggers/月 |
| Cloud 签名由平台集中管理（不像自部署要自签） | 签名文档 | GitHub 安装不必自己签名（以 Cloud 实际行为为准，P0 验证） |

**配额换算（事件驱动方案）**：
- 每收到 1 封 Inbox 邮件 = 1 次 Trigger Event；若每天 50 封 → 1,500 次/月（< 20,000）；
- 每轮工作流通常 1 次 LLM 调用（候选 1–3 封并批）；50 封/天 → 约 1,500 次 LLM/月 → 用**自己的 DeepSeek Key**（成本约几元/月），不消耗 Dify AI credits；
- 兜底 Schedule Trigger 建议 **每天 1–2 次**（不是每 5 分钟！），只占 30–60 次/月，用来补分类、重试失败、处理漏掉的事件；
- 结论：**Education Professional + 自有模型 Key** 是这套方案最经济的组合。

---

## 2. 交付物

| # | 交付物 | 形态 | 用户操作 |
|---|---|---|---|
| 1 | 插件 A `email-manager-tools` | 独立 GitHub 仓库/Release 的 `.difypkg` | 网页版 Dify → Integrations → Install → From GitHub（或上传 `.difypkg`） |
| 2 | 插件 B `email-manager-trigger` | 同上（独立包） | 同上 |
| 3 | 工作流 `email-manager` | DSL `.yml` / `.ifpkg` | Studio → Import DSL |
| 4 | README / 安装向导 | 仓库文档 | 按步骤配置 Entra 应用、环境变量、触发器订阅 |

**为什么拆两个包**：
- trigger 与 tool 是两类 Dify 插件，拆开后各自 `manifest.yaml` / provider 简单、升级互不影响；
- 单个包同时声明 tools+triggers 的组合未经官方文档确认（禁止组合只列了 tools+models、models+endpoints），拆包规避打包风险；
- 用户可以选择只用官方 `outlook_trigger`（备选方案），只装我们一个 tools 包。

---

## 3. 插件规格

### 3.1 插件 A：`email-manager-tools`（必须自研）

**基础**：fork `langgenius/dify-official-plugins` 的 `tools/outlook/`（Apache-2.0，保留 LICENSE 与改动声明），复用其 OAuth/Graph 底座。

| 项 | 内容 |
|---|---|
| 类型 | Tool plugin（`plugins.tools`） |
| OAuth（Dify 托管） | `oauth_schema` + 三个方法；Entra 应用 Web 平台；scope：`offline_access User.Read Mail.ReadWrite Mail.Send` |
| 存储 | `storage.size: 10485760`（状态 + 去重窗口） |
| 工具 | `collect` / `collect_recent` / `apply` / `tag` / `send_report` / `state_get` / `state_lock` / `state_unlock` / `state_advance` / `check` |
| 失败契约 | 业务失败返回 `{success, transient, error}`，不抛异常；写操作不自动重试 |
| 网络声明 | `network.domains: [graph.microsoft.com, login.microsoftonline.com]`（Marketplace 需要，GitHub 安装也建议写） |
| 风险级别 | Medium（写第三方服务、发送邮件、处理个人数据）——README/PRIVACY 要写清边界 |

工具语义与 [PLAN_A_SINGLE_WORKFLOW.md](PLAN_A_SINGLE_WORKFLOW.md) 第 3.3 节完全一致：

- `collect(last_seen, days, max_items≤30, catchup, include_controls)`：只拉邮件头 → 跳过自家报告/`sum` 指令/已分类/ignored → 候选逐封取正文（截断 400+300）→ 同时返回 `controls`（待处理的 `sum` 指令、待补 `Sum` 标签的报告）；
- `collect_recent(days, letters)`：总结报告数据源（**官方插件不返回 categories，所以这一步必须自研**）；
- `apply(verdicts, dry_run)`：非学校跳过；`merge_categories` 只替换自己的标签；S+urgent 打红旗；单封失败不拖垮整批；
- `tag(entryids, names)`：给报告/指令邮件打 `Sum`；
- `send_report(to, subject, html)`：发送 HTML 报告，也用于告警邮件；
- `state_*`：`last_seen / ignored / failed_rounds / lock / paused / last_catchup_date / last_report_at`，workspace 级 KV；
- `advance`：原 `advance_policy` 语义（失败未达 3 轮不推进，连续 3 轮放弃并推进）。

### 3.2 插件 B：`email-manager-trigger`（自研 fork，或直接用官方）

**官方 `langgenius/outlook_trigger` v1.0.3（Marketplace，最低 Dify 1.10）已经可用**，但源码核对出 5 个问题：

| # | 官方行为 | 问题 | fork 修正 |
|---|---|---|---|
| 1 | 订阅 `changeType: created,updated` | 用户读信/我们写分类都会产生 update 通知 → 白白消耗 Trigger Events；极端情况下自触发 | 只订阅 `created` |
| 2 | 事件回调里再 GET 整封邮件，payload 含完整 HTML body | 大邮件（newsletter 正是常见 C 级邮件）撞变量上限、日志膨胀 | 输出瘦身：`email_id/subject/sender/received/categories/flag_status/web_link/body_text(≤1500 字)` |
| 3 | `email_processed_<id>` 永久累积，storage 申报仅 1MB | 约 1 万封后写满 → 触发器失效 | 环形清理（保留最近 7 天/5000 条），申请 10MB |
| 4 | 默认 scope 仅 `Mail.Read + offline_access` | 不能写 categories | 触发包保持只读即可（写操作在插件 A），无需改；但同包 OAuth 配置保留 `Mail.Read` |
| 5 | 触发器与工具分属两个官方包，各需授权 | 用户要授权两次 | 接受（两个包两个授权）；或做"同一 Entra 应用 + 两个 Redirect URI"，减少配置负担 |

**两种选择**：
- **B1（省事）**：直接用 Marketplace 的官方 `outlook_trigger`。缺点 = 上表 5 条，其中 1/3 影响可用性与成本，2 影响大邮件稳定性；但**零维护、Cloud 一键装**。
- **B2（推荐长期）**：fork 成 `email-manager-trigger` 从 GitHub 安装。多维护一个包，换来实时、安静、稳定。

> 如果先做 MVP：用 B1 验证整条链路，同时观察 Trigger Events 消耗与大邮件失败率；确认痛点后再切 B2。

---

## 4. 一个工作流的设计（网页版 Dify 上）

### 4.1 触发器编排

```text
[Integration Trigger: Outlook email_received]  ┐
                                              ├→ [Variable Aggregator: wake] → 公共管道
[Schedule Trigger: 每天 2 次 / 每 6 小时]      ┘
```

- 公共管道**不引用触发器输出变量**（只把触发器当唤醒信号），所以两个触发器可以汇合，且工作流不依赖事件 payload 大小；
- 事件内容（哪封邮件、什么主题）由插件 A 的 `collect` 从邮箱重新读取——比信任事件 payload 更稳（也与原程序"每轮重新扫收件箱"一致）；
- 兜底 Schedule 的频率按配额定：**每天 1–2 次足够**（Cloud 每次触发都算 Trigger Event；不要用 5 分钟轮询）。

### 4.2 公共管道（约 30 个节点）

| 段 | 节点 | 说明 |
|---|---|---|
| 状态与锁 | `state_get` → Code 解析 | `paused=true` 直接结束 |
| | `state_lock(owner={{sys.workflow_run_id}}, ttl=300)` | 抢不到锁 → Output skipped（事件风暴/上一轮未结束时保护） |
| 采集 | `collect` | `catchup = 今天还没补过`；`max_items=30`；返回候选 + 控制邮件 |
| 控制分支 | If `controls.sum_commands` 非空 → `tag` → 报告流程 | 先打 `Sum` 再出报告（原语义） |
| | If `controls.reports` 非空 → `tag` → `advance` | 补报告标签 |
| 无候选 | If candidates 空 → `advance` → 解锁 → Output idle | 一次空跑只花 1 个 Trigger Event |
| 判级 | Code 分批（20+10）→ LLM #1 → Code 校验/兜底 → If 第二批 → LLM #2 → Code | 条数严格对齐、按 `entryid` 对齐、确定性规则、UTC+8 |
| | If 有失败 → Iteration 逐封补判 | 替代原"递归对半拆"（唯一有损点） |
| 写回 | `apply` | 分类 + 红旗；失败返回 failed |
| 推进 | `advance` | 成功→推进；失败未达 3 轮→不推进；3 轮→放弃并推进 |
| 告警 | If 连续错误 / gave_up → `send_report`（告警邮件）→ `state_set(paused)` | 替代原"连续 3 次错误自动暂停" |
| 收尾 | `state_unlock` → Output stats | 所有分支最终都解锁 |

### 4.3 报告分支

`collect_recent(days=SUMMARY_DAYS, letters)` → Code 每 20 封分批 → LLM 一句话要点（提示词移植 `summarizer.build_points_prompt`）→ Code 宽松 JSON 回收 + HTML（移植 `build_html`/`build_subject`，中英标记都保留）→ `send_report` → `tag(report_id, ["Sum"])` → `advance` → Output。

### 4.4 应用环境变量（导入 DSL 后用户填）

`EMAIL / NAME / STUDENT_ID / SCHOOL_DOMAINS / FACULTY / FACULTY_KEYWORDS / COURSES / DORM_KEYWORDS / URGENT_DAYS / CATCHUP_DAYS / SUMMARY_DAYS / BATCH_SIZE(20) / RECIPIENT / LANGUAGE / DRY_RUN / AI_MODEL`。

---

## 5. 网页版 Dify 配额与成本

| 项目 | Sandbox（免费） | Professional | **Education（学生免费 Yearly Pro）** |
|---|---|---|---|
| Apps | 5 | 50 | 50 |
| Trigger Events | 3,000 | 20,000/月 | 20,000/月 |
| AI credits | 200 | 5,000/月 | **200 一次性**（用自己模型 Key 即可） |
| 每个工作流触发器数 | 最多 2 | 不限 | 不限 |
| 日志 | 30 天 | 不限 | 不限 |
| Triggers/工作流 | 2 | 不限 | 不限 |

- 学生资格：Dify 账号使用**学校邮箱**（如 `@connect.ust.hk`）→ Settings > Billing > Get Education Verified → 用教育折扣订阅 Yearly Professional（免费）。
- AI 成本：在 Dify 里接入自己的 DeepSeek/OpenAI 兼容 Key（Model Provider），LLM 节点用它；Dify 的 AI credits 不消耗。
- Trigger Events 才是主成本：事件驱动 + 每天 1–2 次兜底 = 每月约 1.6k–3k 次（按 50 封/天），**Education Pro 的 20k/月足够**；Sandbox 的 3,000 只够试用。
- 如果坚持"5 分钟轮询"：288 次/天 × 30 = 8,640 次/月，Sandbox 直接超，Pro 也要占掉一小半——**不推荐**，事件驱动更省。

---

## 6. 用户安装流程（README 要写的 6 步）

1. **准备 Dify**：用学校邮箱注册 cloud.dify.ai → 申请 Education 折扣 → 接入自己的模型 Key（DeepSeek 等）；
2. **建 Entra 应用**（一次性，约 3 分钟）：Web 平台；两个 Redirect URI（插件 A / 插件 B 的配置页各给一个）；委托权限 `Mail.ReadWrite / Mail.Send / offline_access / User.Read`；创建 client secret；
3. **装两个插件**：Integrations → Install → GitHub → 填两个仓库 URL（或分别上传 `.difypkg`）→ 同意权限；
4. **授权**：插件 A 配置页填 Tenant/Client ID/Secret → Save and Authorize；插件 B 同样填（可复用同一个 Entra 应用）；
5. **导入工作流**：Studio → Import DSL → 选 `email-manager.yml`；按第 4.4 节填环境变量；
6. **发布并打开触发器**：发布工作流 → Access Point 里打开两个 Trigger（Outlook 订阅 + Schedule）→ 发一封测试邮件或点 Test Run 验证日志。

升级：插件在 Dify 里点升级（GitHub 安装会读 Release 的最新版本）；工作流重新导入 DSL（import 会替换 draft）。

---

## 7. P0 验证清单（网页版 Dify 上，半天）

| # | 验证 | 通过标准 | 失败退路 |
|---|---|---|---|
| 1 | Cloud 上从 GitHub 安装两个自研插件 | 安装成功、工具/触发器节点出现 | 改 Marketplace（需审核）或本地 `.difypkg` |
| 2 | 两个插件各自 OAuth 授权（同一 Entra 应用 + 两个 Redirect URI） | 都能授权成功 | 两个独立 Entra 应用 |
| 3 | 触发器在 Cloud 自动创建 Graph 订阅 | Access Point 显示订阅、测试邮件能触发 | 用官方 `outlook_trigger`；或改 Schedule-only |
| 4 | 双触发器汇入同一管道（Variable Aggregator） | 工作流可保存/发布/运行 | 单触发器：只保留 Schedule 或只保留事件 |
| 5 | 事件 payload 瘦身后不超限、大 HTML 邮件可处理 | 500KB 邮件也不报变量错误 | 事件只输出 id |
| 6 | `apply` 在 Cloud 上能 PATCH categories（OAuth scope 正确） | 邮箱里出现 S/A/B/C 标签 | 检查 Entra 权限是否被管理员限制 |
| 7 | 配额观察 | 跑 1 天统计 Trigger Events / LLM 调用次数 | 调低兜底频率、缩小订阅范围 |

---

## 8. 风险清单（网页版 Dify 版）

| 风险 | 影响 | 缓解 |
|---|---|---|
| Cloud 插件安装策略变化（GitHub/本地被收紧） | 装不上 | 备用 Marketplace 上架；或自部署 |
| 学校租户 Entra 应用注册/同意限制 | 授权失败 | 只读自检 + 提示管理员；文档写清 |
| Trigger Events 超配额 | 触发器停摆 | 事件驱动为主 + 兜底每天 1–2 次；监控用量 |
| AI credits 用完（若不用自有 Key） | LLM 节点失败 | 接自有模型 Key；Education 版必须自有 Key |
| 大邮件 body 变量超限 | 个别邮件处理失败 | 插件 A collect 只在需要时取正文并截断；插件 B 瘦身 payload |
| 两套授权 + 两个插件 | 安装步骤变多 | README 步骤化；P0 验证同 Entra 应用两 Redirect URI |
| Cloud 日志保存邮件正文 | 隐私 | 30 天/不限按套餐；README 隐私说明；不分享日志 |
| Cloud 版本升级行为变化 | DSL/触发异常 | 宣告支持版本区间；插件锁 `minimum_dify_version`；保留 Golden Set |

---

## 9. 实施计划

| 阶段 | 内容 | 工作量 |
|---|---|---|
| P0 | 第 7 节 7 条验证（Cloud 装两个最小插件、授权、订阅、双触发器、PATCH 分类） | 0.5d |
| P1 | 插件 A（fork 官方 outlook + collect/apply/state/report 工具） | 2–2.5d |
| P2 | 插件 B（fork 官方 trigger：created/瘦身/清理；或先用官方 trigger） | 0.5–1d |
| P3 | 一个工作流 DSL（双触发器 + 管道 + 报告 + 告警） | 1.5–2d |
| P4 | Golden Set 对照 + 写回/故障注入 + README 安装向导 | 1–1.5d |
| 合计 | | **5–7d** |

---

## 10. 待确认问题

1. 确认是 **cloud.dify.ai（网页版）**、不是自部署的 Web UI？是否已申请 **Education 折扣**（20k triggers/月）？
2. **插件 B 选 B1（直接用官方 outlook_trigger，少一个自研包）还是 B2（fork，实时且安静）**？
3. 是否接受"每个用户自己建一个 Entra 应用并授权两次"作为安装步骤？（也可以后续做设备码方案，免 Entra 应用，但首版复杂）
4. 兜底 Schedule 用**每天 1 次**还是**每 6 小时一次**？（只影响漏事件时的补齐延迟，不影响实时性）
5. 用户量级：只有你自己用，还是要分发给其他同学？（决定是否需要 Marketplace 上架与更严格的隐私/权限说明）
