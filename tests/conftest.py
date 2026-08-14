"""CLI 测试共用：默认 stub 转写与标点，避免拉起真实模型。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from teach_guard.lesson_type import LessonTypeResult
from teach_guard.punctuate import PunctuateResult
from teach_guard.review import ReviewResult
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


@pytest.fixture(autouse=True)
def stub_lesson_type(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("no_stub_lesson_type"):
        return

    def fake(
        punct_json_path: Path,
        run_dir: Path,
        stem: str,
        *,
        source_name: str,
        override: str | None = None,
        **_kwargs: object,
    ) -> LessonTypeResult:
        del punct_json_path
        lesson_type = override or "intro"
        json_path = run_dir / f"{stem}.type.json"
        markdown_path = run_dir / f"{stem}.type.md"
        payload = {
            "lesson_type": lesson_type,
            "confidence": "high",
            "delivery": "stub",
            "overridden": override is not None,
            "filename": source_name,
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        markdown_path.write_text(f"# 课型判定\n\n- 主类型：`{lesson_type}`\n", encoding="utf-8")
        return LessonTypeResult(
            markdown_path=markdown_path,
            json_path=json_path,
            lesson_type=lesson_type,
            prompt_version="stub",
            model="stub-llm",
            overridden=override is not None,
        )

    monkeypatch.setattr("teach_guard.cli.classify_lesson_type", fake)


@pytest.fixture(autouse=True)
def stub_review(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("no_stub_review"):
        return

    def fake(
        punct_json_path: Path,
        type_json_path: Path,
        run_dir: Path,
        stem: str,
        *,
        source_name: str,
        **_kwargs: object,
    ) -> ReviewResult:
        del punct_json_path, source_name
        lesson_type = "intro"
        if type_json_path.is_file():
            try:
                lesson_type = str(json.loads(type_json_path.read_text(encoding="utf-8")).get("lesson_type") or "intro")
            except json.JSONDecodeError:
                lesson_type = "intro"
        json_path = run_dir / f"{stem}.report.json"
        markdown_path = run_dir / f"{stem}.report.md"
        payload = {
            "lesson_type": lesson_type,
            "summary": "stub",
            "must_fix": [],
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        markdown_path.write_text("# 精查报告\n\nstub\n", encoding="utf-8")
        return ReviewResult(
            markdown_path=markdown_path,
            json_path=json_path,
            prompt_version="stub",
            model="stub-llm",
        )

    monkeypatch.setattr("teach_guard.cli.write_review", fake)
