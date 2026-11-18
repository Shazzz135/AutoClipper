import asyncio
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple
from backend.core.config import settings
from backend.core.state import state

class StreamRollingBuffer:
    def __init__(self, channel: str):
        self.channel = channel.lower().lstrip("#")
        self.buffer_dir = settings.BUFFER_DIR
        self.is_running = False
        self._process = None
        self._monitor_task = None

    async def start(self):
        self.is_running = True
        self._monitor_task = asyncio.create_task(self._buffer_loop())
        state.add_col1_log(f"Stream buffer service initialized for channel {self.channel}")

    async def stop(self):
        self.is_running = False
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass
        if self._monitor_task:
            self._monitor_task.cancel()
        state.add_col1_log("Stream buffer service stopped")

    def clear_buffer(self):
        """Cleans out old segment files from previous stream."""
        for f in self.buffer_dir.glob("*.ts"):
            try:
                f.unlink()
            except Exception:
                pass
        state.buffer_size_mb = 0

    async def _buffer_loop(self):
        """Continuously records stream into rolling segments."""
        while self.is_running:
            try:
                # Clear buffer dir on fresh start
                for f in self.buffer_dir.glob("*.ts"):
                    try:
                        f.unlink()
                    except Exception:
                        pass

                stream_url = f"https://twitch.tv/{self.channel}"
                state.add_col1_log(f"Checking stream status for {stream_url} ({settings.STREAM_QUALITY})...")

                # Use streamlink to pipe stream into ffmpeg segmenter
                # -segment_wrap ensures a circular ring buffer (e.g. 150 segments * 2s = 300s = 5 mins)
                max_segments = (settings.BUFFER_MINUTES * 60) // 2
                streamlink_cmd = [
                    "streamlink",
                    "--twitch-disable-ads",
                    "--twitch-low-latency",
                    stream_url,
                    settings.STREAM_QUALITY,
                    "-O"
                ]

                segment_pattern = str(self.buffer_dir / "seg_%04d.ts")
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", "pipe:0",
                    "-c", "copy",
                    "-f", "segment",
                    "-segment_time", "2",
                    "-segment_wrap", str(max_segments),
                    segment_pattern
                ]

                # Spawn pipeline
                state.stream_online = True
                p_streamlink = subprocess.Popen(streamlink_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                p_ffmpeg = subprocess.Popen(ffmpeg_cmd, stdin=p_streamlink.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                p_streamlink.stdout.close() # Allow p_streamlink to receive SIGPIPE if p_ffmpeg exits
                self._process = p_ffmpeg

                state.add_col1_log(f"Rolling buffer active ({settings.BUFFER_MINUTES} min ring buffer)")

                # Monitor process & update buffer size
                while self.is_running and p_ffmpeg.poll() is None:
                    total_bytes = sum(f.stat().st_size for f in self.buffer_dir.glob("*.ts"))
                    state.buffer_size_mb = round(total_bytes / (1024 * 1024), 1)
                    await asyncio.sleep(2)

                state.stream_online = False
                state.add_col1_log("Stream ended or interrupted. Retrying in 10s...")
                await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                state.stream_online = False
                state.add_col1_log(f"Buffer error: {str(e)}. Retrying in 10s...")
                await asyncio.sleep(10)

    def extract_recent_segment(
        self,
        duration_sec: int,
        output_file: Path,
        peak_timestamp: Optional[float] = None,
        before_sec: float = 180.0,
        after_sec: float = 60.0
    ) -> Tuple[bool, float]:
        """
        Concatenates up to `duration_sec` (default 240s = 4 minutes: 3m before & 1m after peak)
        from the rolling buffer, anchored directly to `peak_timestamp` so the peak moment is accurately
        aligned regardless of when the user clicked Process.
        Returns (success, peak_offset_in_clip_sec).
        """
        segments = sorted(list(self.buffer_dir.glob("*.ts")), key=lambda p: p.stat().st_mtime)
        if not segments:
            return False, before_sec

        # Exclude the very last segment if it was modified within the last 0.5s (actively being written by ffmpeg)
        now_ts = time.time()
        completed_segments = [s for s in segments if (now_ts - s.stat().st_mtime) >= 0.4 and s.stat().st_size > 10000]
        if not completed_segments:
            completed_segments = segments

        # Compensate for ~4.5s chat reaction + HLS stream delay (chat reacts ~4-5s AFTER the visual event on stream)
        REACTION_DELAY_COMPENSATION_SEC = 4.5

        if peak_timestamp is not None:
            actual_event_ts = peak_timestamp - REACTION_DELAY_COMPENSATION_SEC
            win_start_ts = actual_event_ts - before_sec
            win_end_ts = actual_event_ts + after_sec
            window_segs = [s for s in completed_segments if win_start_ts <= s.stat().st_mtime <= (win_end_ts + 4.0)]
            if len(window_segs) >= 10:
                selected_segs = window_segs
            else:
                num_segs = (duration_sec // 2) + 2
                selected_segs = completed_segments[-num_segs:] if len(completed_segments) >= num_segs else completed_segments
        else:
            num_segs = (duration_sec // 2) + 2
            selected_segs = completed_segments[-num_segs:] if len(completed_segments) >= num_segs else completed_segments

        # Compute exact peak offset inside the extracted video based on first selected segment's timestamp
        first_seg_start_ts = selected_segs[0].stat().st_mtime - 2.0
        last_seg_end_ts = selected_segs[-1].stat().st_mtime
        approx_real_duration = max(4.0, round(last_seg_end_ts - first_seg_start_ts, 1))
        if peak_timestamp is not None:
            computed_peak_offset = max(2.0, min(approx_real_duration - 2.0, (peak_timestamp - REACTION_DELAY_COMPENSATION_SEC) - first_seg_start_ts))
        else:
            computed_peak_offset = approx_real_duration * 0.75

        # Concatenate MPEG-TS segments at byte level first, then remux once to MP4.
        # Because segments were created with -reset_timestamps 1, ffmpeg -f concat stops after a timestamp reset;
        # byte-concatenating the .ts files and remuxing with +genpts+igndts preserves 100% of all segments cleanly!
        merged_ts_path = self.buffer_dir / f"{output_file.stem}_merged.ts"
        try:
            with open(merged_ts_path, "wb") as out_ts:
                for s in selected_segs:
                    try:
                        with open(s, "rb") as in_ts:
                            shutil.copyfileobj(in_ts, out_ts, length=1024 * 1024)
                    except Exception:
                        pass

            cmd = [
                "ffmpeg", "-y",
                "-fflags", "+genpts+igndts",
                "-i", str(merged_ts_path),
                "-t", str(duration_sec),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                "-movflags", "+faststart",
                str(output_file)
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            if merged_ts_path.exists():
                try:
                    merged_ts_path.unlink()
                except Exception:
                    pass

        if res.returncode != 0 or not output_file.exists():
            return False, computed_peak_offset

        return True, round(computed_peak_offset, 1)
