#!/usr/bin/env python3
"""Spirit (灵枢) — AI Orchestrator 主入口.

Shadow Architect 范式:
  你 → Spirit 拦截任务 → 扫描项目 → GPT(网页版)规划 → Execution Spec
  → DeepSeek API 逐步执行 → 自动验证 → 完成

用法:
  python spirit.py plan "任务描述"     # 阶段1: GPT 规划
  python spirit.py execute             # 阶段3: 自动执行 spec.yaml
  python spirit.py run "任务描述"      # 一键全流程
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent))

from context import ContextScanner, DigestBuilder
from planner import (
    ComplexityRouter, ManualCopyPasteAdapter,
    SpecParser, ExecutionSpec, TaskStep,
)
from executor import DeepSeekExecutor, CheckpointManager
from verifier import Verifier
from reviewer import DiffBuilder, Reviewer


# ─── 配置加载 ─────────────────────────────────────────────────

def load_config(project_key: str | None = None) -> dict:
    """加载 config.yaml 并返回合并后的配置."""
    config_path = Path(__file__).parent / "config" / "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    prompts_path = Path(__file__).parent / "config" / "prompts.yaml"
    with open(prompts_path, encoding="utf-8") as f:
        prompts = yaml.safe_load(f)

    cfg["_prompts"] = prompts
    return cfg


def get_project_root(cfg: dict, project_key: str | None) -> str:
    """解析项目路径."""
    key = project_key or cfg["projects"]["default"]
    roots = cfg["projects"].get("roots", {})
    return roots.get(key, os.getcwd())


def get_api_key(cfg: dict) -> str:
    """获取 DeepSeek API key."""
    env_var = cfg["deepseek"]["api_key_env"]
    key = os.environ.get(env_var, "")
    if not key:
        # fallback: 从 settings.local.json 读取 (Claude Code 模式)
        settings_path = Path.home() / ".claude" / "settings.local.json"
        if settings_path.exists():
            import json
            with open(settings_path, encoding="utf-8") as f:
                settings = json.load(f)
            key = settings.get("env", {}).get(env_var, "")
    return key


# ─── Git 工具 ─────────────────────────────────────────────────

def git_commit(project_root: str, message: str) -> bool:
    """执行 git add + commit."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=project_root, check=True, timeout=10)
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=project_root, check=True, timeout=10,
        )
        print(f"  ✅ committed: {message}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ⚠️  git commit 失败: {e}")
        return False


def apply_diff(project_root: str, diff_text: str) -> bool:
    """应用 unified diff 到项目目录."""
    if not diff_text.strip():
        return False
    # 写入临时文件
    tmp = Path(project_root) / ".spirit_diff.patch"
    tmp.write_text(diff_text, encoding="utf-8")
    try:
        result = subprocess.run(
            ["git", "apply", "--reject", str(tmp)],
            cwd=project_root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,        )
        tmp.unlink(missing_ok=True)
        if result.returncode != 0:
            print(f"  ⚠️  patch 应用警告:\n{result.stderr[:300]}")
            return False
        return True
    except Exception as e:
        print(f"  ❌ patch 失败: {e}")
        return False


def show_diff_summary(diff_text: str):
    """展示 diff 的摘要信息."""
    lines = diff_text.split("\n")
    additions = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    deletions = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    files = {l.split()[-1] for l in lines if l.startswith("+++ ")}
    print(f"  📝 {len(files)} files, +{additions}/-{deletions}")
    print(f"  Files: {', '.join(sorted(files)[:5])}")
    if len(files) > 5:
        print(f"         ... and {len(files) - 5} more")


# ─── 主流程 ───────────────────────────────────────────────────

