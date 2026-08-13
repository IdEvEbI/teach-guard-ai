"""单视频 inspect 的运行目录与清单骨架。"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from teach_guard import __version__

SCHEMA_VERSION = 1
HASH_PREFIX_LEN = 12
ASR_ENGINE = "mlx-whisper"
ASR_SIZE = "large-v3-turbo"
LLM_PROVIDER = "deepseek"

PIPELINE_STEPS = (
    "extract_audio",
    "transcribe",
    "punctuate",
    "lesson_type",
    "review",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_stem(path: Path) -> str:
    stem = path.stem.strip() or "input"
    cleaned = re.sub(r"[^\w.\-]+", "_", stem, flags=re.UNICODE).strip("._")
    return (cleaned[:80] or "input")


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


def prepare_inspect_run(source: Path, output_root: Path) -> Path:
    """创建本次 inspect 目录并写入 manifest.json，返回运行目录。"""
    digest = sha256_file(source)
    run_dir = output_root / f"{safe_stem(source)}-{digest[:HASH_PREFIX_LEN]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(build_manifest(source=source, digest=digest), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return run_dir
