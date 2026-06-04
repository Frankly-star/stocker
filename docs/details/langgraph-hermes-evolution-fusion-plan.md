# LangGraph 团队编排与 Hermes 自我进化融合规划

最后维护：2026-05-10 23:07
维护人：CodeBuddy Agent

## 1. 目标判断

`stocker` 的风险团队、决策团队、数据挖掘/投研团队由 LangGraph 稳定编排，但节点行为主要来自固定 prompt、固定策略配置和 BM25 案例记忆。融合目标不是用 `hermes-agent` 替换 LangGraph，而是在 LangGraph 外增加一层可复用的自我进化 runtime：每个团队、节点、未来任务域都可以拥有可版本化的 `EvolutionSkill`，运行前加载当前 active skill，运行后记录 trace，复盘后生成 patch 草案，再经过安全校验、模拟盘/回测或人工确认后激活。

用户进一步明确：`Strategy Skill` 不应是交易团队特化能力，而应抽象为通用 `EvolutionSkill`。实现应尽量参考或抽取 `hermes-agent` 的 skill 读写、patch、usage telemetry 和 curator 机制，把 Stocker 业务逻辑隔离在 adapter 层，便于后续跟随 `hermes-agent` 更新。

## 2. 当前实现状态

已落地最小可运行骨架：`src/stocker/evolution/hermes_compat` 提供 Hermes-compatible skill core，包括 `skill_schema.py`、`skill_reader.py`、`skill_manager.py`、`skill_usage.py`、`curator.py`、`prompt_guidance.py`；`src/stocker/evolution/adapters` 提供 Stocker 适配层，包括 `langgraph_prompt_resolver.py`、`trace_store.py`、`stocker_reviewer.py`、`stocker_validator.py`、`approval_policy.py`、`patch_store.py`、`seed.py`、`weekly_review.py`；`src/stocker/evolution/models.py` 定义 `EvolutionSkill`、`ResolvedPrompt`、`NodeTrace`、`SkillPatchDraft`、`ValidationResult`。

已接入的 LangGraph 节点包括：`agents/factory.py:create_analysis_node()` 的 `market_data/news/fundamentals/social`，`agents/risk/researchers.py` 的 `bull_researcher/bear_researcher`，`agents/risk/managers.py` 的 `research_manager/portfolio_manager`，`agents/risk/trader.py` 的 `trader`，`agents/risk/risk_debators.py` 的 `aggressive/conservative/neutral`，以及 `graphs/main_graph.py` 的 Supervisor。无 active skill 时回退原 prompt；有 active skill 时注入 skill block，并写入 node trace。

已验证：`python -m pytest tests/test_evolution_core.py tests/test_evolution_validator_reviewer.py tests/test_evolution_api.py tests/test_run_paper_validation.py -q` 通过，结果为 13 passed。

## 3. 三层架构

```text
LangGraph 主流程
  main_graph / intelligence_graph / risk_graph / execution_graph
        ↓
Stocker adapters
  PromptResolver / TraceStore / Reviewer / Validator / ApprovalPolicy / PatchStore / WeeklyReview
        ↓
Hermes-compatible core
  SKILL.md reader / manager / usage sidecar / curator / prompt guidance
        ↓
EvolutionSkill 文件资产
  data/evolution/skills/<domain>/<team>/<skill>/SKILL.md
  references/ templates/ scripts/ assets/
```

分层边界：`hermes_compat` 只处理通用 skill runtime，不懂交易、不懂 LangGraph；`adapters` 处理 Stocker 的 team/node 映射、固定数据源边界、交易安全、trace、patch 审批证据和前端/API 管理；实际团队策略 skill 保存在 `data/evolution/skills`，采用 Hermes-compatible 文件结构。

## 4. Hermes-compatible core

