---
name: tushare
description: Use when the user asks for Tushare-backed stock, index, fund, sector, finance, money-flow, news, macro, or CSV export analysis in this repository.
triggers:
  - tushare
  - 行情分析
  - 财报分析
  - 资金流
  - 板块分析
  - 导出 csv
  - 导出 parquet
  - 宏观数据
---

# Tushare Skill

把自然语言金融数据请求，转成当前仓库里可执行的 Tushare 数据工作流。

## 何时使用

当用户想做以下事情时，优先使用本 skill：

- 看某只股票、指数、ETF、基金最近走势
- 查看最近几个季度财报、估值、盈利质量、现金流
- 对比多个标的的涨跌幅、估值或财务趋势
- 查看北向资金、主力资金、龙虎榜、板块强弱
- 梳理公告、新闻、研报、政策线索
- 查询 CPI / PPI / PMI / GDP / 利率等宏观数据
- 导出 CSV / parquet / 研究数据表

不适用于：

- 直接给交易建议或自动下单
- 在没有权限时伪造数据
- 把实时交易系统或回测引擎本身作为本 skill 的输出

## 仓库内执行约束

- 必须在仓库根目录执行命令。
- Python 命令必须使用 `poetry run`。
- 优先使用环境变量 `TUSHARE_TOKEN`；缺失时先提示用户设置：

```bash
export TUSHARE_TOKEN="your_token_here"
```

- 需要快速脚本时，优先使用：

```bash
poetry run python - <<'PY'
import os
import tushare as ts

token = os.getenv("TUSHARE_TOKEN") or ts.get_token()
assert token, "missing TUSHARE_TOKEN"
pro = ts.pro_api(token)
print(pro.trade_cal(exchange="", start_date="20260101", end_date="20260110").head())
PY
```

- 需要参考现有实现时，优先查看：
  - `download/dl/downloader_tushare.py`
  - `download/dl/downloader.py`
  - `.claude/skills/stock/scripts/shareholder_number.py`

## 开始前检查

在真正取数前，先完成这 4 步：

1. `poetry run python -c "import tushare"` 确认包可用
2. 检查 `TUSHARE_TOKEN`
3. 必要时用轻量接口做冒烟测试，如 `trade_cal`
4. 若用户请求高积分接口，提前说明可能存在积分/权限限制

不要等主查询失败后才暴露环境问题。

## 默认理解规则

### 标的解析

- 优先把中文简称解析为标准 `ts_code`
- 内部统一使用类似 `600519.SH`、`000001.SZ`
- 裸代码如 `000001`，只有在补全规则明确时才自动补全
- 有歧义时，做最小澄清

### 市场默认值

- 用户未特别说明时，默认先按 A 股理解
- 指数、基金、ETF、个股不要混用接口

### 时间默认值

- “最近走势” → 近 20 个交易日
- “最近一段时间” → 近 3 个月
- “财报 / 业绩” → 最近 8 个季度 + 最近年度
- “资金流最近如何” → 近 5 到 20 个交易日
- “宏观最近如何” → 最近 6 到 12 期

### 输入规范化

- 日期统一为 `YYYYMMDD`
- 保证 `start_date <= end_date`
- 未来日期裁剪到最近可用日期并明确说明
- 冲突参数先裁决，再发请求

## 常见任务 → 接口建议

| 任务 | 常用接口 |
| --- | --- |
| 单票走势 / K 线 / 区间涨跌 | `daily`, `pro_bar`, `weekly`, `monthly`, `daily_basic` |
| 基本资料 / 代码解析 | `stock_basic`, `fund_basic`, `index_basic`, `stock_company` |
| 财报 / 盈利质量 | `income`, `fina_indicator`, `balancesheet`, `cashflow`, `forecast`, `express` |
| 估值 / 股息 / PB / PE | `daily_basic`, `fina_indicator` |
| 北向 / 主力 / 龙虎榜 | `moneyflow`, `moneyflow_hsgt`, `hsgt_top10`, `top_list`, `top_inst` |
| 板块 / 指数 / 成分股 | `index_basic`, `index_daily`, `index_classify`, `index_member_all`, `sw_daily`, `ths_index`, `ths_member` |
| 公告 / 新闻 / 研报 | `anns_d`, `news`, `major_news`, `research_report` |
| 宏观数据 | `cn_cpi`, `cn_ppi`, `cn_pmi`, `cn_gdp`, `sf_month`, `shibor`, `shibor_lpr`, `us_tycr`, `hk_daily` |

