"""Project Digest 生成器 — 将原始上下文压缩成 GPT 可消化的摘要."""

from .scanner import ProjectContext


class DigestBuilder:
    """把 ProjectContext 压缩成结构化的 Project Digest Markdown."""

    MAX_TREE_LINES = 60
    MAX_GIT_LOG = 10
    MAX_README_LINES = 50

    def __init__(self, ctx: ProjectContext):
        self.ctx = ctx

    def build(self) -> str:
        """生成 Project Digest 字符串."""
        parts = [
            self._header(),
            self._repo_state(),
            self._structure(),
            self._recent_activity(),
            self._readme_snippet(),
            self._claude_md_snippet(),
        ]
        return "\n\n---\n\n".join(parts)

    def _header(self) -> str:
        return f"# Project: {self.ctx.project_name}\n**Root**: `{self.ctx.project_root}`"

    def _repo_state(self) -> str:
        return (
            f"## Repository State\n"
            f"- **Branch**: `{self.ctx.git_branch}`\n"
            f"- **Status**:\n```\n{self._cap(self.ctx.git_status, 30)}\n```"
        )

    def _structure(self) -> str:
        tree = self._cap_lines(self.ctx.tree, self.MAX_TREE_LINES)
        return f"## Project Structure\n```\n{tree}\n```"

    def _recent_activity(self) -> str:
        log = self._cap_lines(self.ctx.git_log, self.MAX_GIT_LOG)
        recent = "\n".join(f"- `{f}`" for f in self.ctx.recent_files[:8]) or "(none)"
        return (
            f"## Recent Activity\n"
            f"**Last commits**:\n```\n{log}\n```\n"
            f"**Recently modified files**:\n{recent}"
        )

    def _readme_snippet(self) -> str:
        txt = self._cap_lines(self.ctx.readme, self.MAX_README_LINES)
        return f"## README (first {self.MAX_README_LINES} lines)\n```markdown\n{txt}\n```"

    def _claude_md_snippet(self) -> str:
        # CLAUDE.md 可能很大，只取前 80 行
        txt = self._cap_lines(self.ctx.claude_md, 80)
        return f"## CLAUDE.md (project instructions)\n```markdown\n{txt}\n```"

    def _cap(self, s: str, max_lines: int) -> str:
        return self._cap_lines(s, max_lines)

    @staticmethod
    def _cap_lines(s: str, n: int) -> str:
        lines = s.split("\n")
        if len(lines) <= n:
            return s
        return "\n".join(lines[:n]) + f"\n... (truncated, {len(lines)} total lines)"
