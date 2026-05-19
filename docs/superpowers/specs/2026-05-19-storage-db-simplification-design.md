# storage_db 重复保存/查询逻辑简化设计

## 背景

`storage/storage_db.py` 已经承载了大量存取逻辑，当前最明显的问题不是功能缺失，而是**重复实现过多**：

1. 多个 `save_*` 方法重复执行 `rename -> 去后缀 -> 选列 -> 日期转换 -> to_sql`
2. 多个 `load_*` 方法重复拼接“按代码 + 起止日期”的 SQL
3. 多处重复判断数据库方言并构造 insert / upsert 语句
4. 多个历史行情保存方法各自维护表名分支，和已有 `get_table_name()` 能力部分重叠

这些重复让 `storage_db.py` 继续演进时更容易出现：

- 某个表新增字段后，只改了部分保存路径
- 日期格式、证券代码规范化在不同方法中出现细微漂移
- 新增一个同类接口时只能继续复制已有模板

## 目标

本次优化目标是把 `storage_db.py` 中**重复保存/查询逻辑提炼成少量私有 helper**，提升可维护性，同时保持当前业务行为稳定：

1. 不修改 `StorageDb` 的公开方法名
2. 不修改调用方使用方式
3. 不修改现有表结构、字段语义、返回类型约定
4. 优先减少重复分支和样板代码
5. 保持当前“记录日志并返回 `False` / 空结果”的外部行为

## 范围

本次改动包含：

1. 精简 `storage/storage_db.py` 内部重复逻辑
2. 复用已有 `get_table_name()` 或同级 helper 统一表名选择
3. 抽取 DataFrame 预处理、通用写入、通用区间查询、通用方言 insert helper
4. 调整 `storage/` 相关测试，锁定本次纯重构行为

本次改动不包含：

- 把 `storage_db.py` 拆成多个文件
- 修改 `storage/__init__.py` 的公开 API
- 修改 `storage/model/` 结构或表名常量
- 修改监控、SSF、下载等业务语义
- 引入新的 ORM 访问模式替换现有 pandas / SQLAlchemy 混合风格

## 方案对比

### 方案 A：保留公开方法，抽私有 helper 收敛重复逻辑（推荐）

特点：

- 对外接口不变
- 内部新增少量私有 helper
- 让大多数 `save_*` / `load_*` 方法退化成薄封装

优点：

- 风险最低
- 可维护性提升明显
- diff 可控，适合在现有代码基础上渐进整理

缺点：

- `storage_db.py` 文件体积仍然偏大
- 结构改善主要体现在“内部职责收敛”，不是模块级拆分

### 方案 B：按数据域拆分内部 mixin / 子模块

特点：

- 例如把 history / general info / monitor / ssf 各自拆到独立模块
- `StorageDb` 只保留组合入口

优点：

- 模块边界更清晰
- 长期结构更干净

缺点：

- 改动面大
- 导入关系、测试、未来 merge 冲突风险更高
- 超出这次“优先可维护性、保持行为稳定”的确认范围

### 方案 C：只清理少数热点方法

特点：

- 仅处理最显眼的几个重复保存方法
- 其余模式保持原样

优点：

- 改动最小

缺点：

- 改善有限
- 重复模式仍继续存在，后续新增接口时仍容易复制旧写法

## 详细设计

### 1. 表名解析 helper

目标：统一历史行情表名选择逻辑，避免多个方法各写一套 `if/elif`。

做法：

1. 对股票 / ETF 历史数据优先复用已有 `get_table_name()`
2. 对港股历史数据也统一收敛到单独 helper，而不是在 `save_history_data_hk_stock()` 内重复判断
3. `save_history_data_stock()`、`save_history_data_etf()`、`save_history_data_hk_stock()` 统一走“先解析表名，再调用通用写入”

这样可以把“选择表名”和“写入 DataFrame”分离。

### 2. DataFrame 预处理 helper

目标：统一常见的 DataFrame 规范化流水线。

抽取的能力包括：

