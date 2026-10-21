# Stocker

价值投机交易代理产品。交易侧以 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（`dsh`）插件的形式放在本仓库；运行时框架在子模块里，不在这里重写。

本仓库目前只有插件骨架和说明。**还没有接入 dsh profile，也没有交易策略实现。** 启动 harness 不会加载这些插件，也不会下单。

## 布局

```
stocker/
  vendor/deepseek-harness/   # git submodule → Frankly-star/deepseek-harness
  plugins/                   # 本产品的插件骨架
  philosophy/                # 价值投机原则草稿
  profiles/                  # 剖面说明：启用哪些插件，默认 observe
```

| 路径 | 角色 |
| --- | --- |
| `vendor/deepseek-harness` | 用户 fork：<https://github.com/Frankly-star/deepseek-harness>（上游是 `deepseek-ai/deepseek-harness`） |
| `plugins/value-spec-macro` | 宏观层 |
| `plugins/value-spec-industry` | 行业周期层 |
| `plugins/value-spec-micro` | 微观层（技术 + 情绪） |
| `plugins/trade-thesis` | 自然语言交易论点 |
| `plugins/trade-gate` | 交易门禁；默认 observe |
| `plugins/broker-futu` | 富途经纪商适配占位 |
| `plugins/philosophy-reflect` | 对照原则做反思的占位 |
| `philosophy/` | 原则草稿，供仓库所有者改写 |
| `profiles/` | 剖面说明。默认模式是 observe，不发送实盘委托 |

每个插件目录里有一份 README 和一个 `package.json` 占位（包名、描述、`TODO wire Cordis plugin`）。它们还不是可安装的 Cordis 插件：没有 `apply`，也没有 `dsh.bundle`。

## 初始化子模块

已克隆本仓库时：

```sh
git submodule update --init --recursive
```

全新克隆：

```sh
git clone --recurse-submodules https://github.com/Frankly-star/stocker.git
cd stocker
git submodule update --init --recursive
```

子模块 URL 记录在 `.gitmodules`，指向 `https://github.com/Frankly-star/deepseek-harness`，路径是 `vendor/deepseek-harness`。父仓库锁定的是该 fork 在添加子模块时的一次提交，而不是浮动的分支尖。

## 以后如何用 dsh 运行

接通方式以子模块文档为准，本仓库还没有做这一步。上游从源码运行 Web UI 的命令是（在 **harness 仓库**里，不是在本仓库根目录）：

```sh
cd vendor/deepseek-harness
pnpm install
pnpm run build
pnpm dsh web
```

说明见子模块的 [README.md](vendor/deepseek-harness/README.md) 和 [README.zh.md](vendor/deepseek-harness/README.zh.md)。`pnpm dsh web` 使用已构建产物启动 Web UI，默认地址和 `--no-open` 等行为以该 README 为准。`pnpm run build` 负责准备仓库产物，`pnpm dsh web` 不会再构建一遍。

也可以不经过本子模块，直接运行已发布的 CLI：

```sh
npx @deepseek-ai/dsh web
```

在把 `plugins/` 装进某个 dsh profile 之前，上面两种启动方式跑的都是 harness 本身，不是这个交易产品。dsh 里一个 profile 位于 `$DSH_HOME/profiles/<name>`，由可安装 bundle 和该剖面自己的 `cordis.patch.yml` 组成。本仓库的 `profiles/` 只是说明，不是那个目录。

## 默认模式

见 [profiles/README.md](profiles/README.md)。默认是 **observe**：可以讨论和起草论点，不发送实盘委托，直到用户明确批准离开观察模式。

原则提纲见 [philosophy/README.md](philosophy/README.md)，标明为草稿。

## 密钥

不要提交 `.env`、API key 或交易密码。`.gitignore` 已忽略 `.env`。
