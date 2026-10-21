# broker-futu

**富途经纪商**适配的插件骨架。

## 职责

将来作为行情与交易适配层，面向富途 OpenAPI / OpenD。在 `trade-gate` 仍处于 observe、且用户尚未批准之前，这个插件即使接通也不得发送委托。

当前不连接 OpenD，不读取账户，不下单，也不包含富途 SDK。

## 状态

`package.json` 只是占位：有包名和描述，**没有** Cordis `apply`，也没有 `dsh.bundle`。

TODO wire Cordis plugin.
