# 小黑屋倒计时与服务边界重构设计

## 背景

当前小黑屋能力已经包含持久化记录、CLI 管理入口、买入过滤，以及股东减持同步入口。现有实现的主要问题是职责逐渐混在一起：`BlackroomManagementService` 同时承担 CRUD、业务命名、validation、序列化、买入过滤和状态汇总；股东减持服务也直接依赖这个管理服务；有效期判断主要依赖 `expire_at`。

本次设计目标是把小黑屋从“管理型 CRUD 服务”调整为更清晰的业务模型：封禁、解禁、查询、过滤和每日倒计时各自有明确边界。

## 目标

1. 将业务入口从 `BlackroomManagementService` 收敛为 `BlackroomService`。
2. 使用业务命名：`ban` / `unban` / `is_banned` / `filter_buy_candidates`。
3. 引入倒计时模型：`ban_days` 表示原始封禁天数，`remaining_days` 表示剩余封禁天数。
4. 新增 `BlackroomCountdownService`，只负责每日 `remaining_days -= 1`，归零后删除记录。
5. 将 DB 操作继续放在 `storage/storage_db.py`，service 层不承载复杂 SQL 或持久化细节。
6. 将重复 validation 抽到公共模块，减少 monitor 相关 service 的重复代码。
7. 保持 CLI 和已有调用的短期兼容，逐步迁移到业务命名。

## 非目标

1. 不引入额外 repository 层；当前仓库风格仍以 `StorageDb` 作为持久化入口。
2. 不修改 DAG 调度、任务依赖、重试、SLA 或任务边界。
3. 不改变小黑屋“只限制买入、不强制卖出”的规则。
4. 不在本次重构中扩展新的股东减持判定口径。

## 方案对比

### 方案 A：小改现有 `BlackroomManagementService`

保留现有文件和类名，只新增 `remaining_days`、`ban`、`unban` 和 countdown alias。

优点：改动最小，兼容成本低。

缺点：职责仍然混杂，命名仍偏 CRUD，后续功能继续增加时会再次膨胀。

### 方案 B：拆成领域服务与 countdown 服务（推荐）

新增或重命名为：

1. `BlackroomService`：封禁、解禁、查询、过滤、列表和状态。
2. `BlackroomCountdownService`：每日递减剩余天数并删除到期记录。
3. 股东减持同步服务只负责识别外部事件并调用 `BlackroomService.ban(...)`。
4. DB CRUD 和批量更新继续放在 `storage/storage_db.py`。

优点：职责清晰，符合业务语言，便于 CLI、同步服务和未来定时任务复用。

缺点：需要处理旧接口兼容和测试迁移。

### 方案 C：额外引入 `BlackroomRepository`

在 service 与 `StorageDb` 之间新增 repository 层。

优点：边界更标准。

缺点：与当前项目已有风格不一致，对现阶段需求偏过度设计。

## 推荐方案

采用方案 B。它能解决当前职责和命名问题，又避免引入与仓库风格不一致的额外抽象。

## 详细设计

### 1. 数据模型

`blackroom_records` 保留现有字段：

1. `id`
2. `stock_code`
3. `market`
4. `ban_days`
5. `start_at`
6. `expire_at`
7. `source`
8. `note`
9. `enabled`
10. `created_at`
11. `updated_at`

新增字段：

1. `remaining_days`：剩余封禁天数，正整数表示仍在有效封禁期内。

字段语义调整：

1. `ban_days` 表示原始封禁天数，用于审计和展示。
2. `remaining_days` 表示当前剩余天数，是有效性判断的核心字段。
3. `expire_at` 暂时保留用于兼容旧数据和旧接口，但新逻辑不再依赖它作为主判断。

### 2. 有效小黑屋判断

一条记录视为 active，当且仅当：

```text
enabled = true
remaining_days > 0
```

新逻辑不再以 `expire_at > now` 作为主判断。

### 3. 封禁行为

`BlackroomService.ban(...)` 负责业务语义：

```python
ban(stock_code, market, ban_days, start_at=None, source="manual", note=None, enabled=True)
```

规则：

1. `stock_code` 不能为空。
2. `market` 必须是允许市场之一。
3. `ban_days` 必须是正整数。
4. `remaining_days` 初始化为 `ban_days`。
5. `start_at` 默认当前时间。
6. 同一股票可以保留多条历史记录；是否处于封禁状态只看 active 记录。

### 4. 解禁行为

同时支持两种解禁入口：

```python
unban(record_id)
unban_stock(stock_code, market)
```

规则：

1. `unban(record_id)` 精确删除单条记录，适合 CLI 默认行为。
2. `unban_stock(stock_code, market)` 删除该股票当前相关记录，适合按证券维度解除封禁。
3. 解禁采用硬删除，与 countdown 到期删除保持一致。

### 5. Countdown 服务

新增 `BlackroomCountdownService`，只负责每日倒计时。

建议接口：

```python
run()
```

执行规则：

1. 找到 `enabled=true and remaining_days > 0` 的记录。
2. 批量执行 `remaining_days -= 1`。
3. 删除 `remaining_days <= 0` 的记录。
4. 返回稳定 payload，例如：

