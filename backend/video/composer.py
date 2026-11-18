import os
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional
from backend.core.config import settings
from backend.core.state import state

class VideoComposer:
    def render_final_vertical_clip(
        self,
        raw_video_path: Path,
        filter_complex_str: str,
        ass_subtitle_path: Path,
        start_time: float,
        end_time: float,
        output_mp4_path: Path
    ) -> bool:
        """
        Renders the final 1080x1920 vertical video (40/60 split) with burned ASS subtitles
        using an optimized single-pass FFmpeg command.
        """
        state.col3_status = "RENDERING"
        t0 = time.time()
        duration = end_time - start_time
        state.add_col3_log(f"Starting FFmpeg render (duration: {duration:.1f}s, output: 1080x1920)...")

        # Compose full filtergraph including subtitle burning
        # [v_out]ass=subtitles.ass[v_final]
        # On Windows, path to ASS file needs escaped backslashes for FFmpeg
        ass_path_escaped = str(ass_subtitle_path.resolve()).replace("\\", "/").replace(":", "\\:")
        full_filter = f"{filter_complex_str};[v_out]ass='{ass_path_escaped}'[v_final]"

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-t", str(duration),
            "-i", str(raw_video_path),
            "-filter_complex", full_filter,
            "-map", "[v_final]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_mp4_path)
        ]

        state.add_col3_log(f"Executing FFmpeg filter_complex on Snapdragon CPU...")
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

        render_duration = time.time() - t0
        state.last_render_time_sec = render_duration

        if res.returncode == 0:
            file_size_mb = round(output_mp4_path.stat().st_size / (1024 * 1024), 2)
            state.col3_status = "COMPLETED"
            state.add_col3_log(f"Render completed in {render_duration:.1f}s (Size: {file_size_mb} MB)")
            return True
        else:
            state.col3_status = "ERROR"
            state.add_col3_log(f"FFmpeg render failed. Error: {res.stderr[-200:] if res.stderr else 'Unknown'}")
            return False

    def purge_clip_artifacts(self, clip_id: str, raw_segment_path: Optional[Path] = None):
        """
        Cleans up raw stream segments, intermediate audio, and rendered files to reclaim SSD space.
        """
        state.add_col3_log(f"Auto-purging temporary artifacts for clip {clip_id}...")
        # Remove raw segment if provided
        if raw_segment_path and raw_segment_path.exists():
            try:
                raw_segment_path.unlink()
            except Exception:
                pass

        # Purge intermediate wav, ass, and mp4 files in clips_dir matching clip_id
        for f in settings.CLIPS_DIR.glob(f"{clip_id}*"):
            try:
                f.unlink()
            except Exception:
                pass

        state.add_col3_log(f"SSD storage reclaimed for {clip_id}.")

composer = VideoComposer()
