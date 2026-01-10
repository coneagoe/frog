# StorageDb 多进程使用指南

## 问题背景

在多进程环境下使用 `StorageDb` 时，如果多个进程共享同一个数据库连接实例，可能会导致以下问题：

1. **连接状态冲突**：一个进程关闭连接会影响其他进程
2. **事务干扰**：不同进程的事务可能相互影响
3. **cursor竞争**：多个进程同时使用同一个cursor可能导致数据混乱
4. **连接池耗尽**：共享连接可能导致连接池资源耗尽

## 解决方案

### 1. 每个进程创建独立实例（推荐）

修改后的 `get_storage()` 函数确保每个进程获得独立的 `StorageDb` 实例：

```python
# 进程1
storage1 = get_storage()
storage1.save_history_data_stock(df1, PeriodType.DAILY, AdjustType.QFQ)

# 进程2
storage2 = get_storage()  # 获得独立实例
storage2.save_history_data_stock(df2, PeriodType.DAILY, AdjustType.QFQ)
```

### 2. 使用SQLAlchemy Engine操作（安全）

大部分写操作使用SQLAlchemy的`to_sql`方法，相对安全：

```python
df.to_sql(
    table_name,
    storage.engine,  # 使用engine而不是直接cursor
    if_exists="append",
    index=False,
    method="multi",
)
```

### 3. 避免共享cursor操作

避免在多进程间共享使用以下方法：
- `query()`
- `drop_table()`
- `get_last_record()`

## 最佳实践

### 多进程数据写入示例

```python
from multiprocessing import Pool
from storage.storage_db import get_storage
from storage.config import StorageConfig

def process_stock_data(stock_data):
    """处理单个股票数据"""
    # 每个进程创建自己的storage实例
    storage = get_storage()

    try:
        # 使用SQLAlchemy engine进行写操作（安全）
        storage.save_history_data_stock(
            stock_data['df'],
            stock_data['period'],
            stock_data['adjust']
        )
        return True
    except Exception as e:
        print(f"处理股票数据失败: {e}")
        return False
    finally:
        # 确保断开连接
        storage.disconnect()

# 多进程处理
if __name__ == '__main__':
    stock_data_list = [...]  # 股票数据列表

    with Pool(processes=4) as pool:
        results = pool.map(process_stock_data, stock_data_list)
```

### 多进程查询示例

```python
def query_stock_data(query_params):
    """查询股票数据"""
    storage = get_storage()

    try:
        # 使用engine进行查询（安全）
        df = pd.read_sql(query_params['sql'], storage.engine)
        return df
    finally:
        storage.disconnect()

# 注意：大量并发查询可能导致数据库连接压力
```

## 注意事项

1. **连接池配置**：确保PostgreSQL的连接池配置足够大
2. **事务隔离**：重要操作使用数据库事务隔离级别
3. **错误处理**：每个进程都要正确处理连接错误
4. **资源清理**：确保每个进程正确关闭连接
5. **并发控制**：避免过度并发导致数据库压力

## 性能优化建议

1. **批量操作**：尽量使用批量插入而不是单条插入
2. **连接复用**：在单个进程内复用连接，避免频繁创建
3. **索引优化**：确保数据库表有适当的索引
4. **分批处理**：大量数据分批处理，避免内存溢出

## 监控和调试

1. **连接监控**：监控数据库连接数和使用情况
2. **错误日志**：记录详细的错误信息便于调试
3. **性能监控**：监控查询和写入性能
4. **死锁检测**：注意检测和解决死锁问题
