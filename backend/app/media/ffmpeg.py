"""Вызовы ffmpeg.

Создаёт MP4-превью с прогрессом, извлекает аудио в WAV и сохраняет
отдельные кадры. Все команды запускаются отдельными процессами,
а ошибки ffmpeg попадают в текст исключения.
"""

from pathlib import Path
import subprocess

from app.utils.commands import command


def make_preview_with_progress(
    source: Path,
    destination: Path,
    duration: float,
    on_progress,
) -> None:
    process = subprocess.Popen(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-v", "error",
            "-progress", "pipe:1",
            "-i", str(source),
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-map_metadata", "-1",
            "-vf",
            "scale=w='min(1280,iw)':h=-2,setsar=1",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "24",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-movflags", "+faststart",
            str(destination),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    current = {}

    assert process.stdout is not None

    for line in process.stdout:
        line = line.strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        current[key] = value

        if key == "progress" and value == "end":
            on_progress(100.0, "Превью создано")
            break

        if key == "out_time_ms":
            try:
                seconds = float(value) / 1_000_000
                percent = min(100.0, seconds / duration * 100)
                on_progress(percent, "Создаю превью")
            except ValueError:
                pass

    process.wait()

    if process.returncode:
        stderr = process.stderr.read() if process.stderr else ""
        raise RuntimeError(f"ffmpeg: {stderr[-2500:]}")

    if not destination.is_file():
        raise RuntimeError("Не удалось создать превью.")

    
def extract_audio(video: Path, destination: Path) -> None:
    command([
        "ffmpeg",
        "-nostdin",
        "-y",
        "-v", "error",
        "-i", str(video),
        "-map", "0:a:0",
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(destination),
    ])


def extract_frame(
    video: Path,
    destination: Path,
    timestamp: float,
) -> None:
    command([
        "ffmpeg",
        "-nostdin",
        "-y",
        "-v", "error",
        "-i", str(video),
        "-ss", f"{timestamp:.6f}",
        "-frames:v", "1",
        "-q:v", "3",
        str(destination),
    ])

    if not destination.is_file():
        raise RuntimeError(
            f"Не удалось извлечь кадр около {timestamp:.3f} с."
        )
