# Hermes Agent 代码地图与自我迭代 Skill 抽取研究报告

最后维护：2026-05-10 14:20
维护人：CodeBuddy Agent

## Executive Summary

`hermes-agent` 是一个自进化 Agent 代码库，核心闭环由入口层、`AIAgent` 主循环、工具/工具集、Skills/Memory、Session/Context 压缩、Gateway/Cron 自动化、UI 与研究训练模块共同组成。后续要抽取“自我迭代总结 skill 并不断优化”的部分，最关键的代码集中在 `run_agent.py` 的后台 review 触发与 prompt、`tools/skill_manager_tool.py` 的 `skill_manage` 写入能力、`tools/skills_tool.py` 的 skill 读取与 progressive disclosure、`tools/skill_usage.py` + `agent/curator.py` 的 agent-created skill 生命周期治理，以及 `agent/prompt_builder.py` 的 system prompt 技能/记忆约束。

## 1. 总体分层

| 层级 | 代码位置 | 主要职责 | 与自我迭代 skill 的关系 |
| --- | --- | --- | --- |
| 安装与入口层 | `pyproject.toml`、`hermes`、`hermes_bootstrap.py`、`hermes_cli/main.py`、`cli.py`、`run_agent.py`、`mcp_serve.py` | 定义命令入口、Windows UTF-8 自举、CLI/TUI/Gateway/ACP/MCP 启动路径。 | 决定 Agent 以什么 toolset 和 skill 配置启动。 |
| Agent 核心运行层 | `run_agent.py`、`agent/*adapter.py`、`agent/prompt_builder.py`、`agent/context_compressor.py`、`agent/memory_manager.py`、`hermes_state.py` | 组装 prompt、调用模型、执行工具、压缩上下文、保存会话、触发后台 review。 | 自我迭代总结的主控层。 |
| 工具与工具集层 | `toolsets.py`、`model_tools.py`、`tools/*`、`tools/registry.py` | 注册 file/web/terminal/browser/memory/skills/cron/MCP/delegate 等工具，按 toolset 暴露给模型。 | `skills` toolset 暴露 `skills_list`、`skill_view`、`skill_manage`。 |
| Skill 与 Memory 层 | `tools/skills_tool.py`、`tools/skill_manager_tool.py`、`tools/skill_usage.py`、`tools/skills_sync.py`、`agent/skill_commands.py`、`agent/skill_utils.py`、`agent/curator.py`、`skills/`、`optional-skills/` | Skill 索引、加载、创建、补丁、支持文件、使用遥测、生命周期整理、内置/可选技能库。 | 是“经验→skill→使用中修订→定期整理”的实体层。 |
| 会话、上下文和召回层 | `hermes_state.py`、`agent/context_compressor.py`、`trajectory_compressor.py`、`tools/session_search_tool.py`、`tools/memory_tool.py` | SQLite 会话存储、FTS5 搜索、长上下文摘要、memory 持久化、轨迹压缩。 | 给后台 review 和跨会话学习提供输入。 |
| Gateway、Cron 与自动化层 | `gateway/`、`cron/`、`tools/cronjob_tools.py`、`hermes-already-has-routines.md` | 多平台消息网关、定时任务、webhook/API 触发、平台投递和 session reset 策略。 | 可把 skill 链、脚本预处理和总结任务自动化运行。 |
| UI 层 | `ui-tui/`、`tui_gateway/`、`web/`、`website/`、`locales/` | TUI、Python sidecar、Web dashboard、文档站、本地化。 | 展示/管理 skills、会话、工具进度和后台 review 摘要。 |
| Provider 与插件层 | `providers/`、`plugins/model-providers/`、`agent/*adapter.py`、`plugins/*` | 模型后端、外部平台、memory/context/observability 插件。 | 让 review/curator 可使用辅助模型和可插拔 memory/context。 |
| 研究训练层 | `batch_runner.py`、`mini_swe_runner.py`、`rl_cli.py`、`environments/`、`datagen-config-examples/`、`tinker-atropos/`、`trajectory_compressor.py` | 批量轨迹生成、SWE/Atropos RL 环境、reward 评估、训练数据压缩。 | 可把自我迭代过程沉淀为训练轨迹。 |
| 工程与发布层 | `tests/`、`scripts/`、`docker/`、`nix/`、`packaging/`、`CONTRIBUTING.md`、`RELEASE_*.md` | 测试、安装、容器、Nix、打包、发布说明。 | 验证抽取后的 skill 能否在真实入口稳定工作。 |

