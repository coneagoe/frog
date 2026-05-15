# 波动率因子设计说明

## 1. 目标与范围

本次实现新增“波动率因子”完整链路，范围包括：

1. `factor/volatility.py`：提供波动率因子计算函数。
2. `factor/alphapurify_volatility.py`：从 DB 读取数据、构造因子面板并调用 Alphapurify 分析。
3. `test/factor/` 下新增对应测试：覆盖因子计算与脚本主流程。

不包含策略组合权重、线上交易参数调优与新 DAG 编排。

## 2. 因子定义

- 因子名称：`volatility`
- 默认窗口：20 个交易日
- 定义口径：日收益率滚动标准差
- 公式：
  - `ret_t = close_t / close_(t-1) - 1`
  - `volatility_t = std(ret_(t-n+1)...ret_t)`

## 3. 方案选择与取舍

### 方案A（采用）

新增独立因子模块 + 独立 alphapurify 脚本，结构对齐 `momentum/obos`。

优点：

- 与现有代码风格一致，可维护性高
- 因子计算可复用、可单测
- 一次交付完整分析链路

### 方案B（未采用）

直接把计算逻辑写进脚本，不建独立模块。  
缺点：复用性差，测试边界不清晰。

### 方案C（未采用）

仅新增因子函数，不做 alphapurify 接入。  
缺点：无法满足本次“完整接入”目标。

## 4. 架构与组件

### 4.1 计算层

`factor/volatility.py` 暴露：

- `COL_VOLATILITY = "volatility"`
- `compute_volatility(df: pd.DataFrame, n: int = 20) -> pd.DataFrame`

输入至少包含 `date/close`，输出在副本上新增 `volatility` 列，保持原有列。

### 4.2 分析层

`factor/alphapurify_volatility.py` 复用既有脚本模式：

- 参数：`--start-date`、`--end-date`、`--max-stocks`、`--adjust`、`--volatility-n`、`--report-html`
- 从 `storage` 拉取股票列表与历史日线
- 统一标准化成 `datetime/symbol/close/volatility`
- 调用 `FactorAnalyzer(..., factor_name="volatility")`

### 4.3 测试层

- `test/factor/test_volatility.py`：验证因子计算行为
- `test/factor/test_alphapurify_volatility.py`：仿照现有脚本测试模式，mock storage 与 analyzer

## 5. 数据流

1. 读取股票列表（`load_general_info_stock`）
2. 逐标的读取历史日线（`load_history_data_stock`）
3. 过滤并标准化 `date/close`
4. 计算 20 日滚动波动率
5. 拼接全部标的面板并排序
6. 交给 Alphapurify 运行与可选 HTML 报告输出

## 6. 异常与边界处理

- 缺少关键列（`date/close`）或数据为空：返回空 DataFrame
- 价格列非数值：转为 NaN 并剔除
- 滚动窗口不足：`volatility` 为 NaN，后续在面板中剔除
- 主流程异常：统一捕获并输出 `[错误]`，返回非 0 退出码

## 7. 验收标准

1. `volatility` 因子可由独立函数计算，默认窗口 20。
2. 脚本可构造非空面板并以 `volatility` 作为因子名运行分析。
3. 因子单测与脚本测试通过。
4. 保持现有脚本风格与接口一致，不影响已有因子功能。
