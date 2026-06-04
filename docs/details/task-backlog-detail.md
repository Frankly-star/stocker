# Stocker task backlog detail

最后维护：2026-05-10 23:07

本文件承接 `docs/task-map.md` 不再承载的细粒度 backlog。主 task-map 只保留用户需求域；本文件维护具体任务、优先级、状态、涉及文件和验收标准。

状态：`todo`、`doing`、`blocked`、`review`、`done`、`won't-do`。优先级：`P0` 影响运行、安全、交易或主链路正确性；`P1` 明显影响交易辅助效果；`P2` 结构优化、体验增强和技术债。

## 可信数据与分析

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| DATA-001 | P0 | done | 统一分析缓存读取路径。 | `src/stocker/agents/supervisor.py`、`src/stocker/api/routes.py`、`tests/test_analysis_cache_reports.py` | `/api/v1/reports` 能展示 `data/analysis_cache/{ticker}_latest.json`，并忽略 `data/analysis_cache.json`、`data/report_*.json` 旧路径。 |
| DATA-002 | P0 | done | 固定主数据链路，移除主分析流程中的兼容 fallback 和多源并行。 | `src/stocker/agents/intelligence/data_fetcher.py`、`src/stocker/graphs/intelligence_graph.py`、`src/stocker/api/app.py`、`src/stocker/agents/supervisor.py`、`src/stocker/api/routes.py`、`src/stocker/utils/data_helpers.py` | K线/行情/基础数据仅走 westock-data，新闻仅走 finance-news RSS；主源失败只暴露 warnings，不自动切 yfinance、TradingAgents、DDG、Futu 或 DataRouter。 |
| DATA-003 | P2 | todo | 继续统一非投研边界的 ticker 格式转换工具。 | `integrations/futu/mappers.py`、`agents/intelligence/data_fetcher.py` | Futu 交易边界和 westock 投研边界各自清晰，有示例验证。 |

## 持续运行与通知

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| RUN-001 | P0 | done | 建立常驻监控循环，按交易时段/用户监控窗口持续扫描持仓、观察股和关键事件。 | `src/stocker/api/app.py`、`src/stocker/engine/runtime_state.py`、`src/stocker/monitoring/*`、`src/stocker/api/routes.py` | 服务启动后无需用户打开页面也会持续运行；支持配置扫描间隔和启停状态；`/status` 与 `/monitoring` 可查看运行状态。 |
| RUN-002 | P0 | done | 建立预警通知、去重和冷却机制，避免重大事件漏报或重复刷屏。 | `src/stocker/alerts/store.py`、`src/stocker/alerts/models.py`、`src/stocker/api/routes.py`、`src/stocker/monitoring/loop.py` | 同一触发条件在冷却期内不重复提醒；新严重事件立即入队；预警可查询、可标记已处理。 |
| RUN-003 | P0 | done | 建立常驻运行健康检查和恢复策略。 | `src/stocker/api/routes.py`、`src/stocker/api/app.py`、`src/stocker/engine/runtime_state.py`、`src/stocker/monitoring/loop.py` | `/status` 能显示监控循环是否运行、最近扫描时间、失败原因；异常失败会记录并继续下一轮。 |
| RUN-004 | P0 | done | 在 Web UI 直接展示系统是否自动运行。 | `src/stocker/web/templates/index.html`、`src/stocker/web/static/js/app.js`、`src/stocker/web/static/css/style.css` | 页面顶部和侧边栏可看到“监控运行中/扫描中”、周期、轮次、新预警、持仓预警、broker 和执行模式；运行模式页也有常驻监控状态。 |

