# trade-gate

**交易门禁**插件骨架。

## 职责

默认模式是 **observe**：可以讨论，不发送实盘委托。只有用户明确批准离开观察模式之后，后续的经纪商插件才允许进入可下单状态。

本目录不读取账户、不连接 OpenD、不提交任何委托。observe 目前写在 [`profiles/README.md`](../../profiles/README.md) 里，还不是一条 Cordis 配置。

## 状态

`package.json` 只是占位：有包名和描述，**没有** Cordis `apply`，也没有 `dsh.bundle`。

TODO wire Cordis plugin.
