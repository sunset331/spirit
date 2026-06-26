"""Execution Spec 解析器 — 从 GPT 返回中提取结构化任务列表."""

import re
import yaml
from dataclasses import dataclass, field


@dataclass
class TaskStep:
    """执行计划中的单步."""
    id: int
    title: str
    files: list[str] = field(default_factory=list)
    verification: str = ""


@dataclass
class ExecutionSpec:
    """GPT 生成的执行计划."""
    objective: str
    complexity: int
    risk: str              # low / medium / high
    estimated_tasks: int
    tasks: list[TaskStep] = field(default_factory=list)

    @property
    def total_steps(self) -> int:
        return len(self.tasks)

    def get_step(self, idx: int) -> TaskStep | None:
        """获取第 idx 步 (1-based)."""
        for t in self.tasks:
            if t.id == idx:
                return t
        return None


class SpecParser:
    """从 GPT 回复中提取 YAML Execution Spec."""

    @staticmethod
    def parse(text: str) -> ExecutionSpec | None:
        """尝试从 GPT 回复中提取 YAML 并解析."""
        # 方法1: ```yaml ... ``` fence
        yaml_match = re.search(r'```yaml\s*\n(.*?)\n```', text, re.DOTALL)
        if yaml_match:
            raw = yaml_match.group(1)
            return SpecParser._from_yaml(raw)

        # 方法2: ``` ... ``` (无语言标签)
        fence_match = re.search(r'```\s*\n(.*?)\n```', text, re.DOTALL)
        if fence_match:
            raw = fence_match.group(1)
            if 'objective:' in raw and 'tasks:' in raw:
                return SpecParser._from_yaml(raw)

        # 方法3: 全文尝试 YAML
        if 'objective:' in text and 'tasks:' in text:
            return SpecParser._from_yaml(text)

        print(f"⚠️  无法从 GPT 回复中提取 Execution Spec")
        print(f"   回复前 200 字符: {text[:200]}")
        return None

    @staticmethod
    def _from_yaml(raw: str) -> ExecutionSpec | None:
        """解析 YAML 字符串为 ExecutionSpec."""
        try:
            data = yaml.safe_load(raw)
            if not isinstance(data, dict):
                return None

            tasks = []
            for t in data.get("tasks", []):
                tasks.append(TaskStep(
                    id=int(t.get("id", len(tasks) + 1)),
                    title=str(t.get("title", "unknown")),
                    files=[str(f) for f in t.get("files", [])],
                    verification=str(t.get("verification", "")),
                ))

            return ExecutionSpec(
                objective=str(data.get("objective", "unknown")),
                complexity=int(data.get("complexity", 5)),
                risk=str(data.get("risk", "medium")),
                estimated_tasks=int(data.get("estimated_tasks", len(tasks))),
                tasks=tasks,
            )
        except yaml.YAMLError as e:
            print(f"⚠️  YAML 解析失败: {e}")
            return None