## 模拟盘实跑闭环

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| PAPER-001 | P0 | done | 建立 westock 数据本地模拟盘验收路径：读取本地模拟账户/持仓、用 westock 行情或受控价格执行一笔模拟订单。 | `src/stocker/api/routes.py`、`src/stocker/paper/westock_sim.py`、`src/stocker/utils/data_helpers.py`、`src/stocker/portfolio/store.py`、`src/stocker/broker/trade_store.py` | `/paper/status` 可读取 westock-paper 本地模拟账户/持仓；`/paper/validate` 不调用券商路径，支持受控模拟下单并持久化交易记录、更新持仓。 |
| PAPER-002 | P0 | done | 将预警/交易建议转为“待确认 westock 模拟交易计划”，用户确认后才进入本地模拟盘执行。 | `src/stocker/trade_plan/*`、`src/stocker/api/routes.py`、`src/stocker/paper/westock_sim.py`、`src/stocker/alerts/*` | 预警不会直接下单；每次模拟下单都有来源预警、计划、确认动作、执行结果，不调用券商路径。 |
| PAPER-003 | P0 | todo | 模拟盘交易后同步持仓、波段记录和交易历史，形成可复盘闭环。 | `src/stocker/api/routes.py`、`src/stocker/portfolio/store.py`、`src/stocker/swing/store.py`、`src/stocker/broker/trade_store.py` | 下单结果能持久化；持仓/波段状态随成交更新；服务重启后仍可查看。 |

## 持仓预警与操作建议

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| ALERT-001 | P0 | done | 建立持仓预警模型：按持仓成本、现价、支撑/压力、止损/止盈、趋势破位输出分级预警。 | `src/stocker/alerts/position_alerts.py`、`src/stocker/alerts/models.py`、`src/stocker/portfolio/store.py`、`src/stocker/analysis/swing_signals.py` | 对每个持仓输出 `risk_level`、`trigger`、`suggested_action`、`price_level`、`reason`；区分 `must_act`、`watch`、`normal`。 |
| ALERT-002 | P0 | done | 提供持仓预警 API 和 Supervisor 工具，让用户随时看到当前最需要处理的持仓。 | `src/stocker/api/routes.py`、`src/stocker/agents/supervisor.py`、`src/stocker/alerts/*` | `/api/v1/alerts/positions` 返回按严重程度排序的持仓预警；聊天可通过 `get_position_alerts()` 查询“现在哪些持仓要处理”。 |
| ALERT-003 | P0 | done | 将持仓预警接入常驻监控循环，但只做提醒，不默认自动交易。 | `src/stocker/api/app.py`、`src/stocker/engine/runtime_state.py`、`src/stocker/monitoring/*`、`src/stocker/alerts/*` | 常驻循环能持续生成预警摘要；预警只入队和展示，不直接下单。 |

## 关键事件预警

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| EVENT-001 | P0 | todo | 从新闻/公告/评级/财务/资金流中抽取关键事件，并关联到持仓和股票池。 | `src/stocker/agents/intelligence/data_fetcher.py`、`src/stocker/agents/factory.py`、`src/stocker/analysis/models.py`、可新增 `src/stocker/events/*` | 输出事件类型、影响标的、影响方向、紧急程度、建议动作；能解释为什么需要看。 |
| EVENT-002 | P0 | todo | 对价格跳空、跌破支撑、突破压力、成交/资金异常建立事件化预警。 | `src/stocker/utils/data_helpers.py`、`src/stocker/analysis/swing_signals.py`、`src/stocker/watchlist/scanner.py`、可新增 `src/stocker/monitoring/*` | 常驻监控对持仓和观察股生成价格事件，不依赖人工打开单股报告。 |
| EVENT-003 | P1 | todo | 建立事件历史和已读/已处理状态，方便复盘。 | 可新增 `src/stocker/events/store.py`、`src/stocker/api/routes.py` | 事件可持久化、列表展示、标记已处理；重启不丢。 |

## 感兴趣方向推荐

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| RECO-001 | P1 | todo | 增加“关注方向/主题/行业/市场”配置和存储。 | `src/stocker/watchlist/store.py`、可新增 `src/stocker/interests/*`、`src/stocker/api/routes.py` | 用户能维护关注方向，如 AI、半导体、港股互联网、高股息；系统能持久化。 |
| RECO-002 | P1 | todo | 基于固定行情和新闻主源，为关注方向输出少量候选股和入池理由。 | `src/stocker/agents/supervisor.py`、`src/stocker/agents/intelligence/data_fetcher.py`、`src/stocker/watchlist/scanner.py` | 每个方向最多给 3-5 个候选；每个候选必须有数据依据、风险点和后续观察条件。 |
| RECO-003 | P1 | todo | 将候选推荐与股票池联动：一键加入观察池并生成初始交易计划。 | `src/stocker/api/routes.py`、`src/stocker/watchlist/store.py`、前端股票池页 | 推荐结果能进入 watchlist，并带入推荐理由、触发条件和失效条件。 |

