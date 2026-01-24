#!/usr/bin/env python3
"""
Demo: Using Code Simplifier with existing Copilot agents

这个脚本演示了如何在 opencode 环境中使用 code_simplifier.py
来模拟 GitHub Copilot agents 的工作流程
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """运行命令并显示结果"""
    print(f"\n{'='*60}")
    print(f"🚀 {description}")
    print(f"命令: {cmd}")
    print('='*60)
    
    try:
        result = subprocess.run(
            cmd.split() if isinstance(cmd, str) else cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        
        print(result.stdout)
        if result.stderr:
            print(f"错误输出:\n{result.stderr}")
        
        return result.returncode == 0
    except Exception as e:
        print(f"执行失败: {e}")
        return False

def demo_workflow():
    """演示完整的工作流程"""
    print("🎯 Code Simplifier 工作流演示")
    print("这个演示模拟了 GitHub Copilot agents 的 Review → Apply → Verify 流程")
    
    # 步骤 1: Review 阶段（类似 Code Simplifier agent）
    success = run_command(
        "python3 tools/code_simplifier.py review --staged",
        "📋 步骤 1: Review - 分析代码并生成简化建议"
    )
    
    if not success:
        print("⚠️  Review 阶段遇到问题，继续演示...")
    
    # 模拟用户手动修改代码
    input("\n💡 模拟用户修改代码... 按 Enter 继续")
    
    # 步骤 2: Verify 阶段（类似 Code Simplifier Apply agent 的验证）
    success = run_command(
        "python3 tools/code_simplifier.py verify",
        "✅ 步骤 2: Verify - 运行验证命令确保代码正确性"
    )
    
    if success:
        print("\n🎉 工作流程完成！代码已通过验证。")
    else:
        print("\n⚠️  验证未完全通过，请检查代码修改。")
    
    print(f"\n{'='*60}")
    print("📚 相关文档:")
    print("• doc/CODE_SIMPLIFIER.md - 详细使用说明")
    print("• doc/coding_rule.md - 项目编码规范")
    print("• .github/agents/ - GitHub Copilot agents 配置")
    print('='*60)

def compare_workflows():
    """对比不同工具的工作流程"""
    print("\n🔄 工作流程对比:")
    
    workflows = {
        "GitHub Copilot Agents": [
            "1. Code Simplifier (Review) 分析代码",
            "2. 生成结构化 Change List", 
            "3. 用户点击 'Apply changes'",
            "4. Code Simplifier Apply 自动修改",
            "5. 运行白名单验证命令"
        ],
        "opencode Code Simplifier": [
            "1. python3 tools/code_simplifier.py review",
            "2. 获取人类可读的建议报告",
            "3. 用户手动修改代码",
            "4. python3 tools/code_simplifier.py verify", 
            "5. 自动运行验证命令"
        ]
    }
    
    for tool, steps in workflows.items():
        print(f"\n🔧 {tool}:")
        for step in steps:
            print(f"   {step}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--compare":
        compare_workflows()
    else:
        demo_workflow()