写代码前先确认接口名、必填参数、字段和积分限制，不要凭记忆硬写字段。

## 工作流模板

### 1. 单标的走势分析

适用：看看 XX 最近怎么样、今年以来涨了多少、最近强不强

默认流程：

1. 解析标的为 `ts_code`
2. 确定时间范围
3. 拉行情和必要指标
4. 总结区间涨跌、成交活跃度、高低点、波动
5. 如用户要求，导出 CSV / parquet

### 2. 财务趋势分析

适用：看下 XX 财报、最近 8 个季度利润趋势、财务质量怎么样

默认流程：

1. 拉最近 8 个季度和最近年度数据
2. 区分营收、净利润、毛利率、ROE、现金流
3. 标记改善 / 恶化 / 波动点
4. 明确同比、环比、累计口径

### 3. 多标的横向对比

适用：XX 和 YY 谁更强、对比几家公司估值和涨幅

默认流程：

1. 锁定对象和统一时间口径
2. 选择 3 到 5 个关键指标
3. 输出对比表
4. 给出简洁结论

### 4. 资金流 / 板块 / 题材

适用：最近哪个板块最强、北向资金最近买什么

默认流程：

1. 明确口径（北向 / 主力 / 龙虎榜 / 板块资金）
2. 确定时间窗
3. 拉净流入、活跃成交、持续性
4. 必要时与价格表现联动解释

### 5. 导出研究数据

适用：导出 CSV、做研究表、准备回测数据

默认流程：

1. 明确数据范围、频率、字段
2. 长区间分段拉取
3. 合并、去重、排序、标准化类型
4. 输出文件并给出路径、行数、字段列表

## 输出格式

除非用户明确只要原始表，否则优先按这个顺序交付：

1. 一句话结论
2. 数据范围与口径
3. 关键指标 / 简表
4. 风险点 / 限制 / 权限说明
5. 如有本地文件，给出文件路径

## 错误处理

先说人话，再补调试细节：

- token 未配置
- 接口需要更高积分 / 权限
- 日期范围过大，已改为分段拉取
- 标的名称不唯一
- 当前区间为空，可能是非交易日 / 未上市 / 无权限

如果部分分段失败，不要伪装为全量成功；要明确说明哪些成功、哪些失败。

## 典型命令片段

### 获取近三个月日线并导出 CSV

```bash
poetry run python - <<'PY'
import os
from datetime import datetime, timedelta

import tushare as ts

token = os.getenv("TUSHARE_TOKEN") or ts.get_token()
assert token, "missing TUSHARE_TOKEN"
pro = ts.pro_api(token)

end_date = datetime.now().strftime("%Y%m%d")
start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
df = pro.daily(ts_code="300750.SZ", start_date=start_date, end_date=end_date)
df = df.sort_values("trade_date").reset_index(drop=True)
path = f"daily_300750.SZ_{start_date}_{end_date}.csv"
df.to_csv(path, index=False, encoding="utf-8-sig")
print(path)
print(df.tail())
PY
```

### 获取最近 8 个季度财务指标

```bash
poetry run python - <<'PY'
import os

import tushare as ts

token = os.getenv("TUSHARE_TOKEN") or ts.get_token()
assert token, "missing TUSHARE_TOKEN"
pro = ts.pro_api(token)

df = pro.fina_indicator(ts_code="600036.SH")
df = df.sort_values("end_date").tail(8)
print(df[["end_date", "roe", "grossprofit_margin", "netprofit_margin"]])
PY
```

## 快速判断

当用户在说：

- 看走势
- 查财报
- 比较公司
- 看板块
- 看资金流
- 梳理公告新闻
- 看宏观
- 拉数据导出

就优先使用本 skill，把需求翻译成 Tushare 数据工作流，而不是先回到接口名列表。