## 股票池与交易计划

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| PLAN-001 | P1 | todo | 为观察股维护交易计划：买入区间、止损、止盈、加仓/减仓条件、计划失效条件。 | `src/stocker/watchlist/store.py`、`src/stocker/swing/models.py`、`src/stocker/swing/store.py` | 每只观察股可保存结构化计划；扫描预警能引用计划字段。 |
| PLAN-002 | P1 | todo | 股票池扫描从“信号列表”升级为“计划状态”：等待、接近买点、触发、失效。 | `src/stocker/watchlist/scanner.py`、`src/stocker/analysis/swing_signals.py`、前端股票池页 | 用户能快速看到哪些观察股接近操作点，哪些不再值得跟踪。 |

## 安全交易闭环

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| TRADE-001 | P1 | todo | 持久化交易历史，替换 API 内存 `_trade_history`。 | `src/stocker/api/routes.py`、`src/stocker/broker/trade_store.py`、`src/stocker/broker/models.py` | `/api/v1/trades` 重启后仍可读取历史；下单结果统一写入 `TradeStore`。 |
| TRADE-002 | P1 | todo | 对交易执行链路做单一事实源梳理。 | `src/stocker/api/routes.py`、`src/stocker/graphs/execution_graph.py`、`src/stocker/agents/supervisor.py` | 交易校验、价格补全、下单、持仓/波段/交易记录更新职责边界明确。 |

## 持续迭代与复盘

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| ITER-001 | P1 | todo | 建立“预警→建议→模拟交易→结果”的运行日志和指标。 | 可新增 `src/stocker/review/*`、`src/stocker/api/routes.py`、相关 store | 能按周/月查看预警次数、确认次数、模拟成交、胜率、盈亏、误报/漏报标记。 |
| ITER-002 | P1 | todo | 为预警和推荐增加人工反馈：有用/无用/太晚/误报/漏报。 | `src/stocker/api/routes.py`、前端预警/报告页、可新增 `src/stocker/review/store.py` | 用户反馈能持久化，并能反向影响后续任务优先级和规则调整。 |
| ITER-003 | P1 | todo | 建立迭代看板，明确下一轮优先修哪个规则或能力。 | `docs/task-map.md`、`docs/details/task-backlog-detail.md`、可新增 review API | 每轮模拟盘运行后能输出“最该改的 3 个问题”，避免只堆功能。 |

