---
name: shareholder-number
description: Use when querying A-share or Hong Kong-listed company shareholder counts, ownership concentration, shareholder-number trends, or Tushare stk_holdernumber data.
---

# 股东人数查询

使用 Tushare `stk_holdernumber` 查询上市公司股东人数和趋势；接口需要 Tushare 600 积分权限。

## 使用方式

```bash
# 查询近 3 年数据
uv run .agents/skills/shareholder-number/scripts/shareholder_number.py -c 600600.SH

# 显示趋势分析
uv run .agents/skills/shareholder-number/scripts/shareholder_number.py -c 600600.SH -a

# 导出 CSV
uv run .agents/skills/shareholder-number/scripts/shareholder_number.py -c 600600.SH -x

# 指定日期范围
uv run .agents/skills/shareholder-number/scripts/shareholder_number.py -c 600600.SH -s 20230101 -e 20260331
```

## 参数

| 参数 | 说明 |
| --- | --- |
| `-c` | 股票代码，例如 `600600.SH`、`000001.SZ` |
| `-s` | 开始日期，格式 `YYYYMMDD` |
| `-e` | 结束日期，格式 `YYYYMMDD` |
| `-a` | 显示趋势分析 |
| `-x` | 导出 CSV 文件 |

## 输出字段

| 字段 | 含义 |
| --- | --- |
| `ts_code` | 股票代码 |
| `ann_date` | 公告日期 |
| `end_date` | 报告期 |
| `holder_num` | 股东人数 |

## 解读

- 股东数增加：筹码趋于分散，可能反映散户入场或机构派发。
- 股东数减少：筹码趋于集中，可能反映机构吸筹。

上述解读仅为辅助信号，应结合价格、成交量、股东持仓和基本面判断。

## 依赖

- 环境变量 `TUSHARE_TOKEN`
- Tushare `stk_holdernumber` 接口的 600 积分权限
