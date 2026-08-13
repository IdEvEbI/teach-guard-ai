"""教学守护 AI 助手 · 命令行入口。"""

from __future__ import annotations

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
    LessonTypeError,
    classify_lesson_type,
    parse_cli_lesson_type,
)
from teach_guard.llm import EXIT_LLM_CONFIG, LlmConfigError, llm_api_key
from teach_guard.paths import DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR, get_output_dir, resolve_input_file
from teach_guard.punctuate import (
    EXIT_PUNCTUATE_FAILED,
    PunctuateError,
    load_punctuate_if_present,
    punctuate_transcript,
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
    key_ok = bool(llm_api_key())

    typer.echo(f"Python {sys.version.split()[0]} （要求 >= 3.12）：{'通过' if python_ok else '未通过'}")
    typer.echo(
        f"ffmpeg：{'已找到 ' + ffmpeg_path if ffmpeg_path else '未找到（单视频抽轨时需要，可用 brew install ffmpeg 安装）'}"
    )
    typer.echo(
        "mlx-whisper："
        + ("已安装" if asr_ok else "未安装（转写需要，可用 uv sync --group asr 安装）")
    )
    typer.echo("LLM_API_KEY：" + ("已设置" if key_ok else "未设置（标点需要，请复制 .env.example 为 .env 并填写）"))

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
            help=(
                "覆盖课型。取值：intro / practice / syntax / case / principle / "
                "project / stage_first / other。"
            ),
        ),
    ] = None,
) -> None:
    """为单个视频抽轨、转写、补标点，并识别课型。建议报告尚未实现。"""
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

    existing_punct = load_punctuate_if_present(run_dir, stem) if prep.reused else None
    if existing_punct is not None:
        punctuated = existing_punct
        set_artifact(run_dir, "transcript_punct_md", punctuated.markdown_path)
        set_artifact(run_dir, "transcript_punct_json", punctuated.json_path)
        set_prompt_version(run_dir, "punctuate", punctuated.prompt_version)
        mark_step(run_dir, "punctuate", "skipped")
        update_llm(
            run_dir,
            status="done",
            provider=os.environ.get("LLM_PROVIDER", "deepseek").strip() or "deepseek",
            model=punctuated.model,
        )
        typer.echo(f"已有标点逐字稿，跳过标点：{punctuated.markdown_path}")
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

    typer.echo("正在识别课型…" if override is None else f"使用命令行覆盖课型：{override}")
    try:
        typed = classify_lesson_type(
            punctuated.json_path,
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
    typer.echo("后续步骤（建议报告）尚未实现。")
