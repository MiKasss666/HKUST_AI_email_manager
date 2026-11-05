# 分发给同学：新用户使用流程

这套东西 = **1 个 Dify 插件 + 1 个工作流 DSL**。每个同学在自己的 Dify 工作区里装一次、导入一次，
之后每 5 分钟自动整理自己的学校邮箱。

> 前提：Dify Cloud 账号（建议用学校邮箱注册），工作区归**自己**所有；不要把别人的 app 链接当共享入口。

---

## 0. 准备（一次性，约 10 分钟）

| 需要 | 说明 |
|---|---|
| Dify Cloud 账号 | 用学校邮箱注册，Settings → Billing 里申请 **Education 折扣**（免费 Yearly Pro，20,000 Trigger Events/月） |
| AI 模型 | 学校提供的 OpenAI 兼容 API（地址 + Key + 模型名）。在 **Integrations → Model Provider** 里添加 |
| 插件包 | `email_manager.difypkg`（群文件），或 GitHub 仓库地址 |
| DSL 文件 | `HKUST_AI_email_manager.yml`（群文件） |

---

## 1. 安装插件

**本地包**：Integrations → Install → Local Package File → 选 `email_manager.difypkg`。

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
`CATCHUP_DAYS=7`、`LETTERS=sabc`、`DRY_RUN=true`、`TENANT=common`、`FORCE_ACTION=login`。

可选：`COURSES`（如 `COMP 1021, MATH 1014`）、`FACULTY`、`NAME`、`STUDENT_ID` 填了判级更准。

> 改完环境变量一定要点 **Publish**，否则不生效。

---

## 4. 登录自己的邮箱

1. `FORCE_ACTION` = `login` → **Publish**；
2. 点 **Test Run**（或 Web App 页的 **Execute**）；
3. 在结果 **END** 输出里复制 `user_code` 和 `verification_uri`；
4. 浏览器打开链接、输入码、用学校账号登录并接受权限；
5. `FORCE_ACTION` = `login_poll` → **Publish** → **Test Run**；
6. END 里 `signed_in=true` 即成功（`account` 是你的邮箱）。

---

## 5. 第一次试跑（不写回）

1. `FORCE_ACTION` = `reset` → **Publish** → **Test Run**（清空基线，END 里 `last_seen` 为空）；
2. `FORCE_ACTION` = `auto`、`DRY_RUN` = `true` → **Publish** → **Test Run**；
3. 检查 TRACING：`COLLECT MAIL` 有候选、`CLASSIFY MAIL` 有输出、`VALIDATE VERDICTS` 的 `failed=0`；
4. 邮箱不会有任何变化（dry run）。

## 6. 正式写回

`DRY_RUN` = `false` → **Publish** → **Test Run**；Outlook 里出现 S/A/B/C 标签（S 带红旗）。

## 7. 打开自动模式

1. `FORCE_ACTION` = `auto`、`DRY_RUN` = `false` → **Publish**；
2. **Access Point** → 打开 **Schedule Trigger**（每 5 分钟自动运行一次）。

---

## 8. 日常使用

- 收件箱新邮件会每 5 分钟自动分类、打标签；
- **每天 0 点**自动发日报（最近 1 天已分类邮件）；**每周日 0 点**自动发周报（`SUMMARY_DAYS` 天，默认 7 天）；
- 想立刻要报告：给自己发一封主题为 `sum`（全部）或 `sum sa`（只要 S/A）的邮件，下一轮就会：
  1. 给这封指令邮件打 `Sum` 标签；
  2. 把报告发到 `RECIPIENT`；
- 也可以手动：`FORCE_ACTION=sum` → Publish → Test Run。

---

## 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 打开画布一直转圈（`/workflows/draft` 400） | 环境变量用了 boolean 类型；必须是 string/number/secret |
| Code 节点报 `'return' outside function` | 旧版 DSL；重新导入最新 `HKUST_AI_email_manager.yml` |
| 设备码页面提示 "That code didn't work" | 旧设备码被复用/已用过；`FORCE_ACTION=login` 会强制生成新码（插件 0.1.2+） |
| 浏览器授权成功但 `signed_in=false` | 立刻用 `login_poll` 轮询；设备码有时效 |
| 分类结果 `ok=0`、`VALIDATE` 整批作废 | 模型没按 `ref` 返回；用最新 DSL（prompt 已改） |
| 报告邮件没有 `Sum` 标签 | 下一轮才会补打；等 5 分钟或 Test Run 一次 |
| 重装插件后变成未登录 | Dify 插件存储被清空，重新 `login` → 授权 → `login_poll` |
| 想重跑最近邮件 | `FORCE_ACTION=reset` 清基线；或本地运行 `scripts/reset_categories.py` 清标签 |

---

## 安全 / 配额

- 插件只访问**登录者本人**的邮箱；token 存在各自工作区插件存储里；
- 邮件正文会发给**你自己在 Dify 里配置的模型服务**（学校 API）；
- 每 5 分钟一轮 ≈ 288 Trigger Events/天，Education Pro 的 20,000/月够用；
- 不要把自己的 Webhook/App 链接、token 截图发到公开群。
