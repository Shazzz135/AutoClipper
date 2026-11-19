import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from backend.core.config import settings
from backend.core.state import state

# Profanity word list for text censorship (audio remains 100% raw)
PROFANITY_PATTERNS = [
    (re.compile(r'\bfuck\w*', re.IGNORECASE), lambda m: m.group(0)[0] + '*' * (len(m.group(0)) - 1)),
    (re.compile(r'\bshit\w*', re.IGNORECASE), lambda m: m.group(0)[0] + '*' * (len(m.group(0)) - 1)),
    (re.compile(r'\bbitch\w*', re.IGNORECASE), lambda m: m.group(0)[0] + '*' * (len(m.group(0)) - 1)),
    (re.compile(r'\bnigg\w*', re.IGNORECASE), lambda m: m.group(0)[0] + '*' * (len(m.group(0)) - 1)),
    (re.compile(r'\bass\b', re.IGNORECASE), 'a**'),
    (re.compile(r'\basshole\w*', re.IGNORECASE), 'a******'),
    (re.compile(r'\bdick\w*', re.IGNORECASE), 'd***'),
    (re.compile(r'\bpussy\w*', re.IGNORECASE), 'p****'),
]

class SpeechTranscriber:
    def __init__(self):
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                import os
                from faster_whisper import WhisperModel
                threads = min(4, os.cpu_count() or 4)
                state.add_col3_log(f"Loading Faster-Whisper small.en CPU INT8 ({threads} threads)...")
                self._model = WhisperModel("small.en", device="cpu", compute_type="int8", cpu_threads=threads)
                state.add_col3_log("Faster-Whisper small.en loaded successfully.")
            except ImportError:
                state.add_col3_log("Warning: faster-whisper not installed. Running in mock transcription mode.")
                self._model = "MOCK"
        return self._model

    def extract_audio(self, video_path: Path, audio_path: Path, start_time: float = 0.0, duration: Optional[float] = None) -> bool:
        cmd = ["ffmpeg", "-y"]
        if start_time > 0.0:
            cmd.extend(["-ss", str(round(start_time, 2))])
        if duration is not None and duration > 0.0:
            cmd.extend(["-t", str(round(duration, 2))])
        cmd.extend([
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(audio_path)
        ])
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0

    def transcribe_with_word_timestamps(self, audio_path: Path, peak_offset: float = 60.0) -> Tuple[List[Dict[str, Any]], float, float]:
        """
        Transcribes audio and returns word list and optimal snapped start/end boundaries centered around peak_offset.
        """
        model = self._get_model()
        state.col3_status = "TRANSCRIBING"
        state.add_col3_log("Transcribing candidate audio track with word-level precision...")

        if model == "MOCK":
            # Fallback mock words for testing if whisper is not installed
            s_start = max(0.0, peak_offset - 20.0)
            words = [
                {"word": "BRO", "raw_word": "BRO", "start": s_start + 0.5, "end": s_start + 1.0, "probability": 0.99},
                {"word": "YOU", "raw_word": "YOU", "start": s_start + 1.1, "end": s_start + 1.4, "probability": 0.99},
                {"word": "SAW", "raw_word": "SAW", "start": s_start + 1.5, "end": s_start + 1.8, "probability": 0.98},
                {"word": "THAT?!", "raw_word": "THAT?!", "start": s_start + 1.9, "end": s_start + 2.5, "probability": 0.99},
            ]
            state.current_transcript = [{"start": s_start + 0.5, "end": s_start + 2.5, "text": "BRO YOU SAW THAT?!"}]
            return words, s_start, s_start + 45.0

        # Load audio directly into NumPy float32 to bypass PyAV metadata_errors bug
        audio_input = str(audio_path)
        try:
            import wave
            import numpy as np
            with wave.open(str(audio_path), "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                audio_input = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        except Exception as e:
            state.add_col3_log(f"WAV read fallback: {str(e)}")

        # condition_on_previous_text=False prevents Whisper from repeating/duplicating sentences
        # vad_filter=False ensures STT transcribes the entire 2-minute (120s) audio without dropping noisy/music/gaming sections
        segments, _ = model.transcribe(
            audio_input,
            word_timestamps=True,
            language="en",
            condition_on_previous_text=False,
            vad_filter=False,
            temperature=0.0
        )

        words: List[Dict[str, Any]] = []
        last_word_text = ""

        for segment in segments:
            seg_text = segment.text.strip()
            _, count = self._censor_text(seg_text)
            state.censored_count += count

            if segment.words:
                for w in segment.words:
                    clean_word, _ = self._censor_text(w.word.strip())
                    clean_upper = clean_word.upper().strip()

                    # Deduplicate immediate repeated words (e.g. "what what what")
                    if clean_upper == last_word_text and (len(words) > 0 and w.start - words[-1]["end"] < 0.2):
                        continue

                    if clean_word:
                        words.append({
                            "word": clean_word,
                            "raw_word": w.word.strip(),
                            "start": float(w.start),
                            "end": float(w.end),
                            "probability": float(w.probability)
                        })
                        last_word_text = clean_upper

        # Group transcript display into pause-aware rows matching on-screen subtitles
        from backend.pipeline.subtitles import subtitles
        subtitle_chunks = subtitles._chunk_words(words)
        transcript_display: List[Dict[str, Any]] = []
        for chunk in subtitle_chunks:
            if chunk:
                chunk_text = " ".join(w["word"] for w in chunk)
                transcript_display.append({
                    "start": round(chunk[0]["start"], 1),
                    "end": round(chunk[-1]["end"], 1),
                    "text": chunk_text
                })

        state.current_transcript = transcript_display
        state.add_col3_log(f"Transcribed {len(words)} words ({len(transcript_display)} speech segments, pause-synchronized)")

        # Snap boundaries to natural pauses centered near peak_offset
        snapped_start, snapped_end = self._calculate_snapped_boundaries(words, peak_offset=peak_offset)
        return words, snapped_start, snapped_end

    def _censor_text(self, text: str) -> Tuple[str, int]:
        if not settings.SUBTITLE_CENSOR_TEXT:
            return text, 0
        total_censored = 0
        result = text
        for pattern, replacement in PROFANITY_PATTERNS:
            matches = len(pattern.findall(result))
            if matches > 0:
                total_censored += matches
                result = pattern.sub(replacement, result)
        return result, total_censored

    def _calculate_snapped_boundaries(self, words: List[Dict[str, Any]], peak_offset: float = 60.0) -> Tuple[float, float]:
        """
        Finds natural speech pause boundaries centered on the peak moment (max 45-55s duration for YouTube Shorts).
        """
        max_duration = min(55.0, float(settings.MAX_CLIP_DURATION))
        if not words:
            start = max(0.0, peak_offset - 22.0)
            return start, start + max_duration

        # Target 22 seconds before peak and 23 seconds after peak
        ideal_start = max(0.0, peak_offset - 22.0)
        ideal_end = min(words[-1]["end"], ideal_start + max_duration)

        # Snap start to nearest word start near ideal_start
        start_candidates = [w["start"] for w in words if abs(w["start"] - ideal_start) <= 8.0]
        snapped_start = min(start_candidates, key=lambda s: abs(s - ideal_start)) if start_candidates else ideal_start

        # Snap end to sentence end or pause near ideal_end (strict max 58s for Shorts safety)
        max_end = snapped_start + 58.0
        snapped_end = min(ideal_end, max_end)

        for i in range(len(words) - 1, 0, -1):
            w = words[i]
            if snapped_start + 25.0 <= w["end"] <= max_end:
                has_punct = w["raw_word"].endswith(('.', '!', '?', ','))
                if has_punct or (i < len(words) - 1 and words[i+1]["start"] - w["end"] >= 0.25):
                    snapped_end = w["end"] + 0.15
                    break

        return round(snapped_start, 2), round(snapped_end, 2)

transcriber = SpeechTranscriber()
