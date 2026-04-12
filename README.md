# Stocker

基于 LangGraph 的多智能体自动化区间/波段交易系统，默认接入富途模拟盘。

## 系统架构

```
浏览器 Web UI ←→ FastAPI 后端 ←→ Supervisor 主控智能体
                                      ↓
                    ┌─────────────────┼─────────────────┐
                    ↓                 ↓                 ↓
              数据分析团队        风险评估团队        交易执行团队
              (4 并行智能体)     (多空辩论 + 风控)    (富途 Broker)
                    ↓                                   ↓
              行情/新闻/基本面                    OpenD ←→ 富途后端
```

**核心组件：**

1. **Supervisor 主控智能体** — LLM 驱动的协调者，从对话中理解用户意图，自主决定调用哪些团队
2. **数据分析团队** — 4 个并行智能体：行情数据、新闻情绪、基本面、社交媒体 → 生成 `MarketIntelligenceReport`
3. **风险评估团队** — 多空辩论 + 三方风险辩论 → 生成 `RiskAssessmentResult`
4. **交易执行团队** — 订单验证 → 风控检查 → FutuBroker 下单 → 持仓同步
5. **富途集成层** — 自动管理 OpenD 生命周期（下载/启动/停止），封装行情订阅与交易接口
6. **Web UI** — 原生 SPA 前端，包含对话、持仓、分析报告、交易记录、运行日志、策略配置、系统状态等页面

## 快速开始

```bash
pip install -e .
python runserver.py    # 启动服务（自动下载并启动 OpenD）
# 或
stocker serve          # 通过 CLI 启动
```

浏览器打开 `http://127.0.0.1:8899` 即可使用 Web UI。

也可以通过命令行操作：

```bash
stocker analyze AAPL   # 分析一只股票
stocker status         # 查看系统状态（含 Broker 连接信息）
stocker portfolio list # 查看持仓
stocker chat           # 与 Supervisor 交互对话
```

## 执行模式

系统只有两种执行模式，其他所有决策由 Supervisor 自动完成：

- `active` — Supervisor 拥有完整自主权：可以分析、评估，并通过富途 Broker 执行交易
- `observe`（默认）— Supervisor 正常分析和推荐，但不会执行任何实际交易

Supervisor 会根据对话上下文自动决定执行什么操作（分析、风险评估、查询状态、管理持仓等），无需手动选择流程。可在 Web UI 顶栏或"运行模式"页面随时切换。

## 富途 Open API 集成

Stocker 默认通过富途 Open API 接入行情与交易。系统在数据分析链路中读取富途实时行情，在交易执行链路中将指令发送到富途模拟盘（默认）或实盘。

### 前提条件

1. **富途账户**：需拥有富途牛牛交易账户，并在富途官网完成开户与合规确认。
2. **OpenD 网关**：需手动从 [富途 Open API 官网](https://openapi.futunn.com/) 下载安装 OpenD。安装后系统会自动查找并启动它。
3. **行情权限**：行情订阅额度、历史 K 线额度按用户等级动态分配，详见 [权限说明](https://openapi.futunn.com/futu-api-doc/intro/authority.html)。
4. **Python SDK**：`futu-api` 已包含在主依赖中，`pip install -e .` 即可安装。

### OpenD 管理

OpenD 由 Stocker 自动管理（`integrations/futu/opend_manager.py`）：

- **自动查找**：在常见安装路径、系统 PATH、项目 `data/opend/` 目录中查找 OpenD 可执行文件
- **自动拉起**：找到后以无窗口后台进程方式启动（`-no_monitor=1 -console=0`）
- **登录等待**：如果 OpenD 启动但未登录，终端会提示用户登录并等待（最长 5 分钟）
- **自动停止**：Stocker 关闭时自动终止 OpenD 进程
- **智能跳过**：如果 OpenD 已在运行（端口可达），直接连接，不会重复启动

如需手动管理 OpenD，可设置环境变量指向已运行的实例，系统检测到端口可用后会跳过自动启动。

### 环境配置

在项目根目录 `.env` 文件中添加以下配置：

```env
# Broker 选择（futu / simulated）
STOCKER_BROKER_TYPE=futu

# 系统执行模式（observe / active）
STOCKER_EXECUTION_MODE=observe

# Futu OpenD 连接
STOCKER_FUTU_HOST=127.0.0.1
STOCKER_FUTU_PORT=11111

# 交易环境（simulate / real）
STOCKER_FUTU_TRD_ENV=simulate

# 默认市场（HK / US / CN）
STOCKER_FUTU_MARKET=HK

# 交易密码（模拟盘可留空）
STOCKER_FUTU_TRADE_PWD=

# 行情功能开关
STOCKER_FUTU_QUOTE_ENABLED=true

# 启动时默认订阅的标的（逗号分隔，可留空）
STOCKER_FUTU_SUBSCRIBE_CODES=HK.00700,US.AAPL
```

### 启动方式

只需一步：运行 `stocker serve` 或 `python runserver.py`。

系统会自动完成以下流程：

1. **检测 OpenD** — 检查 `127.0.0.1:11111` 是否已有 OpenD 运行
2. **查找 OpenD** — 在常见安装路径和 PATH 中搜索 OpenD 可执行文件
3. **自动启动** — 以后台进程方式启动 OpenD（无窗口、无守护进程）
4. **等待登录** — 如果 OpenD 未登录，终端提示用户登录并轮询等待（最长 5 分钟）
5. **连接与初始化** — 行情/交易连接 → 账户发现 → 交易解锁 → 默认行情订阅

如果已经手动启动了 OpenD（或使用富途牛牛客户端内置的 OpenD），系统会直接连接，不会重复启动。

如果本地未安装 OpenD，系统会在终端打印安装指引并降级到内置模拟盘。

### 环境切换安全设计

Stocker 采用双层安全保护，防止误操作导致真实交易：

| 层级 | 配置项 | 值 | 作用 |
| --- | --- | --- | --- |
| 系统层 | `STOCKER_EXECUTION_MODE` | `observe` / `active` | 控制 Supervisor 是否允许调用交易执行 |
| 富途层 | `STOCKER_FUTU_TRD_ENV` | `simulate` / `real` | 控制富途交易落到模拟盘还是实盘 |

推荐的安全配置组合：

- **开发/测试**：`execution_mode=active` + `trd_env=simulate`（允许执行，但只到模拟盘）
- **只读监控**：`execution_mode=observe` + `trd_env=simulate`（只分析不交易）
- **实盘交易**：`execution_mode=active` + `trd_env=real`（需额外确认，日志会打印醒目警告）

即使在 `observe` 模式下配置了 `trd_env=real`，`FutuBroker.place_order()` 也会在代码层面拒绝所有下单请求。

### 架构概览

```
Stocker / Python SDK
    ↓
OpenD（本地网关, 127.0.0.1:11111）
    ↓
富途后端服务
```

核心模块路径：

- `src/stocker/integrations/futu/` — SDK 封装（quote_client、trade_client、handlers、mappers、config、opend_manager）
- `src/stocker/engine/runtime.py` — FutuRuntime 生命周期管理
- `src/stocker/broker/futu.py` — FutuBroker（适配 BaseBroker 抽象）
- `src/stocker/broker/factory.py` — Broker 工厂（根据配置选择 futu / simulated）
