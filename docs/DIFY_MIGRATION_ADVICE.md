# Email Manager v3.0.0 → Dify 工作流迁移建议

> 阅读对象：`Email_manager_beta` 维护者
> 对照源码：v3.0.0（commit `45ed398`，Graph-only 后端），路径 `C:\Users\xuanh\OneDrive\Desktop\AI\Email Manager Beta\Email Manager\Email_manager_beta`
> 对照 Dify：自部署 Workflow / Chatflow 官方文档（截至 2026-11，主线版本 1.11–1.19）、官方 Marketplace 插件 `langgenius/outlook` 1.0.1
> 结论会随 Dify 版本变化，**落地前请用你自己的 Dify 版本逐条实测第 2 节的硬限制**。

---

## 0. 一句话结论

原程序**不是"一个工作流"**，而是「常驻调度器 + 有状态的邮件代理 + 规则引擎 + 桌面控制台」四件套。Dify 能很好地承接**编排、LLM 判定、报告文案、人工审批**；但它没有跨运行持久状态、官方 Outlook 插件也写不了邮件分类（categories），这两点恰好是原程序幂等与写回语义的地基。

因此建议：

1. **日常长期使用 → 方案 B「混合架构」**：Python 保留 `core/` 的邮件读写、token、状态、幂等写回，Dify 只做 Schedule Trigger 编排 + LLM 判定 + 报告 HTML + Human Input 审批。工作量约 2–3 天，保真度最高。
2. **必须"全 Dify"→ 方案 A**：写 1 个自定义插件（`set_categories` + KV 状态）后可行，工作量约 3–5 天，并接受 3 个硬限制（见 2.3）。
3. **只想用 Dify 管 prompt/模型 → 方案 C**：原程序调用 Dify workflow API 做判定，其余不动，0.5 天，风险最低但不叫"迁移"。

> 不建议一上来就做全量 A。原程序约 5000 行核心/界面代码里，真正值钱的是**失败语义与写回安全**（`selftest.py` 356 项断言），而不是界面；先保住这些，再谈换皮。

---

## 1. 先看清：原程序到底由什么组成

### 1.1 八个可独立评估的部件

| # | 部件 | 职责 | 主要代码 | 能否交给 Dify |
|---|---|---|---|---|
| 1 | 桌面 GUI | 按钮、日志、配置对话框、Force reset | `gui/main_window.py`（450 行）、`gui/*` | ✅ 用 Dify WebApp + 运行日志替代（部分能力会丢，见第 10 节） |
| 2 | 自动监听调度 | 每 30s tick、串行任务、错误计数、退避 | `gui/watcher.py`（566 行） | ⚠️ Schedule Trigger 可替代"定时"，但**状态、单飞、退避语义**要另想办法 |
| 3 | 邮件后端 | Graph 设备码登录、token 缓存/轮换、限流退避、按需取正文、写分类 | `core/graph.py`（852 行） | ⚠️ 官方 Outlook 插件覆盖读/发/旗标，**不覆盖 categories 写回** |
| 4 | 邮件领域约定 | 分类名、报告/指令识别、`merge_categories`、`message_info` | `core/mailmeta.py`（139 行） | ✅ 纯函数，可原样搬进 Code/HTTP 网关 |
| 5 | 分级引擎 | 规则拼装、分批、条数校验、确定性兜底 | `core/classifier.py`（583 行） | ⚠️ LLM 部分容易搬；**"整批作废 + 对半拆分"没有原生递归**，需改造 |
| 6 | 总结报告 | 一句话要点、宽松 JSON 回收、HTML、sendMail | `core/summarizer.py`（264 行） | ✅ 主体可搬；发送靠插件/HTTP 节点 |
| 7 | AI 传输层 | OpenAI/Anthropic/CLI、墙钟超时、重试、JSON 容错 | `core/ai.py`（531 行） | 🔁 被 Dify 模型提供方取代；**容错解析逻辑仍要搬进 Code** |
| 8 | 配置与状态文件 | `config.json` / `graph_token.json` / `watch_state.json` 原子写 | `core/config.py`（546 行） | ⚠️ 配置→Dify 环境变量；token→插件凭据；**watch 状态没有 Dify 原生落点** |

### 1.2 迁移时不能丢的 5 条语义契约（这是验收线，不是实现细节）

| # | 契约 | 源码证据 | 丢了会怎样 |
|---|---|---|---|
| C1 | **条数严格对齐**：模型返回条数与本批不符 → 整批作废，绝不错位贴标签 | `core/classifier.py:282-305`（`to_verdicts` 校验）、`:389-417`（对半拆分） | 一封漏返回，后面所有邮件级别整体错位——比不分类严重得多 |
| C2 | **写回只替换自己的标签**：用户自定义分类必须保留 | `core/mailmeta.py:104-112`（`merge_categories`）、`core/graph.py:826-844` | 用户手动打的标签被静默抹掉且不可撤销 |
| C3 | **状态推进只在真正处理完之后**：有失败且未到 3 轮 → 基线不动；Force reset → 不推进 | `gui/watcher.py:106-128`（`advance_policy`）、`:470-478`（`_commit`）、`:341-378` | 失败的邮件永远不会被重试（静默漏处理） |
| C4 | **失败分两类**：邮箱不可用（网络/429/5xx）不计失败、不暂停；真错误连续 3 次才暂停 | `core/graph.py:72-86`、`gui/watcher.py:544-566` | 断网一次就把监听暂停，或无限重试烧 AI 额度 |
| C5 | **幂等跳过**：已分类 / 自家报告 / `sum` 指令 / ignored 名单不重复送 AI | `core/graph.py:705-736`、`gui/watcher.py:243-270`、`:380-430` | 每轮重复送 AI，成本翻倍、重复出报告 |

这 5 条在 Dify 上的落地难度：

| 契约 | 全 Dify（A） | 混合（B） |
|---|---|---|
| C1 | ⚠️ 需 Loop 模拟递归拆分（无递归原语） | ✅ Python 原实现不动 |
| C2 | ❌ 官方插件无 categories 写回，必须自研插件 | ✅ 原实现不动 |
| C3 | ❌ 无跨 run 变量，必须外部 KV/自定义插件 | ✅ `watch_state.json` 不动 |
| C4 | ⚠️ 只能做到"本轮失败、下轮重试 + 失败分支通知" | ✅ 原实现不动 |
| C5 | ⚠️ 依赖 categories 可读；读不到就得靠外部状态 | ✅ 原实现不动 |

---

## 2. Dify 侧能力盘点（带硬数字）

### 2.1 能直接用的能力