## 2. 入口与运行主链路

| 模块 | 代码位置 | 做什么 | 关键点 |
| --- | --- | --- | --- |
| 包入口 | `pyproject.toml` | 定义 `hermes = hermes_cli.main:main`、`hermes-agent = run_agent:main`、`hermes-acp = acp_adapter.entry:main`，并声明 setuptools 包/模块。 | 现代主入口是 `hermes_cli/main.py`；旧/底层入口仍保留 `run_agent.py` 和 `cli.py`。 |
| 自举 | `hermes_bootstrap.py` | Windows/PowerShell 下强制 UTF-8 stdio 与环境变量，避免中文和特殊字符输出异常。 | 多入口早期导入；Windows 原生是 early beta。 |
| 主 CLI | `hermes_cli/main.py` | 解析 `hermes chat/gateway/setup/acp/model/tools/skills/curator/...` 等命令，初始化日志、配置、profile 与 TUI 环境变量。 | `cmd_chat()` 会同步 bundled skills，并把 `--skills`、`--toolsets`、`--query` 传入 CLI/TUI。 |
| 交互 CLI | `cli.py` | 传统交互 REPL、prompt_toolkit UI、slash command、动态 skill command、工具进度、后台任务显示。 | `HermesCLI` 调用 `AIAgent`；`/skills` 和 `/<skill-name>` 通过 `agent/skill_commands.py` 加载 skill。 |
| Agent 主程序 | `run_agent.py` | `AIAgent` 主循环、模型调用、工具调用、上下文压缩、会话保存、后台 memory/skill review。 | 自我迭代最核心文件。 |
| MCP 服务 | `mcp_serve.py` | 把 Hermes 能力作为 MCP server 暴露。 | 适合被其他 IDE/Agent 调用。 |
| ACP 入口 | `acp_adapter/entry.py`、`acp_adapter/server.py`、`acp_adapter/session.py`、`acp_adapter/tools.py` | 对接 editor/ACP 协议，会话、权限、事件、工具转发。 | `hermes-acp` toolset 也包含 skills 工具。 |
| Gateway 入口 | `gateway/run.py`、`gateway/config.py`、`gateway/session.py`、`gateway/delivery.py` | Telegram/Discord/Slack/WhatsApp/Signal/Email 等平台接入、session 管理、投递路由。 | 让自我迭代能力不局限于本地 CLI。 |
| TUI sidecar | `tui_gateway/entry.py`、`tui_gateway/server.py` | Python sidecar 通过 JSON-RPC 服务 `ui-tui`。 | TUI skills hub、session picker、tool progress 依赖它。 |

核心数据流：用户从 `hermes`、TUI、Gateway、ACP 或 MCP 进入，入口读取 `config.yaml`、profile、toolsets、preloaded skills，构造 `AIAgent`，`AIAgent.run_conversation()` 组装 system prompt 与历史上下文，调用模型，执行工具，压缩上下文，持久化会话，并在满足条件时触发后台 review。

## 3. Agent 核心模块地图

