# Stocker code-dev detail map

最后维护：2026-05-10 23:07

本文件承接 `docs/code-dev-map.md` 不再承载的细粒度代码地图。主 map 只看用户能力与模块边界；本文件记录入口、文件、API、存储、数据流和已知冗余点。

## 对话式投研助手

用户入口：Web `chat` 页面、CLI `stocker chat`、API `/api/v1/chat` 与 `/api/v1/chat/stream`。核心代码为 `src/stocker/api/routes.py` 中 chat/SSE 逻辑、`src/stocker/agents/supervisor.py` 中 `create_supervisor_tools()` 与系统提示词、`src/stocker/graphs/main_graph.py` 的 ReAct 工具循环、`src/stocker/web/static/js/app.js` 的聊天和 SSE 展示。

维护关注：`_conversation_history` 是进程内全局状态，后续需要 session 隔离或明确单用户假设；CLI 与 Web 的图装配不一致，需复用同一构建逻辑。

## 市场机会发现与数据获取

核心代码：`src/stocker/agents/supervisor.py` 的 `discover_market_opportunities`、`get_realtime_quote`、`scan_watchlist_signals`，以及 `src/stocker/agents/intelligence/data_fetcher.py`。固定数据源策略：K线、行情、技术指标、财务、资金流、评级只走 `src/stocker/skills/westock_data.py`；个股新闻和全局市场新闻只走根目录 `skills/finance-news-1.0.1` 的 RSS 能力。

维护关注：主链路不做兼容 fallback；Futu 只保留交易/券商连接边界；`DataRouter`、dataflow tools、yfinance、TradingAgents、DDG 不进入主分析链路。主源失败时通过 `shared_data.data_warnings` 和 `MarketIntelligenceReport.data_warnings` 显式暴露。

## 单股分析报告

核心链路：`run_intelligence(ticker)` → `graphs/intelligence_graph.py` → `data_fetcher` → `market_data/news/fundamentals/social` → `aggregate` → `MarketIntelligenceReport`。`AnalysisCache` 统一写入和读取 `data/analysis_cache/{TICKER}_latest.json`；`/api/v1/reports` 复用 `AnalysisCache.list_latest()` 扫描该目录，并补充 `date`、`environment`、`summary` 供前端展示。相关模型在 `analysis/models.py`，指标在 `analysis/indicators.py`、`range_detector.py`、`swing_signals.py`。

维护关注：若未来要调整报告存储，应替换 `AnalysisCache` 的 canonical 路径，不要重新引入 `data/analysis_cache.json` 或 `data/report_*.json` 双读路径。

## 持续运行与通知

目标链路：服务启动 → `api/app.py` 启动 `monitoring.loop` 常驻监控循环 → 按交易时段或用户监控窗口持续扫描 → 同步 broker 持仓、扫描 watchlist 信号 → 后续触发持仓预警、事件预警和方向推荐 → `alerts` store 去重、冷却、记录已处理状态 → API/前端/聊天展示。当前已落地最小入口：`src/stocker/monitoring/loop.py`、`engine/runtime_state.py` 的 monitoring 状态、`/api/v1/monitoring` 和 `/api/v1/status`。

维护关注：区间交易不是高频，但必须持续运行；重大事件不能等用户打开页面才发现。RUN-001 已完成最小常驻循环，下一步应做通知去重、冷却、预警 store 和真实事件触发。

## 持仓预警与操作建议

目标链路：持仓列表和成本 → `utils/data_helpers.py` / westock-data 获取现价与 K 线 → `analysis/swing_signals.py` 识别区间、支撑压力、趋势和信号 → 预警模型输出“必须处理/重点观察/正常” → API/聊天/前端展示。当前相关代码为 `portfolio/store.py`、`analysis/swing_signals.py`、`watchlist/scanner.py`、`agents/supervisor.py`；后续可新增 `alerts` 模块承载预警模型和 store。

维护关注：这是 P0 交易辅助闭环，不应先做复杂 UI 或自动下单；先保证用户能看到哪些持仓要处理、为什么、价格触发点是什么。

## 关键事件预警

目标链路：`data_fetcher` 获取个股/全局新闻、财务、评级、资金流 → 事件抽取 → 关联持仓和股票池 → 输出影响方向、紧急程度和建议动作。当前相关代码为 `agents/intelligence/data_fetcher.py`、`skills/finance_news.py`、`analysis/models.py`、`agents/factory.py`；后续可新增 `events` 模块承载事件结构、历史和已处理状态。