| 文件 | 职责 | Hermes 参考 |
| --- | --- | --- |
| `src/stocker/evolution/hermes_compat/skill_schema.py` | 解析和渲染 `SKILL.md` frontmatter，将 Markdown 转为 `EvolutionSkill`。 | `hermes-agent/tools/skills_tool.py`、`skill_manager_tool.py` |
| `skill_reader.py` | 扫描 `SKILL.md`，提供 `list_skills()`、`view_skill()`、`get_active_skill()`，支持 linked files 与 prompt injection warning。 | `hermes-agent/tools/skills_tool.py` |
| `skill_manager.py` | 创建、编辑、patch、写支持文件、移除支持文件、归档 skill。 | `hermes-agent/tools/skill_manager_tool.py` |
| `skill_usage.py` | 使用 `.usage.json` 记录 use/view/patch、created_by、pinned、active/stale/archived。 | `hermes-agent/tools/skill_usage.py` |
| `curator.py` | 执行 stale/archive 生命周期管理，只归档不删除。 | `hermes-agent/agent/curator.py` |
| `prompt_guidance.py` | 提供 evolution skill 注入与 reviewer guidance。 | `hermes-agent/agent/prompt_builder.py` |

当前本地差异与同步说明记录在 `docs/details/hermes-evolution-sync-notes.md`。后续同步 `hermes-agent` 时，只同步 core；Stocker 交易和 LangGraph 逻辑不进入 core。

## 5. Stocker adapters

| 文件 | 职责 |
| --- | --- |
| `src/stocker/evolution/adapters/langgraph_prompt_resolver.py` | 按 `domain/team/node/skill_type` 查找 active `EvolutionSkill`，生成 `ResolvedPrompt`。 |
| `trace_store.py` | 将节点输入摘要、输出摘要、skill id/version、prompt hash、data warnings、耗时写入 `data/evolution/traces/YYYYMMDD.jsonl`。 |
| `stocker_reviewer.py` | 根据 reflection/trace 生成 `SkillPatchDraft`，保存到 `data/evolution/patches`，不自动应用。 |
| `stocker_validator.py` | 校验禁止的数据源 fallback、执行安全绕过、高风险审批要求。 |
| `approval_policy.py` | 判断 `trader`、`portfolio_manager`、`supervisor` 等高风险节点是否必须人工或模拟验证。 |
| `patch_store.py` | 持久化 patch draft，提供 validate/approve/apply；高风险 patch 必须 approved 且含 `paper:`/`backtest:` 证据。 |
| `seed.py` | 创建默认 baseline skills，低风险分析节点可 active，高风险 `trader`/`portfolio_manager`/Supervisor 保持 draft。 |
| `weekly_review.py` | 生成确定性周复盘，汇总 skills、usage、trace、patch、data warnings 和下一步建议。 |

## 6. EvolutionSkill 文件格式

`EvolutionSkill` 是通用抽象，不只服务交易策略。一个 skill 可以绑定任意 `domain/team/node/skill_type`。推荐目录为：

```text
data/evolution/skills/stocker/risk/swing-plan/SKILL.md
data/evolution/skills/stocker/risk/swing-plan/references/
data/evolution/skills/stocker/risk/swing-plan/templates/
data/evolution/skills/stocker/risk/swing-plan/scripts/
data/evolution/skills/stocker/risk/swing-plan/assets/
```

示例：

```md
---
name: swing-plan
description: This skill guides swing trading plan generation.
id: stocker.risk.trader.swing-plan
domain: stocker
team: risk
node: trader
skill_type: prompt_strategy
version: 1
status: active
risk_level: high
created_by: reviewer
requires_approval: true
pinned: false
source: stocker_adapter
---

## Trigger
当 `risk.trader` 节点需要把研究经理投资判断转为区间/波段交易计划时使用。

## Strategy
先抽取 current price、支撑、压力、波动区间；数据缺失或 warning 严重时输出 HOLD/WAIT；止损和目标价必须锚定当前价和 `strategy.validators` 约束。

## Anti-patterns
不得复用历史记忆中的绝对价格位；不得绕开固定数据源；不得绕过用户确认或 execution mode。

## Output contract
输出 Current Price、Entry、Stop Loss、Target、Position Size、Risk:Reward、Invalidation。

## Verification
复盘检查价格错位、止损过近、风险收益比不足、模拟盘结果显著劣化。
```

## 7. 运行时流程