| 模块 | 代码位置 | 做什么 | 关键点 |
| --- | --- | --- | --- |
| 主执行体 | `run_agent.py` | `AIAgent` 初始化 provider、tool registry、memory、context compressor、SessionDB、TodoStore；`run_conversation()` 执行主循环。 | 工具调用支持并发/顺序；`IterationBudget` 控制父子 agent 迭代预算。 |
| 后台 review | `run_agent.py` | `_MEMORY_REVIEW_PROMPT`、`_SKILL_REVIEW_PROMPT`、`_COMBINED_REVIEW_PROMPT`、`_spawn_background_review()`。 | 复杂任务后自动复盘 conversation，必要时调用 `memory` 或 `skill_manage`。 |
| Provider 适配 | `agent/anthropic_adapter.py`、`agent/bedrock_adapter.py`、`agent/codex_responses_adapter.py`、`agent/gemini_*adapter.py`、`agent/copilot_acp_client.py`、`agent/auxiliary_client.py` | 适配 Anthropic、Bedrock、Codex Responses、Gemini、Copilot、辅助模型调用。 | review、压缩、标题、curator 等 side task 可走 auxiliary client。 |
| Prompt 构建 | `agent/prompt_builder.py` | 组装身份、memory guidance、skills guidance、session search guidance、context files、skill index、环境提示。 | `SKILLS_GUIDANCE` 明确要求复杂任务后保存 skill，发现 skill 错误时 patch。 |
| Context 压缩 | `agent/context_compressor.py`、`agent/context_engine.py`、`trajectory_compressor.py` | 摘要中间历史、保护首尾上下文、裁剪旧工具输出、轨迹压缩。 | 长任务不会因上下文溢出丢掉关键“Active Task”。 |
| Memory 编排 | `agent/memory_manager.py`、`agent/memory_provider.py`、`tools/memory_tool.py` | 内置/外部 memory provider 注册、预取、同步、工具 schema 合并。 | memory 保存“用户是谁/稳定偏好”，skill 保存“怎么做”。 |
| 会话持久化 | `hermes_state.py` | SQLite `state.db`，WAL/DELETE fallback，sessions/messages/FTS5，session split。 | `session_search` 和跨会话召回依赖这里。 |
| 工具执行展示 | `agent/display.py`、`agent/tool_guardrails.py`、`agent/file_safety.py`、`agent/redact.py`、`agent/think_scrubber.py` | 工具预览、危险操作 guardrail、敏感路径保护、脱敏、思考内容过滤。 | 避免 review/skill 内容泄漏敏感信息或写坏内部缓存。 |
| 账号/限流/计费 | `agent/account_usage.py`、`agent/rate_limit_tracker.py`、`agent/nous_rate_guard.py`、`agent/usage_pricing.py` | 模型用量、限流、价格估算。 | 后台 review 和 curator 也会产生模型成本，需要被纳入预算。 |
| 用户引导与洞察 | `agent/onboarding.py`、`agent/insights.py`、`agent/title_generator.py`、`agent/manual_compression_feedback.py` | 初始引导、会话洞察、标题、压缩反馈。 | 可为总结 skill 提供产品化入口。 |

## 4. 工具与 Toolset 地图

