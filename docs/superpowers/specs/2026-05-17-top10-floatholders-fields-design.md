# top10_floatholders 缺失字段补齐设计

## 背景

当前仓库已接入 `top10_floatholders` 下载、存储和周度 DAG，但实现只覆盖了以下字段：

- `ts_code`
- `ann_date`
- `end_date`
- `holder_name`
- `hold_amount`
- `hold_ratio`

根据 TuShare 文档 `top10_floatholders` 接口当前输出定义，现有实现还缺少：

- `hold_float_ratio`
- `hold_change`
- `holder_type`

这会导致下载请求字段不完整，存储表结构与列映射也无法承接这些返回值。

## 目标

在不改变现有下载入口、DAG 编排、主键策略和数据库迁移策略的前提下，把 `top10_floatholders` 按当前 TuShare 文档一次性补齐到完整的显式字段链路中。

## 范围

本次改动包含：

1. 下载字段清单补齐 3 个缺失字段。
2. 常量与列映射补齐 3 个缺失字段。
3. `top10_floatholders` ORM 模型补齐 3 个缺失列。
4. `save_top10_floatholders()` 保存白名单随映射一起扩展。
5. 下载层、模型层、存储层相关测试同步更新。

本次改动不包含：

- 已存在数据库表的补列或迁移逻辑。
- DAG 调度、任务边界、重试或依赖调整。
- `top10_floatholders` 之外的数据接口改造。
- 动态 schema 或通用透传式存储方案。

## 设计原则

### 延续现有模式

继续使用仓库现有的三段式模式：

1. `downloader_tushare.py` 维护显式 `fields` 清单。
2. `storage/storage_db.py` 维护显式英文字段到中文列名映射。
3. `storage/model/top10_floatholders.py` 维护显式表结构。

本次只补齐遗漏字段，不改变模式。

### 行为兼容

- `ts_code` 仍在保存前裁剪为 6 位股票代码。
- 主键仍为 `股票代码 + 公告日期 + 股东名称`。
- 插入冲突时仍沿用当前 `on_conflict_do_nothing` 逻辑。
- 新增字段不参与主键判定。

### 显式失败优于静默兜底

不为缺失字段增加默认值或静默回填。如果下载返回、映射白名单或测试数据与设计不一致，应显式暴露问题，便于及时修复。

## 详细设计

### 1. 下载层

文件：`download/dl/downloader_tushare.py`

将 `top10_floatholders_fields` 从当前 6 个字段扩展为 9 个字段：

- `ts_code`
- `ann_date`
- `end_date`
- `holder_name`
- `hold_amount`
- `hold_ratio`
- `hold_float_ratio`
- `hold_change`
- `holder_type`

`download_top10_floatholders()` 的调用方式保持不变，继续通过：

```python
client.top10_floatholders(..., fields=top10_floatholders_fields)
```

显式向 TuShare 请求所需字段。

### 2. 常量与映射层

文件：

- `common/const.py`
- `storage/storage_db.py`

新增 3 个中文列常量，并将其加入 `COL_MAP_TOP10_FLOATHOLDERS`。

建议语义如下：

- `hold_float_ratio` → 占流通股本比例(%)
- `hold_change` → 持股变动
- `holder_type` → 股东类型

命名需要遵循仓库当前中文列名风格，与既有 `持有数量（万股）`、`占总流通股本持股比例` 保持一致。

### 3. 存储模型层

文件：`storage/model/top10_floatholders.py`

为 `Top10Floatholders` 新增 3 个非主键列：

- 浮点列：`hold_float_ratio`
- 浮点列：`hold_change`
- 字符串列：`holder_type`

字段约束：

- 全部 `nullable=True`
- 不调整既有主键
- 不改变现有日期列和已存在字段的类型

### 4. 保存逻辑层

文件：`storage/storage_db.py`

`save_top10_floatholders()` 保持当前流程：

1. 用 `COL_MAP_TOP10_FLOATHOLDERS` 重命名列。
2. 用 `list(COL_MAP_TOP10_FLOATHOLDERS.values())` 作为入库白名单。
3. 转换日期列。
4. 批量插入并按主键冲突忽略。

由于保存逻辑本身已经依赖映射表驱动，本次不需要新增分支逻辑，只需要让映射与表结构同步扩展。

### 5. 测试策略

#### 下载层测试

文件：`test/download/dl/test_downloader_tushare.py`

- 更新成功用例的 mock DataFrame，补齐 3 个新字段。
- 断言 `pro.top10_floatholders()` 调用时使用的 `fields` 已包含完整字段清单。

#### 模型层测试

文件：`test/storage/model/test_top10_floatholders.py`

- 更新列存在性断言，确保新中文列出现在表结构中。

#### 存储层测试

文件：`test/storage/test_storage_db.py`

- 更新原始 DataFrame 工具数据，补齐 3 个新字段。
- 扩展“保留字段”断言，确认新增列被写入数据库。
- 保持现有日期转换、股票代码去后缀、幂等性和异常处理测试不变，仅在必要时补充字段。

## 错误处理

沿用当前仓库模式：

- 下载层缺 token 时继续抛 `ConnectionError`。
- 保存层继续在异常时记录日志并返回 `False`。

本次不新增额外兜底逻辑，也不吞掉字段缺失问题。

## 验收标准

满足以下条件即视为完成：

1. `top10_floatholders_fields` 与当前 TuShare 文档输出字段对齐。
2. `COL_MAP_TOP10_FLOATHOLDERS` 能覆盖 9 个显式字段。
3. `Top10Floatholders` 表结构包含 3 个新增列。
4. `save_top10_floatholders()` 能保留并写入新增字段。
5. 相关单元测试同步反映新字段，避免以后再次漏接。

## 备选方案评估

### 方案一：只补 `hold_change`

优点：改动最小。  
缺点：仍然与当前 TuShare 文档不一致，很快还要再次修改。  
结论：不采用。

### 方案二：一次性补齐当前文档缺失字段

优点：范围聚焦，和现有模式一致，后续维护成本最低。  
缺点：涉及下载、常量、模型、保存、测试多个点位，但都在同一条链路内。  
结论：采用。

### 方案三：改为动态透传字段

优点：以后新增字段时维护量更低。  
缺点：偏离当前仓库的显式列映射和 ORM 约束，风险与改动面都偏大。  
结论：不采用。