```text
LangGraph 节点开始
  -> 构造原始 base_prompt
  -> PromptResolver.resolve(team,node,base_prompt,state)
  -> SkillReader.get_active_skill(domain,team,node,skill_type)
  -> 无 active skill：返回 base prompt
  -> 有 active skill：注入 Evolution Skill block，记录 skill use_count
  -> 节点按原方式调用 LLM
  -> TraceStore.record_node_run(...)
  -> 后续 Reflector / Reviewer 读取 trace 和结果
  -> StockerEvolutionReviewer 生成 SkillPatchDraft
  -> StockerValidator 校验
  -> PatchStore validate / approve / apply
  -> 低风险可校验后 apply；高风险必须人工审批并携带 paper/backtest evidence
  -> Curator 周期 stale/archive，不删除
```

## 8. 当前接入点

数据团队统一在 `src/stocker/agents/factory.py:create_analysis_node()` 接入。`report_field` 映射为 `market_data`、`news`、`fundamentals`、`social`。该层只注入“如何分析/输出/降级”的策略，不允许绕开 `data_fetcher` 或新增未批准数据源。

风险和决策团队在各自节点内接入。`researchers.py` 注入 `bull_researcher`、`bear_researcher`；`managers.py` 注入 `research_manager`、`portfolio_manager`；`trader.py` 注入 `trader`；`risk_debators.py` 注入 `aggressive`、`conservative`、`neutral`。其中 `trader` 和 `portfolio_manager` 是高风险节点，patch 不应直接激活。

Supervisor 在 `src/stocker/graphs/main_graph.py:supervisor_node()` 接入，用于优化工具路由策略。该策略不能改变 `execution_mode` 的含义，不能把建议/提醒升级为自动实盘下单。

Reflector 在 `src/stocker/memory/reflector.py` 中保留原 `reflect_and_remember()`，新增 `reflect_and_propose_patches()`，用于在写 BM25 案例记忆的同时生成 `SkillPatchDraft` 草案。

API 入口在 `src/stocker/api/routes.py`：`/evolution/skills`、`/evolution/skills/seed-defaults`、`/evolution/traces`、`/evolution/patches`、`/evolution/curator/run`、`/evolution/review/weekly`。前端入口在 `src/stocker/web/templates/index.html` 的 `#evolution` 页面和 `src/stocker/web/static/js/app.js` 的 `initEvolution()`/`loadEvolution()`。

## 9. 安全边界

硬边界包括：自我进化 skill 不得要求改用 `yfinance`、DDG、TradingAgents、DataRouter、Futu quote 等非主链路数据源；不得要求自动实盘或绕过用户确认；不得绕过 `execution_mode`；不得放宽止损、仓位、风险收益比等约束而不审批；用户创建或 pinned skill 不自动归档；reviewer 生成的 patch 只作为草案；高风险 patch apply 必须先 approve，并携带 `paper:` 或 `backtest:` 证据 ID。

## 10. 后续阶段

下一步应完善 LLM curator 与自动证据生成：把具体案例降级为 `references/`，合并过窄 skill，生成更高质量策略重写建议；同时将模拟盘/回测结果自动转换为 `paper:`/`backtest:` evidence，减少人工填写证据 ID。另一个后续方向是把 `api/routes.py` 的 `/evolution/*` 拆到独立 router，降低单文件复杂度。

## 11. 维护记录

| 时间 | 变更 |
| --- | --- |
| 2026-05-10 19:32 | 初始规划 LangGraph 团队策略自我进化融合：团队策略 skill、PromptResolver、TraceStore、Reviewer、Curator。 |
| 2026-05-10 21:33 | 按用户要求将 Strategy Skill 抽象为通用 `EvolutionSkill`，落地 `hermes_compat` core 与 Stocker adapters，并接入 intelligence/risk/supervisor 节点。 |
| 2026-05-10 22:26 | 补齐 patch store、默认种子 skill、确定性周复盘和 `/evolution/*` API，形成可操作的管理闭环。 |
| 2026-05-10 23:07 | 完成高风险 patch 的 paper/backtest 证据门禁，并新增 `#evolution` 前端管理视图。 |
