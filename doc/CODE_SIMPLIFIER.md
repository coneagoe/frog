# Code Simplifier for opencode

这是为 opencode 实现的代码简化工具，类似于 GitHub Copilot 的 Code Simplifier agent，但专门为 opencode 环境优化。

## 功能特性

### 🔍 Review 模式（审查）
- 分析 Python 代码复杂度
- 识别嵌套过深、长行等问题
- 提供具体的简化建议
- 支持多种文件范围选择

### 🔧 Verify 模式（验证）
- 运行项目白名单中的验证命令
- 确保代码更改不破坏现有功能
- 提供详细的验证报告

## 安装和使用

### 前置条件
- Python 3.11+
- Poetry（推荐）
- Git

### 基本使用

```bash
# 审查当前变更的文件
python3 tools/code_simplifier.py review

# 审查暂存区的文件
python3 tools/code_simplifier.py review --staged

# 审查指定文件
python3 tools/code_simplifier.py review file1.py file2.py

# 运行验证
python3 tools/code_simplifier.py verify
```

### 帮助信息
```bash
python3 tools/code_simplifier.py --help
```

## 与 GitHub Copilot Agent 的对比

| 特性 | GitHub Copilot Agent | opencode Code Simplifier |
|------|---------------------|-------------------------|
| 环境支持 | VS Code + GitHub Copilot | 命令行 + 任何编辑器 |
| 审查方式 | AI 自动分析 | 基于规则的分析 |
| 验证命令 | 手动执行 | 自动执行白名单命令 |
| 输出格式 | 结构化 Change List | 人类可读的报告 |
| 两阶段工作流 | Review → Apply | Review → 手动修改 → Verify |

## 工作流对比

### GitHub Copilot Agent 工作流
1. Code Simplifier (Review) 分析代码
2. 生成 Change List
3. 用户点击 "Apply changes" 
4. Code Simplifier Apply 自动修改并验证

### opencode Code Simplifier 工作流
1. `python3 tools/code_simplifier.py review` 分析代码
2. 获取简化建议报告
3. 用户手动修改代码
4. `python3 tools/code_simplifier.py verify` 验证修改

## 验证白名单

基于 `doc/coding_rule.md` 的规定，仅运行以下验证命令：

1. `poetry run pre-commit run --all-files` - 代码格式和质量检查
2. `poetry run pytest test` - 单元测试
3. `docker compose config` - Docker 配置验证

## 代码分析规则

当前版本支持的简化建议类型：

### 1. 嵌套深度检查
- 识别嵌套超过 3 层的代码块
- 建议使用 early return 或提取函数

### 2. 长行检查
- 识别超过 120 字符的行
- 建议拆分表达式或使用中间变量

## 扩展性

工具设计为可扩展的，未来可以添加：

- 更多代码质量指标分析
- 自动应用简单重构
- 集成更多验证命令
- 支持其他编程语言

## 示例输出

```
🎯 审查范围: 1 个文件
🔍 Code Simplifier Review
==================================================

📁 分析文件: tools/code_simplifier.py
💡 发现 1 个简化机会:
  1. 减少嵌套深度（当前最大深度：55）
     建议: 使用 early return 或提取函数来减少嵌套

==================================================
📊 审查总结
📁 总文件数: 1
🐍 Python 文件数: 1
💡 建议修改数: 1

🎯 优先处理建议:
  • reduce_nesting: 1 个文件

🎯 下一步建议:
1. 手动应用上述简化建议
2. 运行验证确保代码正确性:
   python3 tools/code_simplifier.py verify
3. 提交更改
```

## 集成到开发流程

### Pre-commit Hook（可选）
可以将审查集成到 pre-commit hooks 中：

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: code-simplifier
        name: Code Simplifier
        entry: python3 tools/code_simplifier.py review
        language: system
        always_run: false
        pass_filenames: true
```

### Git Alias
添加便捷的 git 别名：

```bash
git config --global alias.simplify '!python3 tools/code_simplifier.py review'
git config --global alias.verify '!python3 tools/code_simplifier.py verify'
```

## 注意事项

1. **语义不变**: 工具仅提供建议，不自动修改，确保用户完全控制
2. **项目规范**: 严格遵循项目的编码规范和验证白名单
3. **错误处理**: 单个文件错误不会影响其他文件的分析
4. **性能**: 对于大型项目，建议限制分析范围

## 贡献

欢迎提交 Issue 和 PR 来改进这个工具：

- 添加更多代码质量分析规则
- 改进建议的准确性
- 优化性能
- 扩展语言支持