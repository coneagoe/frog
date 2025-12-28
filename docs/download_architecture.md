# 数据下载架构设计

## 概述

新的数据下载架构采用了分层设计，通过 `DownloadManager` 协调 `Downloader` 和 `Storage`，并集成了智能状态管理系统。

## 架构组件

### 1. Downloader（数据下载器）
- **位置**: `stock/data/downloader/downloader.py`
- **职责**: 纯粹的数据下载操作
- **特点**: 操作符模式，灵活映射不同数据源

```python
class Downloader:
    # 基础信息下载方法
    dl_general_info_stock = download_general_info_stock_ak
    dl_general_info_etf = download_general_info_etf_ak
    dl_general_info_hk_ggt_stock = download_general_info_hk_ggt_stock_ak
    
    # 历史数据下载方法
    dl_history_data_etf = download_history_data_etf_ak
    dl_history_data_us_index = download_history_data_us_index_ak
    dl_history_data_stock = download_history_data_stock_ak
```

### 2. Storage（数据存储）
- **位置**: `stock/data/storage/`
- **职责**: 数据持久化和读取
- **支持**: CSV、TimescaleDB 等多种存储方式

### 3. DownloadManager（下载管理器）
- **位置**: `stock/data/download_manager.py`
- **职责**: 协调下载和存储，管控下载逻辑
- **功能**:
  - 集成状态管理
  - 增量更新逻辑
  - 批量下载支持
  - 错误处理

### 4. 状态管理系统
- **位置**: `stock/data/downloader/download_status.py`
- **功能**:
  - 跟踪每日下载状态
  - 自动跳过已完成任务
  - 支持强制重新执行
  - 提供详细执行报告

## 核心特性

### 智能状态管理

每个下载任务都会被自动跟踪状态：

```python
@track_download_status(task_name="stock_general_info")
def download_and_save_stock_info(self, force: bool = False) -> bool:
    # 如果今天已完成，自动跳过（除非 force=True）
    df = self.downloader.dl_general_info_stock()
    return self.storage.save_general_info(df, "stock")
```

### 增量更新

历史数据支持智能增量更新：

```python
def _incremental_update(self, item_id: str, period: str, end_date: str, adjust: str, download_func):
    latest_date = self.storage.get_latest_date(item_id, period, adjust)
    # 只下载缺失的数据
    if latest_date is None or pd.Timestamp(end_date) <= latest_date:
        return True  # 数据已是最新
    # 下载并合并新数据...
```

### 批量处理

支持 Airflow 驱动的批量下载：

```python
def run_batch_history_download(self, item_ids: List[str], item_type: str, ...):
    for item_id in item_ids:
        if download_method(item_id, period, start_date, end_date, adjust):
            success_count += 1
```

## 使用方式

### 基本使用

```python
from stock.data.factory import create_download_manager

# 创建管理器
manager = create_download_manager(storage_type="csv")

# 下载基础信息
manager.download_all_basic_info()

# 下载历史数据
manager.download_and_save_stock_history("000001", "daily", "20240101", "20241231")
```

### 强制刷新

```python
# 强制重新下载，忽略今日已完成状态
manager.download_and_save_stock_info(force=True)
```

### 状态查询

```python
from stock.data.downloader.download_status import get_today_status_summary

status = get_today_status_summary()
print(f"今日状态: {status['summary']}")
```

## Airflow 集成

### DAG 示例

```python
def download_basic_info(**context):
    manager = create_download_manager(storage_type="csv")
    success = manager.download_all_basic_info()
    if not success:
        raise Exception("Failed to download basic info")

task_download_basic_info = PythonOperator(
    task_id='download_basic_info',
    python_callable=download_basic_info,
    dag=dag,
)
```

### 任务依赖

```python
# 设置任务依赖关系
task_download_basic_info >> [task_download_stock_history, task_download_etf_history]
[task_download_stock_history, task_download_etf_history] >> task_check_status >> task_cleanup
```

## 状态文件格式

状态信息以 JSON 格式存储在 `data/download_status.json`：

```json
{
  "2025-09-08": {
    "stock_general_info": {
      "task_name": "stock_general_info",
      "status": "success",
      "timestamp": "2025-09-08T09:30:00.123456",
      "execution_time": 5.23,
      "error_message": null
    }
  }
}
```

## 优势

1. **职责分离**: 下载、存储、管理各司其职
2. **灵活扩展**: 支持多种数据源和存储方式
3. **智能控制**: 自动跳过已完成任务，避免重复下载
4. **错误恢复**: 详细的状态跟踪和错误信息
5. **易于监控**: 完整的执行报告和状态查询
6. **Airflow 友好**: 为调度系统优化设计

## 文件结构

```
stock/data/
├── downloader/
│   ├── download_status.py          # 状态管理
│   ├── downloader.py              # 操作符下载器
│   └── downloader_akshare.py      # AkShare 实现
├── storage/
│   ├── base.py                    # 存储接口
│   ├── csv_storage.py             # CSV 存储
│   └── timescale_storage.py       # TimescaleDB 存储
├── download_manager.py            # 核心管理器
└── factory.py                     # 工厂函数

dags/
└── download_stock_history_daily.py   # Airflow DAG

examples/
└── download_usage_demo.py          # 使用示例

data/
└── download_status.json            # 状态文件
```

这个架构完美契合了"DownloadManager 协调 Downloader 和 Storage，由 Airflow 驱动"的设计理念。