| 模块 | 代码位置 | 做什么 | 关键点 |
| --- | --- | --- | --- |
| Toolset 定义 | `toolsets.py` | 定义 `web`、`terminal`、`file`、`skills`、`browser`、`cronjob`、`memory`、`delegation`、`hermes-acp`、平台 toolsets 等。 | `skills` toolset = `skills_list`、`skill_view`、`skill_manage`；ACP/CLI 平台也包含这些能力。 |
| 工具 schema 与分发 | `model_tools.py`、`tools/registry.py` | 把工具 schema 注册给模型，并将 tool call 分发到 handler。 | 新增自我迭代工具时应走 registry，不要硬编码到主循环。 |
| 文件工具 | `tools/file_tools.py`、`tools/file_operations.py`、`tools/file_state.py`、`tools/checkpoint_manager.py` | `read_file`、`write_file`、`patch`、`search_files`、staleness 检查、checkpoint。 | skill 创建/维护使用自己的 `skill_manage`；普通项目文件修改走 file tools。 |
| 终端/进程 | `tools/terminal_tool.py`、`tools/process_registry.py`、`tools/environments/*` | 命令执行、后台进程、多后端环境。 | skill 支持文件中的脚本可由终端执行。 |
| Web/Browser | `tools/web_tools.py`、`tools/browser_tool.py`、`tools/browser_*`、`tools/web_providers/` | 搜索、网页抽取、浏览器自动化。 | 研究型 skill 可封装检索流程。 |
| Memory | `tools/memory_tool.py`、`agent/memory_manager.py` | 本地 memory 文件和外部 provider 协调。 | 保存稳定用户偏好，不保存复杂流程。 |
| Skills | `tools/skills_tool.py`、`tools/skill_manager_tool.py`、`tools/skills_hub.py`、`tools/skills_sync.py`、`tools/skills_guard.py` | skill 列表/查看/创建/patch/hub 安装/同步/安全扫描。 | 自我迭代总结的写入和读取基础设施。 |
| Cron | `tools/cronjob_tools.py`、`cron/jobs.py`、`cron/scheduler.py` | 定时任务 CRUD、调度、触发、投递。 | 可把固定总结/复盘任务设为周期运行。 |
| 委派 | `tools/delegate_tool.py` | 生成隔离 subagent 处理复杂子任务。 | 可让 review 或任务执行拆分为并行工作流。 |
| MCP | `tools/mcp_tool.py`、`tools/mcp_oauth.py`、`tools/mcp_oauth_manager.py`、`mcp_serve.py` | MCP 客户端/服务端/OAuth。 | 扩展外部工具，也可让其他 Agent 调用 Hermes。 |
| 通知/平台工具 | `tools/send_message_tool.py`、`tools/discord_tool.py`、`tools/homeassistant_tool.py`、`tools/feishu_*` | 平台消息和外部服务工具。 | Cron/Gateway 总结结果可投递到用户指定平台。 |

## 5. Skills、Memory 与自我迭代闭环

### 5.1 Skill 文件与读取

`tools/skills_tool.py` 是 skill 读取的主模块。它定义 `SKILLS_DIR = ~/.hermes/skills`，支持本地 skills 与 `skills.external_dirs`，使用 `skills_list()` 返回低成本 metadata，用 `skill_view(name, file_path)` 加载 `SKILL.md` 或 `references/`、`templates/`、`scripts/`、`assets/` 支持文件。该模块还做 platform 过滤、frontmatter 解析、setup/env var 提示、prompt injection warning、linked files 返回与 tool registry 注册。

`agent/skill_commands.py` 把 skills 变成 CLI/Gateway 的 slash command。它通过 `skill_view()` 加载内容，做 template vars、inline shell 扩展、技能目录注入、支持文件提示和用户附加指令拼接。也就是说，用户输入 `/<skill-name>`、CLI 预加载 `--skills`、TUI/Gateway 加载 skill，最后都会形成一段可注入对话的 skill payload。

`agent/prompt_builder.py` 会把 compact skill index 注入 system prompt。`SKILLS_GUIDANCE` 的核心约束是：复杂任务、困难错误、非平凡 workflow 完成后要用 `skill_manage` 保存为 skill；加载 skill 时若发现过时、错误或缺失，要立即 patch。

### 5.2 Skill 写入与维护

`tools/skill_manager_tool.py` 是 Agent 管理 skill 的主模块。它支持 `create`、`edit`、`patch`、`delete`、`write_file`、`remove_file`，要求 `SKILL.md` 必须有 YAML frontmatter，包括 `name` 和 `description`，并限制名称、内容长度和支持文件大小。支持文件只能写入 `references/`、`templates/`、`scripts/`、`assets/`。该模块通过 `tools.registry` 注册 `skill_manage`，schema 明确说明 skill 是 procedural memory：保存可复用做法、触发条件、步骤、坑点和验证方式。

