# Stocker profile notes

> 说明，不是已接入的 dsh profile。本目录没有 `package.json`、`cordis.patch.yml` 或 `dsh.profile.bundles`。不要把这里指给 `dsh --profile`。

dsh 的 profile 位于 `$DSH_HOME/profiles/<name>`，由已安装的 bundle 和该剖面自己的 `cordis.patch.yml` 组成。创建自定义剖面的入口在 harness 里（例如 `dsh --profile <name> --from-default-profile <template>`，模板名和旗标以 `vendor/deepseek-harness` 的文档为准）。本产品还没有创建那个剖面，也没有把下面的包装进去。

## 默认模式：observe

**默认是 observe，不发送实盘委托**，直到用户明确批准离开观察模式。

在 observe 下，预期行为是：

- 可以阅读材料、讨论三层框架、起草自然语言论点
- `trade-gate` 保持关闭，不把任何经纪商插件置于可下单状态
- `broker-futu` 即使将来接通，在未获批准时也不发送委托

本仓库现在没有下单代码。observe 是产品约定，还不是一条已经写进 Cordis 配置的开关。

## 打算启用的插件

接通之后，剖面应包含这些包（今天都只是骨架）：

| 插件目录 | 包名（占位） | 在剖面中的角色 |
| --- | --- | --- |
| `plugins/value-spec-macro` | `@frankly-star/stocker-value-spec-macro` | 宏观层讨论 |
| `plugins/value-spec-industry` | `@frankly-star/stocker-value-spec-industry` | 行业周期层讨论 |
| `plugins/value-spec-micro` | `@frankly-star/stocker-value-spec-micro` | 微观技术与情绪 |
| `plugins/trade-thesis` | `@frankly-star/stocker-trade-thesis` | 要求每笔交易有可讨论的自然语言论点 |
| `plugins/trade-gate` | `@frankly-star/stocker-trade-gate` | 门禁。默认拒绝离开 observe |
| `plugins/broker-futu` | `@frankly-star/stocker-broker-futu` | 富途适配。未批准时不得下单 |
| `plugins/philosophy-reflect` | `@frankly-star/stocker-philosophy-reflect` | 对照 `philosophy/` 做反思 |

原则正文在 [`philosophy/README.md`](../philosophy/README.md)，目前是草稿。

## 尚未接线

每个插件的 `package.json` 只声明了名字和描述，并写明 `TODO wire Cordis plugin`。接入时需要按 harness 的约定补上 Cordis `apply`（以及若作为 bundle 安装，则补上 `dsh.bundle.patch` 指向的 `cordis.patch.yml`）。空的 patch 文件会导致 dsh 启动失败，所以这里故意没有放 patch。
