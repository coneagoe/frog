# 港股通 TuShare BFQ 下载设计

## 目标

修正港股通每日不复权（BFQ）下载在 TuShare 首选回退链中必然失败的问题，同时保持复权数据的语义正确。

## 背景

当前港股通每日任务请求 `AdjustType.BFQ`，但 TuShare 下载适配器仅接受 `AdjustType.HFQ` 并调用 `hk_daily_adj`。该接口没有 `adjust` 参数，且其文档定义的复权结果为前复权（QFQ），不能作为本仓库的 HFQ 数据来源。因此 BFQ 请求会在发起 TuShare API 调用前失败，并无谓回退到 AkShare。

TuShare 的 `hk_daily` 接口提供原始港股日线，适合作为 BFQ 数据来源。现有 AkShare 实现保留为 HFQ 数据来源及下载失败时的回退来源。

## 设计

### TuShare 港股下载适配器

`download_history_data_stock_hk_ts` 按请求复权类型路由：

| 请求 | 行为 |
| --- | --- |
| `DAILY` + `BFQ` | 调用 TuShare `hk_daily`，并通过既有港股标准化逻辑输出规范 DataFrame。 |
| `DAILY` + `HFQ` | 抛出明确的不支持异常，不调用 TuShare；由既有 fallback chain 尝试 AkShare。 |
| 非日线或 QFQ | 保持不支持并抛出明确异常。 |

不将 `hk_daily_adj` 作为 HFQ 数据源。该接口的 `adj_factor` 对应官方说明的 QFQ 计算规则，直接使用会把 QFQ 数据错误存入 HFQ 表。

### 回退链和存储

无需改变 provider 顺序、`DownloadManager` 回退机制、Airflow DAG 或存储表路由：

- 日线 BFQ：TuShare 首选成功时直接保存至 `history_data_daily_hk_stock_none`；TuShare 失败或返回无效数据时回退 AkShare。
- 日线 HFQ：TuShare 明确拒绝后回退 AkShare，并保存至现有 HFQ 表。

## 错误处理

适配器错误信息应说明受支持的组合，避免将 `hk_daily_adj` 误称为 HFQ 接口。现有 `DownloadManager` 继续将适配器异常视为可回退失败。

## 测试与验证

测试先行，覆盖：

1. BFQ 调用 `hk_daily`，不调用 `hk_daily_adj`，并生成标准字段、日期、数值类型和股票代码。
2. HFQ 不调用 TuShare 客户端，并保留可被 fallback chain 捕获的异常。
3. BFQ manager 路径中 TuShare 成功时不调用 AkShare；TuShare BFQ 失败时仍回退 AkShare。
4. 运行相关 TuShare downloader、DownloadManager 及 provider-order 测试；必要时增加 DAG-source 测试确认 BFQ 任务语义未变。

## 不在范围内

- 不新增港股 QFQ 存储路径。
- 不在仓库内从 `adj_factor` 推导 HFQ。
- 不更改 DAG 的调度、任务边界或当前 BFQ 业务语义。
