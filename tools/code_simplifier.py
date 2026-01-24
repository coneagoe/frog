#!/usr/bin/env python3
"""
Code Simplifier Agent for opencode
基于 doc/coding_rule.md 规范的代码简化工具
提供类似 GitHub Copilot agent 的代码审查和简化功能
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent


def get_git_changes() -> List[str]:
    """获取当前变更的文件列表"""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=get_project_root(),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except Exception:
        pass
    return []


def get_staged_files() -> List[str]:
    """获取暂存区的文件列表"""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "HEAD"],
            cwd=get_project_root(),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except Exception:
        pass
    return []


def read_file_content(filepath: str) -> str:
    """读取文件内容"""
    try:
        full_path = get_project_root() / filepath
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"


def analyze_python_complexity(content: str) -> Dict[str, Any]:
    """分析 Python 代码复杂度"""
    lines = content.split("\n")

    # 简单的复杂度指标
    max_nesting_depth: int = 0
    long_lines: List[int] = []
    complexity_indicators = {
        "max_nesting_depth": 0,
        "long_lines": [],
        "duplicate_patterns": [],
        "complex_functions": [],
    }

    current_depth = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # 跳过空行和注释
        if not stripped or stripped.startswith("#"):
            continue

        # 计算嵌套深度
        if stripped.endswith(":"):
            current_depth += 1
            max_nesting_depth = max(max_nesting_depth, current_depth)
        elif stripped and not line.startswith(" "):
            current_depth = 0

        # 检查长行
        if len(line) > 120:
            long_lines.append(i)

    complexity_indicators["max_nesting_depth"] = max_nesting_depth
    complexity_indicators["long_lines"] = long_lines
    return complexity_indicators


def generate_simplification_suggestions(
    filepath: str, content: str
) -> List[Dict[str, str]]:
    """生成简化建议"""
    suggestions: List[Dict[str, str]] = []

    if not filepath.endswith(".py"):
        return suggestions

    complexity = analyze_python_complexity(content)

    # 嵌套过深建议
    if complexity["max_nesting_depth"] > 3:
        suggestions.append(
            {
                "type": "reduce_nesting",
                "description": "减少嵌套深度（当前最大深度：{}）".format(
                    complexity["max_nesting_depth"]
                ),
                "suggestion": "使用 early return 或提取函数来减少嵌套",
            }
        )

    # 长行建议
    if complexity["long_lines"]:
        suggestions.append(
            {
                "type": "break_long_lines",
                "description": "拆分长行（{}行超过120字符）".format(
                    len(complexity["long_lines"])
                ),
                "suggestion": "将长表达式拆分为多行或使用中间变量",
            }
        )

    return suggestions


def review_files(file_list: List[str]) -> Dict[str, Any]:
    """审查文件并生成简化建议"""
    print("🔍 Code Simplifier Review")
    print("=" * 50)

    all_suggestions = []
    python_files = []

    for filepath in file_list:
        print(f"\n📁 分析文件: {filepath}")

        if not filepath.endswith(".py"):
            print("⏭️  跳过非 Python 文件")
            continue

        python_files.append(filepath)
        content = read_file_content(filepath)

        if content.startswith("Error"):
            print(f"❌ {content}")
            continue

        suggestions = generate_simplification_suggestions(filepath, content)

        if suggestions:
            print(f"💡 发现 {len(suggestions)} 个简化机会:")
            for i, suggestion in enumerate(suggestions, 1):
                print(f"  {i}. {suggestion['description']}")
                print(f"     建议: {suggestion['suggestion']}")

            all_suggestions.extend([{**s, "file": filepath} for s in suggestions])
        else:
            print("✅ 代码结构良好，无需简化")

    # 生成总结报告
    print(f"\n{'='*50}")
    print("📊 审查总结")
    print(f"📁 总文件数: {len(file_list)}")
    print(f"🐍 Python 文件数: {len(python_files)}")
    print(f"💡 建议修改数: {len(all_suggestions)}")

    by_type: Dict[str, List[Any]] = {}
    if all_suggestions:
        print("\n🎯 优先处理建议:")

        # 按类型分组
        for s in all_suggestions:
            t = s["type"]
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(s)

        for suggestion_type, items in by_type.items():
            print(f"  • {suggestion_type}: {len(items)} 个文件")

    return {
        "total_files": len(file_list),
        "python_files": len(python_files),
        "suggestions": all_suggestions,
        "by_type": by_type,
    }


def run_verification():
    """运行验证命令（来自白名单）"""
    print("\n🔧 运行验证命令...")

    commands = [
        ("代码格式检查", "poetry run pre-commit run --all-files"),
        ("测试", "poetry run pytest test"),
        ("Docker 配置", "docker compose config"),
    ]

    results = {}

    for name, cmd in commands:
        print(f"\n🏃 运行: {name}")
        print(f"命令: {cmd}")

        try:
            result = subprocess.run(
                cmd,
                cwd=get_project_root(),
                shell=True,
                capture_output=True,
                text=True,
                timeout=180,  # 3分钟超时
            )

            if result.returncode == 0:
                print(f"✅ {name} - 通过")
                results[name] = True
            else:
                print(f"❌ {name} - 失败")
                if result.stderr:
                    print(f"错误信息: {result.stderr[:200]}...")
                results[name] = False

        except subprocess.TimeoutExpired:
            print(f"⏰ {name} - 超时")
            results[name] = False
        except Exception as e:
            print(f"💥 {name} - 异常: {e}")
            results[name] = False

    success_count = sum(results.values())
    total_count = len(results)

    print(f"\n📊 验证结果: {success_count}/{total_count} 通过")

    if success_count == total_count:
        print("🎉 所有验证都通过了！")
        return True
    else:
        print("⚠️  部分验证失败，请检查代码")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Code Simplifier Agent for opencode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s review                    # 审查当前变更
  %(prog)s review --staged           # 审查暂存区文件
  %(prog)s review file1.py file2.py  # 审查指定文件
  %(prog)s verify                     # 运行验证
        """,
    )

    subparsers = parser.add_subparsers(dest="action", help="执行的操作")

    # review 子命令
    review_parser = subparsers.add_parser("review", help="审查代码并生成简化建议")
    review_parser.add_argument("files", nargs="*", help="目标文件列表（可选）")
    review_parser.add_argument("--staged", action="store_true", help="审查暂存区的文件")
    review_parser.add_argument(
        "--changeset", action="store_true", help="审查当前变更集（默认行为）"
    )

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        return 1

    if args.action == "review":
        # 确定审查范围
        target_files = []

        if args.files:
            target_files = args.files
        elif args.staged:
            target_files = get_staged_files()
        else:  # 默认使用变更集
            target_files = get_git_changes()

        if not target_files:
            print("❌ 没有找到需要审查的文件")
            print("提示:")
            print("  • 提供具体的文件路径")
            print("  • 确保有 git 变更或暂存的文件")
            print("  • 使用 --staged 检查暂存区")
            return 1

        print(f"🎯 审查范围: {len(target_files)} 个文件")

        # 执行审查
        results = review_files(target_files)

        # 给出后续建议
        if results["suggestions"]:
            print("\n🎯 下一步建议:")
            print("1. 手动应用上述简化建议")
            print("2. 运行验证确保代码正确性:")
            print("   python tools/code_simplifier.py verify")
            print("3. 提交更改")
        else:
            print("\n🎉 代码质量良好，无需修改！")

        return 0

    elif args.action == "verify":
        success = run_verification()
        return 0 if success else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