## 自我迭代总结 skill

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| SKILL-ITER-001 | P1 | done | 梳理 `hermes-agent` 模块级代码地图，明确自我迭代总结 skill 的核心代码位置。 | `docs/details/research_report_hermes_agent_code_map.md`、`docs/code-dev-map.md`、`docs/task-map.md` | 文档说明每个主要模块在哪里、做什么，并标出 `run_agent.py`、`skill_manager_tool.py`、`skills_tool.py`、`skill_usage.py`、`curator.py` 等抽取重点。 |
| SKILL-ITER-002 | P1 | done | 抽取最小“会话复盘→skill 创建/patch”闭环设计。 | `src/stocker/evolution/models.py`、`src/stocker/evolution/adapters/stocker_reviewer.py`、`src/stocker/evolution/adapters/patch_store.py`、`src/stocker/api/routes.py` | 有明确数据模型、触发条件、review prompt、skill 文件结构和最小 API 入口，不迁移 Hermes 全量生态。 |
| SKILL-ITER-003 | P1 | done | 建立 skill usage telemetry 和 curator 生命周期治理。 | `src/stocker/evolution/hermes_compat/skill_usage.py`、`src/stocker/evolution/hermes_compat/curator.py`、`src/stocker/evolution/adapters/weekly_review.py` | 区分后台自动生成 skill 与用户手写 skill；支持 use/view/patch 计数、pinned、stale、archive，不自动删除用户资产。 |
| EVOLVE-001 | P1 | done | 建立通用 `EvolutionSkill` 模型和 Hermes-compatible skill 存储。 | `src/stocker/evolution/models.py`、`src/stocker/evolution/hermes_compat/*`、`tests/test_evolution_core.py` | 支持 domain/team/node/status/version/frontmatter/body/provenance，能创建、读取、patch、归档，并和普通用户资产区分。 |
| EVOLVE-002 | P1 | done | 建立 `PromptResolver`，把团队策略 skill 注入 LangGraph 节点 prompt。 | `src/stocker/evolution/adapters/langgraph_prompt_resolver.py`、`src/stocker/agents/factory.py`、`src/stocker/agents/risk/*`、`src/stocker/graphs/main_graph.py` | 默认行为不变；有 active skill 时能按 team/node 注入，并记录 skill_version/prompt_hash。 |
| EVOLVE-003 | P1 | done | 建立 LangGraph `TraceStore`，采集团队节点运行轨迹。 | `src/stocker/evolution/adapters/trace_store.py`、`src/stocker/agents/factory.py`、`src/stocker/agents/risk/*`、`src/stocker/graphs/main_graph.py` | 每个已接入团队节点运行后可记录输入摘要、输出摘要、策略版本、data warning、决策元数据。 |
| EVOLVE-004 | P1 | done | 将 `Reflector` 升级为“案例记忆 + 策略 patch 草案”双输出。 | `src/stocker/memory/reflector.py`、`src/stocker/evolution/adapters/stocker_reviewer.py`、`tests/test_evolution_validator_reviewer.py` | 复盘后既可写 BM25 案例，也可生成可审核 `SkillPatchDraft`，且不会自动应用。 |
| EVOLVE-005 | P1 | done | 对 `trader`、`portfolio_manager`、Supervisor 执行路由的策略 patch 增加安全验证和人工确认策略。 | `src/stocker/evolution/adapters/stocker_validator.py`、`src/stocker/evolution/adapters/approval_policy.py`、`tests/test_evolution_validator_reviewer.py` | 高风险策略不能自动 active；校验器会拒绝禁用数据源/执行绕过，并要求审批。 |
| EVOLVE-006 | P2 | done | 实现 strategy curator 和周复盘。 | `src/stocker/evolution/hermes_compat/curator.py`、`src/stocker/evolution/adapters/weekly_review.py`、`src/stocker/api/routes.py`、`docs/details/hermes-evolution-sync-notes.md` | 已实现 pinned/stale/archive 的确定性 curator，并提供 `/evolution/curator/run` 与 `/evolution/review/weekly` API。 |
| EVOLVE-007 | P1 | done | 将高风险 patch 激活绑定模拟盘/回测验证结果。 | `src/stocker/evolution/adapters/patch_store.py`、`src/stocker/api/routes.py`、`tests/test_evolution_api.py` | `trader`、`portfolio_manager`、Supervisor 高风险 patch 只有在人工审批且关联 `paper:`/`backtest:` 证据后才能 apply。 |
| EVOLVE-008 | P2 | done | 增加 EvolutionSkill 前端管理视图。 | `src/stocker/web/static/js/app.js`、`src/stocker/web/static/js/api.js`、`src/stocker/web/static/js/router.js`、`src/stocker/web/templates/index.html` | 用户能在页面查看 active/draft skills、trace、patch 草案、周复盘，并执行审批/应用。 |
| EVOLVE-009 | P2 | todo | 完善 LLM curator 与自动证据生成。 | `src/stocker/evolution/adapters/weekly_review.py`、可新增 `src/stocker/evolution/adapters/llm_curator.py`、`src/stocker/backtest/*` | 能自动把具体案例降级为 references、合并过窄 skill，并把模拟盘/回测结果转成 patch evidence。 |

## 策略验证与回测

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| BT-001 | P2 | todo | 修复回测 API 前缀重复。 | `src/stocker/api/routes.py`、前端调用处 | 后端主路径为 `/api/v1/backtest`，不再是 `/api/v1/api/v1/backtest`。 |
| REVIEW-001 | P2 | todo | 建立预警/推荐/交易结果复盘视图。 | `src/stocker/api/routes.py`、`src/stocker/web/static/js/app.js`、相关 store | 能看到每次预警后是否触发交易、收益如何、规则是否有效。 |

## 系统运行与可观测

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| START-001 | P2 | todo | 统一 FutuRuntime/Broker 生命周期，避免 `StockerService` 与 `api.app._build_supervisor_graph()` 重复启动。 | `src/stocker/api/app.py`、`src/stocker/engine/service.py`、`src/stocker/broker/factory.py` | `stocker serve` 与 `python runserver.py` 均只有一条清晰初始化路径；shutdown 只释放一次。 |
| OPS-001 | P2 | todo | 日志读取与日志配置模块化。 | `api/app.py`、`api/routes.py`、可新增 `utils/logging.py` | 日志初始化、读取、路径配置集中。 |
| OPS-002 | P2 | todo | 为核心链路补最小回归测试。 | `tests/`、`pyproject.toml` | 可通过 `pytest` 运行；覆盖配置、store、API router、ticker 转换、执行模式保护。 |

