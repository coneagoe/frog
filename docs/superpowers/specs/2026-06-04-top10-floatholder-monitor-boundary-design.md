# 前十大流通股东监控包边界重构设计

## 背景

当前 `shareholder_monitor/` 同时包含两类职责：

- 前十大流通股东领域逻辑：社保基金持有人识别、社保持仓变化分析。
- 监控应用层逻辑：读取候选、保存信号、生成邮件、发送告警、标记处理状态。

同时，`factor/alphapurify_ssf_common.py` 已经复用 `shareholder_monitor.ssf_detector`。如果把全部代码移动到 `monitor/shareholder/` 或 `monitor/top10_floatholder/`，因子模块会依赖监控模块，长期边界不清晰。

## 目标

将领域逻辑和监控编排分开：

- 领域包描述“这是什么数据域”：前十大流通股东。
- 监控包描述“怎么运行监控”：扫描候选、生成告警、发送邮件。
- 避免 `factor/`、研究脚本、回测逻辑依赖 `monitor/`。
- 使用比 `shareholder` 更精确的命名，避免和股东减持、十大股东、控股股东等概念混淆。

## 推荐结构

采用分层方案：

```text
top10_floatholder/
  __init__.py
  ssf_detector.py
  ssf_change_analyzer.py

monitor/
  top10_floatholder/
    __init__.py
    runner.py
    ssf_alert.py
```

原 `shareholder_monitor/` 不再作为长期入口保留。

## 模块职责

### `top10_floatholder/`

领域逻辑包，不能依赖 `monitor/`。

- `ssf_detector.py`
  - 提供 `is_social_security_holder()`。
  - 判断前十大流通股东持有人名称是否为社保基金。
- `ssf_change_analyzer.py`
  - 提供 `analyze_ssf_change()` 和相关结果类型。
  - 基于单只股票的前十大流通股东历史数据判断社保持仓变化信号。
- `__init__.py`
  - 可导出领域层常用 API，例如 `analyze_ssf_change` 和 `is_social_security_holder`。

### `monitor/top10_floatholder/`

监控应用层包，可以依赖 `top10_floatholder/`、`storage/`、`utility/`。

- `runner.py`
  - 提供 `run_ssf_change_alert()` 和 `SSFAlertSummary`。
  - 负责读取候选、调用领域分析、保存信号、发送邮件、标记状态。
- `ssf_alert.py`
  - 提供 `build_ssf_change_alert_email()`。
  - 只负责告警邮件内容构造。
- `__init__.py`
  - 导出 Airflow DAG 使用的入口：`run_ssf_change_alert`、`SSFAlertSummary`。

## 依赖方向

期望依赖关系：

```text
dags/
  -> monitor.top10_floatholder
       -> top10_floatholder
       -> storage
       -> utility

factor/
  -> top10_floatholder
```

禁止方向：

```text
top10_floatholder -> monitor
factor -> monitor.top10_floatholder
```

## 引用变更

Airflow DAG：

```python
from monitor.top10_floatholder import run_ssf_change_alert
```

因子模块：

```python
from top10_floatholder.ssf_detector import is_social_security_holder
```

监控 runner：

```python
from top10_floatholder.ssf_change_analyzer import SSFChangeAnalysisOutcome, analyze_ssf_change
```

## 测试结构

测试也按职责分层：

```text
test/top10_floatholder/
  test_ssf_detector.py
  test_ssf_change_analyzer.py

test/monitor/top10_floatholder/
  test_runner.py
  test_ssf_alert.py
```

测试内容不改变业务行为，只更新 import 路径和 patch 路径。

## 行为保持

本次重构只改变包边界和 import 路径，不改变：

- DAG schedule、依赖、重试、task 边界或 SLA。
- 社保基金识别规则。
- 社保持仓变化分析规则。
- 邮件格式。
- storage 表结构和字段。
- 信号保存、去重、已处理、已发送语义。

## 迁移范围

需要更新的主要位置：

- `shareholder_monitor/ssf_detector.py` -> `top10_floatholder/ssf_detector.py`
- `shareholder_monitor/ssf_change_analyzer.py` -> `top10_floatholder/ssf_change_analyzer.py`
- `shareholder_monitor/runner.py` -> `monitor/top10_floatholder/runner.py`
- `shareholder_monitor/ssf_alert.py` -> `monitor/top10_floatholder/ssf_alert.py`
- `dags/scan_top10_floatholder_weekly.py`
- `factor/alphapurify_ssf_common.py`
- `test/shareholder_monitor/*`
- `docs/ssf_*_factor_evaluation.md`

## 验证

迁移后至少运行：

```bash
poetry run pytest test/top10_floatholder test/monitor/top10_floatholder test/dags/test_scan_top10_floatholder_weekly.py
```

如果 DAG 测试文件名不同，以实际文件名为准搜索并运行相关测试。

最终 CI 门禁仍以仓库约定为准：

```bash
poetry run pre-commit run --all-files
poetry run pytest test
```
