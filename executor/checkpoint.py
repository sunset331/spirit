"""Checkpoint 管理 — 每步完成后检查 diff 大小和质量."""

import subprocess
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Checkpoint:
    """每步执行后的快照."""
    step_id: int
    step_title: str
    diff_lines: int
    diff_summary: str      # git diff --stat
    needs_review: bool     # diff 过大 → 需要 GPT Review
    commit_hash: str


class CheckpointManager:
    """管理每步的 git checkpoint."""

    def __init__(self, project_root: str, threshold: int = 50):
        self.root = Path(project_root)
        self.threshold = threshold  # diff 超过此行数触发 review

    def capture(self, step_id: int, step_title: str) -> Checkpoint:
        """捕获当前 git 状态作为 checkpoint."""
        diff_lines = self._count_diff()
        diff_stat = self._diff_stat()
        commit = self._last_commit()

        return Checkpoint(
            step_id=step_id,
            step_title=step_title,
            diff_lines=diff_lines,
            diff_summary=diff_stat,
            needs_review=diff_lines > self.threshold,
            commit_hash=commit,
        )

    def get_diff(self) -> str:
        """获取当前未提交的 diff (或最近一次提交)."""
        # 优先取 unstaged + staged diff
        diff = self._run(["git", "diff", "HEAD"])
        if not diff.strip():
            diff = self._run(["git", "diff", "HEAD~1"])
        return diff

    def _count_diff(self) -> int:
        """统计当前 diff 行数."""
        out = self._run(["git", "diff", "--shortstat", "HEAD"])
        # 解析 "3 files changed, 42 insertions(+), 5 deletions(-)"
        import re
        ins = re.search(r'(\d+) insertion', out)
        dels = re.search(r'(\d+) deletion', out)
        total = 0
        if ins:
            total += int(ins.group(1))
        if dels:
            total += int(dels.group(1))
        return total

    def _diff_stat(self) -> str:
        return self._run(["git", "diff", "--stat", "HEAD"])

    def _last_commit(self) -> str:
        return self._run(["git", "log", "-1", "--format=%h %s"])

    def _run(self, cmd: list[str]) -> str:
        try:
            r = subprocess.run(
                cmd, cwd=str(self.root), capture_output=True,
                text=True, timeout=10,
            )
            return r.stdout.strip()
        except Exception:
            return ""
