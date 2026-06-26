"""仓库扫描器 — 收集项目上下文信息."""

import subprocess
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict


@dataclass
class ProjectContext:
    """项目上下文原始数据."""
    project_root: str
    project_name: str
    git_status: str
    git_log: str
    git_branch: str
    tree: str
    readme: str
    claude_md: str
    recent_files: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


class ContextScanner:
    """扫描指定项目目录，收集所有上下文信息."""

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        if not self.root.exists():
            raise FileNotFoundError(f"项目目录不存在: {self.root}")

    def scan(self) -> ProjectContext:
        """执行全量扫描."""
        return ProjectContext(
            project_root=str(self.root),
            project_name=self.root.name,
            git_status=self._git_status(),
            git_log=self._git_log(),
            git_branch=self._git_branch(),
            tree=self._tree(),
            readme=self._readme(),
            claude_md=self._claude_md(),
            recent_files=self._recent_files(),
        )

    def _run(self, cmd: list[str], timeout: int = 10) -> str:
        """运行命令，返回 stdout 或空字符串."""
        try:
            result = subprocess.run(
                cmd, cwd=str(self.root), capture_output=True,
                timeout=timeout, shell=False,
                encoding="utf-8", errors="replace",
            )
            return result.stdout.strip() or "(empty)"
        except Exception:
            return "(not available)"

    def _git_status(self) -> str:
        return self._run(["git", "status", "--short"])

    def _git_log(self) -> str:
        return self._run(["git", "log", "--oneline", "-10"])

    def _git_branch(self) -> str:
        return self._run(["git", "branch", "--show-current"])

    def _tree(self) -> str:
        """生成目录树 (max depth 3, 跳过 .git/__pycache__/node_modules)."""
        exclude = [".git", "__pycache__", "node_modules", ".venv", "venv",
                    ".claude", ".mypy_cache", ".pytest_cache", "dist", "build"]
        try:
            result = subprocess.run(
                ["tree", "-L", "3", "-I", "|".join(exclude), "--dirsfirst"],
                cwd=str(self.root), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,            )
            return result.stdout.strip() or "(tree not available)"
        except FileNotFoundError:
            # Windows 可能没有 tree 命令，fallback 到 dir
            return self._run(["cmd", "/c", "dir", "/s", "/b", "/ad"])

    def _readme(self) -> str:
        """读取 README.md 前 80 行."""
        for name in ["README.md", "README.MD", "readme.md", "Readme.md"]:
            p = self.root / name
            if p.exists():
                lines = p.read_text(encoding="utf-8", errors="replace").split("\n")[:80]
                return "\n".join(lines)
        return "(no README found)"

    def _claude_md(self) -> str:
        """读取 CLAUDE.md 全文."""
        p = self.root / "CLAUDE.md"
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
        # 也检查全局
        global_p = Path.home() / "CLAUDE.md"
        if global_p.exists():
            return global_p.read_text(encoding="utf-8", errors="replace")
        return "(no CLAUDE.md found)"

    def _recent_files(self) -> list[str]:
        """返回最近修改的 10 个文件 (非 .git/__pycache__)."""
        try:
            result = subprocess.run(
                ["git", "log", "--name-only", "--oneline", "-5", "--pretty=format:"],
                cwd=str(self.root), capture_output=True, text=True, timeout=10,
            )
            files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
            skip = {".git", "__pycache__", "node_modules", ".venv"}
            unique = []
            for f in files:
                if not any(s in f for s in skip) and f not in unique:
                    unique.append(f)
            return unique[:10]
        except Exception:
            return []
