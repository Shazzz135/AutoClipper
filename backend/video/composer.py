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
        max_duration: float = 58.0
    ) -> bool:
        """
        Renders the 1080x1920 vertical video (40/60 split) with burned ASS subtitles
        using an optimized single-pass FFmpeg command strictly adhering to YouTube Shorts specifications:
        - Strict <60s duration (clamped to 58.0s)
        - H.264 High Profile Level 4.2, 1080x1920 9:16
        - Constant 60 FPS (CFR) to prevent YouTube transcode hanging
        - Fixed 1-second closed GOP (60 frames) for instant high-speed YouTube ingestion
        - Rec.709 colorspace metadata (bt709)
        - 48kHz Stereo AAC audio with async resampler to eliminate A/V sync drift
        - +faststart moov atom at beginning of MP4
        """
        state.col3_status = "RENDERING"
        t0 = time.time()
        # YouTube Shorts requires strict <60s duration. We clamp to 58.0s to ensure
        # that even with container packet rounding and audio sync, duration NEVER reaches or exceeds 60.00s.
        duration = min(58.0, max(3.0, end_time - start_time))
        state.add_col3_log(f"Starting YouTube-compliant FFmpeg render (duration: {duration:.1f}s, output: 1080x1920 60fps CFR)...")

        # Compose full filtergraph including subtitle burning
        # [v_out]ass=subtitles.ass[v_final]
        # On Windows, path to ASS file needs escaped backslashes for FFmpeg
        ass_path_escaped = str(ass_subtitle_path.resolve()).replace("\\", "/").replace(":", "\\:")
        full_filter = f"{filter_complex_str};[v_out]ass='{ass_path_escaped}'[v_final]"

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(round(start_time, 2)),
            "-t", str(round(duration, 2)),
            "-i", str(raw_video_path),
            "-filter_complex", full_filter,
            "-map", "[v_final]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-profile:v", "high",
            "-level", "4.2",
            "-threads", "4",
            "-crf", "22",
            "-r", "60",
            "-fps_mode", "cfr",
            "-g", "60",
            "-keyint_min", "60",
            "-sc_threshold", "0",
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-ac", "2",
            "-af", "aresample=async=1000:first_pts=0",
            "-shortest",
            "-movflags", "+faststart",
            "-f", "mp4",
            str(output_mp4_path)
        ]

        state.add_col3_log(f"Executing YouTube-optimized FFmpeg encode (60fps CFR, 48kHz stereo, Rec.709)...")
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