| 能力 | 说明 | 对原本的用途 |
|---|---|---|
| **Schedule Trigger** | Workflow 专用，cron 5 字段（最小粒度 1 分钟），每个 workflow 最多 1 个，可查看未来 5 次执行时间；见 [Schedule Trigger](https://docs.dify.ai/en/self-host/use-dify/nodes/trigger/schedule-trigger) | 替代 `watcher` 每 30s tick |
| **Workflow / Chatflow** | Workflow 单轮执行；触发器只能用于 Workflow；**只有 User Input 起始的 Workflow 能发布为 WebApp / API / MCP / 被别的应用当工具调用**；见 [Start](https://docs.dify.ai/en/self-host/use-dify/nodes/start) | 手动按钮 → 另一个 User Input 工作流 |
| **Iteration** | 对数组逐项跑子流程，支持并行（最多 10 项同时）、逐项错误策略（终止/继续/剔除）；见 [Iteration](https://docs.dify.ai/en/self-host/use-dify/nodes/iteration) | 逐封取正文、逐封写回 |
| **Loop** | 带跨轮变量的循环、终止条件、最大次数（默认上限 100，`LOOP_NODE_MAX_COUNT`）；见 [Loop](https://docs.dify.ai/en/self-host/use-dify/nodes/loop) | 模拟"分批 + 失败拆分"、状态机 |
| **Code** | Python/JS 沙箱，默认允许联网（`SANDBOX_ENABLE_NETWORK=true`），可 import 常见库；输出上限见 2.2；见 [Code](https://docs.dify.ai/en/self-host/use-dify/nodes/code) | 搬 `mailmeta`/`classifier` 的纯函数、JSON 容错解析 |
| **LLM** | 支持 JSON Schema 结构化输出、Jinja2 提示词（可循环渲染邮件块）、模型配置存环境变量、推理标签分离、节点级重试/兜底；见 [LLM](https://docs.dify.ai/en/self-host/use-dify/nodes/llm) | 替代 `ai.py` + `build_prompt` |
| **Human Input** | 暂停流程、发审批表单；**Email 投递可发给外部邮箱；Trigger 启动的工作流不能用 WebApp 投递**；默认超时 3 天，首个响应即关闭；见 [Human Input](https://docs.dify.ai/en/self-host/use-dify/nodes/human-input) | 替代"写邮箱前确认框"（可选） |
| **节点级错误处理** | LLM/HTTP/Code/Tool 支持"默认值 / 失败分支"；Loop 子节点失败即整体停止，Iteration 有 3 种策略；见 [Handle Errors](https://docs.dify.ai/en/self-host/use-dify/build/predefined-error-handling-logic) | 替代 `AiError`/`MailboxUnavailable` 的部分语义 |
| **应用环境变量** | 全应用共享、可在节点里用 `{{env.X}}` 引用、支持 secret 类型（导出默认不含值）；见 [Key Concepts](https://docs.dify.ai/en/learn/key-concepts) | 替代 `config.json` 的**只读**部分 |
| **官方 Outlook 插件** | `langgenius/outlook` 1.0.1（最低 Dify 1.7）：OAuth 单邮箱 / Service Principal / 每用户登录；工具：List Messages、Get Message、Send Message（支持 HTML body）、Draft、Flag Email、Prioritize Email、日历；**没有 Set Categories**；见 [Marketplace](https://marketplace.dify.ai/plugin/langgenius/outlook) | 替代 `graph.py` 的读信/发信/旗标 |
| **difyctl** | 命令行导出/导入/校验/测试/发布 DSL，可在 CI 里跑；见 [difyctl CI](https://docs.dify.ai/en/cli/scripts-and-ci) | 让 Dify 工作流进 git、做回归 |

### 2.2 关键硬限制（全 Dify 方案必须按这些数字设计）

| 项目 | 默认值 | 对原程序的影响 |
|---|---|---|
| Schedule 最小粒度 | 1 分钟（cron 5 字段） | 30s 轮询 → 1–5 分钟，实时性下降 |
| 单次 workflow 时长 | `WORKFLOW_MAX_EXECUTION_TIME=3600` 秒 | 够用（原批量 40 封通常 1–3 分钟） |
| 单次节点执行数 | `WORKFLOW_MAX_EXECUTION_STEPS=500` | **Iteration 内部节点也计数**：一轮 50 封 × 6 节点 ≈ 300 步，建议单轮 ≤30 封 |
| 单个变量大小 | `MAX_VARIABLE_SIZE=204800`（200KB） | 100 封邮件头数组可能逼近上限；正文必须截断 |
| Code 输出 | 字符串 400,000 字符；`array[object]`/`array[string]` **30 项**；嵌套 5 层 | **Python 里 `batch_size=40`、200 封列表不能原样过 Code 节点** |
| HTTP 响应 | `HTTP_REQUEST_NODE_MAX_TEXT_SIZE=1048576`（1MB） | Graph 200 封带正文必超；只拉头/分页 |
| HTTP 超时 | 连接 ≤10s、读 ≤600s（可配） | Graph 单请求够用 |
| Loop 次数 | `LOOP_NODE_MAX_COUNT=100` | 拆分重试要设保护上限 |
| 并行上限 | `MAX_PARALLEL_LIMIT=10` | 逐封取正文最多 10 并发 |
| 插件存储 | Marketplace 插件资源 10MB（官方 outlook 配置） | 自定义状态插件按工作区存 JSON 足够 |
| WebApp 人工审批 | Trigger 启动的工作流不可用 WebApp 投递 | 审批只能用 Email 投递，且需配 `APP_WEB_URL` |
| Webhook Trigger | 需要公网可达（`TRIGGER_URL`）、HTTPS、Graph subscription 需定期续订 | 想做"秒级"实时才用；不建议起步就上 |

### 2.3 三个"看起来能做、其实做不了/做不完整"的点

1. **跨运行持久状态**：Dify 的 Workflow 变量随本次执行结束消失；Conversation Variables 只属于 Chatflow；应用环境变量只读。`last_entryid` / `ignored` / `failed_rounds` / 运行锁**没有原生落点**，必须外部 KV（第 6.5 节）或保留 Python 状态（方案 B）。
2. **写回邮件分类**：官方 Outlook 插件只有 Flag / Importance，没有 categories。而原程序的幂等、`Sum` 报告识别、`read_recent` 出报告全都建立在 categories 上（`core/graph.py:761-781`、`core/mailmeta.py:99-101`）。**这是全 Dify 方案的第一红线**：要么自研插件补一个 `set_categories`，要么改变设计（用旗标/外部记录替代，接受行为差异）。
3. **Trigger 工作流不能发布为 WebApp/API**：想保留"Categorize / Sum 两个手动按钮"，必须另建 User Input 工作流（可作为工具被 trigger 工作流调用）；"定时"和"手动"天然是两个应用。

---

## 3. 模块级映射总表

> 结论图例：✅ 可直接迁移；⚠️ 需改造/替代；❌ 无对等能力，必须改设计。

| 原程序 | 源码位置 | Dify 落点 | 结论 |
|---|---|---|---|
| `app.py` 单实例互斥 | `app.py:16-50` | 无（Dify 服务端）；用运行锁近似 | ❌ |
| Tkinter 主窗口 / 日志区 | `gui/main_window.py` | Dify WebApp + Run Logs + 环境变量 | ✅（能力缩水） |
| 配置对话框 | `gui/ai_settings_dialog.py`、`user_info_dialog.py` | Dify 环境变量（string/secret）/ 模型提供方设置 | ✅ |
| 手动 `Categorize` / `Sum` / Scope / Dry run | `gui/main_window.py:363-425` | 独立 User Input 工作流（WebApp） | ✅ |
| 写邮箱前确认框 | `gui/main_window.py:372-380` | Human Input（Email 投递，可选） | ⚠️ |
| Force reset / 卡死提示 | `gui/main_window.py:181-242` | 运行超时、Run History；无对等 UI | ❌ |
| 监听调度 + 串行任务 | `gui/watcher.py:142-378` | Schedule Trigger + 外部锁 | ⚠️ |
| 监听状态（`watch_state.json`） | `gui/watcher.py:44-63` | 外部 KV / 自定义插件 / Python 网关 | ❌ 原生 |
| 启动补分类 | `gui/watcher.py:432-468` | User Input 工作流或 Schedule 分支 | ⚠️ |
| `sum` 指令识别 | `core/mailmeta.py:34,73-79`、`gui/watcher.py:406-430` | Code 正则 + Tool 调用报告工作流 | ✅ |
| 报告补 `Sum` 标签 | `gui/watcher.py:380-404` | 无法打标签 → 只靠主题标记 + 外部 `last_report_at` | ❌ |
| Graph 设备码登录 / token 缓存 / scopes 校验 | `core/graph.py:127-145,275-432` | 官方插件 OAuth（托管 token）/ Service Principal / 自研插件 | ⚠️ |
| 轮询只拉邮件头 | `core/graph.py:61-63,550-565` | List Messages（只取头部字段） | ✅ |
| 按需下载正文 | `core/graph.py:638-656` | Iteration → Get Message | ✅ |
| 限流退避（Retry-After） | `core/graph.py:196-248` | 节点重试（≤10 次，间隔 ≤5s）/ 失败分支 | ⚠️ |
| 写分类 + S 红旗 | `core/graph.py:581-590,826-844` | Flag Email（可）；categories（**必须自研插件/HTTP**） | ❌ 部分 |
| 发送 HTML 报告 | `core/graph.py:592-600` | Send Message（`body_type=html`） | ✅ |
| 邮件领域纯函数 | `core/mailmeta.py` | Code 节点（Python stdlib） | ✅ |
| 规则拼装 `build_spec` | `core/classifier.py:73-138` | Template / Code（规则文本来自 env） | ✅ |
| 批提示词 `build_prompt` | `core/classifier.py:168-193` | LLM 节点 system+user 模板 | ✅ |
| LLM JSON 调用/重试 | `core/ai.py:118-185` | LLM 节点（模型提供方 + 节点重试 + 结构化输出） | ✅ |
| JSON 容错解析（裸 JSON/围栏/JSONL/截断回收） | `core/ai.py:188-318` | Code 节点（逻辑原样搬） | ✅ |
| 条数校验 + 对半拆分 | `core/classifier.py:389-417` | Loop/Iteration 模拟（无递归） | ⚠️ |
| 确定性兜底（课程/学院/学校域名） | `core/classifier.py:308-385` | Code 节点 | ✅ |
| ignored 名单 | `gui/watcher.py:41,243-270` | 外部 KV | ⚠️ |
| 报告 HTML 构建 | `core/summarizer.py:156-210` | Code/Template 节点 | ✅ |
| 一句话要点宽松回收 | `core/summarizer.py:101-136` | Code + LLM | ✅ |
| 失败语义 | `core/graph.py:72-86`、`gui/watcher.py:544-566` | 节点错误处理 + 失败分支 + 下轮重试 | ⚠️ |
| `selftest.py` / `guitest.py` | `selftest.py`、`guitest.py` | 保留 Python 作为"规则真值源"+ Golden Set；Dify 侧用 `difyctl test` | ⚠️ |

---

## 4. 三种方案与推荐

### 4.1 方案 A：全量 Dify

```
Schedule Trigger ─→ Code(过滤/分批) ─→ Loop ─→ LLM(判级) ─→ Code(校验+兜底)
      │                                                      │
      └→ Outlook 插件(读/发/旗标)                    Human Input(可选审批)
                                                             │
                                     自研插件(set_categories + KV 状态) ─→ Output
```

- **前置**：自部署 Dify（建议 1.11+，新功能集中在 1.11–1.19）；`langgenius/outlook` 插件；**1 个自研插件**（写 categories + 存 KV 状态，见 6.4）；一个常在线主机（cron 不补跑）；可注册 Entra 应用（OAuth 回调需 HTTPS）。
- **保真度**：补上自研插件后 ≈85%；仍差在"30s→1min"、"3 轮失败语义"、"递归拆分"、"无运行锁"、"无 'Sum' 标签"。
- **成本**：3–5 人天（插件 2–3 天含认证调试）。
- **适合**：想彻底摆脱 Windows 安装包、要 Web 界面、能接受行为微调。

### 4.2 方案 B：混合架构（推荐）

```
┌────────────── Dify ──────────────┐        ┌──────── Python 网关（原 core）────────┐
│ Schedule Trigger (*/5)           │  HTTPS │ GET  /pending    读新邮件(头+正文)   │
│ HTTP /pending → LLM 判级 →        │ ─────→ │ POST /verdicts   合并+写回+打旗标     │
│ Code 校验/兜底 → Human Input(可选)│ ←───── │ POST /advance    基线/失败轮次/ignored│
│ → HTTP /verdicts → HTTP /advance  │        │ GET  /report-source  已分级邮件      │
│ 第二个应用：手动 Categorize/Sum    │        │ POST /report     发 HTML 报告        │
└───────────────────────────────────┘        │ GET/POST /state  锁+状态（原子写）    │
                                             └──────────────────────────────────────┘
```

- **Dify 只做**：调度、prompt 管理、LLM 调用、结构校验、报告 HTML、审批、可视化日志。
- **Python 保留**：Graph 读写、token 生命周期、`merge_categories`、基线/失败语义、幂等跳过、原子写。这些是 `selftest.py` 覆盖最厚、也是最容易写错的部分。
- **保真度**：C1–C5 全部保留（Python 侧）+ 轮询粒度可保持甚至比 Dify 更细。
- **成本**：2–3 人天（写一个约 300 行的 HTTP 网关 + 2 个工作流）。
- **代价**：仍要维护一个常驻进程（可在本机/Tailscale/小 VPS）；"全 Dify"的叙事不成立。
- **适合**：每天真的用它处理学校邮件的人。

### 4.3 方案 C：Dify 只当模型网关

原程序 `core/ai.py` 改成调用 Dify `POST /v1/workflows/run`（`response_mode=blocking`），其余一行不动。

- **收益**：prompt/模型在 Dify 里可视化迭代、A/B 模型、统一日志；其他风险不变。
- **成本**：0.5 人天。
- **适合**：你真正的痛点是"prompt 调不动、换模型麻烦"，而不是"想去掉桌面程序"。

### 4.4 决策矩阵

| 维度 | A 全量 Dify | B 混合 | C 模型网关 |
|---|---|---|---|
| 迁移工作量 | 高（3–5d） | 中（2–3d） | 低（0.5d） |
| 语义保真（C1–C5） | 中（需自研插件） | 高 | 高 |
| 去掉 Windows 程序 | ✅ | ❌（留网关） | ❌ |
| 可视化编排/prompt 迭代 | ✅ | ✅（判定部分） | ✅（仅 prompt） |
| 运维复杂度 | 高（Dify + 常在线 + 插件） | 中（Dify + 网关） | 低 |
| 隐私面 | 中（自部署时邮件数据在 Dify 库/日志） | 中 | 低 |
| 推荐场景 | 毕设/演示/彻底换平台 | **日常使用** | prompt 运维 |

**推荐组合**：先做 **C**（半天，立刻把 prompt 搬到 Dify，验证模型连通与判定质量），再演进到 **B**（保留已验证的 Python 侧，把编排与报告搬进 Dify）；只有确认"必须没有本地进程"时再走 **A**。

---

## 5. 方案 B 落地设计（推荐）

### 5.1 Python 网关接口（新增，`core/` 基本不动）

鉴权：`Authorization: Bearer ${GATEWAY_TOKEN}`；只监听 `127.0.0.1` 或 Tailscale 网段；Dify 的 HTTP 节点默认走 SSRF 代理会拦截内网地址，需要给该主机放行或走公网 HTTPS。

| 方法 | 路径 | 入参 | 出参 | 复用的原代码 |
|---|---|---|---|---|
| GET | `/pending?limit=50&days=7` | — | `{last_seen, items:[{entryid,subject,sender_name,sender,received,web_link,body_head,body_tail}], ignored_count}` | `graph.collect_new_mail` + `fill_body` + `message_info`；`body_head/tail` 按 `classifier.BODY_CHARS/TAIL` |
| POST | `/verdicts` | `{verdicts:[{entryid,level,deadline,urgent,is_school}]}` | `{ok,failed,skipped}` | `mailmeta.merge_categories` + `graph.write_categories`（只改自己的标签） |
| POST | `/advance` | `{oldest_entryid,newest_entryid,failed,ignored_ids[]}` | `{last_seen,failed_rounds,gave_up}` | `watcher.advance_policy` 原样调用 |
| GET | `/report-source?days=7&letters=sabc` | — | `[{entryid,level,subject,sender,body,received,web_link}]` | `graph.read_recent` |
| POST | `/report` | `{subject,html}` | `{sent:true}` | `graph.send_mail` |
| GET/POST | `/state` | — | `{last_seen,failed_rounds,ignored[],lock_until}` | `watcher._persist` + 原子写 |
| POST | `/lock` / `/unlock` | `{owner,ttl}` | `{acquired}` | 新增单飞锁（替代 TaskRunner 串行） |
| GET | `/health` | — | `{ok,graph,ai,version}` | `run.py check` 的只读部分 |

要点：

- 网关**不实现 LLM**；prompt 与模型在 Dify 里，这是迁移的收益点。
- `merge_categories`、条数校验、基线推进必须在网关里做（原样复用、selftest 覆盖），**不要挪到 Dify Code 节点**——否则同一逻辑两处维护。
- 改动集中在新增 `server.py` + `core/` 内的少量包装函数；`selftest.py` 仍应全绿。

### 5.2 Dify 侧两个应用

**App 1 `email-watch`（Schedule Trigger）**

1. Schedule Trigger：`*/5 * * * *`（先 5 分钟，稳定后再试 1 分钟）。
2. HTTP `POST /lock`（原子抢锁，带 TTL）→ If-Else 未抢到 → Output `skipped`。
3. HTTP `GET /pending` → If-Else `items` 为空 → HTTP `/advance`（空推进）+ `/unlock` → Output `idle`。
4. Code：把 items 拼成批提示词（规则文本来自 `{{env.*}}`；正文 400 头 + 300 尾）；若 `items>30` 截断并记日志。
5. Loop（max 8）：LLM 判级（JSON/结构化输出，temperature 0）→ Code 校验条数、解析、确定性兜底（课程/学院/域名）→ 追加结果。
6. If-Else：有未判定邮件 → 单封补判 Iteration（`continue-on-error`），或直接标记失败。
7. Human Input（可选，Email 投递）：展示 `S/A/B/C` 摘要与写回封数；`Approve` → 继续，`Skip` → 不写回。超时默认 Skip。
8. HTTP `POST /verdicts` → HTTP `POST /advance`（失败时不推进）→ HTTP `/unlock`。
9. Output：`{read, ok, failed, skipped, S/A/B/C, report?}`。

**App 2 `email-toolbox`（User Input，WebApp，可手动）**

输入：`action`（classify / sum / check）、`days`、`letters`、`dry_run`。
- `classify` → 调用与 App 1 相同的网关接口（`/pending` → LLM → `/verdicts`/`/advance`），dry_run 时跳过 `/verdicts`。
- `sum` → HTTP `/report-source` → Code 分批 → LLM 一句话要点（宽松解析）→ Code 拼 HTML → HTTP `/report`。
- `check` → HTTP `/health` → Output。

> `sum` 指令邮件仍由 App 1 识别：Code 正则 `^sum(?:\s+([sabc]+))?$`，命中后调用 App 2 的 `sum` 分支（Workflow-as-Tool 只能调 User Input 工作流，所以两个应用正好分工）。

### 5.3 职责边界（为什么这样切）

| 放在 Python | 放在 Dify |
|---|---|
| 邮件读写、token、限流退避 | 调度、编排、可视化 |
| 写回合并、状态推进、幂等 | prompt、模型选择、结构化输出 |
| 原子写、运行锁 | 审批表单、运行日志 |
| `selftest.py` 可覆盖的一切 | 需要人看/需要频繁改的一切 |

这个边界让 **A 方案的迁移变成"把网关替换成自研插件"**：工作流结构不变，风险集中在一个可测的适配层。

---

## 6. 若必须全 Dify：A 方案节点级设计

### 6.1 前置条件

- 自部署 Dify（Workflow + Trigger + Loop + Human Input 可用；官方文档主线 1.11–1.19，老版本先升级）。
- 插件：`langgenius/outlook` 1.0.1（最低 1.7）。
- 自研插件 1 个：`email-manager-ext`（categories 写回 + KV 状态），见 6.4。
- Entra 应用注册：Delegated `Mail.ReadWrite`、`Mail.Send`、`offline_access`；重定向 URI 必须 HTTPS（插件 OAuth 模式）；若走 Service Principal，需要管理员同意 application 权限——**学生账号大概率拿不到**。
- 一台常在线主机（cron 不补跑；笔记本睡眠会漏轮询）。
- `APP_WEB_URL`（Human Input 邮件里的表单链接）、`CONSOLE_WEB_URL` 必须配好。

### 6.2 应用拆分

| App | 起始节点 | 职责 |
|---|---|---|
| `mail-pipeline` | User Input | 取信 → 判级 → 写回 → 推进状态（幂等）；被下面两个应用当工具调用 |
| `email-watch` | Schedule Trigger | 定时调 `mail-pipeline`（mode=watch） |
| `email-toolbox` | User Input | 手动 `classify`（可 dry-run）/ `sum` / `check` |
| `sum-report` | User Input | 读已分级邮件 → 要点 → HTML → 发送（可被 `mail-pipeline` 当工具调用） |

### 6.3 `mail-pipeline` 节点序列（关键配置）

先固定 LLM 节点的 5 个配置（这几项直接决定原程序的失败模式是否会重演）：

1. **模型配置存环境变量**（Environment Variables 里新增 LLM 类型变量），所有 LLM 节点绑同一个变量，换模型只改一处；
2. **temperature = 0**（与原 `AiProfile.temperature=0` 对齐）；
3. **max_tokens 给足**（原程序默认 16384，`core/ai.py:153-164` 记录过"推理内容吃掉输出额度导致 JSON 被截断"的坑）；
4. 优先用 **Structured Output（JSON Schema）**；模型不支持时 Dify 会退化为"把 schema 写进 prompt"，仍需 Code 校验兜底；
5. 打开 **推理标签分离**（reasoning tag separation），避免 `deepseek-flash` 一类模型的思考内容混进 `text` 被当 JSON 解析。

提示词里的邮件块用 **Jinja2 循环**渲染即可，不必先拼字符串（与 `classifier._email_block` 等价）：

```jinja
{% for m in emails %}[{{ loop.index }}] {{ m.subject }}
发件人: {{ m.sender_name }} <{{ m.sender }}>
正文: {{ m.body_head }}
（正文末尾节选，签名通常在这里）: {{ m.body_tail }}
{% endfor %}
```

| # | 节点 | 配置要点 | 失败处理 |
|---|---|---|---|
| 1 | User Input | `mode`(watch/manual)、`days`、`dry_run`、`force` | — |
| 2 | Tool `state_get` | 读 `{last_seen,failed_rounds,ignored,lock_until}` | 失败分支 → Output 错误 |
| 3 | Code：锁 CAS | `now < lock_until` → `locked=true`；否则写新锁并 `state_set` | — |
| 4 | If-Else | `locked` → Output skipped | — |
| 5 | Tool Outlook `list_messages` | limit=50，最新优先；只取头部字段 | 重试 2 次 → 失败分支 |
| 6 | Code：筛选 | 跳过报告主题/`sum` 指令/ignored/已分类（若 categories 可读）/不新于 `last_seen`；上限 30 | — |
| 7 | If-Else | 0 封 → `state_set` 释放锁 → Output idle | — |
| 8 | Iteration（并行 5，`continue-on-error`） | `get_message` → Code 截断 400+300 | 单封失败留空 → 后续不写回 |
| 9 | Code：分批 | 每批 20，输出 `batches` 字符串数组（**用 JSON 字符串，别用 object 数组**） | — |
| 10 | Loop（max 8） | LLM 判级（system=规则模板，user=批内容）→ Code 校验条数/解析/兜底 → Code 更新 `results`、`failed` | 条数不符 → 记录失败，退出 Loop |
| 11 | If-Else | `failed>0` → Iteration 单封补判（`continue-on-error`） | 兜底失败 → 该封留空 |
| 12 | Human Input（可选） | Email 投递；表单列出 `{level subject sender}`；`Approve/Skip`；超时 1 天 → Skip | 超时分支 → 不写回 |
| 13 | Iteration | 逐封：自研插件 `set_categories`（合并规则在插件内做）+ Outlook `flag_email`（仅 S 且 urgent） | `continue-on-error` + 失败计数 |
| 14 | Tool `state_set` | `last_seen`（失败时不推进）、`ignored` 追加、`failed_rounds`、释放锁、stats | 失败分支 → Output 错误 |
| 15 | Output | `{read,ok,failed,skipped,S/A/B/C}` | — |

> 单轮上限建议 **30 封**：500 步预算下，30 封 × ~10 步 ≈ 300，留出重试余量。

### 6.4 自研插件 `email-manager-ext`（A 方案的必要条件）

官方 Outlook 插件没有 categories 写回（[Marketplace 功能列表](https://marketplace.dify.ai/plugin/langgenius/outlook) 只有 Flag / Prioritize / Send / Draft / List / Get），所以必须补。两种做法：

**做法 1（推荐）：自研一个薄插件**
- 工具 `set_categories(message_id, categories, remove_own)`：
  1. `GET /me/messages/{id}?$select=categories,flag` 读现状；
  2. 按 `mailmeta.merge_categories` 只替换 `S/A/B/C/Sum`；
  3. `PATCH /me/messages/{id}` 写 `categories`（+ `flag.flagStatus`）。
- 工具 `state_get(key)` / `state_set(key, value)`：插件存储（10MB）读写 JSON，工作区级；带 `updated_at` 做 CAS。
- 认证：优先 OAuth（单邮箱，适合个人；沿用官方插件的授权模式）；如果想复刻原程序的设备码体验，也可以在自研插件里实现设备码登录，把 refresh token 存插件存储（交互一次后可长期使用）。凭据存插件存储，不经过 LLM。
- 成本：插件脚手架 + OAuth + 2 个工具 ≈ 2–3 人天。

**做法 2：给官方插件提 PR**
在 `langgenius/dify-official-plugins` 里加 `set_categories` 工具，复用其 OAuth 凭据机制——最省事、最可维护，但取决于上游是否接受、等多久。

**替代（不推荐）**：只用 `flag_email` + 外部 KV 记录级别。用户打开 Outlook 看不到 S/A/B/C，`Sum` 报告识别失效，与产品定位不符。

### 6.5 状态设计（外部 KV）

Key：`email-manager/state`，Value（JSON 字符串）：

```json
{
  "last_seen": "AAMk...",
  "last_run_at": "2026-11-05T14:30:00+08:00",
  "failed_rounds": {"<batch_key>": 1},
  "ignored": ["AAMk..."],
  "ignored_cap": 1000,
  "lock_until": 1762345678,
  "lock_owner": "<workflow_run_id>",
  "last_report_at": "2026-11-04T09:00:00+08:00"
}
```

语义对应原实现：

| 原实现 | KV 字段 | 规则 |
|---|---|---|
| `_last_seen`（`watcher.py:154`） | `last_seen` | 只有本轮全部成功/放弃后才推进（`advance_policy`） |
| `_ignored`（`watcher.py:158-159,263-270`） | `ignored` | 非学校邮件 EntryID，上限 1000，新的在前 |
| `_failed_rounds`（`watcher.py:163,368-377`） | `failed_rounds` | 同一批连续失败计数，≥3 放弃并推进 |
| `_errors`（`watcher.py:162,558-565`） | 无对等 | 建议改为失败分支 → 发告警邮件 → 连续 3 轮告警后停用 Trigger |
| `_catchup_pending`（`watcher.py:165`） | 无对等 | 建议每次启动（或每天首次）跑一次"最近 N 天未分类"分支 |
| TaskRunner 串行（`gui/task.py`） | `lock_until` | 抢锁失败 → 本轮 skip；锁 TTL > 最大运行时长 |

### 6.6 用 Loop 模拟"整批作废 + 对半拆分"

原实现是递归（`classifier.py:391-417`，40→20→10→5，最多 3 层）。Dify 无递归，用 **队列 + Loop 变量** 等价表达：

```text
Loop 变量：
  queue   = [batch_20]      # 待判定批次（批次少，用 JSON 字符串数组即可）
  results = []              # 已成功的结果
  fails   = []              # 最终失败的 entryid
  depth   = 0

循环体：
  1. Code: 取出 queue[0] 作为本批，queue = queue[1:]
  2. LLM 判级（失败/超时 → 视为本批失败）
  3. Code: 解析并校验条数
       条数正确 → results += 结果
       条数错误 且 len(batch) > 1 且 depth < 3 → queue += [前一半, 后一半], depth += 1
       条数错误 且 (len(batch) == 1 或 depth >= 3) → fails += 本批 entryid
  4. If-Else: queue 为空 → Exit Loop
```

保险：Loop 最大次数设为 16；`depth` 作为 Loop 变量持久化（对应原 `SPLIT_MAX_DEPTH=3`）；最终失败封数进入 Output，并让 `state_set` 不推进基线。
如果嫌复杂，**降级方案**：批 20 失败 → 直接逐封补判（Iteration 单封）。少一层拆分，成本可控，语义可接受。

### 6.7 数据体积预算（按 2.2 的硬限制核算）

| 数据 | 估算 | 限制 | 结论 |
|---|---|---|---|
| 单封邮件对象（700 正文 + 头） | ≈1KB | — | — |
| 30 封候选数组 | ≈30KB | 变量 200KB / object 数组 30 项 | ✅ 卡在 30 封上限 |
| 100 封邮件头（List Messages） | ≈100–150KB | 变量 200KB | ⚠️ 建议 50 封/页 |
| Graph 原始响应（200 封带头） | 500KB–1MB | HTTP 1MB | ❌ 必须分页/只取头部 |
| 判级提示词（20 封 × 700 字） | ≈20KB | 模型上下文 | ✅ |
| HTML 报告（100 封） | ≈100–200KB | Code 字符串 400KB / 变量 200KB | ⚠️ 超过 100 封要分页或裁剪正文 |

### 6.8 时间与成本估算

| 项 | 估算 |
|---|---|
| 自研插件（认证 + set_categories + KV） | 2–3 人天 |
| 4 个应用编排 + 调试 | 1.5–2 人天 |
| Golden Set 对照与修正 | 1 人天 |
| 每日运行成本 | 轮询 5 分钟 = 288 runs/天 ×（1 次 list + 0~N 次 get）；LLM 成本与原程序同量级（判级 1 批/次，总结 1 批/次） |
| 运行开销 | 5 分钟轮询比原 30 秒少 83% 的 Graph 调用；但 Dify 每次 run 都写日志/节点记录，需开清理（`WORKFLOW_LOG_CLEANUP_ENABLED`） |

---

## 7. 必须逐条改造的 8 个技术点

### 7.1 状态持久化

- **原实现**：`watch_state.json` 原子写，`last_entryid`/`ignored`/`interval`（`gui/watcher.py:44-63`）。
- **Dify**：无跨 run 变量（[Key Concepts](https://docs.dify.ai/en/learn/key-concepts)：Workflow Variables 随执行结束重置；Conversation Variables 仅 Chatflow；Environment Variables 只读）。
- **做法**：方案 B 留在 Python；方案 A 用 6.5 的 KV 插件。
- **风险**：并发两个 run 同时读改写 → 用 CAS（带 `updated_at` 的比较交换）或锁。
- **验证**：连续跑两次同一批邮件，第二次必须 0 封待处理；人为制造"读完未推进"的崩溃，下一轮应重试而非跳过。

### 7.2 分类写回（categories）

- **原实现**：`merge_categories` 只剔除自己的名字，其余保留；`PATCH /me/messages/{id}`（`core/graph.py:826-844`、`:581-590`）。
- **Dify**：官方插件只支持 flag/importance。
- **做法**：方案 B 留在 Python；方案 A 自研插件（6.4）。
- **风险**：直接覆盖 categories 会抹掉用户标签；不做"已分类跳过"会重复送 AI。
- **验证**：测试邮箱里手动打一个自定义标签 → 跑一轮 → 标签仍在；再跑一轮 → 无新 AI 调用。

### 7.3 认证

- **原实现**：设备码 + refresh token 轮换 + scopes 校验（`core/graph.py:127-145,275-432`）。
- **Dify**：官方插件 OAuth（托管 token，推荐）/ Service Principal（需管理员同意）/ 每用户登录（不适合单人定时任务）。
- **关键坑**：
  - refresh token 轮换 → **不能**把 token 放在 Dify 环境变量里自己刷新（每次刷新都会让旧 token 失效，而环境变量不可写）；要么交给插件托管，要么自研插件存储。
  - scopes 必须覆盖写：只读 token 给 PATCH 会 403（原实现踩过，见 `graph.py:127-145` 注释）。
  - 学校租户可能限制应用注册/用户同意 → 先确认 Entra 权限，再决定 A 是否可行。
- **验证**：`GET /me` + 一次 PATCH；重启 Dify 插件后 token 仍有效。

### 7.4 轮询频率与并发

- **原实现**：30s tick + TaskRunner 串行 + busy 时 2s 重试（`gui/watcher.py:273-300`）。
- **Dify**：cron 最小 1 分钟；无运行锁。
- **做法**：间隔 ≥ 单轮最长耗时（先 5 分钟，跑一周统计 P95 后再调）；KV 锁；一轮没跑完则 skip 而不是排队。
- **风险**：重叠 run 会重复写、重复烧 AI。**没有锁的全 Dify 方案不要上生产**。
- **验证**：把一轮耗时人为拉长（mock 慢响应），观察第二轮是否被锁挡住。

### 7.5 条数契约与拆分重试

- **原实现**：`to_verdicts` 数量不符 → None；`_ask_batch` 对半拆，深度 3（`classifier.py:282-305,389-417`）。
- **Dify**：LLM 节点输出不保证条数；节点级重试只处理"调用失败/解析失败"，**不会**因为"条数不对"自动重试；无递归。
- **做法**：Code 校验 + Loop 队列（6.6）；或"批 20 → 失败逐封"。
- **风险**：**绝不可以用 index zip 硬对齐**；Dify 的 JSON 数组顺序也可能被模型打乱 → 要求模型在元素里带 `index`（或直接用 `entryid`），Code 按 id 对齐，比按顺序更安全（这是相对原实现的改进点）。
- **验证**：故障注入——让模型少返回 1 条、多返回 1 条、打乱顺序，检查是否整批作废且无错位写回。

### 7.6 数据体积

- **原实现**：`SELECT_HEADERS` 不含 body；正文按需（`graph.py:61-63,638-656`）。
- **Dify**：200KB/变量、1MB/HTTP、30 项 object 数组、400K 字符串（2.2）。
- **做法**：候选 ≤30；List 50/页；正文截断 400+300（总结 800）；HTML >100 封分页。
- **验证**：造 120 封未分类邮件，确认失败点在"截断"而不是"变量超限"。

### 7.7 失败语义

- **原实现**：`MailboxUnavailable` 不计失败、120s 后退避；其它错误连续 3 次暂停（`graph.py:72-86`、`watcher.py:544-566`）。
- **Dify**：节点级"默认值/失败分支"；HTTP/工具失败不会自动分类；cron 下一轮自然重试。
- **做法**：
  - 把 "网络/429/5xx" 当"本轮不推进状态、下轮重试"（HTTP 状态码分支或工具 `success/error` 字段）；
  - 真错误 → 失败分支 → 发告警邮件（Send Message 给自己）→ KV 错误计数，连续 3 次停用 Trigger（手动恢复）。
  - 不做"无限重试"：Loop 次数上限 + KV 失败轮次（对应 `MAX_FAILED_ROUNDS=3`）。
- **验证**：断网/429/500 三种注入，确认状态不推进、告警只发一次、恢复后自动接上。

### 7.8 人工确认与可观测性

- **原实现**：非 dry-run 时确认框（`gui/main_window.py:372-380`）；日志区 + `app.log`；watchdog 卡死提示。
- **Dify**：Human Input（Email 投递，需 `APP_WEB_URL`；Trigger 工作流不能用 WebApp 投递）；Run Logs + Variable Inspector；无本地日志。
- **做法**：审批可选（日常用会烦；建议只在"首次上线/大改 prompt 后"开一周）；日志靠 Run History + 每日汇总邮件；`difyctl test` 做冒烟。
- **验证**：Human Input 的邮件链接能打开、Approve/Skip 分支都走通；超时分支不写回。

---

## 8. 迁移路线与验收

### 8.1 路线（先小步，后全量）

| 阶段 | 内容 | 产出 | 退出条件 |
|---|---|---|---|
| P0（0.5d） | 方案 C：原程序接 Dify workflow 做判级；同批邮件与原 AI 结果对比 | 判定质量基线 | 一致率达标 |
| P1（1d） | 方案 B 网关只读接口 `/pending` `/health`；Dify 工作流跑 dry-run | 端到端跑通 | 30 封试跑无错 |
| P2（1d） | `/verdicts` `/advance` 写回；测试邮箱验证 | 写回正确 | C2/C3/C5 验收通过 |
| P3（0.5d） | `/report-source` `/report`；`sum` 指令；Human Input | 报告闭环 | 收到 HTML 报告，主题标记正确 |
| P4（按需） | 评估是否上 A：自研插件、迁移规则/状态 | 无本地进程 | 插件验收 + 一周稳定 |

### 8.2 Golden Set 对照（最重要的验收）

1. 固定一批邮件（建议 100 封：最近 30 天 + 20 封历史难题），导出为 JSON（`entryid/subject/sender_name/sender/body/received/web_link`）。原程序没有导出器，写一个约 20 行的**只读**脚本复用 `core.mail.connect/read_inbox` 即可（或用 `run.py classify --days 30 --dry-run` 的日志解析）。
2. 用原程序 `py -3 run.py classify --days 30 --dry-run` 产 baseline（记录每封 level/deadline/is_school）；同一批 JSON 也作为第 3 步的输入。
3. 用 Dify 的 `email-toolbox`（dry-run、输入同一 JSON）跑 3 次。
4. 指标：
   - **非学校误判为学校 = 0**（会多贴标签）与 **学校误判为非学校 = 0**（会永远漏贴）优先于级别一致率；
   - `is_school` 一致率 ≥ 99%；
   - `S` 召回 ≥ 95%，`A/B/C` 一致率 ≥ 90%；
   - `deadline` 差 ≤ 1 天（注意时区：原实现用本地日期 `date.today()`，Dify 沙箱容器的时区通常不是 `Asia/Hong_Kong`，必须在 Code 节点显式按 UTC+8 计算，见附录 B 第 3 段）。
5. 不一致的逐条归因：prompt 差异 / 温度 / 正文截断 / 时区 / 模型版本。
6. 把 Golden Set 与 Dify DSL 一起进 git，用 `difyctl test` 在 CI 跑冒烟（[difyctl CI](https://docs.dify.ai/en/cli/scripts-and-ci)）。

### 8.3 写回 / 故障 / 成本验收

- **写回**：自定义分类保留；同一封重复跑不改级别；非学校不写回；`S+urgent` 才有红旗；报告不会被再分类。
- **故障注入**：断网、429、5xx、模型少返回 1 条、JSON 截断、进程中途退出、连续两轮重叠触发。
- **成本**：统计每轮的 Graph 调用数（目标 ≤ 3 + 候选数）、AI token/封、每天 run 数；对比原程序 `app.log` 的日均调用。
- **回归**：`selftest.py` 保持 356 项全绿（Python 侧）；Dify 侧用 Golden Set + `difyctl check/test`。

---

## 9. 隐私、合规、运维红线

1. **数据出境面扩大**：原程序只把邮件正文发给你自己配置的模型服务；Dify Cloud 会额外经过 Dify 平台。**建议自部署**，模型仍可接原 DeepSeek（或本地 Ollama）。
2. **Dify 运行日志会存节点输入输出**：判级节点的输入就是邮件正文。设置日志保留/清理（`WORKFLOW_LOG_CLEANUP_ENABLED`、`WORKFLOW_LOG_RETENTION_DAYS`），`DEBUG=false`，不要把 token/正文写进 Output。
3. **token 存放**：原程序 `graph_token.json` 明文在 OneDrive 同步目录（README 已提示风险）；Dify 方案 token 在插件存储/后端数据库，记得 volumes 不进同步盘、备份加密。撤销授权时在 Entra 里移除应用同意即可。
4. **插件供应链**：第三方插件能读你的全部邮件。只用官方/自研，安装前看权限与存储需求。
5. **网络**：OAuth 回调需要 HTTPS 域名；`APP_WEB_URL`/`TRIGGER_URL`/`CONSOLE_WEB_URL` 必须与实际访问地址一致（否则 Human Input 邮件链接、webhook 回调失效）。HTTP 节点默认走 SSRF 代理，内网网关要单独放行。
6. **常在线**：cron 不补跑；Dify 容器停机/笔记本睡眠会漏轮询。原程序有关闭后补分类的语义，Dify 侧要靠"每天首次跑一次最近 N 天"分支补。
7. **版本升级**：Dify 迭代很快（1.11→1.19 数个版本）；升级前导出 DSL/`.ifpkg` 进 git、备份 volumes，升级后跑 Golden Set。
8. **合规**：分类结果会写回学校邮箱；`S/A/B/C` 标签与红旗属于个人使用，不要分发含他人邮箱/内容的快照。原程序的 `FALLBACK_CLIENTS`（`graph.py:54-58`）借用微软公开 client id 仅适合自用——Dify 方案要注册自己的 Entra 应用。

---

## 10. 明确不建议迁进 Dify 的部分

| 能力 | 原因 | 替代 |
|---|---|---|
| Tkinter 界面 / 主题 / 图标 | Dify 是 Web 产品，重做无收益 | Dify WebApp（仅 User Input 工作流） |
| 单实例互斥（`app.py:16-50`） | 桌面进程概念 | 运行锁 + 单 schedule |
| Force reset / watchdog 卡死提示（`main_window.py:181-242`） | Dify 无对等 UI；运行可超时/取消 | 运行超时 + Run History 排障 |
| TaskRunner 代次令牌/串行（`gui/task.py`） | 桌面线程概念 | KV 锁 |
| 原子写（`config.py:517-528`） | Dify 用数据库 | 无需 |
| app.log 轮转（`gui/log_view.py`） | Dify 运行日志 + 外部告警 | Run Logs、告警邮件 |
| PyInstaller/`build.bat`/单文件发布 | Dify 部署形态 | Docker/DSL 导入 |
| `selftest.py`/`guitest.py` | Dify 无单测框架 | 保留 Python 真值源 + Golden Set + `difyctl test` |

---

## 11. 需要你确认的 6 个问题

1. **Dify 部署形态与版本**：自部署还是 Cloud？版本是否 ≥1.11（有没有 trigger/loop/human-input）？主机能否 7×24 在线？
2. **Entra 权限**：你能在 HKUST 租户注册应用并配置重定向 URI 吗？能否拿到管理员同意（决定能否用 Service Principal 或只能 OAuth 委托）？
3. **是否接受保留一个常驻 Python 网关**（方案 B）？还是必须"纯 Dify、无本地进程"？
4. **categories 写回是否必须**？如果官方插件写不了，你接受"旗标/importance + 外部记录"替代，还是愿意投入自研插件？
5. **轮询频率**：30 秒 → 1–5 分钟可接受吗？"秒级"是否真的需要（要公网 Webhook + Graph subscription 续订）？
6. **目标**：日常长期使用（→B）、毕设/演示/换平台（→A 简化版）、还是只调 prompt（→C）？

---

## 附录 A：关键常量迁移映射

| 原常量 | 值 | Dify 对应 | 建议 |
|---|---|---|---|
| `DEFAULT_INTERVAL` | 30s | cron 最小 1 分钟 | `*/5 * * * *` 起步 |
| `MAX_MAIL_PER_ROUND` | 100 | 500 步/200KB/30 项限制 | 单轮 ≤30 封 |
| `CATCHUP_DAYS` | 7 | 查询窗口 | 每天首轮跑一次最近 3–7 天未分类 |
| `MAX_FAILED_ROUNDS` | 3 | KV `failed_rounds` | 原样保留 |
| `MAX_CONSECUTIVE_ERRORS` | 3 | KV 错误计数 + 告警 | 保留，改为邮件告警 |
| `MAILBOX_RETRY_DELAY` | 120s | 下一轮 schedule | 语义变为"下轮再试" |
| `REPORT_TAG_DAYS` | 30 | 主题标记 + `last_report_at` | 无法打 `Sum` 标签（A） |
| `RECENT_MAX` | 200 | List Messages 分页 | 50/页 × 1–2 页 |
| `RECENT_TTL` | 10s | — | 不需要 |
| `TOKEN_MARGIN` | 300s | 插件托管 | 不需要 |
| `MAX_ATTEMPTS` | 3 | 节点重试 ≤10 次/≤5s | HTTP 节点 2 次即可 |
| `batch_size` | 40 | Code object 数组 30 / 500 步 | **20–25** |
| `BODY_CHARS`/`TAIL` | 400/300 | Code 节点 | 原样 |
| `BODY_CHARS`（总结） | 800 | Code 节点 | 原样 |
| `urgent_days` | 14 | Code 日期计算 | 显式 `Asia/Hong_Kong` |
| `summary_days` | 7 | User Input 默认值 | 原样 |
| `SPLIT_MIN`/`SPLIT_MAX_DEPTH` | 2/3 | Loop `depth` 变量 | 或降级为逐封补判 |
| `DEFAULT_SCHOOL_DOMAINS`（config `school_domains`） | `ust.hk` | 环境变量 | `{{env.SCHOOL_DOMAINS}}` |
| `courses` / `faculty` / `name` / `student_id`（config） | — | 环境变量（secret 用于 key） | 不要硬编码进 prompt |

## 附录 B：可直接复用的 Code 节点要点

```python
# 1) 条数校验（移植 classifier.to_verdicts 的核心思想，但按 id 对齐更稳）
def main(expected_ids: list, raw_items: list) -> dict:
    if len(raw_items) != len(expected_ids):
        return {"ok": False, "reason": f"count {len(raw_items)} != {len(expected_ids)}", "verdicts": []}
    got = {str(x.get("id", "")): x for x in raw_items if isinstance(x, dict)}
    if set(got) != set(expected_ids):
        return {"ok": False, "reason": "id mismatch", "verdicts": []}   # 宁可整批作废
    return {"ok": True, "verdicts": [got[i] for i in expected_ids]}

# 2) 合并写回（移植 mailmeta.merge_categories；B 方案留在 Python）
def main(existing: list, ours: list) -> dict:
    own = {"S", "A", "B", "C", "Sum", "S 紧急", "A 重要", "B 普通", "C 可忽略"}
    kept = [str(x).strip() for x in existing if str(x).strip() and str(x).strip() not in own]
    return {"categories": kept + [str(x) for x in ours]}

# 3) 时区安全的 urgent 判定（原实现依赖本地日期）
from datetime import datetime, date, timedelta, timezone
def main(level: str, deadline: str, urgent_days: int) -> dict:
    tz = timezone(timedelta(hours=8))            # Asia/Hong_Kong，按部署地调整
    today = datetime.now(tz).date()
    try:
        due = datetime.strptime(deadline[:10], "%Y-%m-%d").date()
    except Exception:
        return {"urgent": False}
    return {"urgent": level == "S" and 0 <= (due - today).days <= urgent_days}

# 4) 宽松 JSON 回收（移植 ai.parse_json/salvage_array 的骨架）
import json, re
def main(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?", "", text or "").strip()
    try:
        return {"data": json.loads(cleaned)}
    except Exception:
        pass
    for a, b in (("[", "]"), ("{", "}")):
        i, j = cleaned.find(a), cleaned.rfind(b)
        if i != -1 and j > i:
            try:
                return {"data": json.loads(cleaned[i:j + 1])}
            except Exception:
                pass
    # 截断：raw_decode 逐元素回收（完整元素保留，残缺元素丢弃）
    dec, out, k = json.JSONDecoder(), [], cleaned.find("[")
    while k != -1 and k < len(cleaned):
        k += 1
        while k < len(cleaned) and cleaned[k] in " \t\r\n,":
            k += 1
        try:
            v, k = dec.raw_decode(cleaned, k)
            out.append(v)
        except Exception:
            break
    return {"data": out or None, "truncated": bool(out)}
```

## 附录 C：参考链接

- Schedule Trigger：https://docs.dify.ai/en/self-host/use-dify/nodes/trigger/schedule-trigger
- Trigger 总览（含多 trigger、发布限制）：https://docs.dify.ai/en/self-host/use-dify/nodes/trigger/overview
- Start 节点（User Input vs Trigger、发布为 API/WebApp/MCP/工具的限制）：https://docs.dify.ai/en/self-host/use-dify/nodes/start
- Loop：https://docs.dify.ai/en/self-host/use-dify/nodes/loop
- Iteration：https://docs.dify.ai/en/self-host/use-dify/nodes/iteration
- Code（沙箱网络、依赖、输出限制）：https://docs.dify.ai/en/self-host/use-dify/nodes/code
- Human Input：https://docs.dify.ai/en/self-host/use-dify/nodes/human-input
- 错误处理：https://docs.dify.ai/en/self-host/use-dify/build/predefined-error-handling-logic
- 变量与 Key Concepts（环境变量只读、会话变量仅 Chatflow）：https://docs.dify.ai/en/learn/key-concepts
- 环境变量与运行限制（`WORKFLOW_MAX_EXECUTION_TIME`、`MAX_VARIABLE_SIZE`、`LOOP_NODE_MAX_COUNT`、`CODE_MAX_*`、`HTTP_REQUEST_NODE_MAX_TEXT_SIZE`、`APP_WEB_URL` 等）：https://docs.dify.ai/en/self-host/deploy/configuration/environments
- 官方 Outlook 插件（功能/认证模式/最低版本）：https://marketplace.dify.ai/plugin/langgenius/outlook
- difyctl（DSL 导出/导入/测试/发布、CI）：https://docs.dify.ai/en/cli/create-and-update-apps-from-dsl-files
- difyctl CI 示例：https://docs.dify.ai/en/cli/scripts-and-ci
