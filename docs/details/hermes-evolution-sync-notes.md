# Hermes Evolution 同步说明

最后维护：2026-05-10 23:07
维护人：CodeBuddy Agent

本文件记录 `src/stocker/evolution/hermes_compat` 与 `hermes-agent` 的对应关系和本地差异，便于后续跟随 `hermes-agent` 更新。

## 同步原则

`hermes_compat` 只保存通用 skill runtime 能力：`SKILL.md` 解析、技能列表/查看、create/edit/patch/write_file/remove_file、usage telemetry、curator 生命周期。Stocker 的 LangGraph、交易、数据源、安全审批等业务逻辑必须放在 `src/stocker/evolution/adapters`，不要混进 `hermes_compat`。

后续同步 `hermes-agent` 时，优先对比上游文件，再同步通用逻辑，最后运行 evolution 兼容测试和 Stocker 集成测试。

## 当前抽取映射

| Stocker 文件 | Hermes 参考文件 | 当前本地差异 |
| --- | --- | --- |
| `src/stocker/evolution/hermes_compat/skill_schema.py` | `hermes-agent/tools/skills_tool.py`、`hermes-agent/tools/skill_manager_tool.py` | 提供最小 frontmatter 解析和渲染；支持无 PyYAML fallback；增加 `EvolutionSkill` 字段。 |
| `src/stocker/evolution/hermes_compat/skill_reader.py` | `hermes-agent/tools/skills_tool.py` | 保留 `skills_list`/`skill_view`/linked files/progressive disclosure 思路；移除 Hermes CLI/tool registry 依赖；根目录改为 `data/evolution/skills`。 |
| `src/stocker/evolution/hermes_compat/skill_manager.py` | `hermes-agent/tools/skill_manager_tool.py` | 保留 create/edit/patch/write_file/remove_file 和支持目录约束；默认不暴露硬删除，用 archive 代替。 |
| `src/stocker/evolution/hermes_compat/skill_usage.py` | `hermes-agent/tools/skill_usage.py` | 保留 `.usage.json` sidecar、view/use/patch、pinned、active/stale/archived；根目录改为项目数据目录。 |
| `src/stocker/evolution/hermes_compat/curator.py` | `hermes-agent/agent/curator.py` | 先实现确定性 lifecycle pass；LLM 合并/umbrella skill 后续放在 reviewer adapter。 |
| `src/stocker/evolution/hermes_compat/prompt_guidance.py` | `hermes-agent/agent/prompt_builder.py` | 将 Hermes skill guidance 收敛为 Stocker evolution skill 的安全提示，不直接复用完整 system prompt。 |

## Stocker 适配层

| 文件 | 职责 |
| --- | --- |
| `src/stocker/evolution/adapters/langgraph_prompt_resolver.py` | 将 `domain/team/node/skill_type` 映射为 active `EvolutionSkill`，并注入 LangGraph 节点 prompt。 |
| `src/stocker/evolution/adapters/trace_store.py` | 记录 LangGraph 节点运行轨迹到 `data/evolution/traces/YYYYMMDD.jsonl`。 |
| `src/stocker/evolution/adapters/stocker_reviewer.py` | 从 reflection/trace 生成 `SkillPatchDraft`，只保存草案，不自动应用。 |
| `src/stocker/evolution/adapters/stocker_validator.py` | 校验固定数据源、执行安全、高风险审批边界。 |
| `src/stocker/evolution/adapters/approval_policy.py` | 判断高风险 skill/patch 是否必须人工或模拟盘验证。 |

## 后续同步流程

1. 对比 `hermes-agent/tools/skills_tool.py` 与 `src/stocker/evolution/hermes_compat/skill_reader.py`。
2. 对比 `hermes-agent/tools/skill_manager_tool.py` 与 `src/stocker/evolution/hermes_compat/skill_manager.py`。
3. 对比 `hermes-agent/tools/skill_usage.py` 与 `src/stocker/evolution/hermes_compat/skill_usage.py`。
4. 对比 `hermes-agent/agent/curator.py` 与 `src/stocker/evolution/hermes_compat/curator.py`。
5. 将通用增强同步到 `hermes_compat`；业务差异仍放入 `adapters`。
6. 运行 `python -m pytest tests/test_evolution_core.py tests/test_evolution_validator_reviewer.py -q`。
7. 运行相关 LangGraph/交易安全回归测试。

## 当前已验证

2026-05-10 21:33：新增 evolution 核心测试和 reviewer/validator 测试，`python -m pytest tests/test_evolution_core.py tests/test_evolution_validator_reviewer.py -q` 通过，结果为 6 passed。

2026-05-10 23:07：补充 API 与高风险证据门禁测试，`python -m pytest tests/test_evolution_core.py tests/test_evolution_validator_reviewer.py tests/test_evolution_api.py tests/test_run_paper_validation.py -q` 通过，结果为 13 passed。