维护关注：事件预警必须服务交易决策，只保留会影响“持有/减仓/止损/继续观察/加入观察池”的信息，避免做泛新闻聚合。

## 感兴趣方向推荐

目标链路：用户维护方向/主题/市场 → `discover_market_opportunities` 和固定数据源获取行情、板块、资金与新闻 → 推荐少量候选股 → 写入 watchlist 并生成观察理由。当前相关代码为 `agents/supervisor.py`、`watchlist/store.py`、`watchlist/scanner.py`、`agents/intelligence/data_fetcher.py`。

维护关注：推荐必须有数据依据和风险点；每个方向候选数量要少，避免信息噪音。

## 风险评估与投资决策

核心链路：`run_risk_assessment(ticker)` → `graphs/risk_graph.py` → bull/bear researcher → research manager → trader → aggressive/conservative/neutral → portfolio manager。相关目录：`agents/risk`、`memory`、`graphs/state.py`、`analysis/models.py`。

维护关注：风险结果依赖 Intelligence cache 文本；若数据质量差，应在用户响应中明确暴露。

## 安全交易执行

核心链路：API `/trade` 或 Supervisor `run_execution` → execution mode 检查 → `graphs/execution_graph.py` 校验/补价/下单 → `broker` → `integrations/futu`。配置边界：`STOCKER_EXECUTION_MODE` 控制 observe/active，`STOCKER_FUTU_TRD_ENV` 控制 simulate/real。

维护关注：API `/trade` 与 ExecutionGraph 都包含交易校验和执行职责；`/trades` 已优先读取 `TradeStore`，但交易职责仍需继续收敛。

## 模拟盘实跑闭环

目标链路：预警或交易计划 → 风险评估 → 生成待确认模拟交易计划 → 用户确认 → `paper/westock_sim.py` 使用 westock 行情执行本地模拟订单 → 同步持仓、波段记录和交易历史 → 复盘。当前已落地：`/api/v1/paper/status` 读取 westock-paper 本地模拟账户/持仓，`/api/v1/paper/validate` 不调用券商/Futu broker 路径，执行受控模拟订单并写入 `TradeStore`、更新 `PositionStore`；`/api/v1/trade-plans/from-alert` 可从预警生成待确认计划，`/api/v1/trade-plans/{id}/execute` 用户确认后执行 westock 本地模拟盘。相关代码为 `paper/westock_sim.py`、`trade_plan/*`、`utils/data_helpers.py`、`api/routes.py`、`portfolio/store.py`、`swing/store.py`、`broker/trade_store.py`。

维护关注：功能完成标准必须是能在模拟盘跑出订单和持仓变化，而不是只返回分析文本。PAPER-001/PAPER-002 已完成最小验收路径；下一步是完善交易记录复盘指标，并让模拟交易结果反向进入迭代看板。

## 持续迭代与复盘

目标链路：常驻监控与模拟盘运行记录 → 预警次数、确认次数、模拟成交、盈亏、误报/漏报反馈 → 迭代看板 → 更新规则和 backlog。后续可新增 `review` 模块，也可先通过 `alerts`、`trade_store`、`docs/details/task-backlog-detail.md` 串联。

维护关注：持续迭代是产品有效性的保障；每轮开发都应回答“模拟盘运行后是否真的帮助交易”。

## 股票池交易计划与复盘

核心代码：`portfolio/store.py`、`watchlist/store.py`、`watchlist/scanner.py`、`swing/store.py`、`swing/models.py`、`analysis/swing_signals.py`。前端在 `web/templates/index.html` 的 `stocks/trading` 页面和 `web/static/js/app.js` 对应逻辑。股票池扫描使用 `utils/data_helpers.py` 的 `fetch_ohlcv_westock()`，与主投研路线保持 westock-data 固定主源。

维护关注：股票池后续应围绕交易计划组织，而不是只保存 ticker；每只观察股需要入池理由、买入区间、止损、止盈、失效条件和复盘结果。`PositionStore` 自带路径解析，与 `utils/store_helpers.py` 重复；前端部分接口没有走 `api.js`。

