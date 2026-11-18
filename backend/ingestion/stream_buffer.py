import asyncio
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional
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
                    "-reset_timestamps", "1",
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

    def extract_recent_segment(self, duration_sec: int, output_file: Path) -> bool:
        """
        Concatenates the most recent `duration_sec` seconds from the rolling buffer.
        """
        segments = sorted(list(self.buffer_dir.glob("*.ts")), key=lambda p: p.stat().st_mtime)
        if not segments:
            return False

        # Each segment is ~2s. Number of segments needed = ceil(duration_sec / 2) + 2 for safety
        num_segs = min(len(segments), (duration_sec // 2) + 3)
        selected_segs = segments[-num_segs:]

        # Create ffmpeg concat file
        concat_file = self.buffer_dir / "concat_list.txt"
        with open(concat_file, "w") as f:
            for s in selected_segs:
                f.write(f"file '{s.resolve()}'\n")

        # Concat without re-encoding
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_file)
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if concat_file.exists():
            concat_file.unlink()

        return res.returncode == 0
