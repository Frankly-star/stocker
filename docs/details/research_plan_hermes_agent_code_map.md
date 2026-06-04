# Hermes-agent 代码地图研究计划

目标：梳理 `hermes-agent` 的完整模块代码地图，说明每个主要模块位于哪里、承担什么职责，并特别标出后续可抽取“自我迭代总结 skill 并持续优化”的相关代码路径。

查询类型判断：这是本地代码库的 breadth-first 代码探索任务，可拆成入口/运行时、Agent 核心、工具与技能、界面/服务/部署、测试文档五条并行线索。

执行方案：先用本地代码搜索与 `code-explorer` 子任务并行扫描目录结构、入口文件、核心类、配置、技能/例程/计划/记忆相关实现；再把发现汇总进 `docs/code-dev-map.md` 的高维能力地图、`docs/details/code-dev-detail-map.md` 的细粒度模块地图，并同步维护 `docs/task-map.md` 与 `docs/details/task-backlog-detail.md` 中关于“自我迭代总结 skill”的需求判断。

信息源策略：主要信息来自本地 `hermes-agent` 源码、README、docs、tests、release notes。按 Deep Research 规则，外部中文信息检索可使用 `wechat-article-search`，关键词建议为“AI Agent 自我迭代 总结 skill 2026”“Code Agent memory routine skill 2026”，时间范围建议最近 365 天；但本任务核心是本地源码映射，外部结果只作为命名与抽象思路参考，不覆盖本地代码事实。

预期产物：更新后的代码地图文档，包含模块路径、职责、关键文件、与自我迭代/总结/skill 优化抽取的关系，以及后续抽取任务的 backlog。