def cmd_plan(cfg: dict, task: str, project: str | None):
    """阶段1: GPT 规划 → 生成 Execution Spec."""
    project_root = get_project_root(cfg, project)

    print(f"\n{'='*60}")
    print(f"🧠 Spirit (灵枢) — Planner      {datetime.now():%H:%M:%S}")
    print(f"📂 项目: {project_root}")
    print(f"📋 任务: {task}")
    print(f"{'='*60}\n")

    # 1. 扫描上下文
    print("🔍 [1/4] 扫描项目上下文...")
    ctx = ContextScanner(project_root).scan()
    digest = DigestBuilder(ctx).build()
    print(f"  ✅ 生成 Digest ({len(digest)} 字符)")

    # 2. 复杂度路由
    print("🎯 [2/4] 分析复杂度...")
    router = ComplexityRouter()
    result = router.score(task)
    print(f"  复杂度: {result.score}/10 | {'🔴 需规划' if result.needs_planner else '🟢 直接执行'}")
    print(f"  原因: {result.reason}")

    if not result.needs_planner:
        print("\n💡 建议: 任务简单，不需要 GPT 规划。直接让 Claude Code 执行。")
        print("   (如果要强制走规划流程，按 Enter 继续)")
        input()

    # 3. 生成 GPT prompt
    print("📝 [3/4] 生成 Planner prompt...")
    prompts = cfg["_prompts"]
    plan_prompt = (
        prompts["planner"]["user"]
        .replace("{{DIGEST}}", digest[:5000])
        .replace("{{TASK}}", task)
    )
    system_prompt = prompts["planner"]["system"]

    # 保存完整 prompt 供 GPT 用
    work_dir = Path(project_root) / ".spirit"
    work_dir.mkdir(exist_ok=True)

    full_prompt = f"System:\n{system_prompt}\n\nUser:\n{plan_prompt}"
    prompt_file = work_dir / "plan_prompt.md"
    prompt_file.write_text(full_prompt, encoding="utf-8")
    print(f"  ✅ Prompt → {prompt_file}")

    # 4. 等待用户从 GPT 网页版获取结果
    print(f"\n{'='*60}")
    print(f"👉 复制 {prompt_file} 的内容到 GPT 网页版")
    print(f"👉 把 GPT 的回复保存为 {work_dir / 'spec.yaml'}")
    print(f"{'='*60}")
    input("\n按 Enter 确认已完成...")

    spec_file = work_dir / "spec.yaml"
    if not spec_file.exists():
        print("❌ spec.yaml 不存在，终止。")
        return None

    spec_text = spec_file.read_text(encoding="utf-8")
    spec = SpecParser.parse(spec_text)
    if spec is None:
        print("❌ 无法解析 Execution Spec，终止。")
        return None

    # 保存 spec 到工作目录
    spec_file.write_text(spec_text, encoding="utf-8")
    print(f"\n✅ Execution Spec 已生成:")
    print(f"   目标: {spec.objective}")
    print(f"   步骤: {spec.total_steps}")
    print(f"   风险: {spec.risk}")
    for t in spec.tasks:
        print(f"   [{t.id}] {t.title}")

    # 可选: GPT Review
    print(f"\n{'='*60}")
    ans = input("🔍 是否需要 GPT Review 此计划? [Y/n] ").strip().lower()
    if ans != "n":
        review_prompt = (
            prompts["reviewer"]["user"]
            .replace("{{DIFF}}", spec_text[:5000])
            .replace("{{ERRORS}}", "(no errors yet — this is the plan, not code)")
            .replace("{{TASK}}", task)
        )
        review_file = work_dir / "review_prompt.md"
        review_file.write_text(
            f"System:\n{prompts['reviewer']['system']}\n\nUser:\n{review_prompt}",
            encoding="utf-8",
        )
        print(f"🔍 Review prompt → {review_file}")
        print(f"👉 复制到 GPT，回复保存为 {work_dir / 'review_result.md'}")
        input("按 Enter 确认完成...")

        review_result = work_dir / "review_result.md"
        if review_result.exists():
            print("📋 Review 结果:")
            print(review_result.read_text(encoding="utf-8")[:600])

    return spec


