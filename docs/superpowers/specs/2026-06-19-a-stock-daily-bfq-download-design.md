# A 股日线不复权下载入库设计

## 背景

当前 A 股历史行情已有前复权和后复权两套日线/周线表。baostock 下载层已经能通过 `AdjustType.BFQ` 使用 `adjustflag=3` 获取不复权行情，但存储层没有 A 股日线 BFQ 表和路由，导致 `tools/download_stock_history.py none` 或 DAG 中传入 `AdjustType.BFQ` 时无法保存到 DB。

paper trade 的成交、持仓、市值等应使用真实市场报价，即不复权价格。因此需要补齐 A 股日线不复权行情的下载入库链路。

## 目标

- 支持从 baostock 下载 A 股日线不复权行情并保存到 DB。
- 只覆盖 A 股日线，不扩展 A 股周线、ETF 或港股。
- 直接在 `dags/download_stock_history_daily.py` 中增加 BFQ 调用，不新增独立 DAG 文件。
- 保持现有 HFQ 日线 DAG 行为不变。

## 非目标

- 不迁移或合并现有 `qfq/hfq` 表结构。
- 不修改 DAG 的 schedule、retries、SLA、max_active_runs 或分片策略。
- 不改变 baostock downloader 的 API 调用字段或价格标准化逻辑。
- 不把 BFQ 扩展到周线、ETF、港股或其它数据源。

## 设计

### DB 模型

新增表 `history_data_daily_a_stock_bfq`，字段与 `history_data_daily_a_stock_qfq` 和 `history_data_daily_a_stock_hfq` 保持一致：

- 主键：`日期`、`股票代码`
- 行情字段：`开盘`、`收盘`、`最高`、`最低`、`成交量`、`成交额`
- 扩展字段：`换手率`、`涨跌幅`、`市盈率_TTM`、`市净率_MRQ`、`市销率_TTM`、`市现率_TTM`、`是否ST`

SQLAlchemy 模型命名为 `HistoryDataDailyAStockBFQ`，表名常量命名为 `tb_name_history_data_daily_a_stock_bfq`。

### 存储路由

在 `storage/storage_db.py` 中补齐 `SecurityType.STOCK + PeriodType.DAILY + AdjustType.BFQ` 路由，返回 `history_data_daily_a_stock_bfq`。

`StorageDb.save_history_data_stock()` 继续复用当前统一保存逻辑，不增加新方法。`StorageDb.load_history_data_stock()` 支持用 `AdjustType.BFQ` 读取 A 股日线 BFQ 表。`PeriodType.WEEKLY + AdjustType.BFQ` 继续抛出或返回不支持，避免隐式创建未规划的数据集。

### 下载链路

`download/dl/downloader_baostock.py` 已支持 `AdjustType.BFQ -> adjustflag=3`，无需修改。`DownloadManager.download_stock_history()` 会通过 `get_table_name()` 获取增量表名；存储路由补齐后，现有下载流程即可保存 BFQ 日线。

### DAG 集成

在 `dags/download_stock_history_daily.py` 内增加 BFQ 分片任务，复用现有 HFQ DAG 的结构：

- 新增 `download_stock_history_bfq_partition_task()`，逻辑与 HFQ 分片任务一致，但传入 `AdjustType.BFQ`。
- 新增 BFQ 分片 `PythonOperator` 列表，task id 使用 `download_stock_history_bfq_pXX`。
- 直接在同一个 DAG 中运行 BFQ 下载，不新增 DAG 文件。
- 保持现有 `download_stock_history_hfq_pXX` 任务和 Redis 聚合逻辑可用。

Redis 聚合可以继续以现有 HFQ 结果作为 DAG 成功标记，也可以纳入 BFQ 计数；实现时优先保持聚合函数简单可读，且不改变 Redis key。

### 导入导出

更新 `tools/db_common.sh` 的 `BUSINESS_TABLES`，加入 `history_data_daily_a_stock_bfq`，确保 `db_export.sh` 和 `db_import.sh` 不漏掉新表。

## 测试计划

- storage 单元测试：验证 A 股日线 BFQ 表名解析到 `history_data_daily_a_stock_bfq`。
- storage 保存测试：验证 `save_history_data_stock(..., PeriodType.DAILY, AdjustType.BFQ)` 写入 BFQ 表。
- load 测试：验证 `load_history_data_stock(..., PeriodType.DAILY, AdjustType.BFQ)` 查询 BFQ 表。
- DAG source 测试：验证 `download_stock_history_daily.py` 同时包含 HFQ 和 BFQ 分片任务，并且 BFQ 任务传入 `AdjustType.BFQ`。
- focused 验证命令使用 `uv run pytest`，符合仓库约定。

## 风险与约束

- 新表由 `Base.metadata.create_all()` 自动创建；已有数据库需要在服务启动或初始化路径运行后才会出现。
- 新增 DAG 任务会增加每日 baostock 请求量，失败处理应沿用现有分片失败聚合方式。
- DAG 文件中直接增加 BFQ 任务会让单个 DAG 文件更长，但符合本次“直接在现有 daily DAG 中调”的约束。

## 验收标准

- `AdjustType.BFQ` 的 A 股日线下载可成功保存到 `history_data_daily_a_stock_bfq`。
- 现有 HFQ 日线 DAG 任务名、调度和行为保持兼容。
- `tools/db_common.sh` 包含新 BFQ 表。
- 相关 focused tests 通过。
