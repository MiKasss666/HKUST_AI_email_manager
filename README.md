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

> **Language policy**: all user-facing docs and release notes are bilingual — English first, Chinese second.

**GitHub**: <https://github.com/MiKasss666/HKUST_AI_email_manager>
**Download (Release)**: <https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest>

**For prototype reviewers** → **[docs/DEMO.md](docs/DEMO.md)**: guided walkthrough, workflow flow,
example input → expected category table, reproduce steps and known limitations.

---

## Download & install

**Option A — release files (recommended)**

1. Open [Releases](https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest) and download:
   - `email_manager.difypkg` (Dify plugin)
   - `HKUST_AI_email_manager.yml` (workflow DSL)
2. Dify → Integrations → Install → **Local Package File** → pick `email_manager.difypkg`;
3. Studio → Import DSL → pick `HKUST_AI_email_manager.yml`;
4. Fill the 2 environment variables below → **Publish**.

**Option B — install the plugin directly from GitHub**

- Plugin source: this repository (manifest.yaml at the repo root)
- Dify → Integrations → Install → **From GitHub** → paste `MiKasss666/HKUST_AI_email_manager`
- The workflow still comes from this repository's Release (`HKUST_AI_email_manager.yml`).

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

#### Recommended: fill in as much as you can

The more context you give, the more accurate S/A/B/C classification and reports become.
These variables are optional but strongly recommended — edit them once, then Publish:

| Variable | Example | What it improves |
|---|---|---|
| `COURSES` | `COMP 1021, MATH 1014, LANG1416` | any mail mentioning one of your courses is raised to at least **A** |
| `FACULTY` | `School of Science` | faculty/department mail is raised to at least **A** |
| `NAME` | `Fok Pak Kwan` | detects mail that addresses **you** (`点名到我`) |
| `STUDENT_ID` | `12345678` | same, by student id |
| `DORM_KEYWORDS` | `UG Hall, 宿舍, Residence` | dorm/hall-related mail is raised to at least **A** |
| `SCHOOL_DOMAINS` | `ust.hk` | sender-domain match counts as school mail |
| `LANGUAGE` | `zh` or `en` | report language |
| `URGENT_DAYS` | `14` | S-level "urgent" red-flag window (days) |
| `SUMMARY_DAYS` | `7` | report window for `sum` / weekly report (days) |
| `REPORT_MAX` | `50` | max mails listed in one report (effective max: 100) |
| `CATCHUP_DAYS` | `7` | how far back the daily catch-up scan looks |
| `LETTERS` | `sabc` | default levels for manual/`sum` reports (`s` = S only, `sa` = S+A …) |

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
One report lists at most `REPORT_MAX` classified mails (default 50, effective max 100) — raise it
if your windows hold more. A 7-day and a 30-day report can show the same count when all classified
mail falls inside the shorter window (or when both hit the cap).

### Summary by e-mail — the `sum` command

The easiest way to get a report on demand: **send an e-mail to your own school mailbox** with the
command as the subject. The next scheduled round (≤5 minutes) handles it:

| Subject | Report content |
|---|---|
| `sum` | all levels (`LETTERS=sabc` by default) |
| `sum sa` | only S and A |
| `sum sabc` | explicit all levels |
| `sum b` | only B |

Rules:

1. The subject must be **exactly** `sum` or `sum <levels>` (levels are any combination of `s/a/b/c`,
   case-insensitive). Extra words — e.g. `Please send sum sa` — are treated as a normal mail and ignored;
2. `FORCE_ACTION` must be `auto` (not a forced action);
3. The next round: tags that command mail with **`Sum`**, then builds an HTML report from mails
   classified within `SUMMARY_DAYS` (default 7) and sends it to `RECIPIENT`;
4. The report mail itself gets its `Sum` label on the **following** round (so it is never reported twice);
5. If there is no classified mail inside the window yet, no report is sent — run a classification round first.

Also possible without e-mail: set `FORCE_ACTION=sum` → Publish → Test Run, and pick levels with `LETTERS`.

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

> **Note**: `workflows/HKUST_AI_email_manager.yml` is now a Dify **0.7.0** exported DSL with a tidy
> node layout. If you edit the graph, do it in Dify and export/replace the file — running
> `gen_workflows.py` would overwrite the layout with the generator's default positions.

