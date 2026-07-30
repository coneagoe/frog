# small_market_capital_3 迁移设计

## 1. 目标

在不改动原策略文件职责的前提下，将双因子（小市值 + 波动率）实现落到新文件：

- 恢复 `backtest/small_market_capital_2.py` 为原始小市值策略；
- 新建 `backtest/small_market_capital_3.py` 承载双因子版本；
- 新增并对齐测试到 `test/backtest/test_small_market_capital_3.py`。

## 2. 方案

采用“复制 + 回退”方案：

1. 复制当前 `small_market_capital_2.py` 的双因子逻辑为 `small_market_capital_3.py`；
2. 将 `small_market_capital_2.py` 回退到分支基线版本（无双因子新增函数与参数）；
3. 测试文件改为 `test/backtest/test_small_market_capital_3.py`，导入与断言保持双因子逻辑。

## 3. 迁移边界

- 不改动其他 backtest 策略；
- 不引入额外通用抽象；
- 不调整调仓频率、空仓月份与基础过滤逻辑。

## 4. 验收标准

1. `small_market_capital_2.py` 仅保留原版小市值逻辑；
2. `small_market_capital_3.py` 包含双因子参数与评分实现并可运行；
3. `test/backtest/test_small_market_capital_3.py` 通过；
4. 相关 pre-commit 检查通过。
