"""ffmpeg-based frame + audio extraction -- the technique behind the popular Claude
/watch skill (bradautomates/claude-video): sample auto-scaled, timestamped JPEG frames
so a multimodal model can "watch" a video it can't ingest whole.

Used two ways here:
- Pipeline fallback: videos over Gemini's ~19MB inline limit are sent as sampled
  frames + a mono audio track instead of being rejected.
- MCP tool: extract_video_frames lets an MCP client (e.g. Claude) Read the frames
  itself, frame by frame, exactly like /watch does.
"""

import json
import logging
import subprocess
from pathlib import Path

from .config import DATA_DIR

log = logging.getLogger(__name__)

FRAMES_DIR = DATA_DIR / "frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)


def video_duration_s(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def frame_budget(duration_s: float) -> int:
    """Auto-scale frame count by length, same ladder as /watch: ~1fps for a short
    reel, capped at 100 frames so token cost stays bounded."""
    if duration_s <= 30:
        return max(1, round(duration_s))
    if duration_s <= 60:
        return 40
    if duration_s <= 180:
        return 60
    if duration_s <= 600:
        return 80
    return 100


def extract_frames(video: Path, out_dir: Path | None = None) -> list[Path]:
    """Uniformly sample timestamped JPEGs (512px wide) across the video.

    Filenames carry the timestamp (tMM-SS_NNNN.jpg) so frames can be aligned with
    the audio/transcript without guessing offsets -- the /watch convention.
    """
    duration = video_duration_s(video)
    n = frame_budget(duration)
    out = out_dir or (FRAMES_DIR / video.stem)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.jpg"):
        old.unlink()
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(video),
            "-vf", f"fps={n / max(duration, 1)},scale=512:-2",
            "-q:v", "4", str(out / "frame_%04d.jpg"),
        ],
        check=True,
    )
    raw = sorted(out.glob("frame_*.jpg"))
    interval = duration / max(len(raw), 1)
    frames: list[Path] = []
    for i, f in enumerate(raw):
        t = int(i * interval)
        dest = out / f"t{t // 60:02d}-{t % 60:02d}_{i:04d}.jpg"
        f.rename(dest)
        frames.append(dest)
    log.info("Extracted %d frames from %s (%.1fs)", len(frames), video.name, duration)
    return frames


def extract_audio(video: Path, out_dir: Path | None = None) -> Path | None:
    """Strip audio to mono 16kHz mp3 (the format ASR/multimodal models like best).
    Returns None if the video has no audio track."""
    out = (out_dir or (FRAMES_DIR / video.stem)) / "audio.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(video),
             "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "64k", str(out)],
            check=True,
        )
    except subprocess.CalledProcessError:
        return None
    return out if out.exists() and out.stat().st_size > 0 else None
