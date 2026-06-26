"""GPT 适配器 — 模型无关的抽象层."""

from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass


@dataclass
class ReviewResult:
    problems: list[dict]     # [{file, severity, description, suggestion}]
    lgtm: bool              # 是否通过审查


class GPTAdapter(ABC):
    """适配器接口 — 不绑定网页版/API/本地模型."""

    @abstractmethod
    def plan(self, prompt: str) -> str:
        """发送规划 prompt，返回 Execution Spec (YAML/markdown)."""
        ...

    @abstractmethod
    def review(self, diff: str, errors: str, task: str) -> str:
        """发送审查 prompt，返回修正建议."""
        ...


class ManualCopyPasteAdapter(GPTAdapter):
    """v1.0: 手动 copy-paste 适配器.

    工作流:
    1. Spirit 生成 prompt → 写入 {name}_prompt.md
    2. 用户复制到 GPT 网页版
    3. GPT 回复粘贴到 {name}.md
    4. 按回车, Spirit 读取继续
    """

    def __init__(self, work_dir: str = "."):
        self.work_dir = Path(work_dir)

    def plan(self, prompt: str) -> str:
        out = self.work_dir / "plan_prompt.md"
        result = self.work_dir / "spec.yaml"
        out.write_text(prompt, encoding="utf-8")
        print(f"\n{'='*60}")
        print(f"📋 Planner prompt → {out}")
        print(f"   长度: {len(prompt)} 字符")
        print(f"{'='*60}")
        print(f"👉 复制 {out} 的内容到 GPT 网页版")
        print(f"👉 把 GPT 的回复保存为 {result}")
        print(f"👉 按 Enter 继续...")
        input()
        if result.exists():
            content = result.read_text(encoding="utf-8")
            print(f"✅ 已读取 spec.yaml ({len(content)} 字符)")
            return content
        print("⚠️  spec.yaml 不存在，跳过")
        return ""

    def review(self, diff: str, errors: str, task: str) -> str:
        out = self.work_dir / "review_prompt.md"
        result = self.work_dir / "review_result.md"
        out.write_text(diff, encoding="utf-8")
        print(f"\n{'='*60}")
        print(f"🔍 Review prompt → {out}")
        print(f"{'='*60}")
        print(f"👉 复制 {out} 到 GPT 网页版")
        print(f"👉 把 GPT 回复保存为 {result}")
        print(f"👉 按 Enter 继续...")
        input()
        if result.exists():
            content = result.read_text(encoding="utf-8")
            print(f"✅ 已读取 review_result.md ({len(content)} 字符)")
            return content
        print("⚠️  review_result.md 不存在，跳过")
        return ""