## 代码精简与模块边界

| ID | 优先级 | 状态 | 任务 | 涉及文件 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| CLEAN-001 | P2 | todo | 拆分 `api/routes.py`，按领域建立 routers。 | `src/stocker/api/routes.py`、`src/stocker/api/*` | 单文件显著变小；`create_router()` 只负责聚合；原有接口兼容。 |
| CLEAN-002 | P2 | todo | 拆分 `web/static/js/app.js`，按页面或领域模块拆分。 | `src/stocker/web/static/js/app.js`、`router.js`、`index.html` | 聊天、股票池、交易、日志、策略等页面逻辑独立；页面功能不回归。 |
| CLEAN-003 | P2 | todo | 判断根目录 `langgraph/` 是否为必要 vendored 资源。 | `langgraph/`、`pyproject.toml`、README | 若未被引用，文档标注用途或移出主维护范围；不误删项目数据。 |
| CLEAN-004 | P2 | todo | 判断根目录 `TradingAgents/` 是否仍需保留为 legacy 资源。 | `TradingAgents/`、`src/stocker/skills/trading_agents.py` | 明确保留/删除/外置策略；不得重新接入主投研数据链路。 |
| CLEAN-005 | P2 | todo | README 与 map 同步，避免架构说明过期。 | `README.md`、`docs/code-dev-map.md`、`docs/task-map.md` | README 保留用户向说明，map 保留 agent 维护说明。 |

## 已完成

| ID | 完成时间 | 任务 | 产出 |
| --- | --- | --- | --- |
| DONE-001 | 2026-05-07 20:52 | 建立项目维护地图。 | 新增 `docs/code-dev-map.md` 与 `docs/task-map.md`。 |
| DONE-002 | 2026-05-07 21:06 | 将主 map 重构为最高维用户视角，迁移细粒度内容。 | 新增 `docs/details/code-dev-detail-map.md` 与本文件。 |
| DONE-003 | 2026-05-07 21:51 | 收敛可信数据链路为固定主源且无 fallback。 | `DataFetcher`、Supervisor quote/discovery/watchlist、API quote/watchlist scan 均对齐 westock-data + finance-news RSS；新增 `tests/test_market_data_source_policy.py`。 |
| DONE-004 | 2026-05-07 22:41 | 统一分析缓存读取路径。 | `AnalysisCache` 新增 `list_latest()`，`/api/v1/reports` 改为读取 `data/analysis_cache/*_latest.json`；新增 `tests/test_analysis_cache_reports.py`。 |
| DONE-005 | 2026-05-07 22:50 | 重排区间/波段交易产品优先级。 | 明确 P0 为持仓预警、关键事件预警、可信数据与安全边界；P1 为方向推荐、股票池交易计划和交易记录；P2 为回测、可观测和架构优化。 |
| DONE-006 | 2026-05-07 23:09 | 修正为持续运行模式。 | 新增 `RUN-001/002/003`：常驻监控循环、预警通知/去重/冷却、运行健康检查。 |
| DONE-007 | 2026-05-08 21:14 | 完成 RUN-001 与 PAPER-001 最小实跑闭环。 | 新增常驻监控循环、`/monitoring`、`/paper/status`、`/paper/validate`、持久化交易记录接入和 `tests/test_run_paper_validation.py`。 |
| DONE-008 | 2026-05-08 21:31 | 完成 RUN-002 与 ALERT-001。 | 新增 `alerts` 模块、持仓预警模型、预警去重/冷却/已处理状态、`/alerts/positions` API、Supervisor 预警工具和 `tests/test_alerts.py`。 |
| DONE-009 | 2026-05-08 22:55 | 将 PAPER-001 改为 westock 数据本地模拟盘。 | 新增 `src/stocker/paper/westock_sim.py`，`/paper/status` 和 `/paper/validate` 不再调用 broker/Futu，使用 westock quote、本地持仓和 `TradeStore`。 |
| DONE-010 | 2026-05-10 14:20 | 梳理 Hermes Agent 代码地图。 | 新增 `docs/details/research_report_hermes_agent_code_map.md`，并在主 map 中标出自我迭代总结 skill 的抽取方向。 |
| DONE-011 | 2026-05-10 19:32 | 规划 LangGraph 团队策略自我进化融合。 | 新增 `docs/details/langgraph-hermes-evolution-fusion-plan.md`，明确团队策略 skill、PromptResolver、TraceStore、Reviewer、Curator 分阶段落地。 |
| DONE-012 | 2026-05-10 21:33 | 落地通用 EvolutionSkill runtime 最小闭环。 | 新增 `src/stocker/evolution`、Hermes-compatible skill core、Stocker adapters、LangGraph 节点 prompt 注入、TraceStore、Reviewer/Validator 和 evolution 单元测试。 |
| DONE-013 | 2026-05-10 22:26 | 补齐 EvolutionSkill 管理 API 和周复盘。 | 新增 `patch_store.py`、`seed.py`、`weekly_review.py`、`/evolution/*` API 和 `tests/test_evolution_api.py`，覆盖种子 skill、patch 校验/审批/应用、周复盘。 |
| DONE-014 | 2026-05-10 23:07 | 完成高风险 patch 证据门禁和前端管理视图。 | `PatchStore.apply()` 对高风险 patch 强制要求审批和 `paper:`/`backtest:` 证据；新增前端 `#evolution` 页面查看 skills、patches、traces、周复盘并执行校验/审批/应用。 |
| DONE-015 | 2026-05-11 15:14 | 增强 Web 自动运行状态可视化。 | 顶部 runtime pill、侧边栏运行详情和运行模式页状态网格直接展示常驻监控是否运行、周期、轮次、预警数、broker 和执行模式。 |

