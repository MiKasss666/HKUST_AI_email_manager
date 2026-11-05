# Distribution guide — new user walkthrough

> English | [中文版](#中文版)

This project = **1 Dify plugin + 1 workflow DSL**. Every user installs the plugin and imports the workflow
in their **own** Dify workspace; afterwards their school mailbox is organized every 5 minutes.

> Prerequisite: a Dify Cloud account (register with your school e-mail). The workspace must belong to you —
> never share someone else's app link as a shared entry point.

---

## 0. Prepare (once, ~10 minutes)

| Need | Notes |
|---|---|
| Dify Cloud account | Register with your school e-mail; apply for the **Education discount** under Settings → Billing (free Yearly Pro, 20,000 Trigger Events/month) |
| AI model | The school's OpenAI-compatible API (base URL + key + model name); add it under **Integrations → Model Provider** |
| Plugin package | `email_manager.difypkg` from [Releases](https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest) |
| DSL file | `HKUST_AI_email_manager.yml` from the same Release |

---

## 1. Install the plugin

**Option A (recommended)**: download `email_manager.difypkg` from
[Releases](https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest), then
Integrations → Install → Local Package File.

**Option B**: Integrations → Install → **From GitHub** → paste `MiKasss666/HKUST_AI_email_manager`
(the plugin source lives at this repository's root).

After installing, open `Email Manager` — it should list **15 tools**.

---

## 2. Import the workflow

Studio → **Import DSL** → `HKUST_AI_email_manager.yml`.

Fix-ups after import (~2 minutes):

1. Tool nodes with a red border: open them → pick provider `Email Manager` → re-select the same tool;
2. The two LLM nodes (`Classify mail`, `Write one-liners`): pick a model of your workspace (e.g. `gpt-5.6-luna`);
3. If Publish complains about multiple End nodes, send the error to the maintainer.

---

## 3. Environment variables

Settings → Environment Variables — **only 2 need editing**:

| Variable | Value |
|---|---|
| `EMAIL` | your school e-mail |
| `RECIPIENT` | where reports go (usually the same address) |

Everything else is pre-filled: `SCHOOL_DOMAINS=ust.hk`, `LANGUAGE=zh`, `URGENT_DAYS=14`, `SUMMARY_DAYS=7`,
`CATCHUP_DAYS=7`, `LETTERS=sabc`, `DRY_RUN=true`, `TENANT=common`, `FORCE_ACTION=auto`.

Optional but strongly recommended — fill in as much as you can, it makes classification much better:

| Variable | Example | Effect |
|---|---|---|
| `COURSES` | `COMP 1021, MATH 1014, LANG1416` | mail mentioning your courses is raised to at least A |
| `FACULTY` | `School of Science` | faculty/department mail is raised to at least A |
| `NAME` | `Fok Pak Kwan` | detects mail addressed to you |
| `STUDENT_ID` | `12345678` | same, by student id |
| `DORM_KEYWORDS` | `UG Hall, 宿舍, Residence` | dorm-related mail is raised to at least A |
| `LANGUAGE` | `zh` / `en` | report language |
| `SUMMARY_DAYS` | `7` | report window for `sum` / weekly report |
| `URGENT_DAYS` | `14` | S-level urgent red-flag window |
| `CATCHUP_DAYS` | `7` | daily catch-up scan window |
| `LETTERS` | `sabc` | default levels for `sum` reports |

> After editing the variables you **must click Publish**, otherwise nothing changes.

---

## 4. Sign in (automatic)

1. Publish the workflow and open **Access Point** → enable the **Schedule Trigger** (every 5 minutes);
2. The first unsigned run sends a sign-in e-mail to your **Dify account e-mail**
   (device code + Microsoft link + form link);
3. Authorize in the browser (school account, accept the permissions);
4. Open the form link from the e-mail → click **I have completed the sign-in**;
5. The run resumes → `Poll sign-in` → `signed_in=true` (the `account` field is your mailbox).

> If the e-mail never arrives, use the manual fallback: `FORCE_ACTION=login` → Publish → Test Run →
> copy `user_code` / `verification_uri` from the END output, authorize, then `FORCE_ACTION=login_poll`.

---

## 5. First dry run (no write-back)

1. `FORCE_ACTION=reset` → **Publish** → **Test Run** (clears the baseline; `last_seen` becomes empty);
2. `FORCE_ACTION=auto`, `DRY_RUN=true` → **Publish** → **Test Run**;
3. Check TRACING: `COLLECT MAIL` has candidates, `CLASSIFY MAIL` returns output,
   `VALIDATE VERDICTS` has `failed=0`;
4. The mailbox does not change (dry run).

## 6. Real write-back

`DRY_RUN=false` → **Publish** → **Test Run**; Outlook should show S/A/B/C categories (S is flagged red).

## 7. Go automatic

1. `FORCE_ACTION=auto`, `DRY_RUN=false` → **Publish**;
2. **Access Point** → enable the **Schedule Trigger** (runs every 5 minutes).

---

## 8. Daily use

- New inbox mail is classified and labelled every 5 minutes;
- **Every day at 00:00** a daily report is sent (classified mail of the last day);
  **every Sunday at 00:00** a weekly report is sent (`SUMMARY_DAYS` days, default 7);
- **Summary by e-mail (`sum` command)** — the easiest way to get a report on demand:
  send an e-mail **to your own school mailbox** with the subject

  | Subject | Report |
  |---|---|
  | `sum` | all levels (default `LETTERS=sabc`) |
  | `sum sa` | only S and A |
  | `sum sabc` | explicitly all levels |
  | `sum b` | only B |

  The subject must be **exactly** `sum` or `sum <levels>` (levels: any combination of `s/a/b/c`,
  case-insensitive; extra words are ignored as a normal mail). `FORCE_ACTION` must be `auto`.
  The next round tags that command mail with `Sum`, then mails an HTML report built from mails
  classified within `SUMMARY_DAYS` to `RECIPIENT`. The report mail itself is tagged `Sum` on the
  following round, so it is never reported twice.
- Manual option without e-mail: `FORCE_ACTION=sum` → Publish → Test Run (levels from `LETTERS`).

---

## FAQ

| Symptom | Cause / fix |
|---|---|
| Canvas keeps spinning (`/workflows/draft` 400) | an environment variable used boolean; only string/number/secret are allowed |
| Code node error `'return' outside function` | old DSL; import the latest `HKUST_AI_email_manager.yml` |
| "That code didn't work" on the Microsoft page | the device code was reused/consumed; `FORCE_ACTION=login` forces a new code |
| Browser authorized but `signed_in=false` | poll immediately with `login_poll`; device codes expire |
| `ok=0` and VALIDATE rejects the whole batch | the model did not answer with `ref`; use the latest DSL |
| Report mail has no `Sum` label | it is tagged on the next round; wait 5 minutes or Test Run once |
| Signed out after reinstalling the plugin | Dify cleared the plugin storage; sign in again |
| Want to reprocess recent mail | `FORCE_ACTION=reset`, or run `scripts/reset_categories.py` locally |

---

## Security / quota

- The plugin only accesses the signed-in user's own mailbox; the token lives in each workspace's plugin storage;
- Mail bodies are only sent to **the model service configured in your own Dify workspace**;
- One round every 5 minutes ≈ 288 Trigger Events/day; the Education Pro quota (20,000/month) is enough;
- Never post your app/webhook links, tokens or mailbox screenshots in public chats.

---

# 中文版

> [English](#distribution-guide--new-user-walkthrough) | **中文**

这套东西 = **1 个 Dify 插件 + 1 个工作流 DSL**。每个同学在自己的 Dify 工作区里装一次、导入一次，
之后每 5 分钟自动整理自己的学校邮箱。

> 前提：Dify Cloud 账号（建议用学校邮箱注册），工作区归**自己**所有；不要把别人的 app 链接当共享入口。

---

## 0. 准备（一次性，约 10 分钟）

| 需要 | 说明 |
|---|---|
| Dify Cloud 账号 | 用学校邮箱注册，Settings → Billing 里申请 **Education 折扣**（免费 Yearly Pro，20,000 Trigger Events/月） |
| AI 模型 | 学校提供的 OpenAI 兼容 API（地址 + Key + 模型名）。在 **Integrations → Model Provider** 里添加 |
| 插件包 | 从 [Releases](https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest) 下载 `email_manager.difypkg` |
| DSL 文件 | 从同一个 Release 下载 `HKUST_AI_email_manager.yml` |

---

## 1. 安装插件

**方式 A（推荐）**：从 [Releases](https://github.com/MiKasss666/HKUST_AI_email_manager/releases/latest) 下载 `email_manager.difypkg`，
Integrations → Install → Local Package File → 选它。

**方式 B**：Integrations → Install → **From GitHub** → 填 `MiKasss666/HKUST_AI_email_manager`
（插件源码就在本仓库根目录）。

装好后点开 `Email Manager`，应该看到 **15 个工具**。

---

## 2. 导入工作流

Studio → **Import DSL** → 选 `HKUST_AI_email_manager.yml`。

导入后需要 fix-up（生成草稿，约 2 分钟）：

1. 有红框的 **Tool 节点**：点开 → Provider 选 `Email Manager` → 重新选同名工具；
2. 两个 **LLM 节点**（`Classify mail`、`Write one-liners`）：模型选你工作区里的模型（如 `gpt-5.6-luna`）；
3. 如果 Publish 时提示多 End 节点问题，把报错发给维护者。

---

## 3. 填环境变量

Settings → Environment Variables，**只需要改 2 个**：

| 变量 | 填什么 |
|---|---|
| `EMAIL` | 你的学校邮箱 |
| `RECIPIENT` | 收报告的邮箱（通常同上） |

其余已预填：`SCHOOL_DOMAINS=ust.hk`、`LANGUAGE=zh`、`URGENT_DAYS=14`、`SUMMARY_DAYS=7`、
`CATCHUP_DAYS=7`、`LETTERS=sabc`、`DRY_RUN=true`、`TENANT=common`、`FORCE_ACTION=auto`。

可选但强烈建议尽量填全，判级会准很多：

| 变量 | 示例 | 作用 |
|---|---|---|
| `COURSES` | `COMP 1021, MATH 1014, LANG1416` | 提到你上的课 → 至少升到 A |
| `FACULTY` | `School of Science` | 学院/系相关 → 至少升到 A |
| `NAME` | `Fok Pak Kwan` | 识别点名到你的邮件 |
| `STUDENT_ID` | `12345678` | 同上，按学号 |
| `DORM_KEYWORDS` | `UG Hall, 宿舍, Residence` | 宿舍相关 → 至少升到 A |
| `LANGUAGE` | `zh` / `en` | 报告语言 |
| `SUMMARY_DAYS` | `7` | `sum`/周报的报告窗口 |
| `URGENT_DAYS` | `14` | S 级加急红旗窗口 |
| `CATCHUP_DAYS` | `7` | 每日补扫窗口 |
| `LETTERS` | `sabc` | `sum` 默认级别 |

> 改完环境变量一定要点 **Publish**，否则不生效。

---

## 4. 登录自己的邮箱（自动）

1. Publish 工作流，打开 **Access Point** → 开启 **Schedule Trigger**（每 5 分钟）；
2. 第一轮发现未登录 → 给你的 **Dify 账号邮箱**发登录邮件（设备码 + 微软授权链接 + 表单链接）；
3. 浏览器里用学校账号授权（首次接受权限）；
4. 打开邮件里的表单链接 → 点 **I have completed the sign-in**；
5. 运行恢复 → `Poll sign-in` → `signed_in=true`（`account` 就是你的邮箱）。

> 没收到邮件时的兜底：`FORCE_ACTION=login` → Publish → Test Run → 从 END 输出复制
> `user_code` / `verification_uri`，授权后再 `FORCE_ACTION=login_poll`。

---

## 5. 第一次试跑（不写回）

1. `FORCE_ACTION=reset` → **Publish** → **Test Run**（清空基线，END 里 `last_seen` 为空）；
2. `FORCE_ACTION=auto`、`DRY_RUN=true` → **Publish** → **Test Run**；
3. 检查 TRACING：`COLLECT MAIL` 有候选、`CLASSIFY MAIL` 有输出、`VALIDATE VERDICTS` 的 `failed=0`；
4. 邮箱不会有任何变化（dry run）。

## 6. 正式写回

`DRY_RUN=false` → **Publish** → **Test Run**；Outlook 里出现 S/A/B/C 标签（S 带红旗）。

## 7. 打开自动模式

1. `FORCE_ACTION=auto`、`DRY_RUN=false` → **Publish**；
2. **Access Point** → 打开 **Schedule Trigger**（每 5 分钟自动运行一次）。

---

## 8. 日常使用

- 收件箱新邮件会每 5 分钟自动分类、打标签；
- **每天 0 点**自动发日报（最近 1 天已分类邮件）；**每周日 0 点**自动发周报（`SUMMARY_DAYS` 天，默认 7 天）；
- **用邮件触发总结（`sum` 指令）**：给自己的学校邮箱发一封邮件，主题写：

  | 主题 | 报告内容 |
  |---|---|
  | `sum` | 全部级别（默认 `LETTERS=sabc`） |
  | `sum sa` | 只要 S 和 A |
  | `sum sabc` | 明确全部级别 |
  | `sum b` | 只要 B |

  主题必须**正好**是 `sum` 或 `sum <级别>`（级别是 `s/a/b/c` 的任意组合，大小写不限；
  多写别的字会被当成普通邮件）。`FORCE_ACTION` 必须是 `auto`。
  下一轮会先给这封指令邮件打 `Sum` 标签，再把 `SUMMARY_DAYS` 内已分类邮件的 HTML 报告发到 `RECIPIENT`；
  报告邮件本身会在再下一轮被打 `Sum`（不会重复总结）。
- 也可以不发邮件，手动：`FORCE_ACTION=sum` → Publish → Test Run（级别由 `LETTERS` 决定）。

---

## 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 打开画布一直转圈（`/workflows/draft` 400） | 环境变量用了 boolean 类型；必须是 string/number/secret |
| Code 节点报 `'return' outside function` | 旧版 DSL；重新导入最新 `HKUST_AI_email_manager.yml` |
| 设备码页面提示 "That code didn't work" | 旧设备码被复用/已用过；`FORCE_ACTION=login` 会强制生成新码 |
| 浏览器授权成功但 `signed_in=false` | 立刻用 `login_poll` 轮询；设备码有时效 |
| 分类结果 `ok=0`、`VALIDATE` 整批作废 | 模型没按 `ref` 返回；用最新 DSL |
| 报告邮件没有 `Sum` 标签 | 下一轮才会补打；等 5 分钟或 Test Run 一次 |
| 重装插件后变成未登录 | Dify 插件存储被清空，重新走一次登录 |
| 想重跑最近邮件 | `FORCE_ACTION=reset` 清基线；或本地运行 `scripts/reset_categories.py` 清标签 |

---

## 安全 / 配额

- 插件只访问**登录者本人**的邮箱；token 存在各自工作区插件存储里；
- 邮件正文会发给**你自己在 Dify 里配置的模型服务**（学校 API）；
- 每 5 分钟一轮 ≈ 288 Trigger Events/天，Education Pro 的 20,000/月够用；
- 不要把自己的 App 链接、token 截图发到公开群。
