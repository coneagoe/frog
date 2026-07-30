# monitor `fetch_price` 替换 `fetch_close_price` 设计草案

## 背景

当前 `monitor/price_fetcher.py` 中的 `fetch_current_price()` 直接调用
`stock.data.eastmoney.fetch_close_price.fetch_close_price(stock_code)` 获取实时价格。

这带来两个问题：

1. monitor 当前价来源固定绑定 EastMoney，无法切换到 Tushare。
2. `monitor/price_fetcher.py` 的职责是“获取监控所需当前价和历史行情”，但当前实时价逻辑只是旧接口的薄包装，缺少面向 monitor 的 provider 约束和错误处理说明。

本次目标是在 `monitor/price_fetcher.py` 中实现 `fetch_price`，并用它替换掉当前对
`fetch_close_price` 的依赖。

## 现状梳理

### 当前实现

- `fetch_current_price(stock_code, market)` 只是把 `stock_code` 传给 EastMoney 的
  `fetch_close_price()`。
- `fetch_history_df()` 继续从 storage 读取历史日线，这部分与本次改动无直接冲突。

### 当前测试覆盖

现有 `test/monitor/test_price_fetcher.py` 主要验证：

- `fetch_current_price()` 是否调用了 `fetch_close_price()`
- `fetch_history_df()` 在 A 股 / ETF 下的历史数据读取逻辑

`test/monitor/test_price_fetcher_imports.py` 额外验证：

- 导入 `monitor.price_fetcher` 不需要依赖 `scipy`

因此，实时价替换后需要同步调整 import-safe 行为和对应测试断言。

### Tushare 适配结论

基于 Tushare 实时接口能力，当前可以采用如下市场范围：

- **A 股**：支持，通过 `rt_k` 获取实时日 K，`close` 可视为当前价
- **A 股 ETF**：如果代码是 `.SH/.SZ` 的交易代码，可沿用 `rt_k`
- **港股**：`rt_k` / `rt_min` 未见明确常规支持，当前不建议在本次实现中兼容

用户已确认的失败策略：

- **只使用 Tushare**
- **Tushare 不可用、未配置 token、返回空结果或不支持时，返回 `np.nan`**

## 方案对比

### 方案 1：在 `monitor/price_fetcher.py` 内直接实现 `fetch_price`（推荐）

做法：

- 在 `monitor/price_fetcher.py` 内新增 `fetch_price(stock_code, market)`。
- 函数内部懒加载 `tushare`，读取 `TUSHARE_TOKEN`，创建 `pro` client。
- A 股 / ETF 将代码转换为 `ts_code` 后调用 `pro.rt_k(...)`，读取最新 `close`。
- HK 直接返回 `np.nan`。
- `fetch_current_price()` 改为调用 `fetch_price()`。

优点：

- 改动范围最小，只影响 monitor 当前价逻辑。
- 不再依赖 EastMoney 的 `fetch_close_price`。
- 函数内导入 `tushare`，更容易维持 monitor 模块的轻量导入特性。

缺点：

- monitor 内部会出现少量 Tushare client 初始化逻辑。

### 方案 2：复用 `download.dl.downloader_tushare` 的辅助函数

做法：

- 直接复用 `_create_pro_client()` / `require_pro_client()` 等现有 Tushare 辅助逻辑。

优点：

- token 校验逻辑可复用。

缺点：

- monitor 依赖 downloader 层，边界不够清晰。
- 为一个单点读取实时价而引入跨层耦合，收益较小。

### 方案 3：抽象统一的行情 provider

做法：

- 在 `stock/` 或 `monitor/` 下新增统一 provider，把实时价来源抽象成独立层。

优点：

- 后续扩展更多实时行情源时更容易复用。

缺点：

- 对当前需求明显过度设计。
- 需要额外梳理全仓库其他 `fetch_close_price` 使用点，不适合本次局部改造。

## 推荐方案

采用 **方案 1**。

理由：

- 用户目标是“在 `@monitor/price_fetcher.py` 实现 `fetch_price`，替换掉
  `fetch_close_price`”，优先满足 monitor 这一处的需求即可。
- 当前 monitor 实时价逻辑本来就是单文件薄包装，直接在这里完成 provider 切换最清晰。
- 可以保留历史行情读取逻辑不变，把改动严格限定在 monitor 当前价获取路径上。

## 设计细节

### 1. 对外行为

- 新增 `fetch_price(stock_code: str, market: str) -> float`
- `fetch_current_price(stock_code, market)` 改为委托给 `fetch_price(stock_code, market)`
- 不再从 `stock.data.eastmoney.fetch_close_price` 导入 `fetch_close_price`

### 2. 市场处理规则

- `market == "A"`：按 A 股代码转换为 `ts_code`，如 `600519 -> 600519.SH`
- `market == "ETF"`：按 ETF 代码前缀转换为 `ts_code`
  - `5xxxxx` 通常映射 `.SH`
  - `1xxxxx` 通常映射 `.SZ`
- `market == "HK"`：直接返回 `np.nan`
- 其他未知 market：返回 `np.nan`

### 3. Tushare 调用方式

- 从环境变量 `TUSHARE_TOKEN` 读取 token
- 如果 token 缺失，直接返回 `np.nan`
- 使用 `ts.pro_api(token=token)` 创建 client
- 调用 `pro.rt_k(ts_code=...)`
- 从返回 DataFrame 中读取最新一行的 `close`

### 4. 错误处理

保持与 monitor 当前实现一致的“失败时给出空值”的风格：

- token 缺失：返回 `np.nan`
- `tushare` 导入失败：返回 `np.nan`
- `rt_k` 返回空 DataFrame / 缺少 `close` 字段：返回 `np.nan`
- `close` 无法转成浮点数：返回 `np.nan`
- Tushare 请求异常：返回 `np.nan`

不引入回退到 EastMoney 的逻辑。

### 5. import 安全性

当前有测试确保导入 `monitor.price_fetcher` 时不会因为额外依赖出错。

因此本次实现应避免在模块顶层直接初始化 Tushare client。更稳妥的方式是：

- 在 `fetch_price()` 内部局部导入 `tushare`
- 在真正调用实时价接口时再访问 token 和创建 client

这样即使运行环境未安装完整数据依赖，单纯导入 monitor 模块仍应保持稳定。

## 测试调整

建议补充 / 更新以下测试：

1. `fetch_current_price()` 委托给 `fetch_price()`
2. A 股代码通过 Tushare `rt_k` 成功返回当前价
3. ETF 代码通过 Tushare `rt_k` 成功返回当前价
4. HK market 返回 `np.nan`
5. 缺少 `TUSHARE_TOKEN` 时返回 `np.nan`
6. `rt_k` 返回空 DataFrame 时返回 `np.nan`
7. 导入 `monitor.price_fetcher` 仍不要求运行时提前初始化实时行情依赖

## 范围界定

本次改动只覆盖：

- `monitor/price_fetcher.py`
- 对应 monitor 测试

本次不覆盖：

- 全仓库其他 `fetch_close_price` 调用点
- monitor 历史行情读取逻辑
- 港股实时价兼容
- 新的统一行情 provider 抽象

## 后续实现步骤

1. 在 `monitor/price_fetcher.py` 中加入 `fetch_price`
2. 让 `fetch_current_price()` 改为调用 `fetch_price`
3. 删除 monitor 对 EastMoney `fetch_close_price` 的直接依赖
4. 更新并补充 monitor 相关测试