```python
{
    "success": True,
    "code": "OK",
    "message": "countdown completed",
    "data": {
        "decremented": 12,
        "deleted": 3,
    },
}
```

`BlackroomCountdownService` 不负责 ban、unban、Tushare 同步或 CLI 参数解析。

### 6. Storage 层职责

`storage/storage_db.py` 继续作为 DB 操作入口，新增或调整以下能力：

1. 创建记录时写入 `remaining_days`。
2. active 查询使用 `enabled=true and remaining_days > 0`。
3. 支持按 `record_id` 删除记录。
4. 支持按 `stock_code + market` 删除记录。
5. 支持 countdown 批量递减和到期删除。
6. 如保留 `expire_at`，只作为兼容字段，不作为新 active 查询主条件。

Storage 层不返回 CLI payload，不包装业务错误码。

### 7. 服务层职责

新增或重命名为 `monitor/blackroom_service.py`，提供业务入口：

```python
ban(...)
unban(record_id)
unban_stock(stock_code, market)
get(record_id)
list(market=None, enabled=None, active_only=False)
status()
is_banned(stock_code, market)
filter_buy_candidates(candidates, market)
```

短期兼容旧方法：

```python
add -> ban
remove -> unban
check -> is_banned
filter -> filter_buy_candidates
```

新代码只使用新命名。

### 8. 股东减持同步服务边界

`BlackroomService` 和股东减持同步服务不是重复关系，而是上下游关系。

股东减持同步服务建议重命名为：

```python
ShareholderSellingPunishmentService
```

职责：

1. 拉取 Tushare 股东减持数据。
2. 归一化 `stock_code + market`。
3. 批内去重。
4. 检查是否已 banned。
5. 调用 `BlackroomService.ban(...)`。

它不直接理解或操作黑屋存储细节。

### 9. Validation 抽取

将 monitor service 中重复的基础校验抽到公共模块，例如 `monitor/validation.py`。

建议包含：

1. `validate_positive_int(value, field_name)`
2. `validate_bool(value, field_name)`
3. `validate_stock_code(value)`
4. `validate_market(value, allowed_markets)`
5. `validate_datetime_or_none(value, field_name)`
6. `validate_yyyymmdd(value, field_name)`
7. `validate_date_range(start_date, end_date)`

公共 validator 可以抛 `ValueError` 或统一 validation 异常；各 service 捕获后转换成自己的稳定 payload。

### 10. CLI 命名

建议新增业务命令：

```bash
stock-monitor blackroom ban
stock-monitor blackroom unban --id 1
stock-monitor blackroom unban --stock-code 600519 --market A
stock-monitor blackroom list
stock-monitor blackroom get
stock-monitor blackroom status
stock-monitor blackroom countdown
stock-monitor blackroom sync-shareholder-selling
```

短期兼容旧命令：

```bash
add -> ban
remove -> unban --id
sync-shareholder-reduction -> sync-shareholder-selling
```

## 旧数据兼容

如果旧记录没有 `remaining_days`，迁移或补偿逻辑按以下顺序处理：

1. 若 `ban_days` 有值，则 `remaining_days = ban_days`。
2. 若 `ban_days` 为空但 `expire_at` 存在，可按剩余自然日估算。
3. 若两者都无法推断，则不迁移为 active 记录。

新 active 查询只看 `remaining_days`，因此旧数据需要在上线前完成 backfill 或在创建表迁移中设置默认值。

## 错误处理

1. 参数错误返回 `VALIDATION_ERROR`。
2. 记录不存在返回 `NOT_FOUND`。
3. 存储层异常返回 `STORAGE_ERROR`。
4. 买入过滤失败不静默放行，应显式返回失败。
5. countdown 失败时返回失败 payload，不部分伪装成功。

## 测试策略

至少覆盖：

1. 数据模型：`remaining_days` 字段存在，默认和 nullable 语义正确。
2. Storage：创建记录初始化 `remaining_days`，active 查询使用 `remaining_days > 0`，按 id/股票删除，countdown 批量递减和删除。
3. `BlackroomService`：`ban/unban/unban_stock/is_banned/filter/list/status`。
4. 兼容 alias：`add/remove/check/filter` 仍可用。
5. `BlackroomCountdownService`：返回稳定 payload，统计 `decremented/deleted`。
6. 股东减持同步服务：调用 `BlackroomService.ban(...)`，不直接操作 storage。
7. CLI：新命令和旧命令兼容，JSON 输出和退出码保持稳定。

## 验收标准

1. 新业务代码使用 `BlackroomService`，不再使用 `BlackroomManagementService` 作为主入口。
2. 新封禁记录包含 `ban_days` 和 `remaining_days`，且二者初始相等。
3. active 判断基于 `enabled=true and remaining_days>0`。
4. countdown 每次运行递减剩余天数，并删除归零记录。
5. 支持按记录 ID 和按股票维度解禁。
6. 股东减持同步服务与小黑屋服务职责清晰，不重复封装小黑屋业务。
7. validation 重复逻辑集中到公共模块。
8. 原有 CLI/测试路径在兼容期内仍能运行。