```powershell
# generate tools + the single workflow DSL
py -3 scripts/gen_tools.py
py -3 scripts/gen_workflows.py

# validation + smoke tests
py -3 scripts/validate_dsl.py
py -3 scripts/smoke_code_nodes.py
py -3 scripts/smoke_pipeline.py
py -3 -m unittest discover -s tests

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

**给原型评审者** → **[docs/DEMO.md](docs/DEMO.md)**：演示流程、示例输入 → 预期分类表、复现步骤、已知限制。

---

## 下载与安装

**方式 A —— 用 Release 文件（推荐）**

1. 打开 [Releases](https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest)，下载两个文件：
   - `email_manager.difypkg`（插件包）
   - `HKUST_AI_email_manager.yml`（工作流 DSL）
2. Dify → Integrations → Install → **Local Package File** → 选 `email_manager.difypkg`；
3. Studio → Import DSL → 选 `HKUST_AI_email_manager.yml`；
4. 按下面的「环境变量」填 2 个值 → Publish。

**方式 B —— 直接从 GitHub 安装插件**

- 插件源码：本仓库根目录（`manifest.yaml` 在仓库根目录）
- Dify → Integrations → Install → **From GitHub** → 填 `MiKasss666/HKUST_AI_email_manager`
- 工作流仍然从本仓库的 Release 下载（`HKUST_AI_email_manager.yml`）。

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

#### 建议：尽量填全这些信息

你填的信息越多，S/A/B/C 判级和报告越准。以下都是可选项，但强烈建议填一次后 Publish：

| 变量 | 示例 | 作用 |
|---|---|---|
| `COURSES` | `COMP 1021, MATH 1014, LANG1416` | 邮件提到你上的课 → 至少升到 **A** |
| `FACULTY` | `School of Science` | 学院/系相关邮件 → 至少升到 **A** |
| `NAME` | `Fok Pak Kwan` | 识别"点名到我"的邮件 |
| `STUDENT_ID` | `12345678` | 同上，按学号识别 |
| `DORM_KEYWORDS` | `UG Hall, 宿舍, Residence` | 宿舍/书院相关邮件 → 至少升到 **A** |
| `SCHOOL_DOMAINS` | `ust.hk` | 发件域名命中即算学校邮件 |
| `LANGUAGE` | `zh` 或 `en` | 报告语言 |
| `URGENT_DAYS` | `14` | S 级"加急"红旗的截止窗口（天） |
| `SUMMARY_DAYS` | `7` | `sum`/周报的报告窗口（天） |
| `REPORT_MAX` | `50` | 单份报告最多列出的邮件数（有效上限 100） |
| `CATCHUP_DAYS` | `7` | 每天补扫回看的天数 |
| `LETTERS` | `sabc` | 手动/`sum` 报告的默认级别（`s`=只 S，`sa`=S+A…） |

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
每份报告最多列出 `REPORT_MAX` 封已分类邮件（默认 50，有效上限 100）——邮件多时调大即可。
7 天报告和 30 天报告数量相同，通常是因为已分类邮件都在 7 天内，或两者都达到了上限。

### 用邮件触发总结 —— `sum` 指令

最方便的出报告方式：**给自己的学校邮箱发一封邮件**，主题写指令，下一轮（≤5 分钟）就会处理：

| 主题 | 报告内容 |
|---|---|
| `sum` | 全部级别（默认 `LETTERS=sabc`） |
| `sum sa` | 只要 S 和 A |
| `sum sabc` | 明确全部级别 |
| `sum b` | 只要 B |

规则：

1. 主题必须**正好**是 `sum` 或 `sum <级别>`（级别是 `s/a/b/c` 的任意组合，大小写不限）。
   多写别的字（如 `请帮我 sum sa`）会被当成普通邮件，不会触发；
2. `FORCE_ACTION` 必须是 `auto`（不能是强制动作）；
3. 下一轮会：先给这封指令邮件打 **`Sum`** 标签，再从 `SUMMARY_DAYS`（默认 7 天）内已分类的邮件
   生成 HTML 报告，发到 `RECIPIENT`；
4. 报告邮件本身会在**再下一轮**被打上 `Sum` 标签（所以不会被重复总结）；
5. 如果窗口内还没有已分类邮件，不会发报告——先让分类跑一轮。

不想发邮件时也可以用：`FORCE_ACTION=sum` → Publish → Test Run，级别由 `LETTERS` 决定。

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

> **注意**：`workflows/HKUST_AI_email_manager.yml` 现在是 Dify **0.7.0** 导出的 DSL，节点排版已整理。
> 以后改节点请在 Dify 里改完再导出替换该文件；直接跑 `gen_workflows.py` 会用生成器的默认坐标覆盖排版。

```powershell
# 生成工具 + 唯一的单工作流 DSL
py -3 scripts/gen_tools.py
py -3 scripts/gen_workflows.py

# 校验 + 冒烟
py -3 scripts/validate_dsl.py
py -3 scripts/smoke_code_nodes.py
py -3 scripts/smoke_pipeline.py
py -3 -m unittest discover -s tests

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
