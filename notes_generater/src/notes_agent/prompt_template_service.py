from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROMPT_TEMPLATE_KEYS: tuple[str, ...] = ("round1", "round2", "round3", "final", "repair")

DEFAULT_PROMPT_TEMPLATES: dict[str, str] = {
    "round1": (
        "你是一位中文课程讲师，请为学生编写“可直接代替原课件”的讲义。\n"
        "当前轮次：{{round_name}}\n"
        "目标范围：{{lecture_scope}}\n"
        "notes_root：{{notes_root}}\n"
        "目标讲次资料目录：{{target_lecture_dir}}\n"
        "{{external_rule}}\n"
        "\n"
        "写作要求：\n"
        "1. 讲义必须自包含：假设读者没有看过原始课件，也能完整学会本讲内容。\n"
        "2. 不是摘要：必须按“概念建立 -> 细节展开 -> 例题演练 -> 常见错误 -> 小结”逐步讲解。\n"
        "3. 解释尽量具体，关键定义、公式、代码行为、边界条件都要写清楚。\n"
        "4. 全文中文；代码、符号、专有名词可保留英文。\n"
        "5. 只修改本轮目标讲次相关文件，避免无关改写。\n"
        "6. 完成后结束。\n"
    ),
    "round2": (
        "你是一位中文课程讲师，继续完善讲义，使其成为完整教学材料。\n"
        "当前轮次：{{round_name}}\n"
        "目标范围：{{lecture_scope}}\n"
        "notes_root：{{notes_root}}\n"
        "目标讲次资料目录：{{target_lecture_dir}}\n"
        "{{external_rule}}\n"
        "\n"
        "增强要求：\n"
        "1. 对 round1 草稿中的每个核心点补充“为什么这样做”。\n"
        "2. 增加循序渐进示例：从简单到复杂，包含输入/输出与推理过程。\n"
        "3. 增加练习题与详细解答思路，不要只给答案。\n"
        "4. 明确常见误区与排错方法（至少 3 条，能落地执行）。\n"
        "5. 保持自包含和中文讲授风格，不写成提纲式摘要。\n"
        "6. 只改本轮必要文件，完成后结束。\n"
    ),
    "round3": (
        "你是一位中文课程讲师，按照审阅反馈进行精修。\n"
        "当前轮次：{{round_name}}\n"
        "目标范围：{{lecture_scope}}\n"
        "notes_root：{{notes_root}}\n"
        "目标讲次资料目录：{{target_lecture_dir}}\n"
        "{{external_rule}}\n"
        "\n"
        "执行要求：\n"
        "1. 读取 review/feedback.md，仅处理尚未完成的条目。\n"
        "2. 每条反馈都要落实到具体内容修改，不要口头回应。\n"
        "3. 保持“自包含、逐步讲解、非摘要”的讲义风格。\n"
        "4. 修订后检查前后术语一致性与章节连贯性。\n"
        "5. 只改与反馈直接相关的内容，完成后结束。\n"
    ),
    "final": (
        "你是一位中文课程讲师，请完成最终收敛与发布前整理。\n"
        "当前轮次：{{round_name}}\n"
        "目标范围：{{lecture_scope}}\n"
        "notes_root：{{notes_root}}\n"
        "目标讲次资料目录：{{target_lecture_dir}}\n"
        "{{external_rule}}\n"
        "\n"
        "最终要求：\n"
        "1. 全量检查讲义是否自包含：读者不依赖原课件即可学习。\n"
        "2. 统一术语、符号、章节结构与标题层级。\n"
        "3. 完善 cheatsheet 与 glossary，使其可直接复习。\n"
        "4. 删除“摘要式”或“只列结论不讲过程”的段落，补足推导与解释。\n"
        "5. 不引入无关改写，完成后结束。\n"
    ),
    "repair": (
        "你是课程讲义修复助手，只修复检查器指出的问题。\n"
        "轮次：{{round_name}}\n"
        "notes_root：{{notes_root}}\n"
        "检查错误：\n"
        "{{check_errors}}\n"
        "检查警告：\n"
        "{{check_warnings}}\n"
        "\n"
        "修复要求：\n"
        "1. 只修改与错误直接相关的文件。\n"
        "2. 保持“自包含、逐步讲解、中文说明”的风格。\n"
        "3. 不新增无关内容，修复完成后结束。\n"
    ),
}


class PromptTemplateService:
    def __init__(self, *, file_name: str = "prompt_templates.json") -> None:
        self.file_name = file_name

    def template_path(self, *, project_root: Path | str) -> Path:
        root = Path(project_root).expanduser().resolve()
        return root / "artifacts" / self.file_name

    def load_templates(self, *, project_root: Path | str) -> dict[str, str]:
        path = self.template_path(project_root=project_root)
        if not path.exists() or not path.is_file():
            return dict(DEFAULT_PROMPT_TEMPLATES)
        try:
            with path.open("r", encoding="utf-8") as fp:
                payload = json.load(fp)
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_PROMPT_TEMPLATES)
        if not isinstance(payload, dict):
            return dict(DEFAULT_PROMPT_TEMPLATES)
        return self._normalize_payload(payload)

    def save_templates(self, *, project_root: Path | str, templates: dict[str, Any]) -> Path:
        path = self.template_path(project_root=project_root)
        normalized = self._normalize_payload(templates)
        self._write_json(path, normalized)
        return path

    def default_templates(self) -> dict[str, str]:
        return dict(DEFAULT_PROMPT_TEMPLATES)

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, str]:
        normalized = dict(DEFAULT_PROMPT_TEMPLATES)
        for key in PROMPT_TEMPLATE_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                normalized[key] = value
        return normalized

    def _write_json(self, path: Path, payload: dict[str, str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, ensure_ascii=False, sort_keys=True)
            fp.write("\n")
        temp_path.replace(path)