## 维护记录

| 时间 | 变更 |
| --- | --- |
| 2026-05-07 21:06 | 从主 `task-map.md` 迁移细粒度 P0/P1/P2 backlog，并按用户需求域重新分组。 |
| 2026-05-07 21:51 | 将 `DATA-002` 调整并完成为“固定主数据链路、移除兼容 fallback”，同步新增回归测试记录。 |
| 2026-05-07 22:41 | 完成 `DATA-001`：`/api/v1/reports` 统一读取 canonical analysis cache，并新增回归测试。 |
| 2026-05-07 22:50 | 按区间/波段交易辅助驾驶舱重排 backlog：新增持仓预警、关键事件预警、方向推荐和交易计划任务。 |
| 2026-05-07 23:09 | 根据用户反馈将系统定位修正为持续运行，新增常驻监控、通知去重冷却和健康检查 P0 任务。 |
| 2026-05-08 21:14 | 完成 `RUN-001` 和 `PAPER-001`：常驻监控循环启动、状态 API、模拟盘状态检查和受控下单验收。 |
| 2026-05-08 21:31 | 完成 `RUN-002` 和 `ALERT-001`：持仓预警模型接入常驻监控，支持去重/冷却、查询和标记已处理。 |
| 2026-05-08 22:55 | 根据用户反馈将模拟盘路径改为 westock 数据本地模拟，不再调用券商/Futu broker 路径。 |
| 2026-05-08 23:38 | 完成 `PAPER-002`：持仓预警可生成待确认 westock 模拟交易计划，用户确认后执行本地模拟盘。 |
| 2026-05-10 14:20 | 新增 `hermes-agent` 代码地图和“自我迭代总结 skill”抽取 backlog。 |
| 2026-05-10 19:32 | 新增 LangGraph 团队策略自我进化融合规划和 `EVOLVE-*` backlog。 |
| 2026-05-10 21:33 | 完成通用 `EvolutionSkill` runtime 最小落地：Hermes-compatible core、Stocker adapters、LangGraph 节点注入、TraceStore 与核心测试。 |
| 2026-05-10 22:26 | 补齐 EvolutionSkill 管理 API、默认种子 skill、patch 审批/应用、确定性周复盘和 API 测试。 |
| 2026-05-10 23:07 | 完成高风险 patch 证据门禁和 `#evolution` 前端管理视图，新增 EVOLVE-009 后续任务。 |
| 2026-05-11 15:14 | 根据实跑反馈完成 RUN-004：Web UI 直接展示常驻监控自动运行状态和最近预警摘要。 |
