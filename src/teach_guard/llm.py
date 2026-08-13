"""DeepSeek（OpenAI 兼容）调用。密钥只从环境读取，不写入日志。"""

from __future__ import annotations

import json
import os
import re
from typing import Any

DEFAULT_LLM_BASE_URL = "https://api.deepseek.com"
DEFAULT_LLM_MODEL = "deepseek-v4-flash"

EXIT_LLM_CONFIG = 6


class LlmConfigError(RuntimeError):
    pass


def llm_api_key() -> str:
    return os.environ.get("LLM_API_KEY", "").strip()


def llm_base_url() -> str:
    return os.environ.get("LLM_BASE_URL", DEFAULT_LLM_BASE_URL).strip() or DEFAULT_LLM_BASE_URL


def llm_model() -> str:
    return os.environ.get("LLM_MODEL", DEFAULT_LLM_MODEL).strip() or DEFAULT_LLM_MODEL


def llm_provider() -> str:
    return os.environ.get("LLM_PROVIDER", "deepseek").strip() or "deepseek"


def require_api_key() -> str:
    key = llm_api_key()
    if not key:
        raise LlmConfigError("未设置 LLM_API_KEY（请复制 .env.example 为 .env 并填写 DeepSeek 密钥）")
    return key


def _strip_fences(content: str) -> str:
    text = content.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _friendly_llm_error(exc: BaseException) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    lowered = detail.lower()
    if "socksio" in lowered or "socks proxy" in lowered:
        return (
            "调用大模型失败：当前环境使用了 SOCKS 代理，但未安装 httpx 的 socks 支持。"
            "请执行 uv sync --group asr 后重试（依赖组已包含 httpx[socks]）。"
        )
    if "401" in detail or "authentication" in lowered or "invalid api key" in lowered:
        return "调用大模型失败：密钥无效或未授权，请检查 .env 中的 LLM_API_KEY。"
    return f"调用大模型失败：{detail}"


def chat_json(*, system: str, user: str) -> dict[str, Any]:
    """发送 system + user，解析模型返回的 JSON 对象。"""
    api_key = require_api_key()
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LlmConfigError("未安装 openai 包（请执行 uv sync 后重试）") from exc

    client = OpenAI(api_key=api_key, base_url=llm_base_url(), timeout=120.0)
    try:
        response = client.chat.completions.create(
            model=llm_model(),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except LlmConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 — 转成不带密钥的中文错误
        raise RuntimeError(_friendly_llm_error(exc)) from exc

    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("调用大模型失败：返回内容为空。")
    try:
        parsed = json.loads(_strip_fences(content))
    except json.JSONDecodeError as exc:
        raise RuntimeError("调用大模型失败：返回内容不是合法 JSON。") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("调用大模型失败：返回内容不是 JSON 对象。")
    return parsed
