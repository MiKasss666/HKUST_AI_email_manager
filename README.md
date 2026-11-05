# HKUST_AI_email_manager

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
- 不要把 `WEBHOOK_TOKEN`、token 缓存、含邮箱内容的截图发到公开仓库；
- 设备码登录使用微软公开客户端（与原桌面程序一致），不需要管理员许可。

背景与方案：

- [分发给同学：新用户使用流程](docs/DISTRIBUTE.md)
- [迁移建议书](docs/DIFY_MIGRATION_ADVICE.md)
- [方案 A 单工作流设计](docs/PLAN_A_SINGLE_WORKFLOW.md)
- [网页版 Dify + 设备码 + 分发设计](docs/PLAN_A_CLOUD_DEVICECODE_SHARE.md)