## Hermes Agent 自我迭代参考地图

完整模块地图已整理到 `docs/details/research_report_hermes_agent_code_map.md`。核心参考链路：`hermes-agent/run_agent.py` 的 `AIAgent.run_conversation()`、`_spawn_background_review()`、`_SKILL_REVIEW_PROMPT`、`_COMBINED_REVIEW_PROMPT` 负责在复杂任务后触发后台复盘；`hermes-agent/agent/prompt_builder.py` 注入 memory/skills guidance；`hermes-agent/tools/skills_tool.py` 负责 `skills_list`/`skill_view` 和 progressive disclosure；`hermes-agent/tools/skill_manager_tool.py` 负责 `skill_manage` 的 create/edit/patch/write_file/remove_file；`hermes-agent/tools/skill_usage.py` 记录 agent-created skill 的使用、patch、pinned/stale/archive 状态；`hermes-agent/agent/curator.py` 定期合并、归档、整理 agent-created skills。

当前已抽象为通用 `EvolutionSkill` runtime：`src/stocker/evolution/hermes_compat/*` 保持 Hermes-compatible skill reader/manager/usage/curator；`src/stocker/evolution/adapters/*` 承载 Stocker 的 LangGraph prompt 注入、trace、reviewer、validator 和审批策略。同步边界记录在 `docs/details/hermes-evolution-sync-notes.md`。

## LangGraph 团队策略自我进化融合

融合规划已整理到 `docs/details/langgraph-hermes-evolution-fusion-plan.md`。当前接入点：`agents/factory.py:create_analysis_node()` 注入 intelligence 四个 analyst 节点；`agents/risk/researchers.py`、`agents/risk/managers.py`、`agents/risk/trader.py`、`agents/risk/risk_debators.py` 注入风险/决策节点；`graphs/main_graph.py` 注入 Supervisor routing strategy。所有节点无 active skill 时回退原 prompt，有 active skill 时注入 skill block，并通过 `TraceStore` 写入 `data/evolution/traces/YYYYMMDD.jsonl`。

维护关注：自我进化只能优化团队“如何分析、如何辩论、如何输出、如何降级”，不能破坏固定数据源、执行安全边界和 `strategy.validators` 数值约束。高风险节点如 `trader`、`portfolio_manager`、Supervisor 执行路由默认必须人工确认或模拟盘验证后才能启用新策略。

## 策略配置

核心代码：`strategy/models.py`、`strategy/manager.py`、`strategy/presets.py`、`strategy/validators.py`，API 为 `/strategy`、`/strategy/presets`、`/strategy/preset/{name}`、`/strategy/reset`。

维护关注：策略参数应成为指标、数据抓取、风险阈值的单一事实源；AutoPilot 仍有硬编码 prompt 和阈值。

## 回测验证

核心代码：`backtest/runtime.py`、`backtest/broker.py`、`backtest/data_store.py`、`backtest/collector.py`、`backtest/models.py`。API 当前在 `routes.py` 中注册为 `@router.post("/api/v1/backtest")`。

维护关注：router 已挂载 `/api/v1`，所以实际路径变成 `/api/v1/api/v1/backtest`；应改成 `@router.post("/backtest")`。

## 系统运行与可观测

核心代码：`api/app.py` 的 FastAPI app、日志、startup/shutdown、AutoPilot；`engine/service.py` 的 CLI 服务生命周期；`engine/runtime.py` 的 FutuRuntime；`engine/scheduler.py`、`engine/events.py`、`engine/runtime_state.py`。API 包括 `/status`、`/health`、`/monitoring`、`/logs`、`/broker/config`、`/auto-pilot`。前端 `web/templates/index.html`、`web/static/js/app.js`、`web/static/css/style.css` 在顶部栏、侧边栏和运行模式页展示监控运行状态、周期、轮次、预警数、broker 和 execution mode。

维护关注：`api/app.py` 与 `engine/service.py` 都可能创建 FutuRuntime/Broker；日志读取逻辑散在 app/routes 中。

## 外部交易与数据集成

富途集成在 `integrations/futu`，包括 `config.py`、`mappers.py`、`quote_client.py`、`trade_client.py`、`handlers.py`、`opend_manager.py`。Broker 工厂在 `broker/factory.py`，富途 broker 在 `broker/futu.py`，模拟 broker 在 `broker/simulated.py`。

