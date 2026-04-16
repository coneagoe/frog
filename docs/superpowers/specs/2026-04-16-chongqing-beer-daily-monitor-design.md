# 重庆啤酒日频价格监控设计

## 背景

需要为重庆啤酒新增一条价格监控，条件为股价超过 54 元时告警，检查频率为 daily。

## 方案

复用现有 `tools/stock_monitor_cli.py` 的 `target add` 能力插入监控目标，不直接写 SQL。

目标参数如下：

- `stock_code`: `600132`
- `market`: `A`
- `condition`: `{"type":"price_threshold","direction":"above","value":54}`
- `note`: `重庆啤酒超过54元`
- `frequency`: `daily`
- `reset_mode`: `auto`
- `enabled`: `true`
- `last_state`: `false`

## 数据流

1. 通过 CLI 调用 `TargetManagementService.add_target(...)`。
2. 服务层校验市场、频率和条件 JSON。
3. 存储层写入 `stock_monitor_targets`。
4. `dags/monitor_stock_daily.py` 在每日收盘后加载该目标并评估条件。
5. 条件首次从不满足变为满足时发送邮件告警。

## 错误处理

- 若条件 JSON 非法或字段不符合规则，由服务层返回校验错误。
- 若数据库未初始化或连接失败，CLI 返回内部错误，不做静默降级。

## 验收标准

- 能在监控目标列表中看到 `600132` 的新增记录。
- 记录频率为 `daily`。
- 条件类型为 `price_threshold`，方向为 `above`，阈值为 `54`。
