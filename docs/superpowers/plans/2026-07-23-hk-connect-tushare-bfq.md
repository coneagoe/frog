# 港股通 TuShare BFQ 下载 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让港股通日线 BFQ 使用 TuShare `hk_daily`，同时让 HFQ 继续通过现有 fallback chain 交由 AkShare 下载。

**Architecture:** 仅改 TuShare 港股下载适配器。BFQ 调 `hk_daily` 并统一标准化 `pct_chg`；HFQ/QFQ 在创建 TuShare client 前明确拒绝，供 `DownloadManager` 回退。Provider 顺序、DAG 与存储不变。

**Tech Stack:** Python 3.11+, pandas, TuShare Pro API, pytest, uv.

## Global Constraints

- Python 命令使用 `uv run`。
- 不改 DAG 调度、任务边界、BFQ 业务语义、存储表路由或 fallback 控制流。
- `hk_daily_adj` 不作为 HFQ 数据源；不新增 QFQ 存储或因子换算。

---

### Task 1: 编写 TuShare BFQ 路由的失败测试

**Files:**
- Modify: `test/download/dl/test_downloader_tushare.py:412-509`

**Interfaces:**
- Consumes: `download_history_data_stock_hk_ts(..., adjust=AdjustType.BFQ)`。
- Produces: `client.hk_daily(...)` 被调用，返回 `hk_history_columns`。

- [ ] **Step 1: 将现有港股成功测试改为 BFQ 的期望行为**

```python
pro_stub.hk_daily.return_value = pd.DataFrame({
    "ts_code": ["00700.HK"], "trade_date": ["20240105"],
    "open": [391], "high": [395], "low": [389], "close": [394],
    "change": [5], "pct_chg": [1], "vol": [1020300], "amount": [401020300],
})
result = module.download_history_data_stock_hk_ts(
    "00700", "2024-01-01", "2024/01/05", adjust=module.AdjustType.BFQ
)
pro_stub.hk_daily.assert_called_once_with(
    ts_code="00700.HK", trade_date="", start_date="20240101", end_date="20240105",
    fields=module.hk_daily_fields,
)
pro_stub.hk_daily_adj.assert_not_called()
assert list(result.columns) == module.hk_history_columns
assert result[module.COL_CHANGE_RATE].tolist() == [1.0]
```

- [ ] **Step 2: 验证测试为红**

Run: `uv run pytest test/download/dl/test_downloader_tushare.py::test_download_history_data_stock_hk_ts_bfq_uses_hk_daily -q`

Expected: FAIL，当前实现会抛出 `Only HFQ adjust is supported`。

- [ ] **Step 3: 写入非 BFQ 组合的失败测试**

```python
@pytest.mark.parametrize("adjust", ["hfq", "qfq"])
def test_download_history_data_stock_hk_ts_rejects_non_bfq_adjust(
    downloader_ts_module, monkeypatch, adjust
):
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")
    with pytest.raises(ValueError, match="Only BFQ adjust is supported"):
        module.download_history_data_stock_hk_ts(
            "00700", "20240101", "20240105", adjust=module.AdjustType(adjust)
        )
    ts_stub.pro_api.assert_not_called()
    pro_stub.hk_daily.assert_not_called()
    pro_stub.hk_daily_adj.assert_not_called()
```

- [ ] **Step 4: 验证 HFQ 测试为红**

Run: `uv run pytest test/download/dl/test_downloader_tushare.py::test_download_history_data_stock_hk_ts_rejects_non_bfq_adjust -q`

Expected: FAIL，当前 HFQ 路径调用 `hk_daily_adj`。

### Task 2: 最小实现 BFQ API 路由

**Files:**
- Modify: `download/dl/downloader_tushare.py:165-281,749-784`
- Test: `test/download/dl/test_downloader_tushare.py:412-509`

**Interfaces:**
- Consumes: `hk_daily` 的 `pct_chg`。
- Produces: BFQ 返回规范 DataFrame；HFQ/QFQ 抛 `ValueError`。

