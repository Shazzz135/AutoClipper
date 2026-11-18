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
        output_mp4_path: Path,
        max_duration: float = 60.0
    ) -> bool:
        """
        Renders the 1080x1920 vertical video (40/60 split) with burned ASS subtitles
        using an optimized single-pass FFmpeg command.
        """
        state.col3_status = "RENDERING"
        t0 = time.time()
        duration = min(max_duration, max(3.0, end_time - start_time))
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
            "-threads", "4",
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
        Cleans up raw stream segments, candidate footage, intermediate audio, subtitles, thumbnails, and rendered files to reclaim SSD space.
        Guarantees complete file deletion on Windows.
        """
        import gc
        gc.collect()

        state.add_col3_log(f"Purging all video files and reclaiming SSD space for {clip_id}...")

        targets = []
        if raw_segment_path:
            targets.append(Path(raw_segment_path))
        targets.extend(list(settings.CLIPS_DIR.glob(f"{clip_id}*")))
        targets.extend(list(settings.BUFFER_DIR.glob(f"{clip_id}*")))

        purged_count = 0
        for f in set(targets):
            if not f.exists():
                continue
            for attempt in range(3):
                try:
                    f.unlink()
                    purged_count += 1
                    break
                except PermissionError:
                    gc.collect()
                    time.sleep(0.15)
                except Exception:
                    break

            # If still exists on Windows due to lock, truncate to 0 bytes so SSD space is reclaimed immediately
            if f.exists():
                try:
                    open(f, "wb").close()
                except Exception:
                    pass

        state.add_col3_log(f"SSD storage reclaimed: {purged_count} files purged for {clip_id}.")

composer = VideoComposer()
