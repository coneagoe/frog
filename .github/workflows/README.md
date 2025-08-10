# GitHub Actions CI/CD Setup

本项目配置了完整的 GitHub Actions CI/CD 流水线，包括以下功能：

## Workflows 说明

### 1. CI Pipeline (`ci.yml`)
- **触发条件**: Push 到 main/develop 分支，或 PR 到这些分支
- **功能**: 
  - 代码质量检查 (pre-commit hooks: black, isort, flake8, mypy)
  - 安全检查 (safety, bandit)
  - 构建包
- **Python 版本**: 3.12

### 2. Docker Build & Deploy (`docker.yml`)
- **触发条件**: Push 到 main 分支或标签
- **功能**:
  - 构建 Docker 镜像
  - 推送到 GitHub Container Registry (ghcr.io)
  - 可选的部署步骤

### 3. 依赖更新 (`update-deps.yml`)
- **触发条件**: 每周一 UTC 9:00 自动执行，或手动触发
- **功能**:
  - 自动更新 Poetry 依赖
  - 创建 PR 用于审查

### 4. 代码质量检查 (`quality.yml`)
- **触发条件**: Push 到 main/develop 分支，或 PR 到这些分支
- **功能**:
  - 代码复杂度分析
  - 重复代码检查
  - SonarCloud 代码质量分析
  - 文档构建

### 5. 发布流程 (`release.yml`)
- **触发条件**: 推送标签 (v*)
- **功能**:
  - 创建 GitHub Release
  - 生成变更日志
  - 可选的 PyPI 发布

## 设置说明

### 1. 基本设置
这些 workflows 开箱即用，不需要额外配置。

### 2. 可选配置

#### SonarCloud (代码质量分析)
1. 访问 [SonarCloud](https://sonarcloud.io)
2. 导入您的 GitHub 仓库
3. 在 GitHub 仓库设置中添加 Secret: `SONAR_TOKEN`

#### PyPI 发布
1. 获取 PyPI API Token
2. 在 GitHub 仓库设置中添加 Secret: `PYPI_TOKEN`
3. 取消注释 `release.yml` 中的 `poetry publish` 行

#### 自动部署
在 `docker.yml` 的 deploy job 中添加您的部署脚本。

### 3. GitHub 设置

#### 必需的权限
确保 GitHub Actions 有以下权限：
- Contents: Read (读取代码)
- Packages: Write (推送 Docker 镜像)
- Pull Requests: Write (创建依赖更新 PR)

#### 环境保护 (可选)
为生产环境设置保护规则：
1. 进入仓库设置 → Environments
2. 创建 `production` 环境
3. 设置审批规则

## 使用方法

### 开发流程
1. 创建功能分支
2. 提交代码 (会自动运行 pre-commit hooks)
3. 创建 PR (会触发 CI 检查)
4. 合并到 main 分支 (会构建和部署)

### 发布流程
1. 确保 main 分支是最新的
2. 创建并推送标签:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
3. GitHub Actions 会自动创建 Release

### 手动操作
- **依赖更新**: 在 Actions 页面手动触发 "Update Dependencies" workflow
- **重新运行**: 任何失败的 workflow 都可以重新运行

## 状态徽章

在 README.md 中添加状态徽章：

```markdown
![CI](https://github.com/coneagoe/frog/workflows/CI/badge.svg)
![Docker](https://github.com/coneagoe/frog/workflows/Docker%20Build%20&%20Deploy/badge.svg)
![Quality](https://github.com/coneagoe/frog/workflows/Code%20Quality/badge.svg)
```

## 故障排除

### 常见问题
1. **权限错误**: 检查 GitHub Actions 权限设置
2. **Docker 构建失败**: 检查 Dockerfile 和依赖
3. **依赖更新失败**: 检查 Poetry 配置和锁文件

### 日志查看
在 GitHub 仓库的 Actions 标签页可以查看详细的执行日志。
