# A 股历史日线数据源 fallback 设计

## 背景

当前仓库的数据源包括 tushare、baostock 和 akshare。A 股历史日线下载链路目前默认通过 baostock 获取数据，下载失败时不会自动尝试其它数据源。每日收盘后执行 A 股历史日线下载时，如果默认数据源临时不可用、返回空数据或返回格式异常，会导致当日下载失败。

本设计只覆盖 A 股股票历史日线下载，不扩展 ETF、港股通或其它每日下载任务。

## 目标

- A 股历史日线下载支持按配置的数据源顺序 fallback。
- 默认顺序为 `baostock,tushare,akshare`。
- 当某个数据源抛异常、返回空数据或返回必要字段缺失/格式异常时，自动尝试下一个数据源。
- 任一数据源返回有效数据后，复用现有入库流程保存。
- 保持现有 DAG schedule、task boundary 和依赖关系不变。

## 非目标

- 不修改 ETF、港股通、daily_basic、涨跌停、停复牌等其它下载任务。
- 不在 storage 保存失败时切换数据源；入库失败应作为真实失败暴露。
- 不改变现有表结构或存储路由。
- 不调整 Airflow DAG 的 schedule、retries、SLA、max_active_runs 或任务分片策略。

## 配置

在 `[download]` 中新增配置项：

```ini
[download]
process_count = 4
stock_history_provider_order = baostock,tushare,akshare
```

`conf/global_settings.py` 继续作为 `config.ini` 到环境变量的桥接层。新增配置解析后写入环境变量，例如：

```text
DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER=baostock,tushare,akshare
```

如果配置缺失，使用默认值 `baostock,tushare,akshare`。provider order 解析规则：

- 使用逗号分隔。
- 去除每个 provider 名称前后的空白。
- 忽略空项。
- 去重并保留首次出现顺序。
- 只允许 `baostock`、`tushare`、`akshare`。
- 遇到未知 provider 时抛出明确的配置错误，避免静默跳过错误配置。

## 下载链路设计

fallback 逻辑放在下载编排层，而不是 DAG 层。这样可以复用现有 DAG 和任务分片结构，同时让单只下载和批量下载走一致的数据源选择规则。

建议在下载层补齐以下边界：

- `Downloader` 提供“按 provider 下载 A 股历史日线”的小接口，将 provider 名称映射到具体实现：
  - `baostock` → 现有 baostock A 股历史日线下载函数。
  - `tushare` → tushare A 股历史日线下载函数或最小适配后的函数。
  - `akshare` → akshare A 股历史日线下载函数或最小适配后的函数。
- `DownloadManager` 在 A 股历史日线下载时读取 provider order，按顺序尝试。
- 任一 provider 返回有效 `DataFrame` 后停止尝试，并进入现有保存流程。
- 如果所有 provider 都失败，返回失败并保留每个 provider 的失败原因日志。

fallback 触发条件：

- provider 调用抛异常。
- 返回 `None`。
- 返回空 `DataFrame`。
- 返回数据缺少保存历史日线所需的必要字段。
- 返回数据字段格式无法转换为现有 storage 期待格式。

不触发 fallback 的情况：

- `save_history_data` 或 storage 层失败。
- 数据库连接、约束冲突、写入权限等入库异常。

## 数据格式校验

A 股历史日线 fallback 的有效数据应满足现有保存逻辑所需字段。实现时应在保存前做轻量校验和必要字段对齐，避免不同 provider 的字段名差异直接泄漏到 storage 层。

字段适配应尽量靠近 provider 下载边界，保持 `DownloadManager` 只判断“是否得到有效历史日线 DataFrame”。如果某个 provider 的原始字段需要重命名或类型转换，应在对应 downloader 或 provider adapter 内完成。

## 日志与错误处理

每次 provider 尝试都应记录：

- provider 名称。
- 股票代码。
- 下载日期范围。
- 复权类型。
- 失败原因或成功返回的数据行数。

如果某个 provider 失败但后续 provider 成功，整体下载应视为成功，同时日志中保留 fallback 过程，便于排查数据源稳定性。

如果所有 provider 都失败，最终错误信息应汇总各 provider 的失败原因，避免只看到最后一个 provider 的错误。

## DAG 集成

不修改 `dags/download_stock_history_daily.py` 的调度、任务依赖或分片边界。现有每日收盘后 A 股历史日线下载任务继续调用 `DownloadManager`，fallback 在下载层内部完成。

批量下载路径如果绕过 `DownloadManager` 直接在 multiprocessing worker 中选择 downloader，也需要复用同一 provider-order 解析和 fallback 逻辑，确保每日 DAG 分片任务和单只下载行为一致。

## 测试计划

- 配置解析测试：缺失配置时默认 `baostock,tushare,akshare`。
- 配置解析测试：自定义顺序被正确解析、去空、去重。
- 配置解析测试：未知 provider 抛出明确错误。
- fallback 测试：baostock 抛异常后尝试 tushare。
- fallback 测试：baostock 返回空数据后尝试 tushare。
- fallback 测试：baostock 返回字段缺失数据后尝试 tushare。
- 成功短路测试：首个 provider 成功时不再调用后续 provider。
- 全失败测试：所有 provider 失败时返回失败并包含各 provider 失败原因。
- 入库失败测试：下载成功但保存失败时不尝试下一个 provider。

验证命令遵循仓库约定，使用 `uv run pytest` 执行 focused tests。

## 风险与约束

- 不同 provider 的历史日线字段、复权语义和停牌日返回行为可能不完全一致。实现时只做本次需要的最小字段对齐，不扩展到行情质量仲裁。
- fallback 可能增加每日 API 请求量；只有前序 provider 失败时才会调用后续 provider，避免无谓放大请求。
- provider 顺序配置错误应尽早失败，否则会导致每日任务静默使用非预期数据源。

## 验收标准

- A 股历史日线下载按 `stock_history_provider_order` 顺序尝试数据源。
- baostock 下载异常、空数据或字段异常时会自动尝试下一个配置的数据源。
- 任一 provider 下载成功后复用现有入库流程保存。
- 入库失败不会触发 provider fallback。
- 每日 A 股历史日线 DAG 的 schedule、任务边界和依赖关系保持不变。
- 相关 focused tests 通过。
