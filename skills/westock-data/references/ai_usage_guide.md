# WeStock Data - AI 深度参考指南

> **定位**：本文档提供详细的数据格式参考、分析模板。命令列表和基本用法请参见 [SKILL.md](../SKILL.md)。
> 完整分析场景示例请参见 [scenarios-guide.md](./scenarios-guide.md)。

---

## 一、输出格式

命令执行后输出 **Markdown 表格**，AI 直接从表格中读取数据进行分析。

**单股查询**：输出一个 Markdown 表格，每列对应一个数据字段。

**批量查询**：输出批量摘要行 + 每个 symbol 的独立表格。

**查询失败**：输出 JSON 格式的错误信息（含 `success: false` 和 `error` 对象）。

---

## 二、各命令数据格式

### K线（`kline`）

输出表格列：`date | open | last | high | low | volume | amount | exchange`

> K线数值为原始数值，AI 在分析时自行进行单位换算

### 资金数据

#### 港股（`hkfund`）

| 字段 | 单位 | 说明 |
|------|------|------|
| `TotalNetFlow` | 港元 | 总净流入 |
| `MainNetFlow` | 港元 | 主力净流入 |
| `RetailNetFlow` | 港元 | 散户净流入 |
| `ShortShares` | 股 | 卖空数量 |
| `ShortRatio` | % | 卖空比例 |
| `LgtHoldInfo` | json | 南下资金信息 |

#### A股（`asfund`）

| 字段 | 单位 | 说明 |
|------|------|------|
| `MainNetFlow` | 元 | 主力净流入（正=流入，负=流出）|
| `JumboNetFlow` | 元 | 超大单净流入 |
| `BlockNetFlow` | 元 | 大单净流入 |
| `MidNetFlow` | 元 | 中单净流入 |
| `SmallNetFlow` | 元 | 小单净流入 |

#### 美股（`usfund`）

| 字段 | 单位 | 说明 |
|------|------|------|
| `ShortRatio` | % | 卖空比例 |
| `ShortShares` | 股 | 卖空股数 |
| `ShortRecoverDays` | 天 | 回补天数 |

### 机构评级（`rating`）

**A股**：输出表格，列含 `code | name | forecastInstitutions | targetPriceAvg | ratingBuyCnt | ratingIncCnt | ratingHoldCnt | ratingDecCnt | ratingSellCnt | ratingCnt`

**港股/美股**：同上，额外可能含 `earningsForecast`（盈利预测，JSON 格式）

> ⚠️ 港股/美股评级字段（ratingBuyCnt等）MCP服务暂不返回，当前仅港股 `earningsForecast` 可用

### A股一致预期（`consensus`）

输出表格，列含 `code | name | targetPrice`，以及 `forecasts` 数组中的 `year | revenue | netProfit | eps | pe | pb | ps | revenueYoy | netProfitYoy | institutionCnt`

**分析要点**：目标价 vs 当前价（上涨空间）、EPS增速（盈利确定性）、PE走势（估值消化）、机构数（共识可信度）

### 技术指标（`technical`）

#### 截面查询

输出表格列：`code | name | date | closePrice | ma.MA_5 | ma.MA_10 | ... | macd.DIF | macd.DEA | macd.MACD | kdj.KDJ_K | ...`

嵌套对象（ma/macd/kdj/rsi/boll/bias/wr/dmi）的字段会展平为 `分组.字段名` 格式。

#### 历史区间查询

输出表格，每行一个交易日，列名同上。

### 筹码成本（`chip`）

#### 截面

输出表格列：`code | name | date | closePrice | chipProfitRate | chipAvgCost | chipConcentration90 | chipConcentration70`

#### 历史区间

输出表格，每行一个交易日，列名同上。

**解读**：盈利率>80%=获利盘占优；收盘价>平均成本=整体盈利；集中度越低=筹码越集中（主力控盘可能）

### 市场/指数/板块（`market`）

#### 截面（`MarketQuoteData`）关键字段

| 字段 | 说明 |
|------|------|
| `closePrice`/`changePct` | 收盘价/涨跌幅 |
| `chg5D`/`chg10D`/`chg20D`/`chg60D`/`chgYtd` | 多日涨跌幅(%) |
| `advancingCount`/`decliningCount` | 上涨/下跌家数 |
| `mainNetFlow`/`jumboNetFlow`/`blockNetFlow` | 主力/超大单/大单净流入（沪深，元）|
| `midNetFlow`/`smallNetFlow` | 中单/小单净流入（沪深，元）|
| `totalNetFlow`/`retailNetFlow` | 总/散户净流入（港股，港元）|

> ⚠️ 美股不支持资金流向字段

#### 历史区间

输出表格，每行一个交易日，含 `date | closePrice | changePct | mainNetFlow | ...`

### 市场资讯（`marketnews`）

输出 Markdown 表格，列含 `time | id | type | symbol | title | url | ...`