def cmd_execute(cfg: dict, project: str | None):
    """阶段2: 自动执行 Execution Spec."""
    project_root = get_project_root(cfg, project)
    work_dir = Path(project_root) / ".spirit"
    spec_file = work_dir / "spec.yaml"

    if not spec_file.exists():
        print("❌ spec.yaml 不存在，请先运行 `spirit plan`")
        return

    # 解析 spec
    spec_text = spec_file.read_text(encoding="utf-8")
    spec = SpecParser.parse(spec_text)
    if spec is None:
        print("❌ 无法解析 spec.yaml")
        return

    # 初始化各模块
    api_key = get_api_key(cfg)
    if not api_key:
        print("❌ 未找到 DeepSeek API key (检查环境变量 DEEPSEEK_API_KEY)")
        return

    dc = cfg["deepseek"]
    prompts = cfg["_prompts"]
    executor = DeepSeekExecutor(
        api_key=api_key, api_base=dc["api_base"],
        model=dc["model"], effort=dc.get("executor_effort", "high"),
    )
    executor.project_root = project_root
    verifier = Verifier(project_root, cfg.get("verifier", {}).get("commands", []))
    checkpoint_mgr = CheckpointManager(project_root, cfg.get("executor", {}).get("diff_threshold", 50))
    max_retries = cfg.get("executor", {}).get("max_fix_attempts", 2)

    # 重新生成 digest (项目状态可能变了)
    ctx = ContextScanner(project_root).scan()
    digest = DigestBuilder(ctx).build()

    print(f"\n{'='*60}")
    print(f"🔨 Spirit (灵枢) — Executor      {datetime.now():%H:%M:%S}")
    print(f"📂 项目: {project_root}")
    print(f"🎯 目标: {spec.objective}")
    print(f"📋 步骤: {spec.total_steps}")
    print(f"{'='*60}\n")

    # 逐步执行
    for i, step in enumerate(spec.tasks):
        print(f"\n{'─'*60}")
        print(f"🔨 [{step.id}/{spec.total_steps}] {step.title}")
        print(f"   文件: {', '.join(step.files) if step.files else '(自动判定)'}")
        print(f"   验证: {step.verification[:80] if step.verification else '(无)'}")
        print(f"{'─'*60}")

        # 调用 DeepSeek API 生成 diff
        print("  ⏳ DeepSeek 生成代码...")
        result = executor.run_step(
            step=step, spec=spec, digest=digest,
            executor_prompt=prompts["executor"]["user"],
            executor_system=prompts["executor"]["system"],
        )

        if not result.success:
            print(f"  ❌ DeepSeek 未返回有效 diff")
            ans = input("  ⏭  跳过此步骤? [Y/n] ").strip().lower()
            if ans == "n":
                return
            continue

        # 展示 diff
        show_diff_summary(result.diff)
        print(f"\n  --- Diff Preview (前 20 行) ---")
        for line in result.diff.split("\n")[:20]:
            print(f"  {line}")
        if len(result.diff.split("\n")) > 20:
            print(f"  ... ({len(result.diff.split(chr(10)))} total lines)")

        # 人工确认
        ans = input("\n  ✅ 应用此 diff? [Y/n/s(kip)/q(uit)] ").strip().lower()
        if ans == "q":
            print("👋 退出执行")
            return
        if ans == "s":
            print("  ⏭  跳过")
            continue
        if ans == "n":
            print("  ⏭  跳过 (diff 未应用)")
            continue

        # 应用 diff
        ok = apply_diff(project_root, result.diff)
        if not ok:
            print("  ⚠️  patch 应用失败，尝试直接调用 DeepSeek 修复...")
            # 让 DeepSeek 重新生成一次
            result = executor.run_step(step, spec, digest,
                                       prompts["executor"]["user"],
                                       prompts["executor"]["system"])
            ok = apply_diff(project_root, result.diff)

        if ok:
            git_commit(project_root, f"spirit: [{step.id}/{spec.total_steps}] {step.title}")

        # 自动验证
        print("  🧪 验证中...")
        vr = verifier.check(step.verification)
        retries = 0

        while not vr.passed and retries < max_retries:
            print(f"  ❌ 验证失败 (尝试 {retries + 1}/{max_retries})")
            print(f"  错误:\n{vr.errors[:300]}")
            print("  🔧 DeepSeek 修复中...")
            fix_diff = executor.fix(
                step=step, errors=vr.errors,
                fixer_prompt=prompts["fixer"]["user"],
                fixer_system=prompts["fixer"]["system"],
            )
            if fix_diff:
                apply_diff(project_root, fix_diff)
                git_commit(project_root, f"spirit: fix [{step.id}] {step.title}")
            vr = verifier.check(step.verification)
            retries += 1

        if vr.passed:
            print(f"  ✅ 验证通过")
        else:
            # Checkpoint: 失败 → GPT Review
            print(f"  ⚠️  自动修复 {max_retries} 次后仍未通过")
            print(f"  错误:\n{vr.errors[:500]}")
            diff = checkpoint_mgr.get_diff()
            build_review_prompt(cfg, work_dir, diff, vr.errors, step.title)
            print(f"  👉 GPT Review prompt 已生成: {work_dir / 'review_prompt.md'}")

            ans = input("  ⏭  继续下一步? [Y/n] ").strip().lower()
            if ans == "n":
                return

        # Checkpoint 检查
        cp = checkpoint_mgr.capture(step.id, step.title)
        if cp.needs_review:
            print(f"  ⚠️  Diff 较大 ({cp.diff_lines} lines)，建议 Review")
            ans = input("  🔍 生成 Review prompt? [Y/n] ").strip().lower()
            if ans != "n":
                diff = checkpoint_mgr.get_diff()
                build_review_prompt(cfg, work_dir, diff, "", step.title)
                print(f"  📝 Review prompt → {work_dir / 'review_prompt.md'}")

    print(f"\n{'='*60}")
    print(f"✅ 执行完成！{spec.total_steps} 步已处理")
    print(f"📂 {project_root}")
    print(f"📋 日志: {work_dir}")
    print(f"{'='*60}")


