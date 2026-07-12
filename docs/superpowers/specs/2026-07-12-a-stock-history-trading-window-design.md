# A 股历史日线交易日窗口预处理设计

## 背景

A 股历史日线下载已经支持按 `baostock,tushare,akshare` 顺序 fallback。实际运行中出现过这样的增量窗口：最后一条记录是交易日周五，下一次任务在周日运行，下载窗口变成周六到周日。该窗口没有 A 股交易日，baostock 返回空数据，tushare 返回 `None`，随后继续 fallback 到 akshare 并触发代理重试，最终被记录为所有数据源失败。

这种情况不是数据源故障，而是下载前没有把原始日期窗口规整为有效交易日窗口。

## 目标

- 只覆盖 A 股股票历史日线下载。
- 在调用任何 provider 前计算 A 股交易日窗口。
- 原始窗口没有 A 股交易日时直接跳过下载并返回成功。
- 原始窗口有交易日时，将下载窗口收缩到首个交易日和最后一个交易日。
- 单只下载和批量分片下载行为一致。
- 保持现有 provider fallback、数据格式校验和 storage 保存边界不变。

## 非目标

- 不修改 ETF、港股通、daily_basic、涨跌停、停复牌等其它下载任务。
- 不修改 DAG schedule、task boundary、依赖、重试或 SLA。
- 不引入 provider API 作为交易日日历来源。
- 不改变数据源 fallback 顺序或字段归一逻辑。

## 设计

### 交易日 helper

在 `stock/market.py` 增加一个 A 股交易日窗口 helper：

```python
def get_a_stock_trading_window(start_date: str, end_date: str) -> tuple[str, str] | None:
    ...
```

行为：

- 接受 `YYYYMMDD`、`YYYY-MM-DD` 等 `pandas.to_datetime` 可解析的日期字符串。
- 使用现有 `pandas_market_calendars` 的 `XSHG` 日历。
- 查询 `[start_date, end_date]` 闭区间内的交易日。
- 没有交易日时返回 `None`。
- 有交易日时返回 `(first_trading_day, last_trading_day)`，格式为 `YYYYMMDD`。
- 如果 `start_date > end_date`，返回 `None`。
- 日历查询或日期解析异常不静默吞掉，由调用方记录错误并使下载失败。

使用 `XSHG` 是为了复用仓库已有 A 股交易日判断体系。沪深 A 股日线交易日基本一致，适合作为股票历史日线下载窗口判断。

### 单只下载路径

`DownloadManager.download_stock_history()` 当前会根据最后一条 DB 记录计算 `actual_start_date`。在得到 `actual_start_date` 后、调用 `_download_stock_history_with_fallback()` 前，加入交易日窗口计算：

- `trading_window = get_a_stock_trading_window(actual_start_date, end_date)`
- 如果为 `None`：记录 `No A-share trading days in range...`，返回 `True`
- 如果有窗口：用 `(window_start, window_end)` 替代原来的 `actual_start_date/end_date` 调用 provider fallback

这样周末、节假日、长假期间不会触发任何 provider。

### 批量分片路径

`download/mp_utils.py::_history_batch_worker()` 当前也会为每只股票计算 `actual_start_date`。对于 `SecurityType.STOCK`，在调用 `_download_stock_history_with_fallback()` 前复用同一个交易日窗口 helper：

- 无交易日：该股票计为成功并跳过 provider。
- 有交易日：用规整后的窗口调用 fallback。
- ETF、港股通继续走现有路径，不使用该 helper。

### 错误处理与日志

- 无交易日不是错误，日志级别使用 `info`。
- 日历 helper 抛出的异常是环境/配置/日期输入问题，应被现有外层异常处理捕获并让该股票下载失败。
- provider 返回空数据的 fallback 逻辑保持不变；只有在窗口内存在交易日时，空数据才继续被视为当前 provider 失败。

## 测试计划

- `stock/market.py` 单元测试：周末窗口返回 `None`。
- `stock/market.py` 单元测试：跨周末窗口收缩到工作日。
- `DownloadManager` 测试：无交易日窗口不调用任何 provider，不调用 storage save，返回 `True`。
- `DownloadManager` 测试：有交易日窗口时，provider 收到规整后的 `start_date/end_date`。
- `mp_utils` 测试：股票批量 worker 无交易日窗口计成功且不调用 provider。
- `mp_utils` 测试：股票批量 worker 有交易日窗口时使用规整后的窗口调用 fallback。
- 回归测试：ETF 批量路径不调用 A 股交易日窗口 helper。

验证命令使用 `uv run pytest` 和 `uv run ruff check`。

## 验收标准

- A 股历史日线下载在无交易日窗口内直接跳过并返回成功。
- A 股历史日线下载在有交易日窗口内只请求首个到最后一个交易日。
- 无交易日窗口不会触发 baostock/tushare/akshare fallback。
- 单只下载和批量分片下载行为一致。
- ETF、港股通和其它每日任务行为不变。
