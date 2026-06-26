"""Git Diff 构建器 — 生成可审查的 diff 文件."""

import subprocess
from pathlib import Path


class DiffBuilder:
    """将 git diff 整理成可读的 markdown."""

    def __init__(self, project_root: str):
        self.root = Path(project_root)

    def build(self, from_commit: str = "HEAD~1") -> str:
        """生成 diff 报告."""
        diff = self._git_diff(from_commit)
        stat = self._git_diff_stat(from_commit)

        return (
            f"# Code Review Diff\n\n"
            f"## Stats\n```\n{stat}\n```\n\n"
            f"## Full Diff\n```diff\n{diff}\n```\n"
        )

    def short(self) -> str:
        """简洁版 diff，用于日常 checkpoint."""
        return self.build("HEAD")

    def _git_diff(self, ref: str) -> str:
        try:
            r = subprocess.run(
                ["git", "diff", ref], cwd=str(self.root),
                capture_output=True, text=True, timeout=10,
            )
            out = r.stdout.strip()
            # 截断过大的 diff
            if len(out) > 15000:
                out = out[:15000] + "\n... (diff truncated at 15000 chars)"
            return out or "(empty diff)"
        except Exception as e:
            return f"(git diff failed: {e})"

    def _git_diff_stat(self, ref: str) -> str:
        try:
            r = subprocess.run(
                ["git", "diff", "--stat", ref], cwd=str(self.root),
                capture_output=True, text=True, timeout=10,
            )
            return r.stdout.strip() or "(empty)"
        except Exception:
            return "(failed)"
