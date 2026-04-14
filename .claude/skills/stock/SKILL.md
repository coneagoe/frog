---
name: stock
description: A股/港股股东人数、股本结构查询工具，基于 Tushare API
triggers:
  - 股东人数
  - 股东户数
  - 股东结构
  - 筹码分布
---

# Stock 技能

查询上市公司股东人数及趋势分析，基于 Tushare `stk_holdernumber` 接口（需 600 积分）。

## 使用方式

```bash
# 查询股东人数（默认近3年）
poetry run python .claude/skills/stock/scripts/shareholder_number.py -c 600600.SH

# 显示趋势分析
poetry run python .claude/skills/stock/scripts/shareholder_number.py -c 600600.SH -a

# 导出 CSV
poetry run python .claude/skills/stock/scripts/shareholder_number.py -c 600600.SH -x

# 指定日期范围
poetry run python .claude/skills/stock/scripts/shareholder_number.py -c 600600.SH -s 20230101 -e 20260331
```

## 参数说明

| 参数 | 说明 |
|------|------|
| `-c` | 股票代码，如 `600600.SH`、`000001.SZ` |
| `-s` | 开始日期 YYYYMMDD |
| `-e` | 结束日期 YYYYMMDD |
| `-a` | 显示趋势分析 |
| `-x` | 导出为 CSV 文件 |

## 输出字段

- `ts_code`: 股票代码
- `ann_date`: 公告日期
- `end_date`: 报告期
- `holder_num`: 股东人数

## 趋势分析解读

- **股东数增加** → 筹码分散，散户入场、机构派发
- **股东数减少** → 筹码集中，机构吸筹

## 依赖

- Tushare token（环境变量 `TUSHARE_TOKEN`）
- 需 600 积分权限
