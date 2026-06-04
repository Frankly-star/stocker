# Stocker code-dev-map

最后维护：2026-05-10 23:07
维护人：CodeBuddy Agent

本文件只保留最高维、用户视角的代码模块地图：用户看到什么能力、这项能力由哪些代码模块承载、后续 agent 应该从哪里进入。细粒度 API、文件、路由、存储、风险点维护到 `docs/details/code-dev-detail-map.md`。

## 1. 产品能力总览

`stocker` 面向用户提供的是一个持续运行的区间/波段交易辅助驾驶舱：系统不是做高频交易，而是在交易时段/用户监控窗口内常驻运行，围绕用户持仓、关注方向和关键事件，提供及时持仓预警、候选推荐、交易计划、风险判断、执行保护和复盘。

最高维链路：常驻监控循环 → 用户持仓/关注方向/关键事件 → 固定数据源 → 预警与推荐 → 风险评估 → 通知用户确认或受控执行 → 记录与复盘。

## 2. 用户能力到代码模块地图

| 用户能力 | 用户视角目标 | 核心代码模块 | 细节文档 |
| --- | --- | --- | --- |
| 对话式投研助手 | 用户用自然语言询问持仓、预警、候选股、交易计划和账户状态，系统给出操作级结论。 | `api`、`web`、`agents/supervisor.py`、`graphs/main_graph.py` | `docs/details/code-dev-detail-map.md#对话式投研助手` |
| 持续运行与通知 | 用户不用打开页面也能让系统持续监控，重大风险或机会出现时及时收到预警。 | `engine/scheduler.py`、`api/app.py`、`engine/runtime_state.py`、可新增 `monitoring`/`alerts` | `docs/details/code-dev-detail-map.md#持续运行与通知` |
| 持仓预警与操作建议 | 用户看到哪些持仓接近止损/止盈/支撑压力/趋势破位，哪些需要马上处理。 | `portfolio`、`analysis/swing_signals.py`、`agents/supervisor.py`、可新增 `alerts` | `docs/details/code-dev-detail-map.md#持仓预警与操作建议` |
| 关键事件预警 | 用户知道重大新闻、财报、评级、资金异动、价格破位影响哪些持仓或观察股。 | `agents/intelligence/data_fetcher.py`、`skills/finance_news.py`、`analysis`、可新增 `events` | `docs/details/code-dev-detail-map.md#关键事件预警` |
| 感兴趣方向推荐 | 用户输入方向/行业/主题后，系统用真实数据筛出少量候选股和入池理由。 | `agents/supervisor.py`、`watchlist`、`agents/intelligence/data_fetcher.py`、`skills/westock_data.py` | `docs/details/code-dev-detail-map.md#感兴趣方向推荐` |
| 单股分析报告 | 用户输入股票代码后，系统输出技术面、新闻、基本面、情绪、数据质量和历史报告。 | `graphs/intelligence_graph.py`、`agents/intelligence/data_fetcher.py`、`agents/supervisor.py`、`analysis` | `docs/details/code-dev-detail-map.md#单股分析报告` |
| 安全交易执行 | 用户在允许模式下执行模拟/实盘交易，并防止误操作。 | `graphs/execution_graph.py`、`broker`、`integrations/futu`、`engine/runtime_state.py` | `docs/details/code-dev-detail-map.md#安全交易执行` |
| 模拟盘实跑闭环 | 用户能用 westock 行情把预警和交易计划放到本地模拟盘验证，看到订单、持仓、交易记录和结果。 | `paper/westock_sim.py`、`api/routes.py`、`portfolio`、`broker/trade_store.py`、`swing` | `docs/details/code-dev-detail-map.md#模拟盘实跑闭环` |
| 股票池、交易计划与复盘 | 用户维护观察列表、交易计划、波段记录和出入场信号，并能复盘结果。 | `watchlist`、`swing`、`analysis/swing_signals.py`、`portfolio` | `docs/details/code-dev-detail-map.md#股票池交易计划与复盘` |
| 持续迭代与复盘 | 用户能看到预警和模拟交易是否有用，并把反馈转成下一轮优化任务。 | 可新增 `review`、`alerts`、`broker/trade_store.py`、`docs` | `docs/details/code-dev-detail-map.md#持续迭代与复盘` |
| Agent 自我迭代参考抽取 | 用户希望借鉴 `hermes-agent` 的自进化机制，把运行经验总结为可持续优化的 skill。 | `hermes-agent/run_agent.py`、`hermes-agent/tools/skill_manager_tool.py`、`hermes-agent/tools/skills_tool.py`、`hermes-agent/tools/skill_usage.py`、`hermes-agent/agent/curator.py`、可新增 `review`/`skills` | `docs/details/research_report_hermes_agent_code_map.md` |
| LangGraph 团队策略自我进化 | 用户希望风险团队、决策团队、数据挖掘团队不只按固定 prompt/策略运行，而能基于运行结果持续优化团队策略。 | `graphs/main_graph.py`、`graphs/intelligence_graph.py`、`graphs/risk_graph.py`、`agents/factory.py`、`agents/risk/*`、`memory/reflector.py`、可新增 `evolution` | `docs/details/langgraph-hermes-evolution-fusion-plan.md` |
| 策略配置 | 用户调整技术指标、风险阈值、数据抓取参数，并切换策略预设。 | `strategy`、`api/routes.py`、`web` | `docs/details/code-dev-detail-map.md#策略配置` |
| 回测验证 | 用户用历史数据验证策略表现。 | `backtest`、`broker/backtest`、`api` | `docs/details/code-dev-detail-map.md#回测验证` |
| 系统运行与可观测 | 用户查看系统状态、日志、连接状态、AutoPilot 状态。 | `engine`、`api/app.py`、`api/routes.py`、`web` | `docs/details/code-dev-detail-map.md#系统运行与可观测` |
| 外部交易与数据集成 | 用户通过固定投研数据源和独立券商能力获得行情、资讯和交易能力。 | `agents/intelligence/data_fetcher.py`、`skills/westock_data.py`、`skills/finance_news.py`、`integrations/futu` | `docs/details/code-dev-detail-map.md#外部交易与数据集成` |

