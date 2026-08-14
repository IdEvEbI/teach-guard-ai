"""教学守护 AI 助手 · 命令行入口。"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from teach_guard import __version__
from teach_guard.extract import (
    EXIT_EXTRACT_FAILED,
    EXIT_FFMPEG_MISSING,
    ExtractError,
    FfmpegMissingError,
    extract_audio,
    existing_audio_path,
)
from teach_guard.inspect_run import (
    mark_step,
    prepare_inspect_run,
    set_artifact,
    set_prompt_version,
    update_asr,
    update_llm,
)
from teach_guard.lesson_type import (
    EXIT_LESSON_TYPE_FAILED,
    TYPE_HELP,
    LessonTypeError,
    classify_lesson_type,
    load_type_if_present,
    parse_cli_lesson_type,
)
from teach_guard.review import EXIT_REVIEW_FAILED, ReviewError, write_review
from teach_guard.checked import EXIT_CHECKED_FAILED, CheckedError, write_checked
from teach_guard.confirm import (
    EXIT_CONFIRM_FAILED,
    ConfirmError,
    load_confirm_if_present,
    write_confirm,
)
from teach_guard.llm import EXIT_LLM_CONFIG, LlmConfigError, llm_api_key
from teach_guard.paths import DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR, get_output_dir, resolve_input_file
from teach_guard.punctuate import (
    EXIT_PUNCTUATE_FAILED,
    PunctuateError,
    load_punctuate_if_present,
    punctuate_transcript,
)
from teach_guard.screen_ocr import (
    EXIT_OCR_FAILED,
    EXIT_OCR_MISSING,
    OcrError,
    OcrMissingError,
    load_screen_if_present,
    ocr_snapshots,
)
from teach_guard.snapshot import (
    EXIT_SNAPSHOT_FAILED,
    SnapshotError,
    capture_snapshots,
    existing_snapshots,
)
from teach_guard.transcribe import (
    EXIT_ASR_MISSING,
    EXIT_TRANSCRIBE_FAILED,
    AsrMissingError,
    TranscribeError,
    load_transcript_if_present,
    transcribe_audio,
)

load_dotenv()


def _ask_line(text: str) -> str:
    return str(typer.prompt(text, default="", show_default=False, prompt_suffix=""))


app = typer.Typer(
    no_args_is_help=True,
    help="教学守护 AI 助手：检查授课视频并生成报告。",
)


@app.command()
def version() -> None:
    """打印版本号。"""
    typer.echo(__version__)


@app.command()
def check() -> None:
    """检查本机是否具备后续流水线所需的基础环境。"""
    python_ok = sys.version_info >= (3, 12)
    ffmpeg_path = shutil.which("ffmpeg")
    try:
        import mlx_whisper  # noqa: F401
    except ImportError:
        asr_ok = False
    else:
        asr_ok = True
    try:
        import rapidocr  # noqa: F401
    except ImportError:
        ocr_ok = False
    else:
        ocr_ok = True
    key_ok = bool(llm_api_key())

    typer.echo(f"Python {sys.version.split()[0]} （要求 >= 3.12）：{'通过' if python_ok else '未通过'}")
    typer.echo(
        f"ffmpeg：{'已找到 ' + ffmpeg_path if ffmpeg_path else '未找到（单视频抽轨时需要，可用 brew install ffmpeg 安装）'}"
    )
    typer.echo(
        "mlx-whisper："
        + ("已安装" if asr_ok else "未安装（转写需要，可用 uv sync --group asr 安装）")
    )
    typer.echo(
        "RapidOCR："
        + ("已安装" if ocr_ok else "未安装（画面词表需要，可用 uv sync --group ocr 安装）")
    )
    typer.echo(
        "LLM_API_KEY："
        + ("已设置" if key_ok else "未设置（确认与建议报告需要，请复制 .env.example 为 .env 并填写）")
    )

    if not python_ok:
        raise typer.Exit(code=1)


@app.command()
def inspect(
    source: Annotated[
        Path,
        typer.Argument(
            help=f"视频或音频文件。相对路径会先看当前目录，再看 {DEFAULT_INPUT_DIR}/。",
        ),
    ],
    output_root: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=f"产物根目录，默认 {DEFAULT_OUTPUT_DIR}/。",
        ),
    ] = None,
    lesson_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            help=TYPE_HELP,
        ),
    ] = None,
    want_punctuate: Annotated[
        bool,
        typer.Option(
            "--punctuate",
            help="额外写出标点稿。默认跳过；课型与报告使用原始逐字稿。",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            help="确认步骤不逐条提问，按草稿自动接受（测试与非交互使用）。",
        ),
    ] = False,
) -> None:
    """为单个视频抽轨、转写、截图、识别画面词，确认后再写出建议报告。"""
    override: str | None = None
    if lesson_type:
        try:
            override = parse_cli_lesson_type(lesson_type)
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

    try:
        resolved = resolve_input_file(source)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    prep = prepare_inspect_run(resolved, output_root or get_output_dir())
    run_dir = prep.run_dir
    stem = resolved.stem
    typer.echo(f"已创建运行目录：{run_dir}" if not prep.reused else f"复用运行目录：{run_dir}")
    typer.echo(f"运行清单：{run_dir / 'manifest.json'}")

    existing_audio = existing_audio_path(run_dir, stem) if prep.reused else None
    if existing_audio is not None:
        extracted_audio = existing_audio
        set_artifact(run_dir, "audio", extracted_audio)
        mark_step(run_dir, "extract_audio", "skipped")
        typer.echo(f"已有音轨，跳过抽轨：{extracted_audio}")
    else:
        typer.echo("正在抽轨…")
        try:
            extracted = extract_audio(resolved, run_dir)
        except FfmpegMissingError as exc:
            mark_step(run_dir, "extract_audio", "failed", error=str(exc))
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_FFMPEG_MISSING) from exc
        except ExtractError as exc:
            mark_step(run_dir, "extract_audio", "failed", error=str(exc))
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_EXTRACT_FAILED) from exc

        extracted_audio = extracted.audio_path
        extract_skipped = extracted.skipped
        set_artifact(run_dir, "audio", extracted_audio)
        mark_step(run_dir, "extract_audio", "skipped" if extract_skipped else "done")
        if extract_skipped:
            typer.echo(f"输入已是音频，已跳过抽轨：{extracted_audio}")
        else:
            typer.echo(f"已抽出音轨：{extracted_audio}")

    existing_transcript = load_transcript_if_present(run_dir, stem) if prep.reused else None
    if existing_transcript is not None:
        transcript = existing_transcript
        set_artifact(run_dir, "transcript_raw_md", transcript.markdown_path)
        set_artifact(run_dir, "transcript_raw_json", transcript.json_path)
        mark_step(run_dir, "transcribe", "skipped")
        update_asr(run_dir, status="done", repo=transcript.model)
        typer.echo(f"已有原始逐字稿，跳过转写：{transcript.markdown_path}")
    else:
        typer.echo("正在转写（原始逐字稿，不补标点）…")
        try:
            transcript = transcribe_audio(extracted_audio, run_dir, stem)
        except AsrMissingError as exc:
            mark_step(run_dir, "transcribe", "failed", error=str(exc))
            update_asr(run_dir, status="failed")
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_ASR_MISSING) from exc
        except TranscribeError as exc:
            mark_step(run_dir, "transcribe", "failed", error=str(exc))
            update_asr(run_dir, status="failed")
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_TRANSCRIBE_FAILED) from exc

        set_artifact(run_dir, "transcript_raw_md", transcript.markdown_path)
        set_artifact(run_dir, "transcript_raw_json", transcript.json_path)
        mark_step(run_dir, "transcribe", "done")
        update_asr(run_dir, status="done", repo=transcript.model)
        typer.echo(f"已写出原始逐字稿：{transcript.markdown_path}")

    if want_punctuate:
        existing_punct = load_punctuate_if_present(run_dir, stem) if prep.reused else None
        if existing_punct is not None:
            set_artifact(run_dir, "transcript_punct_md", existing_punct.markdown_path)
            set_artifact(run_dir, "transcript_punct_json", existing_punct.json_path)
            set_prompt_version(run_dir, "punctuate", existing_punct.prompt_version)
            mark_step(run_dir, "punctuate", "skipped")
            typer.echo(f"已有标点逐字稿，跳过标点：{existing_punct.markdown_path}")
        else:
            typer.echo("正在补标点（不改词）…")
            try:
                punctuated = punctuate_transcript(
                    transcript.json_path,
                    run_dir,
                    stem,
                    on_batch=lambda index, total: typer.echo(f"标点批次 {index}/{total}…"),
                )
            except LlmConfigError as exc:
                mark_step(run_dir, "punctuate", "failed", error=str(exc))
                update_llm(run_dir, status="failed")
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=EXIT_LLM_CONFIG) from exc
            except PunctuateError as exc:
                mark_step(run_dir, "punctuate", "failed", error=str(exc))
                update_llm(run_dir, status="failed")
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=EXIT_PUNCTUATE_FAILED) from exc

            set_artifact(run_dir, "transcript_punct_md", punctuated.markdown_path)
            set_artifact(run_dir, "transcript_punct_json", punctuated.json_path)
            set_prompt_version(run_dir, "punctuate", punctuated.prompt_version)
            mark_step(run_dir, "punctuate", "done")
            update_llm(
                run_dir,
                status="done",
                provider=os.environ.get("LLM_PROVIDER", "deepseek").strip() or "deepseek",
                model=punctuated.model,
            )
            typer.echo(f"已写出标点逐字稿：{punctuated.markdown_path}")
    else:
        mark_step(run_dir, "punctuate", "skipped")
        typer.echo("默认跳过标点；课型与报告使用原始逐字稿。可用 --punctuate 打开。")

    existing_shots = existing_snapshots(run_dir) if prep.reused else None
    if existing_shots is not None:
        shots = existing_shots
        set_artifact(run_dir, "snapshot_dir", shots.directory)
        mark_step(run_dir, "snapshot", "skipped")
        typer.echo(f"已有截图，跳过抽帧：{shots.directory}（{len(shots.frames)} 张）")
    else:
        typer.echo("正在按 10 秒间隔截图…")
        try:
            shots = capture_snapshots(resolved, run_dir)
        except FfmpegMissingError as exc:
            mark_step(run_dir, "snapshot", "failed", error=str(exc))
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_FFMPEG_MISSING) from exc
        except SnapshotError as exc:
            mark_step(run_dir, "snapshot", "failed", error=str(exc))
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_SNAPSHOT_FAILED) from exc
        set_artifact(run_dir, "snapshot_dir", shots.directory)
        mark_step(run_dir, "snapshot", "skipped" if shots.skipped else "done")
        if shots.skipped:
            typer.echo(f"输入已是音频，已跳过截图：{shots.directory}")
        else:
            typer.echo(f"已写出截图：{shots.directory}（{len(shots.frames)} 张）")

    existing_screen = (
        load_screen_if_present(run_dir, stem) if prep.reused and existing_shots is not None else None
    )
    if existing_screen is not None:
        screen = existing_screen
        set_artifact(run_dir, "screen_md", screen.markdown_path)
        set_artifact(run_dir, "screen_json", screen.json_path)
        mark_step(run_dir, "screen_ocr", "skipped")
        typer.echo(f"已有画面词表，跳过识别：{screen.markdown_path}")
    else:
        typer.echo("正在识别画面文字（RapidOCR）…")
        try:
            screen = ocr_snapshots(shots.frames, run_dir, stem)
        except OcrMissingError as exc:
            mark_step(run_dir, "screen_ocr", "failed", error=str(exc))
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_OCR_MISSING) from exc
        except OcrError as exc:
            mark_step(run_dir, "screen_ocr", "failed", error=str(exc))
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_OCR_FAILED) from exc
        set_artifact(run_dir, "screen_md", screen.markdown_path)
        set_artifact(run_dir, "screen_json", screen.json_path)
        mark_step(run_dir, "screen_ocr", "done")
        typer.echo(f"已写出画面词表：{screen.markdown_path}（{screen.frame_count} 帧）")

    existing_type = load_type_if_present(run_dir, stem) if prep.reused and override is None else None
    if existing_type is not None:
        typed = existing_type
        set_artifact(run_dir, "lesson_type_md", typed.markdown_path)
        set_artifact(run_dir, "lesson_type_json", typed.json_path)
        set_prompt_version(run_dir, "pedagogy_type", typed.prompt_version)
        mark_step(run_dir, "lesson_type", "skipped")
        typer.echo(f"已有课型判定，跳过识别：{typed.markdown_path}（`{typed.lesson_type}`）")
    else:
        typer.echo("正在识别课型…" if override is None else f"使用命令行覆盖课型：{override}")
        try:
            typed = classify_lesson_type(
                transcript.json_path,
                run_dir,
                stem,
                source_name=resolved.name,
                override=override,
            )
        except LlmConfigError as exc:
            mark_step(run_dir, "lesson_type", "failed", error=str(exc))
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_LLM_CONFIG) from exc
        except LessonTypeError as exc:
            mark_step(run_dir, "lesson_type", "failed", error=str(exc))
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_LESSON_TYPE_FAILED) from exc

        set_artifact(run_dir, "lesson_type_md", typed.markdown_path)
        set_artifact(run_dir, "lesson_type_json", typed.json_path)
        set_prompt_version(run_dir, "pedagogy_type", typed.prompt_version)
        mark_step(run_dir, "lesson_type", "done")
        typer.echo(f"已写出课型判定：{typed.markdown_path}（`{typed.lesson_type}`）")

    existing_confirm = load_confirm_if_present(run_dir, stem) if prep.reused else None
    if existing_confirm is not None:
        confirmed = existing_confirm
        set_artifact(run_dir, "confirm_md", confirmed.markdown_path)
        set_artifact(run_dir, "confirm_json", confirmed.json_path)
        set_prompt_version(run_dir, "confirm", confirmed.prompt_version)
        mark_step(run_dir, "confirm", "skipped")
        typer.echo(f"已有确认记录，跳过提问：{confirmed.markdown_path}")
    else:
        typer.echo("正在准备确认项…" if yes else "请逐条确认（稿上用词与开场三项）…")
        try:
            segments = json.loads(transcript.json_path.read_text(encoding="utf-8")).get("segments") or []
            screen_payload = json.loads(screen.json_path.read_text(encoding="utf-8"))
            confirmed = write_confirm(
                run_dir,
                stem,
                source_name=resolved.name,
                lesson_type=typed.lesson_type,
                segments=list(segments),
                screen=screen_payload if isinstance(screen_payload, dict) else None,
                auto=yes,
                ask=None if yes else _ask_line,
            )
        except LlmConfigError as exc:
            mark_step(run_dir, "confirm", "failed", error=str(exc))
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_LLM_CONFIG) from exc
        except ConfirmError as exc:
            mark_step(run_dir, "confirm", "failed", error=str(exc))
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=EXIT_CONFIRM_FAILED) from exc
        set_artifact(run_dir, "confirm_md", confirmed.markdown_path)
        set_artifact(run_dir, "confirm_json", confirmed.json_path)
        set_prompt_version(run_dir, "confirm", confirmed.prompt_version)
        mark_step(run_dir, "confirm", "done")
        typer.echo(f"已写出确认记录：{confirmed.markdown_path}")

    typer.echo("正在按确认记录写出确认逐字稿…")
    try:
        checked = write_checked(transcript.json_path, confirmed.json_path, run_dir, stem)
    except CheckedError as exc:
        mark_step(run_dir, "checked", "failed", error=str(exc))
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=EXIT_CHECKED_FAILED) from exc
    set_artifact(run_dir, "transcript_checked_md", checked.markdown_path)
    set_artifact(run_dir, "transcript_checked_json", checked.json_path)
    mark_step(run_dir, "checked", "done")
    typer.echo(f"已写出确认逐字稿：{checked.markdown_path}（替换 {checked.applied_count} 处）")

    typer.echo("正在写建议报告…")
    try:
        reviewed = write_review(
            checked.json_path,
            typed.json_path,
            run_dir,
            stem,
            source_name=resolved.name,
            confirm_json_path=confirmed.json_path,
        )
    except LlmConfigError as exc:
        mark_step(run_dir, "review", "failed", error=str(exc))
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=EXIT_LLM_CONFIG) from exc
    except ReviewError as exc:
        mark_step(run_dir, "review", "failed", error=str(exc))
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=EXIT_REVIEW_FAILED) from exc

    set_artifact(run_dir, "report_md", reviewed.markdown_path)
    set_artifact(run_dir, "report_json", reviewed.json_path)
    set_prompt_version(run_dir, "review", reviewed.prompt_version)
    mark_step(run_dir, "review", "done")
    typer.echo(f"已写出建议报告：{reviewed.markdown_path}")