关键治理点在 `skill_manager_tool.py` 的 telemetry：只有后台 self-improvement review fork 中的 `skill_manage(action="create")` 会通过 `tools.skill_provenance.is_background_review()` 被标记为 agent-created；前台用户直接创建的 skill 属于用户，不进入 curator 自动治理范围。`patch/edit/write_file/remove_file` 会 bump patch 计数，`delete` 会清理记录。Pinned skill 禁止删除，但允许 patch/edit。

### 5.3 Skill 使用遥测与 Curator

`tools/skill_usage.py` 用 `~/.hermes/skills/.usage.json` sidecar 记录 skill 使用、查看、patch、created_at、state、pinned、archived_at 等信息。它区分 `active`、`stale`、`archived`，并通过 provenance 只把 agent-created skill 纳入治理。它还提供 `archive_skill()`、`restore_skill()`、`agent_created_report()`、`set_pinned()` 等 curator 需要的接口。

`agent/curator.py` 是周期性 skill 维护编排器。它按默认 7 天 interval、2 小时 idle、30 天 stale、90 天 archive 运行；只处理 agent-created skills，不碰 bundled/hub/manual skills；不会自动删除，只会 archive；pinned skills 跳过自动迁移。Curator 会先做不需要 LLM 的 `apply_automatic_transitions()`，再在需要时 spawn 一个后台 review agent，根据 skill 内容聚类、合并 umbrella skill、把窄技能降级为 `references/`/`templates/`/`scripts/`，或 archive 过窄/过期技能。

### 5.4 Memory 与 Session

`tools/memory_tool.py` 管理内置 memory，`agent/memory_manager.py` 统一内置和外部 provider。Memory 用于保存用户偏好、环境事实、长期稳定约定；skill 用于保存“如何做某类任务”。`hermes_state.py` 使用 SQLite 和 FTS5 保存所有 session/messages；`tools/session_search_tool.py` 基于这个存储提供会话搜索和 LLM 摘要召回。`agent/context_compressor.py` 负责长上下文摘要，防止 review 或长任务丢失关键状态。

## 6. 自我迭代总结 Skill 的核心代码链路

| 阶段 | 触发/数据 | 代码位置 | 说明 |
| --- | --- | --- | --- |
| 任务执行 | 用户消息、system prompt、skill index、memory context、工具结果 | `run_agent.py::AIAgent.run_conversation()` | 主循环记录完整 messages。 |
| 计数触发 | `_iters_since_skill`、`_skill_nudge_interval`，默认约 10 个 tool-calling iterations | `run_agent.py` | 当有 `skill_manage` 工具且达到阈值时触发 skill review。 |
| Review prompt 选择 | memory review、skill review 或 combined review | `run_agent.py::_MEMORY_REVIEW_PROMPT`、`_SKILL_REVIEW_PROMPT`、`_COMBINED_REVIEW_PROMPT` | Combined prompt 同时判断用户事实和可复用 workflow。 |
| 后台 fork | `messages_snapshot`、review prompt、独立 session/messages | `run_agent.py::_spawn_background_review()` | 不阻塞前台回答，用后台 Agent 复盘本轮会话。 |
| Skill 读写 | `skills_list`、`skill_view`、`skill_manage` | `tools/skills_tool.py`、`tools/skill_manager_tool.py` | Review agent 优先 patch loaded/current skill，其次更新 umbrella，再创建新 class-level skill 或写支持文件。 |
| Provenance 标记 | `is_background_review()` | `tools/skill_provenance.py`、`tools/skill_usage.py` | 只有后台 review 创建的 skill 会被标记 agent-created。 |
| 生命周期治理 | usage sidecar、stale/archive/pin | `tools/skill_usage.py`、`agent/curator.py` | 后续按使用情况合并、归档、恢复、pin/unpin。 |
| 用户可见性 | CLI/TUI/Gateway 显示后台摘要、skills hub、curator 命令 | `cli.py`、`ui-tui/`、`hermes_cli/main.py`、`agent/curator.py` | 用户可看到/运行 curator，也能浏览 skill。 |

