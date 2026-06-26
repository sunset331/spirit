"""审查流程 — 与 GPT 适配器交互."""

from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ReviewOutput:
    """审查结果."""
    lgtm: bool
    issues: list[str] = field(default_factory=list)
    raw_response: str = ""


class Reviewer:
    """管理 review 流程: 构建 prompt → GPT → 解析结果."""

    def __init__(self, adapter, prompt_system: str, prompt_user: str):
        self.adapter = adapter
        self.system = prompt_system
        self.user_template = prompt_user

    def review(self, diff: str, errors: str, task_title: str) -> ReviewOutput:
        """发起审查."""
        prompt = (
            self.user_template
            .replace("{{DIFF}}", diff[:10000])
            .replace("{{ERRORS}}", errors[:2000])
            .replace("{{TASK}}", task_title)
        )
        response = self.adapter.review(prompt, errors, task_title)

        if not response:
            return ReviewOutput(lgtm=False, issues=["GPT 未返回结果"], raw_response="")

        # 简单解析: 是否 LGTM
        lgtm = "lgtm" in response.lower()
        issues = []
        if not lgtm:
            # 提取问题行
            for line in response.split("\n"):
                line = line.strip()
                if line.startswith("- ") or line.startswith("* "):
                    issues.append(line[2:])

        return ReviewOutput(lgtm=lgtm, issues=issues, raw_response=response)
