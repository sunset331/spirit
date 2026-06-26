"""复杂度路由器 — 决定任务是直接执行还是走 GPT 规划."""

import re
from dataclasses import dataclass


@dataclass
class ComplexityResult:
    score: int              # 0-10
    needs_planner: bool     # score >= 5 → True
    reason: str


class ComplexityRouter:
    """基于关键词 + 文件数 + 项目规模做二分类路由."""

    # 触发规划的关键词
    PLAN_KEYWORDS = [
        "集成", "合并", "迁移", "重构", "架构", "设计",
        "integrate", "merge", "migrate", "refactor", "architecture",
        "新模块", "新增功能", "插件", "plugin", "module",
        "替换", "replace", "重写", "rewrite", "overhaul",
        "多文件", "跨模块", "cross-cutting",
    ]

    # 简单任务关键词 — 直接执行
    SKIP_KEYWORDS = [
        "修改readme", "更新readme", "加注释", "格式化",
        "fix typo", "typo", "lint", "format",
        "加版本号", "改版本", "bump version",
        "加一行", "删一行", "小改",
    ]

    def score(self, task: str) -> ComplexityResult:
        """根据任务描述和项目上下文估算复杂度."""
        task_lower = task.lower()

        # 第一层: 确定性规则
        for kw in self.SKIP_KEYWORDS:
            if kw in task_lower:
                return ComplexityResult(2, False, f"命中简单关键词: {kw}")

        for kw in self.PLAN_KEYWORDS:
            if kw in task_lower:
                return ComplexityResult(7, True, f"命中规划关键词: {kw}")

        # 第二层: 启发式估算
        indicators = 0
        reasons = []

        # 文件数量暗示
        file_mentions = len(re.findall(r'[\w-]+\.[a-z]{1,4}', task))
        if file_mentions >= 3:
            indicators += 3
            reasons.append(f"涉及 {file_mentions}+ 文件")

        # "和" "以及" "包括" 暗示多步骤
        multi_step = len(re.findall(r'和|以及|包括|同时|也|并且', task))
        if multi_step >= 2:
            indicators += 2
            reasons.append("多步骤任务")

        # 任务长度暗示复杂度
        if len(task) > 100:
            indicators += 1

        # 边界判定
        score = min(indicators + 3, 10)  # 底分 3
        needs = score >= 5

        if not reasons:
            reasons.append("任务描述简洁，默认简单")

        return ComplexityResult(score, needs, "; ".join(reasons))