可以抽取的最小闭环是：`AIAgent.run_conversation()` 中维护 `messages_snapshot` 与触发条件，调用 `_spawn_background_review()`，让 review agent 只能使用 `memory` 和 `skills` 工具集；review prompt 复用 `_COMBINED_REVIEW_PROMPT` 的策略；skill 写入复用 `skill_manage` 的 create/patch/write_file；skill 生命周期复用 `skill_usage` 的 agent-created 标记和 `curator` 的整理逻辑。

## 7. Gateway、Cron 和 Routine 自动化

| 模块 | 代码位置 | 做什么 | 对抽取的价值 |
| --- | --- | --- | --- |
| Gateway core | `gateway/__init__.py`、`gateway/config.py`、`gateway/session.py`、`gateway/delivery.py`、`gateway/run.py` | 多平台消息接入、session key、home channel、reset policy、投递路由。 | 自我总结结果可以通过平台投递。 |
| 平台适配 | `gateway/platforms/*`、`plugins/platforms/*` | Telegram、Discord、Slack、WhatsApp、Google Chat、IRC 等平台适配。 | 抽取时不需要全量迁移，但应保留抽象边界。 |
| Streaming | `gateway/stream_consumer.py` | 把同步 Agent streaming callback 转成平台异步编辑消息。 | 后台总结不应打断前台流式输出。 |
| Cron job | `cron/jobs.py`、`cron/scheduler.py`、`tools/cronjob_tools.py` | 解析 cron/human interval，执行自然语言任务，支持 script 预处理和 deliver。 | 可把“每周整理 skill/总结运行经验”做成 routine。 |
| Routine 文档 | `hermes-already-has-routines.md` | 说明 Hermes 已支持 scheduled、GitHub webhook、API triggers、script injection、multi-skill workflows。 | 为 stocker 后续常驻复盘/总结任务提供产品参考。 |

## 8. UI、文档与辅助模块

| 模块 | 代码位置 | 做什么 | 对抽取的价值 |
| --- | --- | --- | --- |
| TUI | `ui-tui/src/entry.tsx`、`ui-tui/src/gatewayClient.ts`、`ui-tui/src/app/*`、`ui-tui/src/components/*` | React + Ink 终端 UI，JSON-RPC 连接 Python sidecar，支持 streaming、slash、session picker、skills hub。 | 可参考如何展示 skill 管理、后台任务和会话状态。 |
| TUI gateway | `tui_gateway/*` | Python 侧 JSON-RPC 服务，驱动 Agent session/tools/model。 | 抽取 UI 时需保留前后端协议。 |
| Web dashboard | `web/*`、`hermes_cli/web*` | Web 管理/展示入口。 | 对 stocker 暂时是参考，不是抽取核心。 |
| 文档站 | `website/docs/*`、`website/scripts/*` | Docusaurus 文档、技能文档生成、LLMs txt 生成。 | 后续写 skill 使用说明时可参考文档组织。 |
| 本地化 | `locales/*`、`agent/i18n.py` | 多语言文案。 | 中文化自我迭代 skill 时可参考。 |
| Release notes | `RELEASE_v*.md` | 历史功能变更。 | 追踪 curator/skills/gateway/routine 的演进背景。 |

## 9. Provider、插件、环境和训练模块

