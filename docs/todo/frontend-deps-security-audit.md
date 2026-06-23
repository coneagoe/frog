# Paper Trading Frontend: npm 依赖安全审计

发现时间: 2026-06-18
来源: `frontend/paper-trading/` 首次 `npm install` / `npm ci`

## 概览

`npm audit` 报告 7 个漏洞（5 moderate, 1 high, 1 critical）。

## 漏洞明细

| 包 | 严重度 | 类型 | 影响 | 修复方向 |
|---|---|---|---|---|
| **vitest** (dev) | **critical** | `@vitest/mocker` 传递 | 测试运行器 | `vitest` ≥ 3.x |
| **vite** (dev) | high | 路径遍历 (`.map`) | 开发服务器安全 | `vite` ≥ 6.4.2 |
| **postcss** (传递) | moderate | XSS via `<style>` | CSS 解析输出 | `postcss` ≥ 8.5.10 |
| **esbuild** (传递) | moderate | 开发服务请求读取 | 开发环境 | `esbuild` ≥ 0.25.0 |
| **@vitest/mocker** (dev) | moderate | vitest 传递 | 测试隔离 | `vitest` 升级连带修复 |
| **vite-node** (dev) | moderate | vite 传递 | 开发服务器 | `vite` 升级连带修复 |
| **next** | moderate | postcss 传递 | 构建/运行时 | `next` ≥ 15.x 新版本 |

## 备注

- `vitest` / `vite` 为 devDependencies，生产镜像不包含，影响范围有限。
- `postcss` 是 `next` 的传递依赖，需等 Next.js 升级携带修复版本。
- 当前 `package.json` 锁定 Next.js `^15.1.4`，vite `^2.1.8`，vitest `^2.1.8`。
- 未运行 `npm audit fix --force`（可能引入 breaking changes）。
- 建议在常规依赖升级周期中一并处理，无需单独紧急修复。
