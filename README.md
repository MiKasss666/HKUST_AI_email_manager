# HKUST_AI_email_manager

> **English** | [中文版](#中文版)

A Dify port of the original Windows desktop app `Email_manager_beta` v3.0.0 (Microsoft Graph):
**one plugin (Email Manager) + one workflow (HKUST_AI_email_manager)**.

The workflow signs in with a Microsoft device code, classifies school mail into S/A/B/C,
writes the categories back to Outlook, and sends daily / weekly / on-demand `sum` HTML reports.

> **Status**: v1.0 — verified on Dify Cloud (sign-in, classification, write-back, reports).
> - Plugin **0.1.4**, workflow **86 nodes / 90 edges**, a single Schedule Trigger;
> - Offline checks: DSL validation, all Code nodes smoke-tested, pipeline sample, 29 unit tests;
> - A new user only fills **2 environment variables** (`EMAIL`, `RECIPIENT`); sign-in happens automatically through Dify e-mail.

**GitHub**: <https://github.com/MiKasss666/HKUST_AI_email_manager>
**Download (Release)**: <https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest>

---

## Download & install (recommended)

1. Open [Releases](https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest) and download:
   - `email_manager.difypkg` (Dify plugin)
   - `HKUST_AI_email_manager.yml` (workflow DSL)
2. Dify → Integrations → Install → **Local Package File** → pick `email_manager.difypkg`;
3. Studio → Import DSL → pick `HKUST_AI_email_manager.yml`;
4. Fill the 2 environment variables below → **Publish**.

Full new-user walkthrough: **[docs/DISTRIBUTE.md](docs/DISTRIBUTE.md)**.

---

## Quick start

### 1. Install the plugin

Dify → Integrations → Install → **Local Package File** → `email_manager.difypkg`.
Open `Email Manager` afterwards — it should list **15 tools**.

### 2. Import the workflow

Studio → Import DSL → **`workflows/HKUST_AI_email_manager.yml`**.

Small fix-ups after import (generated draft, ~2 minutes):

- Tool nodes with a red border: re-select the same tool under `Email Manager`;
- The two LLM nodes (`Classify mail`, `Write one-liners`): pick a model of your workspace (e.g. `gpt-5.6-luna`).

### 3. Environment variables (only 2 need editing)

Settings → Environment Variables:

| Variable | Value |
|---|---|
| `EMAIL` | your school e-mail |
| `RECIPIENT` | where reports go (usually the same address) |

Everything else is pre-filled:

| Variable | Default | Meaning |
|---|---|---|
| `SCHOOL_DOMAINS` | `ust.hk` | matches school mail |
| `LANGUAGE` | `zh` | set `en` for English reports |
| `URGENT_DAYS` / `SUMMARY_DAYS` / `CATCHUP_DAYS` | `14` / `7` / `7` | urgent window / report window / daily catch-up window |
| `DRY_RUN` | `true` | keep `true` at first: classify only, no write-back |
| `LETTERS` | `sabc` | default levels for manual reports |
| `FORCE_ACTION` | `auto` | automatic mode; can force an action for testing |
| `TENANT` / `CLIENT_ID` | `common` / empty | device-code tenant / optional own Entra client id |

Click **Publish** afterwards — environment variable changes only apply when published.

### 4. Sign in (automatic)

1. Open **Access Point** and enable the **Schedule Trigger** (every 5 minutes);
2. The first unsigned run e-mails a sign-in message to your **Dify account e-mail**
   (device code + Microsoft link + form link);
3. Authorize in the browser → open the form link → click **I have completed the sign-in**;
4. The run resumes → `Poll sign-in` → `signed_in=true`; the next round starts classifying.

### 5. Go automatic

`FORCE_ACTION=auto`, `DRY_RUN=false` → Publish → enable the Schedule Trigger.

---

## What the workflow does

### Every 5 minutes

1. Read `FORCE_ACTION` (`auto` in normal mode);
2. Not signed in → run the sign-in e-mail flow;
3. Signed in → `state_get` → pause check → acquire lock → `collect` (headers only) →
   classify (≤20 mails per round, a single LLM call) → strict validation → write-back
   (only replaces its own S/A/B/C categories, keeps your labels) → advance baseline → unlock;
4. On failure the baseline is not advanced; after 3 consecutive failed rounds it gives up and moves on.

### Scheduled reports (automatic)

| Time | Content |
|---|---|
| Every day **00:00–00:09** (first round) | Daily report: classified mail from the last day |
| **Sunday 00:00–00:09** | Weekly report: `SUMMARY_DAYS` days (default 7); no extra daily report that day |

The send date is recorded, so **nothing is sent twice on the same day**.

### `FORCE_ACTION` manual actions

| Value | Effect |
|---|---|
| `auto` | automatic mode (default) |
| `login` | force a fresh device code; END outputs `user_code` / `verification_uri` |
| `login_poll` | poll sign-in; `signed_in=true` means success |
| `report_daily` | send a daily report now (testing) |
| `report_weekly` | send a weekly report now (testing) |
| `sum` | send a manual summary now (levels from `LETTERS`) |
| `check` | self-check: sign-in / account / inbox count |
| `resume` | clear an automatic pause |
| `reset` | clear baseline, failed rounds, ignored list, report marks (test reset) |
| `logout` | forget the Microsoft credential (token + pending device code) |

---

## Known limitations

1. **Fix-ups after import**: tool nodes depend on the installed plugin id, so they may need re-selecting; LLM nodes need a model.
2. **Dify environment variable types** are `string` / `number` / `secret` only (a boolean causes a draft 400).
3. **Code nodes must define `def main(...)`** and their return keys must match the declared outputs exactly (the generators validate this).
4. **Re-installing the plugin clears the Microsoft token**, so you have to sign in again.
5. At most 2 triggers per workflow on Dify Cloud Sandbox; this version uses a single Schedule trigger.
6. Real-time "new mail" triggers (Graph change subscriptions) are not implemented; the workflow polls every 5 minutes.

---

## Development

```powershell
# generate tools + the single workflow DSL
py -3 scripts/gen_tools.py
py -3 scripts/gen_workflows.py

# validation + smoke tests
py -3 scripts/validate_dsl.py
py -3 scripts/smoke_code_nodes.py
py -3 scripts/smoke_pipeline.py
py -3 -m unittest discover -s plugin/email_manager/tests

# package the plugin
py -3 scripts/package_plugin.py

# testing helper: clear project labels (S/A/B/C/Sum) on the newest N mails
py -3 scripts/reset_categories.py --limit 30 --dry-run
py -3 scripts/reset_categories.py --limit 30
py -3 scripts/reset_categories.py --all --limit 50
py -3 scripts/reset_categories.py --sign-out
```

---

## Privacy & security

- The plugin only accesses the signed-in user's own mailbox; the token lives in the plugin storage of each Dify workspace;
- Mail bodies are only sent to **the model service you configure in Dify**;
- Do not publish tokens, token caches, or screenshots containing mailbox content;
- Device-code sign-in uses Microsoft's well-known public clients (same as the original desktop app) and needs no admin consent.

More:

- [Distribution guide for classmates](docs/DISTRIBUTE.md)
- [Migration advice](docs/DIFY_MIGRATION_ADVICE.md)
- [Single-workflow design](docs/PLAN_A_SINGLE_WORKFLOW.md)
- [Dify Cloud + device code + distribution design](docs/PLAN_A_CLOUD_DEVICECODE_SHARE.md)

---

# 中文版

> [English](#hkust_ai_email_manager) | **中文**

把原来的 Windows 桌面程序 `Email_manager_beta` v3.0.0（Microsoft Graph 版）搬进 **Dify 网页版**：
**一个插件（Email Manager）+ 一个工作流（HKUST_AI_email_manager）**。

工作流自动完成：设备码登录 → 学校邮件判级（S/A/B/C）→ 写回 Outlook 分类 → 日报/周报 → `sum` 指令报告。

> **状态**：v1.0（已在 Dify Cloud 上跑通：登录、判级、写回、报告）。
> - 插件 **0.1.4**，工作流 **86 节点 / 90 边**，只有一个 Schedule Trigger；
> - 离线检查：DSL 结构校验、全部 Code 节点冒烟、核心流水线样例、29 项单测；
> - 新用户只需要改 **2 个环境变量**（`EMAIL`、`RECIPIENT`），登录会通过 Dify 邮件自动完成。

**GitHub**：<https://github.com/MiKasss666/HKUST_AI_email_manager>
**下载（Release）**：<https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest>

---

## 下载与安装（推荐方式）

1. 打开 [Releases](https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest)，下载两个文件：
   - `email_manager.difypkg`（插件包）
   - `HKUST_AI_email_manager.yml`（工作流 DSL）
2. Dify → Integrations → Install → **Local Package File** → 选 `email_manager.difypkg`；
3. Studio → Import DSL → 选 `HKUST_AI_email_manager.yml`；
4. 按下面的「环境变量」填 2 个值 → Publish。

完整的新用户步骤见 **[docs/DISTRIBUTE.md](docs/DISTRIBUTE.md)**。

---

## 快速开始

### 1. 装插件

Dify → Integrations → Install → **Local Package File** → 选 `build/email_manager.difypkg`。
装好后点开 `Email Manager`，应有 **15 个工具**。

### 2. 导入工作流

Studio → Import DSL → 选 **`workflows/HKUST_AI_email_manager.yml`**。

导入后的 fix-up（生成草稿，约 2 分钟）：

- 红框的 Tool 节点：重新选 `Email Manager` 下同名工具；
- 两个 LLM 节点（`Classify mail`、`Write one-liners`）：选你工作区的模型（如 `gpt-5.6-luna`）。

### 3. 环境变量（只改 2 个）

Settings → Environment Variables：

| 变量 | 填什么 |
|---|---|
| `EMAIL` | 你的学校邮箱 |
| `RECIPIENT` | 收报告的邮箱（通常同上） |

其余已预填：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SCHOOL_DOMAINS` | `ust.hk` | 命中即算学校邮件 |
| `LANGUAGE` | `zh` | `en` 则报告用英文 |
| `URGENT_DAYS` / `SUMMARY_DAYS` / `CATCHUP_DAYS` | `14` / `7` / `7` | 加急阈值 / 报告窗口 / 每日补扫窗口 |
| `DRY_RUN` | `true` | 首次建议 true，只判定不写回 |
| `LETTERS` | `sabc` | 手动总结默认级别 |
| `FORCE_ACTION` | `auto` | 自动模式；测试时可强制动作（见下表） |
| `TENANT` / `CLIENT_ID` | `common` / 空 | 设备码登录租户 / 可选自有客户端 |

改完 **Publish**（环境变量必须发布才生效）。

### 4. 登录（自动）

1. Access Point 打开 **Schedule Trigger**（每 5 分钟）；
2. 第一轮发现未登录 → 工作流给 **Dify 账号邮箱**发登录邮件（设备码 + 微软授权链接 + 表单链接）；
3. 浏览器授权 → 打开邮件里的表单 → 点 **I have completed the sign-in**；
4. 运行恢复 → `Poll sign-in` → `signed_in=true`，下一轮开始正常分类。

### 5. 开自动

`FORCE_ACTION=auto`、`DRY_RUN=false` → Publish → 打开 Schedule Trigger。

---

## 工作流行为

### 每 5 分钟

1. 读 `FORCE_ACTION`（自动模式为 `auto`）；
2. 未登录 → 走登录邮件流程；
3. 已登录 → `state_get` → 暂停检查 → 抢锁 → `collect`（只拉邮件头）→ 判级（每轮 ≤20 封，单次 LLM）→ 严格校验 → 写回（只替换自己的 S/A/B/C 标签、保留用户标签）→ 推进基线 → 解锁；
4. 失败不推进基线，连续 3 轮失败后放弃并继续。

### 定时报告（自动）

| 时间 | 内容 |
|---|---|
| 每天 **00:00–00:09** 第一轮 | 日报：最近 1 天已分类邮件 |
| **周日 00:00–00:09** | 周报：`SUMMARY_DAYS` 天（默认 7 天）；当天不再另发日报 |

发送后记录日期，**同一天不重复发**。

### `FORCE_ACTION` 手动动作

| 值 | 作用 |
|---|---|
| `auto` | 自动模式（默认） |
| `login` | 强制生成新设备码，END 输出 `user_code` / `verification_uri` |
| `login_poll` | 轮询登录结果，`signed_in=true` 即成功 |
| `report_daily` | 立即发日报（测试用） |
| `report_weekly` | 立即发周报（测试用） |
| `sum` | 立即发手动总结（级别取 `LETTERS`） |
| `check` | 自检登录/账号/收件箱 |
| `resume` | 解除自动暂停 |
| `reset` | 清空基线、失败计数、忽略列表、日报/周报标记（测试初始化） |
| `logout` | 退出 Microsoft 登录（清 token + 待用设备码） |

---

## 已知限制

1. **导入后 fix-up**：Tool 节点 `provider_id` 依赖安装后的插件 id，可能需要重新选一次；LLM 节点要选模型。
2. **Dify 环境变量类型**只能是 `string` / `number` / `secret`（boolean 会导致 draft 400）。
3. **Code 节点必须 `def main(...)`**，返回字段必须与声明的输出参数完全一致（生成器已内置校验）。
4. **重装插件会清掉 Microsoft token**，需要重新走一次登录。
5. 每工作流最多 2 个 Trigger（Cloud Sandbox）；本版本只用 1 个 Schedule。
6. 实时"新邮件触发"（Graph 变更订阅）未实现，当前靠 5 分钟轮询。

---

## 开发

```powershell
# 生成工具 + 唯一的单工作流 DSL
py -3 scripts/gen_tools.py
py -3 scripts/gen_workflows.py

# 校验 + 冒烟
py -3 scripts/validate_dsl.py
py -3 scripts/smoke_code_nodes.py
py -3 scripts/smoke_pipeline.py
py -3 -m unittest discover -s plugin/email_manager/tests

# 打包插件
py -3 scripts/package_plugin.py

# 测试用：清除最近 N 封邮件的项目标签（S/A/B/C/Sum）
py -3 scripts/reset_categories.py --limit 30 --dry-run
py -3 scripts/reset_categories.py --limit 30
py -3 scripts/reset_categories.py --all --limit 50
py -3 scripts/reset_categories.py --sign-out
```

---

## 隐私与安全

- 插件只访问登录者本人邮箱；token 存在各自 Dify 工作区的插件存储里；
- 邮件正文只发给**你在 Dify 里配置的模型服务**；
- 不要把 token、token 缓存、含邮箱内容的截图发到公开仓库；
- 设备码登录使用微软公开客户端（与原桌面程序一致），不需要管理员许可。

背景与方案：

- [分发给同学：新用户使用流程](docs/DISTRIBUTE.md)
- [迁移建议书](docs/DIFY_MIGRATION_ADVICE.md)
- [方案 A 单工作流设计](docs/PLAN_A_SINGLE_WORKFLOW.md)
- [网页版 Dify + 设备码 + 分发设计](docs/PLAN_A_CLOUD_DEVICECODE_SHARE.md)