1. `rename(columns=...)`
2. 提取证券代码 / ETF 代码，去掉 `.SH`、`.SZ` 等后缀
3. 按目标列顺序选列
4. 对一个或多个日期列统一做 `%Y%m%d -> YYYY-MM-DD` 或 `date` 转换
5. 为 `top10_floatholders` 这类场景补齐可选列

该 helper 不追求覆盖全部特殊情况，而是覆盖当前最常见的重复路径。个别特殊逻辑仍保留在具体方法中，例如：

- `top10_floatholders` 的 optional columns
- 需要 `date` 而不是字符串日期的场景
- SSF 信号专用 payload 归一化

### 3. 通用写入 helper

目标：把重复的 `df.to_sql(..., if_exists=..., index=False, method="multi")` 收敛到单点。

设计：

1. 提供统一私有 helper，接收 `table_name`、`df`、`if_exists`
2. 默认沿用当前 `index=False`
3. 在 append 场景继续默认 `method="multi"`
4. replace 场景保留与现有实现一致的写法，不额外改变参数语义

公开 `save_*` 方法只负责：

1. 调用预处理 helper
2. 选择表名
3. 调用通用写入 helper
4. 保留各自现有的日志语义与返回值

### 4. 通用区间查询 helper

目标：统一“按代码 + 可选起止日期”的 `load_*` 查询构造。

适用场景包括：

- `load_history_data_fund()`
- `load_etf_daily()`
- 其他同类需要按证券代码过滤并按日期排序的读取接口

设计约束：

1. helper 负责拼接 where 子句、参数列表和排序
2. 仍返回 `pd.read_sql(...)` 结果
3. 不强制把所有查询都变成同一个抽象；仅收敛重复的区间查询模式

这样既减少样板 SQL，又保留现有按业务语义命名的公开方法。

### 5. 通用方言 insert / upsert helper

目标：把多处 `postgresql/sqlite` 分支判断集中，避免方言差异散落。

设计：

1. 提供 helper 返回当前方言对应的 insert 构造函数
2. 需要 `on_conflict_do_nothing()` 的场景统一复用
3. 保留 `top10_floatholders` 和 `ssf_change_signal` 的业务差异：
   - 前者是 DataFrame -> records -> 按主键忽略冲突
   - 后者是 payload 归一化 -> insert returning id

也就是说，**统一的是方言分发**，不是强行把两类业务写成一套模板。

### 6. 行为保持原则

本次是纯重构，明确保持以下行为不变：

1. `StorageDb` 公开方法名、参数和返回类型不变
2. 原有成功 / 失败布尔返回约定不变
3. 原有日志级别与错误兜底策略尽量不变
4. 表名、列名、日期语义不变
5. SSF 与 monitor 相关业务行为不借机重构

## 错误处理

本次改动不引入宽泛吞错新策略，也不把现有错误传播语义改成另一套风格。

原则如下：

1. 已经是“捕获异常 -> 记录日志 -> 返回 `False` / 空结果”的方法，继续保持
2. 已经是显式抛错的路径（如不支持字段、方言不支持），继续显式抛错
3. `engine is None`、方言选择、参数拼接这些基础检查收敛到 helper 内，减少分散判断
4. 不新增静默 fallback

## 测试策略

至少覆盖以下几类验证：

1. 代表性的 `save_*` 方法在重构后仍按原列映射、代码规范化和日期格式写入
2. 代表性的区间查询方法在有 / 无 `start_date`、`end_date` 时仍生成等价行为
3. `top10_floatholders` 冲突忽略逻辑不变
4. `ssf_change_signal` 的 returning / conflict 语义不变
5. 仓库现有 `storage/` 相关测试继续通过

## 验收标准

满足以下条件即可认为完成：

1. `storage_db.py` 中重复的 DataFrame 保存逻辑明显收敛
2. 至少一类区间查询逻辑被抽成通用 helper
3. 历史行情表名选择不再由多个方法重复维护
4. SSF / top10 的方言 insert 分支减少重复但行为不变
5. 相关测试和仓库已有检查通过