维护关注：投研数据 ticker 到 westock code 的转换已集中到 `agents/intelligence/data_fetcher.py`，API quote 和 Supervisor quote 已复用；Futu mapper 仅服务券商/交易边界。

## API 路由清单

业务 router 统一挂载在 `/api/v1` 下。当前主要接口：`/status`、`/analyze`、`/trade`、`/trades`、`/account`、`/logs`、`/reports`、`/broker/config`、`/execution-mode`、`/auto-pilot`、`/portfolio`、`/chat`、`/chat/stream`、`/chat/reset`、`/skills`、`/strategy`、`/strategy/presets`、`/strategy/preset/{name}`、`/strategy/reset`、`/api/v1/backtest`、`/quote/{ticker}`、`/quotes`、`/watchlist`、`/watchlist/{ticker}`、`/watchlist/scan`、`/swing-trades`、`/swing-trades/stats`、`/swing-trades/open`、`/swing-trades/close`。其中 `/reports` 读取 `data/analysis_cache/*_latest.json`。

## 存储清单

持仓：`data/{broker_type}/positions.json`；股票池：`data/{broker_type}/watchlist.json`；波段交易：`data/{broker_type}/swing_trades.json`；交易记录：`data/{broker_type}/trades.json`；分析缓存：`data/analysis_cache/{TICKER}_latest.json`；日志：`data/logs/stocker_YYYYMMDD.log`；回测报告：`data/backtest/reports`。

## 维护记录

| 时间 | 变更 |
| --- | --- |
| 2026-05-07 21:06 | 从主 `code-dev-map.md` 迁移细粒度入口、API、存储、数据流和风险点。 |
| 2026-05-07 21:51 | 记录固定主数据源策略：投研数据仅 westock-data，新闻仅 finance-news RSS；DataRouter/yfinance/TradingAgents/DDG/Futu 不进入主分析链路。 |
| 2026-05-07 22:41 | 记录分析缓存统一读取：`AnalysisCache` 与 `/api/v1/reports` 均使用 `data/analysis_cache/{TICKER}_latest.json`。 |
| 2026-05-07 22:50 | 按区间/波段交易定位新增持仓预警、关键事件预警、方向推荐、股票池交易计划的代码目标链路。 |
| 2026-05-07 23:09 | 根据用户反馈补充持续运行与通知链路：常驻监控、预警去重冷却、健康检查为 P0。 |
| 2026-05-07 23:21 | 补充模拟盘实跑闭环和持续迭代链路，明确功能必须能在模拟盘验证价值。 |
| 2026-05-08 21:14 | 记录 RUN-001/PAPER-001 实现：新增 `monitoring.loop`、`/monitoring`、`/paper/status`、`/paper/validate` 与交易记录持久化接入。 |
| 2026-05-08 21:31 | 记录 RUN-002/ALERT-001 实现：新增 `alerts` 模块、`/alerts/positions`、预警去重冷却、已处理状态和 Supervisor 预警工具。 |
| 2026-05-08 22:55 | 记录 westock 本地模拟盘调整：新增 `paper/westock_sim.py`，`/paper/status` 与 `/paper/validate` 不再调用券商/Futu broker。 |
| 2026-05-08 23:38 | 记录 PAPER-002 实现：新增 `trade_plan` 模块和 `/trade-plans/*` API，支持预警转待确认 westock 模拟交易计划。 |
| 2026-05-10 14:20 | 新增 Hermes Agent 自我迭代参考地图入口，完整模块地图保存到 `docs/details/research_report_hermes_agent_code_map.md`。 |
| 2026-05-10 19:32 | 新增 LangGraph 团队策略自我进化融合规划入口，明确 `evolution` 侧车层与现有团队图的接入点。 |
| 2026-05-10 21:33 | 记录 `src/stocker/evolution` 落地：Hermes-compatible core、Stocker adapters、LangGraph 节点注入、TraceStore 与同步说明。 |
| 2026-05-10 22:26 | 补充 EvolutionSkill 管理闭环：`patch_store.py`、`seed.py`、`weekly_review.py` 和 `/evolution/*` API。 |
| 2026-05-10 23:07 | 完成高风险 patch 的 paper/backtest 证据门禁，并新增 `#evolution` 前端管理视图。 |
