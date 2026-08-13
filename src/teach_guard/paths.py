"""本地输入 / 输出目录约定。"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_INPUT_DIR = Path("data/input")
DEFAULT_OUTPUT_DIR = Path("data/output")


def get_input_dir() -> Path:
    return Path(os.environ.get("INPUT_DIR", DEFAULT_INPUT_DIR))


def get_output_dir() -> Path:
    return Path(os.environ.get("OUTPUT_DIR", DEFAULT_OUTPUT_DIR))


def resolve_input_file(source: Path, input_root: Path | None = None) -> Path:
    """解析输入文件：已存在则用该路径；相对路径再尝试默认输入目录。"""
    if source.exists():
        if source.is_file():
            return source
        raise FileNotFoundError(f"不是文件：{source}")

    tried = [source]
    if not source.is_absolute():
        nested = (input_root or get_input_dir()) / source
        tried.append(nested)
        if nested.is_file():
            return nested

    detail = "；".join(str(path) for path in tried)
    raise FileNotFoundError(f"找不到输入文件（已尝试：{detail}）")