def build_review_prompt(cfg: dict, work_dir: Path, diff: str, errors: str, task_title: str):
    """生成 GPT Review prompt."""
    prompts = cfg["_prompts"]
    prompt = (
        prompts["reviewer"]["user"]
        .replace("{{DIFF}}", diff[:10000])
        .replace("{{ERRORS}}", errors[:2000])
        .replace("{{TASK}}", task_title)
    )
    review_file = work_dir / "review_prompt.md"
    review_file.write_text(
        f"System:\n{prompts['reviewer']['system']}\n\nUser:\n{prompt}",
        encoding="utf-8",
    )


def cmd_run(cfg: dict, task: str, project: str | None):
    """一键全流程: plan → execute."""
    spec = cmd_plan(cfg, task, project)
    if spec is None:
        return
    print("\n⏳ 进入执行阶段...\n")
    cmd_execute(cfg, project)


# ─── CLI 入口 ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Spirit (灵枢) — AI Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python spirit.py plan "集成 PiAgent 到 OneScience"
  python spirit.py execute
  python spirit.py run "给 music-player 加版本号"
        """,
    )
    parser.add_argument("command", choices=["plan", "execute", "run"],
                        help="plan: GPT规划 | execute: 执行spec | run: 一键全流程")
    parser.add_argument("task", nargs="?", default="",
                        help="任务描述 (plan/run 需要)")
    parser.add_argument("--project", "-p", default=None,
                        help="项目 key (见 config.yaml projects.roots)")
    parser.add_argument("--config", default=None,
                        help="自定义 config.yaml 路径")

    args = parser.parse_args()
    cfg = load_config(args.project)

    if args.command == "plan":
        if not args.task:
            print("❌ plan 需要任务描述，例如: python spirit.py plan '集成 PiAgent'")
            sys.exit(1)
        cmd_plan(cfg, args.task, args.project)

    elif args.command == "execute":
        cmd_execute(cfg, args.project)

    elif args.command == "run":
        if not args.task:
            print("❌ run 需要任务描述")
            sys.exit(1)
        cmd_run(cfg, args.task, args.project)


if __name__ == "__main__":
    main()
