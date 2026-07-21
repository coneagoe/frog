# 港股通不复权历史日线 fallback 设计

## 背景

现有 `download_hk_ggt_history_daily` DAG 已有港股通历史日线框架，但当前链路固定下载后复权（HFQ）数据，并且只走 TuShare 单一数据源。paper trading 场景需要使用不复权价格，避免复权价格进入模拟成交、持仓估值和现金流水。

当前港股通历史数据链路有几个重要约束：

- DAG 中 `DEFAULT_START_DATE` 为 `2010-01-01`，调用 `DownloadManager.download_hk_ggt_history(... adjust=AdjustType.HFQ)`。
- `DownloadManager.download_hk_ggt_history()` 目前是单 provider 路径，不具备 A 股历史日线已有的 fallback chain。
- TuShare 港股 downloader 当前只支持 HFQ，并对非 HFQ adjust 直接报错。
- AkShare 的港股历史接口支持不复权日线。
- storage 当前港股通历史表和读写路由以 HFQ 为主，不能直接把不复权数据写入现有 HFQ 表。

## 目标

- 保留现有港股通 HFQ downloader 和已有 HFQ 数据，不删除、不迁移。
- 将 `dags/download_hk_ggt_history_daily.py` 改为下载港股通不复权日线。
- 不复权历史起始日为 `2026-01-01`；首次回补后，后续运行按不复权表最新日期增量补齐。
- 为港股通历史下载增加可配置 provider fallback chain，默认顺序为 `tushare,akshare`。
- 当 provider 抛异常、返回 `None`、空数据、缺少核心字段或核心数值不可转换时，尝试下一个 provider。
- 全部 provider 失败时，该标的下载失败，并保留各 provider 失败原因。
- 不复权数据使用独立存储表，避免与 HFQ 数据混存。

## 非目标

- 不修改 Airflow DAG 的 schedule、依赖关系、retries、SLA 或 `max_active_runs`。
- 不实现港股通交易规则、paper trading 撮合规则或费用规则。
- 不回填 2026-01-01 以前的不复权数据。
- 不删除或迁移已有 HFQ 表和数据。
- 不让 storage 写入失败触发 provider fallback；入库失败应作为真实失败暴露。
- 不把本次 HK fallback 扩展到 A 股、ETF 或其它下载任务。

## 调整类型语义

实现层应明确支持“不复权”语义。仓库中已有 `AdjustType.BFQ` 在部分入口表示不复权；本设计允许两种兼容实现：

- 增加 `AdjustType.NONE` 作为不复权的清晰别名，同时保留 `BFQ` 兼容。
- 或继续使用 `AdjustType.BFQ` 作为内部不复权值，但 DAG、任务命名和文档中使用 `none` / `unadjusted` 语义，避免误解。

无论选择哪种实现，HFQ 现有行为必须保持不变。

## 配置

新增港股通历史日线 provider order 配置，独立于 A 股：

```ini
[download]
hk_stock_history_provider_order = tushare,akshare
```

`conf/global_settings.py` 将配置桥接到环境变量：

```text
DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER=tushare,akshare
```

解析规则与 A 股 provider order 保持一致：

- 使用逗号分隔。
- 去除 provider 名称前后空白。
- 忽略空项。
- 去重并保留首次出现顺序。
- 只允许 `tushare`、`akshare`。
- 遇到未知 provider 时抛出明确配置错误。

默认值为 `tushare,akshare`。在当前代码能力下，TuShare 对不复权请求会失败并 fallback 到 AkShare；保留该默认顺序是为了将来 TuShare 增加不复权支持后无需调整配置。

## 下载链路设计

fallback 逻辑放在下载编排层，而不是 DAG 层。DAG 只表达“港股通不复权日线下载任务”，provider 选择和失败切换由下载层统一处理。

建议边界如下：

- `Downloader` 增加按 provider 下载港股通历史日线的小接口。
  - `tushare` → 现有 TuShare HK downloader。HFQ 请求继续成功；不复权请求当前会抛出不支持异常。
  - `akshare` → AkShare HK history downloader，使用 `adjust=""` 获取不复权数据。
- `DownloadManager.download_hk_ggt_history()` 或其内部 helper 读取 HK provider order，并按顺序尝试。
- 任一 provider 返回有效 `DataFrame` 后停止尝试，并进入现有保存流程。
- 如果所有 provider 都失败，返回失败并记录每个 provider 的失败原因。

fallback 触发条件：

- provider 调用抛异常。
- 返回 `None`。
- 返回空 `DataFrame`。
- 返回数据缺少核心字段。
- 核心数值字段无法转换为数值。

不触发 fallback 的情况：

- 已得到有效数据后，storage 保存失败。
- 数据库连接、表不存在、约束冲突、写入权限等入库异常。