- [ ] **Step 1: 声明 BFQ API 的字段与归一化映射**

```python
hk_daily_fields = [
    "ts_code", "trade_date", "open", "high", "low", "close",
    "change", "pct_chg", "vol", "amount",
]

# _normalize_hk_history_dataframe 的 columns 映射内加入：
"pct_chg": COL_CHANGE_RATE,
```

- [ ] **Step 2: 用 BFQ 分支替换现有 HFQ-only 分支**

```python
if period != PeriodType.DAILY:
    raise ValueError("Only daily period is supported for HK Tushare history downloads.")
if adjust != AdjustType.BFQ:
    raise ValueError("Only BFQ adjust is supported for HK Tushare history downloads.")

client = require_pro_client(pro) if pro is not None else _create_pro_client()
df = client.hk_daily(
    ts_code=ts_code, trade_date="", start_date=normalized_start_date,
    end_date=normalized_end_date, fields=hk_daily_fields,
)
```

删除该函数内的单日 `hk_daily_adj` 缓存分支；保留空结果和最终 stock ID 归一化。将函数默认 `adjust` 改为 `AdjustType.BFQ`。

- [ ] **Step 3: 验证两项测试转绿**

Run: `uv run pytest test/download/dl/test_downloader_tushare.py::test_download_history_data_stock_hk_ts_bfq_uses_hk_daily test/download/dl/test_downloader_tushare.py::test_download_history_data_stock_hk_ts_rejects_non_bfq_adjust -q`

Expected: PASS。

- [ ] **Step 4: 更新关联 TuShare downloader 测试并运行文件**

把该下载函数相关的空结果与 `assert_not_called` 断言改为 `hk_daily`；不删除其他功能仍使用的 `hk_daily_adj` 节流/cache helper 测试。

Run: `uv run pytest test/download/dl/test_downloader_tushare.py -q`

Expected: PASS。

### Task 3: 移除已失效的 BFQ 拒绝测试

**Files:**
- Modify: `test/download/test_download_manager.py:666-691`

**Interfaces:**
- Consumes: 已有的 `test_download_hk_ggt_history_falls_back_to_akshare_on_tushare_exception`。
- Produces: fallback 测试只描述仍然成立的通用 provider 异常行为，不再声称 BFQ 会被 TuShare 本地校验拒绝。

- [ ] **Step 1: 删除已失效的测试**

删除 `test_download_hk_ggt_history_bfq_falls_back_on_tushare_adjust_rejection` 整个方法。它的 `ValueError("Only HFQ adjust is supported")` 描述的是已修复的缺陷；相邻的 `test_download_hk_ggt_history_falls_back_to_akshare_on_tushare_exception` 已覆盖 provider 异常的回退契约。

- [ ] **Step 2: 运行 fallback 测试类**

Run: `uv run pytest test/download/test_download_manager.py::TestDownloadHkGgtHistoryFallback -q`

Expected: PASS；空数据、无效数据和任意 provider 异常仍会回退，首个有效结果仍会短路。

### Task 4: 范围验证

**Files:**
- Verify: `download/dl/downloader_tushare.py`
- Verify: `test/download/dl/test_downloader_tushare.py`
- Verify: `test/download/test_download_manager.py`

- [ ] **Step 1: 执行相关测试**

Run: `uv run pytest test/download/dl/test_downloader_tushare.py test/download/test_download_manager.py test/download/test_provider_order.py -q`

Expected: PASS。

- [ ] **Step 2: 执行目标 Ruff 检查**

Run: `uv run ruff check download/dl/downloader_tushare.py test/download/dl/test_downloader_tushare.py test/download/test_download_manager.py`

Expected: `All checks passed!`

- [ ] **Step 3: 检查差异边界**

Run: `git diff --check && git diff -- download/dl/downloader_tushare.py test/download/dl/test_downloader_tushare.py test/download/test_download_manager.py`

Expected: 无空白错误；不纳入已有未提交的 `dags/download_hk_ggt_history_daily.py` 或其他无关文件。
