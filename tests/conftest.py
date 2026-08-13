"""CLI 测试共用：默认 stub 转写与标点，避免拉起真实模型。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from teach_guard.punctuate import PunctuateResult
from teach_guard.transcribe import TranscribeResult


@pytest.fixture(autouse=True)
def stub_transcribe(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("no_stub_transcribe"):
        return

    def fake(audio_path: Path, run_dir: Path, stem: str) -> TranscribeResult:
        json_path = run_dir / f"{stem}.raw.json"
        markdown_path = run_dir / f"{stem}.raw.md"
        payload = {
            "model": "stub",
            "language": "zh",
            "text": "stub",
            "segments": [{"start": 0.0, "end": 1.0, "text": "老师说 DeepSeek 8b 模型"}],
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        markdown_path.write_text("# 原始逐字稿（未补标点）\n\nstub\n", encoding="utf-8")
        return TranscribeResult(markdown_path=markdown_path, json_path=json_path, model="stub")

    monkeypatch.setattr("teach_guard.cli.transcribe_audio", fake)


@pytest.fixture(autouse=True)
def stub_punctuate(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("no_stub_punctuate"):
        return

    def fake(
        raw_json_path: Path,
        run_dir: Path,
        stem: str,
        **_kwargs: object,
    ) -> PunctuateResult:
        payload = json.loads(raw_json_path.read_text(encoding="utf-8"))
        segments = []
        for item in payload.get("segments") or []:
            text = str(item.get("text", "")).strip()
            segments.append(
                {
                    "start": float(item.get("start", 0)),
                    "end": float(item.get("end", 0)),
                    "text": text if text.endswith("。") else f"{text}。",
                    "punctuated": True,
                }
            )
        json_path = run_dir / f"{stem}.punct.json"
        markdown_path = run_dir / f"{stem}.punct.md"
        json_path.write_text(
            json.dumps({"model": "stub-llm", "segments": segments}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text("# 标点逐字稿（不改词）\n\nstub\n", encoding="utf-8")
        return PunctuateResult(
            markdown_path=markdown_path,
            json_path=json_path,
            prompt_version="stub",
            model="stub-llm",
        )

    monkeypatch.setattr("teach_guard.cli.punctuate_transcript", fake)