## 数据格式校验

不同 HK provider 返回字段不完全一致，因此 fallback 有效性校验只要求公共核心字段：

- `日期`
- `股票代码`
- `开盘`
- `收盘`
- `最高`
- `最低`
- `成交量`
- `成交额`

核心数值字段应能转换为数值。以下字段作为可选字段，存在则保存，不存在则允许为空：

- `涨跌额`
- `涨跌幅`
- `换手率`
- `振幅`

字段适配应尽量靠近 provider downloader 或 provider adapter，避免把 provider 原始字段差异泄漏到 storage 层。

## 存储设计

不复权港股通日线必须使用独立表，最低需要新增：

```text
history_data_daily_hk_stock_none
```

表结构建议与现有港股通 HFQ 日线表保持一致，便于复用保存和读取逻辑。差异只体现在表名和 adjust 路由。

需要调整的边界：

- ORM model 增加不复权日线表模型。
- storage metadata 自动导入该 model。
- `get_table_name()` 或等价路由能按 `SecurityType.HK_GGT_STOCK + PeriodType.DAILY + AdjustType.NONE/BFQ` 返回不复权表。
- `save_history_data_hk_stock()` 不再强制写入 HFQ 表，而是尊重 adjust。
- `load_history_data_stock_hk_ggt()` 或新增通用读取接口能读取不复权表，供增量计算和后续 paper trading 使用。

HFQ 表和读取路径继续保留，避免破坏现有分析或历史数据。

## DAG 集成

`dags/download_hk_ggt_history_daily.py` 的语义从“HK GGT HFQ history download”切换为“HK GGT unadjusted daily history download”：

- `DEFAULT_START_DATE = "2026-01-01"`。
- 下载调用使用不复权 adjust。
- task id、函数名、日志前缀和 Redis summary 文案从 `hfq` 改为 `none` 或 `unadjusted`。
- 保持 `PARTITION_COUNT = 1`。
- 保持 schedule、依赖关系、`catchup` 和 `max_active_runs` 不变。

首次运行时，storage 中没有不复权记录，因此从 `2026-01-01` 回补。后续运行时，下载层基于不复权表中该标的最新日期计算 `last_date + 1 day` 到当天的增量范围。

## 日志与错误处理

每次 provider 尝试应记录：

- provider 名称。
- 股票代码。
- 日期范围。
- adjust 类型。
- 成功行数或失败原因。

如果前序 provider 失败但后续 provider 成功，整体下载视为成功，但日志保留 fallback 过程。若所有 provider 失败，最终错误信息应汇总各 provider 失败原因，方便区分配置错误、provider 不支持和数据质量问题。

## 测试计划

focused tests 覆盖以下内容：

- HK provider order 默认值为 `tushare,akshare`。
- HK provider order 支持自定义顺序、去空、去重。
- HK provider order 遇到未知 provider 抛出明确错误。
- HK fallback 在 TuShare 不支持不复权时尝试 AkShare。
- HK fallback 在 provider 抛异常、返回 `None`、空数据、缺少核心字段、核心数值坏值时尝试下一个 provider。
- 首个 provider 成功时不调用后续 provider。
- 所有 provider 失败时返回失败并包含失败原因。
- 下载成功但保存失败时不尝试下一个 provider。
- 不复权 HK 日线表路由、保存和读取正确。
- DAG 使用 `2026-01-01` 起始日和不复权 adjust，task/log 命名不再标记 HFQ。

验证命令遵循仓库约定，使用 `uv run pytest` 执行 focused tests。

## 风险与约束

- 当前 TuShare HK downloader 不支持不复权，因此默认链路在短期内会实际依赖 AkShare。
- 新表必须纳入 ORM metadata 导入，否则运行时可能无法自动创建或迁移。
- 新表如需被数据库导入导出脚本管理，应同步更新 `tools/db_common.sh`。
- 下游如果仍默认读取 HFQ 表，则 paper trading 需要显式使用不复权读取路径。
- provider 返回的停牌日、成交量单位和可选字段语义可能不完全一致；本设计只做本次需要的最小字段规范化，不做行情质量仲裁。

## 验收标准

- 现有 HFQ 港股通 downloader 和 HFQ 数据路径保持可用。
- `download_hk_ggt_history_daily` DAG 下载不复权日线，起始日为 `2026-01-01`。
- 不复权数据写入独立表，不与 HFQ 数据混存。
- HK provider fallback 顺序可通过 `DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER` 配置，默认 `tushare,akshare`。
- provider 异常、空数据或数据格式异常会触发 fallback。
- storage 保存失败不会触发 fallback。
- 首次运行回补 2026-01-01 起数据，后续基于不复权表增量下载。
- 相关 focused tests 通过。
