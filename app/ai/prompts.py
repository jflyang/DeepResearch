"""Prompt 模板管理 - 从文件加载并渲染变量。"""

from pathlib import Path
from typing import Any

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateNotFound,
    UndefinedError,
)

_DEFAULT_TEMPLATE_DIR = Path("config/prompt_templates")


class PromptTemplateNotFound(Exception):
    """模板文件不存在。"""

    def __init__(self, task_name: str, language: str) -> None:
        self.task_name = task_name
        self.language = language
        self.template_name = f"{task_name}.{language}.md"
        super().__init__(f"Prompt template not found: {self.template_name}")


class PromptRenderError(Exception):
    """模板渲染失败（变量缺失等）。"""

    def __init__(self, template_name: str, detail: str) -> None:
        self.template_name = template_name
        self.detail = detail
        super().__init__(f"Render error in '{template_name}': {detail}")


class PromptStore:
    """加载和渲染 prompt 模板。"""

    def __init__(self, template_dir: Path | None = None) -> None:
        self._dir = template_dir or _DEFAULT_TEMPLATE_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self._dir)),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )

    def get_template_path(self, task_name: str, language: str) -> Path:
        """返回模板文件的完整路径。"""
        return self._dir / f"{task_name}.{language}.md"

    def render(self, task_name: str, language: str, payload: dict[str, Any]) -> str:
        """渲染指定模板，返回最终 prompt 文本。"""
        template_name = f"{task_name}.{language}.md"
        try:
            tpl = self._env.get_template(template_name)
        except TemplateNotFound:
            raise PromptTemplateNotFound(task_name, language)
        try:
            return tpl.render(**payload)
        except UndefinedError as e:
            raise PromptRenderError(template_name, str(e))
