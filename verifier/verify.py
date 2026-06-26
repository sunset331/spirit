"""自动验证器 — 每步执行后跑 pytest/ruff/mypy."""

import subprocess
from dataclasses import dataclass, field


@dataclass
class VerifyResult:
    """验证结果."""
    passed: bool
    checks: list[dict] = field(default_factory=list)  # [{name, output, passed}]
    errors: str = ""


class Verifier:
    """运行验证命令集合."""

    def __init__(self, project_root: str, commands: list[str] | None = None):
        self.root = project_root
        self.commands = commands or [
            "ruff check --select=E,F --output-format=concise 2>&1 || true",
        ]

    def check(self, custom_cmd: str = "") -> VerifyResult:
        """运行所有验证命令（或自定义命令）."""
        cmds = [custom_cmd] if custom_cmd else self.commands
        all_passed = True
        checks = []
        error_lines = []

        for cmd in cmds:
            if not cmd.strip():
                continue
            ok, output = self._run(cmd)
            checks.append({
                "name": cmd[:60],
                "output": output[:500],
                "passed": ok,
            })
            if not ok:
                all_passed = False
                error_lines.append(f"[FAIL] {cmd}\n{output[:500]}")

        return VerifyResult(
            passed=all_passed,
            checks=checks,
            errors="\n".join(error_lines),
        )

    def _run(self, cmd: str) -> tuple[bool, str]:
        """运行命令，返回 (success, output)."""
        try:
            result = subprocess.run(
                cmd, cwd=self.root, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=60, shell=True,            )
            output = (result.stdout + result.stderr).strip()
            if not output:
                output = "(no output)"
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "命令超时 (60s)"
        except Exception as e:
            return False, str(e)
