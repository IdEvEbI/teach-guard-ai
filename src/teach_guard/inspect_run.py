"""单视频 inspect 的运行目录与清单骨架。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from teach_guard import __version__
from teach_guard.paths import get_input_dir, output_run_dir

SCHEMA_VERSION = 1
ASR_ENGINE = "mlx-whisper"
ASR_SIZE = "large-v3-turbo"
LLM_PROVIDER = "deepseek"

PIPELINE_STEPS = (
    "extract_audio",
    "transcribe",
    "punctuate",
    "snapshot",
    "screen_ocr",
    "lesson_type",
    "confirm",
    "review",
)


@dataclass(frozen=True)
class InspectPrep:
    run_dir: Path
    reused: bool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(*, source: Path, digest: str) -> dict[str, Any]:
    resolved = source.resolve()
    return {
        "schema_version": SCHEMA_VERSION,
        "cli_version": __version__,
        "command": "inspect",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": {
            "path": str(resolved),
            "name": resolved.name,
            "bytes": resolved.stat().st_size,
            "sha256": digest,
        },
        "models": {
            "asr": {
                "engine": ASR_ENGINE,
                "size": ASR_SIZE,
                "status": "not_run",
            },
            "llm": {
                "provider": LLM_PROVIDER,
                "status": "not_run",
            },
        },
        "prompts": {"versions": {}},
        "steps": [{"id": step_id, "status": "pending"} for step_id in PIPELINE_STEPS],
        "artifacts": {},
    }


def prepare_inspect_run(
    source: Path, output_root: Path, input_root: Path | None = None
) -> InspectPrep:
    """创建或复用本次 inspect 目录。输入哈希未变时保留已有清单，避免冲掉已完成步骤。"""
    digest = sha256_file(source)
    run_dir = output_run_dir(source, output_root, input_root or get_input_dir())
    run_dir.mkdir(parents=True, exist_ok=True)
    dest = run_dir / "manifest.json"
    if dest.is_file():
        try:
            existing = json.loads(dest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        if existing.get("input", {}).get("sha256") == digest:
            return InspectPrep(run_dir=run_dir, reused=True)
    dest.write_text(
        json.dumps(build_manifest(source=source, digest=digest), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return InspectPrep(run_dir=run_dir, reused=False)


def manifest_path(run_dir: Path) -> Path:
    return run_dir / "manifest.json"


def load_manifest(run_dir: Path) -> dict[str, Any]:
    return json.loads(manifest_path(run_dir).read_text(encoding="utf-8"))


def save_manifest(run_dir: Path, data: dict[str, Any]) -> None:
    manifest_path(run_dir).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def mark_step(run_dir: Path, step_id: str, status: str, *, error: str | None = None) -> None:
    data = load_manifest(run_dir)
    for step in data["steps"]:
        if step["id"] == step_id:
            step["status"] = status
            if error:
                step["error"] = error
            else:
                step.pop("error", None)
            save_manifest(run_dir, data)
            return
    data.setdefault("steps", []).append(
        {"id": step_id, "status": status, **({"error": error} if error else {})}
    )
    save_manifest(run_dir, data)


def set_artifact(run_dir: Path, name: str, path: Path) -> None:
    data = load_manifest(run_dir)
    data.setdefault("artifacts", {})[name] = str(path.resolve())
    save_manifest(run_dir, data)


def update_asr(run_dir: Path, *, status: str, repo: str | None = None) -> None:
    data = load_manifest(run_dir)
    asr = data.setdefault("models", {}).setdefault("asr", {})
    asr["status"] = status
    if repo:
        asr["repo"] = repo
    save_manifest(run_dir, data)


def update_llm(
    run_dir: Path,
    *,
    status: str,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    data = load_manifest(run_dir)
    llm = data.setdefault("models", {}).setdefault("llm", {})
    llm["status"] = status
    if provider:
        llm["provider"] = provider
    if model:
        llm["model"] = model
    save_manifest(run_dir, data)


def set_prompt_version(run_dir: Path, name: str, version: str) -> None:
    data = load_manifest(run_dir)
    versions = data.setdefault("prompts", {}).setdefault("versions", {})
    versions[name] = version
    save_manifest(run_dir, data)