| 模块 | 代码位置 | 做什么 | 对抽取的价值 |
| --- | --- | --- | --- |
| Provider 插件 | `plugins/model-providers/*`、`providers/` | OpenRouter、Gemini、Bedrock、custom 等 provider 插件。 | 自我 review 可用辅助模型，但 stocker 可先固定一个模型。 |
| Memory/context 插件 | `plugins/memory/*`、`plugins/context_engine/*` | 外部 memory、context engine 扩展。 | 可先保留接口思想，暂不迁移插件生态。 |
| Observability | `plugins/observability/*` | Langfuse 等观测插件。 | 后续评估总结质量时可参考。 |
| Teams/Kanban | `plugins/teams_pipeline/*`、`plugins/kanban/*`、`tools/kanban_tools.py` | 多 agent/team/pipeline/看板。 | 不是最小闭环必需，但适合复杂迭代组织。 |
| Batch runner | `batch_runner.py` | 并行跑数据集 prompt，保存 trajectory、stats、checkpoint。 | 可把总结 skill 的运行样本保存为训练数据。 |
| RL environments | `environments/*`、`rl_cli.py`、`tinker-atropos/` | Atropos 环境、web research、SWE/agent loop、reward。 | 不参与产品抽取第一阶段。 |
| Mini SWE | `mini_swe_runner.py` | SWE 风格任务执行。 | 可作为代码修改类 skill 的评估样例。 |

## 10. 后续抽取建议

第一阶段只抽取最小可用的“运行后总结→生成/修订 skill”闭环，不要迁移 Hermes 全生态。建议目标模块包括：一个 `ReviewTrigger` 记录本轮 messages、工具调用次数和是否达到阈值；一个 `SelfImprovementReviewer` 使用固定 prompt 复盘本轮；一个 `SkillStore` 管理 `SKILL.md`、frontmatter、`references/`、`templates/`、`scripts/`；一个 `SkillUsageStore` 记录 agent-created、view/patch/use、pinned/stale/archive；一个 `SkillCurator` 做周期性整理。

第二阶段再加入会话搜索和 memory。此时可参考 `hermes_state.py` 的 SQLite + FTS5、`agent/context_compressor.py` 的摘要模板、`tools/memory_tool.py` 的 USER/MEMORY 分离。注意边界：memory 存用户偏好和长期事实，skill 存可复用流程和验证脚本。

第三阶段再考虑 Cron/Gateway routine 化，把“每周复盘预警/交易/开发会话并更新 skill/backlog”做成计划任务；此阶段可以参考 `cron/*`、`gateway/*` 和 `hermes-already-has-routines.md` 的 script injection、multi-skill workflow、deliver anywhere 设计。

## 11. 已发现的维护注意点

中文 README 的 Windows 描述仍写“原生 Windows 不受支持”，英文 README 则写 native Windows early beta；后续引用 Hermes 能力时应以英文 README 和当前代码为准。`hermes-agent` 体量很大，`run_agent.py`、`cli.py` 都是超大文件，抽取时不要复制整文件，应按“review prompt/trigger/skill store/usage/curator”切薄。`.codebuddy` 是项目数据，不要当临时缓存清理。Hermes 的后台 review 创建 skill 与前台用户创建 skill 的 provenance 区分很关键，迁移时必须保留，否则自动 curator 可能误归档用户手写技能。

## References

1. [Hermes Agent README](../../hermes-agent/README.md)
2. [Hermes Agent 中文 README](../../hermes-agent/README.zh-CN.md)
3. [Hermes routines comparison](../../hermes-agent/hermes-already-has-routines.md)
4. [Hermes pyproject entry points](../../hermes-agent/pyproject.toml)
5. [AIAgent runtime](../../hermes-agent/run_agent.py)
6. [Prompt builder](../../hermes-agent/agent/prompt_builder.py)
7. [Skill read tool](../../hermes-agent/tools/skills_tool.py)
8. [Skill manager tool](../../hermes-agent/tools/skill_manager_tool.py)
9. [Skill usage telemetry](../../hermes-agent/tools/skill_usage.py)
10. [Skill curator](../../hermes-agent/agent/curator.py)
11. [Memory manager](../../hermes-agent/agent/memory_manager.py)
12. [Context compressor](../../hermes-agent/agent/context_compressor.py)
13. [Session state store](../../hermes-agent/hermes_state.py)
14. [Toolsets](../../hermes-agent/toolsets.py)