**预设市场**：`hs`(沪深)、`sh`(沪市)、`sz`(深市)、`hk`(港股)、`us`(美股)，或自定义逗号分隔指数代码

### 分红历史（`dividend history`）

输出表格，字段因市场不同：

- **A股**：`reportEndDate | exDiviDate | rightRegDate | cashDiviRMB | dividendPlan`
- **港股**：`reportEndDate | exDiviDate | cashPayDate | cashDivPerShare | specialDivPerShare | totalCashDivi`
- **美股**：`exDivDate | regDate | payDate | dividendCurrency | dividend | dividendPlan`

> 美股可能额外包含 `splitInfo`（拆合股信息）

**参数说明**：
- `years`：查询年数，默认5年（可自定义，如 `--years 10`）
- 返回记录按报告期/除权日降序排列（最新的在前）

### 业绩预告（`reserve`）

输出表格，字段因市场不同：

- **A股**：`reportEndDate | disclosureEndDate | disclosureDate | disclosureDesc`
- **港股**：`reportEndDate | disclosureDesc`
- **美股**：`reportEndDate | disclosureDate | disclosureDesc`

---

## 三、货币单位处理

> ⚠️ **重要**：港股财报返回港元/美元，美股返回美元，展示时**必须**标注正确货币单位

**港股**：检查 `CurrencyType`（"港币"/"美元"/"人民币"）和 `CurrencyUnit` 字段
- ✅ 正确：`营业收入：832.3亿港元`
- ❌ 错误：`营业收入：¥832.3亿`

**跨期对比注意**：同比/环比增长率可能受汇率换算影响，展示时建议添加说明：`"注：同比数据可能受汇率波动影响"`

---

## 四、单位换算

| 数据类型 | 原始单位 | 转换 |
|---------|---------|------|
| 成交量 | 手 | ÷10000=万手 |
| 成交额/市值/主力资金 | 元 | ÷100000000=亿元 |
| 港股金额 | 港元 | ÷100000000=亿港元 |
| 美股金额 | 美元 | ÷100000000=亿美元 |
| 卖空数量 | 股 | ÷1000000=百万股 |

---

## 五、分析模板

### 成交量分析

1. `kline <CODE> day 20` → 从表格中提取 `volume` 列
2. 计算：平均值、最大/最小值、前10日均值 vs 后10日均值
3. 识别：放量日（>均值×1.5）、缩量日（<均值×0.5）

### 资金流向分析

**A股**：`asfund <CODE>` → 提取 `MainNetFlow`/`JumboNetFlow`/`BlockNetFlow` → 转换单位（元→亿元）→ 统计净流入/流出天数

**港股**：`hkfund <CODE>` → 提取 `TotalNetFlow`/`MainNetFlow`/`ShortRatio`/`LgtHoldInfo` → 分析主力趋势、卖空占比、南下资金变化

**美股**：`usfund <CODE>` → `ShortRatio`>10%需关注，`ShortRecoverDays`>5天需关注

**指数/板块**：`market <CODE>` → 提取 `mainNetFlow`/`jumboNetFlow`/`blockNetFlow` → 转换单位 → 判断主力方向

### 技术指标分析

**MACD**：DIF与DEA交叉（金叉=买信号/死叉=卖信号）、MACD柱正负变化、DIF/DEA相对0轴位置

**KDJ**：K与D交叉、J值>80超买/<20超卖

**RSI**：RSI_6>70超买/<30超卖，RSI_6与RSI_12背离

**均线**：多头排列（MA5>MA10>MA20>MA60）、MA60/120/250作为支撑/压力位

### 筹码趋势分析（历史区间）

- 盈利率上升 = 获利盘增加（股价上涨）
- 平均成本抬升 = 筹码成本中枢上移（主力可能建仓）
- 集中度下降 = 筹码趋于集中（主力吸筹控盘）
- 集中度上升 = 筹码趋于分散（可能派发）

### 机构评级分析（港股/美股）

1. 评级共识度：`(ratingBuyCnt + ratingIncCnt) / ratingCnt`
2. 目标均价 vs 当前价 → 上涨/下跌空间
3. 港股：`earningsForecast` EPS × 目标PE → 合理估值区间

### A股一致预期分析

1. 目标价 vs 当前价 → 上涨空间
2. 多年度EPS增速 → 盈利增长确定性
3. PE走势 → 估值是否逐年降低（估值消化）
4. `institutionCnt` → 共识覆盖度

---

## 六、格式化输出规范

- 金额超过亿元：使用"亿元"/"亿港元"/"亿美元"
- 成交量超过万手：使用"万手"
- 涨跌幅：保留2位小数，带 +/- 号
- 日期：YYYY-MM-DD 格式
- 数据为空时说明"暂无数据"，**不可伪造数据**
- 港股/美股财务数据必须标注货币单位
