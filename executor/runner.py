"""DeepSeek API 执行器 — 每步独立调用 API 生成 diff."""

import os
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass
from urllib import request, error


@dataclass
class ExecResult:
    """单步执行结果."""
    success: bool
    diff: str             # unified diff
    new_file: str         # 如果是新文件，完整内容
    step_title: str
    errors: list[str]


class DeepSeekExecutor:
    """调用 DeepSeek API 执行单个任务步骤."""

    def __init__(self, api_key: str, api_base: str = "https://api.deepseek.com",
                 model: str = "deepseek-chat", effort: str = "high"):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.effort = effort
        self.project_root = "."

    def run_step(self, step: "TaskStep", spec: "ExecutionSpec",
                 digest: str, executor_prompt: str,
                 executor_system: str) -> ExecResult:
        """执行单个步骤，返回 diff."""
        # 读取相关文件内容
        file_contents = self._read_files(step.files)

        # 构造 prompt
        user_prompt = executor_prompt
        # 模板变量替换
        user_prompt = user_prompt.replace("{{STEP_ID}}", str(step.id))
        user_prompt = user_prompt.replace("{{STEP_TITLE}}", step.title)
        user_prompt = user_prompt.replace("{{OBJECTIVE}}", spec.objective)
        user_prompt = user_prompt.replace("{{VERIFICATION}}", step.verification)
        user_prompt = user_prompt.replace("{{DIGEST}}", digest[:3000])  # 截断
        user_prompt = user_prompt.replace("{{FILES}}", "\n".join(f"- {f}" for f in step.files))
        user_prompt = user_prompt.replace("{{FILE_CONTENTS}}", file_contents)

        # 调用 API
        response = self._call_api(executor_system, user_prompt)
        diff = self._extract_diff(response)

        return ExecResult(
            success=bool(diff),
            diff=diff,
            new_file="",
            step_title=step.title,
            errors=[] if diff else ["API 未返回有效 diff"],
        )

    def fix(self, step: "TaskStep", errors: str,
            fixer_prompt: str, fixer_system: str) -> str:
        """根据错误信息生成修复 diff."""
        user_prompt = (
            fixer_prompt
            .replace("{{ERRORS}}", errors[:2000])
            .replace("{{TASK}}", step.title)
            .replace("{{DIFF}}", "see previous attempt")
        )
        response = self._call_api(fixer_system, user_prompt)
        return self._extract_diff(response)

    def _call_api(self, system: str, user: str) -> str:
        """调用 DeepSeek Chat API."""
        url = f"{self.api_base}/v1/chat/completions"
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "max_tokens": 8000,
        }).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            req = request.Request(url, data=payload, headers=headers, method="POST")
            with request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                return content
        except error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"❌ DeepSeek API HTTP {e.code}: {body[:500]}")
            return ""
        except Exception as e:
            print(f"❌ DeepSeek API 调用失败: {e}")
            return ""

    def _extract_diff(self, response: str) -> str:
        """从 LLM 回复中提取 diff."""
        import re
        # ```diff ... ```
        m = re.search(r'```diff\s*\n(.*?)\n```', response, re.DOTALL)
        if m:
            return m.group(1).strip()
        # ``` ... ``` (可能包含 diff)
        m = re.search(r'```\s*\n(.*?)\n```', response, re.DOTALL)
        if m:
            body = m.group(1)
            if '--- ' in body and '+++ ' in body:
                return body.strip()
        # 纯文本中找 diff
        if '--- ' in response and '+++ ' in response:
            return response.strip()
        return response.strip()  # fallback

    def _read_files(self, files: list[str]) -> str:
        """读取指定文件的内容（用于注入 prompt）."""
        parts = []
        for f in files:
            p = Path(self.project_root) / f
            if p.exists():
                content = p.read_text(encoding="utf-8", errors="replace")
                # 截断大文件
                if len(content) > 4000:
                    content = content[:4000] + "\n... (truncated)"
                parts.append(f"### {f}\n```\n{content}\n```")
            else:
                parts.append(f"### {f}\n(文件不存在，需新建)")
        return "\n\n".join(parts)