## 3. 模块分层地图

| 层级 | 职责 | 主要目录 |
| --- | --- | --- |
| 用户入口层 | Web UI、CLI、REST/SSE API。 | `web`、`api`、`cli` |
| 智能编排层 | 理解用户意图，选择预警、推荐、投研、风险、交易、管理工具。 | `agents/supervisor.py`、`graphs/main_graph.py` |
| 常驻监控层 | 按交易时段/监控窗口持续扫描、触发预警、去重冷却、记录状态。 | `engine/scheduler.py`、`api/app.py`、`engine/runtime_state.py`、可新增 `monitoring`/`alerts` |
| 投研与预警层 | 数据获取、持仓预警、事件预警、方向推荐、分析报告、风险辩论。 | `agents/intelligence`、`agents/risk`、`analysis`、可新增 `alerts`/`events` |
| 交易与账户层 | Broker 抽象、富途/模拟盘、订单、账户、持仓同步。 | `broker`、`integrations/futu`、`engine/runtime.py` |
| 用户资产层 | 持仓、股票池、交易计划、波段交易、策略配置、回测结果。 | `portfolio`、`watchlist`、`swing`、`strategy`、`backtest` |
| 基础设施层 | 配置、调度、事件、JSON 存储、日志、工具函数。 | `config.py`、`engine`、`utils`、`memory` |
| 外部参考与自我迭代层 | 借鉴 `hermes-agent` 的会话复盘、skill 写入、usage 遥测和 curator 整理机制，为 Stocker 的 LangGraph 团队策略持续优化提供参考。 | `hermes-agent`、`graphs`、`agents`、可新增 `evolution`/`review`/`skills`/`curator` |

## 4. 后续维护原则

主 map 不记录单个函数、单条 API、单个 bug；这里只维护“用户能力 ↔ 代码模块”的高维对应关系。若改动改变了用户能力边界、模块归属、主链路或分层关系，更新本文件。若只是具体路由、文件、任务、风险点变化，更新 `docs/details/code-dev-detail-map.md` 或 `docs/details/task-backlog-detail.md`，并在本文件维护记录中追加摘要。

## 5. 维护记录

| 时间 | 变更 |
| --- | --- |
| 2026-05-07 20:52 | 初始建立 code-dev-map，梳理入口、模块、API、数据流、存储、配置与冗余风险。 |
| 2026-05-07 21:06 | 按用户反馈重构为最高维用户能力到代码模块地图，细节迁移到 `docs/details/code-dev-detail-map.md`。 |
| 2026-05-07 21:51 | 将“可信数据与分析”高维边界更新为固定主数据入口：投研数据走 westock-data，新闻走 finance-news RSS，富途保留交易/券商边界。 |
| 2026-05-07 22:41 | 将单股分析报告能力补充为统一缓存读取：`/reports` 读取 `data/analysis_cache/{TICKER}_latest.json`，不再读取旧聚合报告路径。 |
| 2026-05-07 22:50 | 按区间/波段交易辅助驾驶舱重排能力地图：持仓预警、关键事件预警、方向推荐和交易计划优先。 |
| 2026-05-07 23:09 | 将系统能力修正为持续运行模式，新增常驻监控层与通知能力。 |
| 2026-05-07 23:21 | 将模拟盘实跑闭环和持续迭代反馈加入高维能力地图，要求功能能被实际运行验证。 |
| 2026-05-08 21:14 | 落地 RUN-001/PAPER-001 最小代码入口：常驻监控层启动、监控状态 API、模拟盘状态和受控下单验收。 |
| 2026-05-08 21:31 | 落地 RUN-002/ALERT-001：新增 alerts 模块、持仓预警模型、去重冷却、预警查询和已处理 API。 |
| 2026-05-08 22:55 | 按用户要求将模拟盘闭环改为 westock 数据本地模拟盘，不再依赖券商/Futu broker 路径。 |
| 2026-05-08 23:38 | 完成 PAPER-002 能力入口：预警生成待确认交易计划，确认后执行 westock 本地模拟盘。 |
| 2026-05-10 14:20 | 新增 `hermes-agent` 代码地图入口，标出自我迭代总结 skill 的核心参考模块和后续抽取方向。 |
| 2026-05-10 19:32 | 新增 LangGraph 团队策略自我进化规划：保留图编排，新增策略 skill、trace、reviewer、curator 融合层。 |
| 2026-05-10 21:33 | 落地通用 `EvolutionSkill` runtime：新增 Hermes-compatible core、Stocker adapters，并接入 intelligence/risk/supervisor 节点。 |
| 2026-05-10 22:26 | 补齐 EvolutionSkill 管理闭环：patch 审批/应用、默认种子 skill、周复盘和 `/evolution/*` API。 |
| 2026-05-10 23:07 | 完成高风险 patch 证据门禁和自我进化前端管理视图，支持页面审批、应用、查看 trace/周复盘。 |
| 2026-05-11 15:14 | 增强 Web 运行状态可视化：顶部和侧边栏显示常驻监控是否运行、周期、轮次、预警数和 broker/mode。 |
