import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple
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
                from faster_whisper import WhisperModel
                state.add_col3_log("Loading Faster-Whisper small.en CPU INT8 model...")
                self._model = WhisperModel("small.en", device="cpu", compute_type="int8")
                state.add_col3_log("Faster-Whisper small.en loaded successfully.")
            except ImportError:
                state.add_col3_log("Warning: faster-whisper not installed. Running in mock transcription mode.")
                self._model = "MOCK"
        return self._model

    def extract_audio(self, video_path: Path, audio_path: Path) -> bool:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(audio_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0

    def transcribe_with_word_timestamps(self, audio_path: Path) -> Tuple[List[Dict[str, Any]], float, float]:
        """
        Transcribes audio and returns word list and optimal snapped start/end boundaries.
        """
        model = self._get_model()
        state.col3_status = "TRANSCRIBING"
        state.add_col3_log("Transcribing audio track with word-level precision...")

        if model == "MOCK":
            # Fallback mock words for testing if whisper is not installed
            words = [
                {"word": "BRO", "raw_word": "BRO", "start": 0.5, "end": 1.0, "probability": 0.99},
                {"word": "YOU", "raw_word": "YOU", "start": 1.1, "end": 1.4, "probability": 0.99},
                {"word": "SAW", "raw_word": "SAW", "start": 1.5, "end": 1.8, "probability": 0.98},
                {"word": "THAT?!", "raw_word": "THAT?!", "start": 1.9, "end": 2.5, "probability": 0.99},
            ]
            state.current_transcript = [{"start": 0.5, "end": 2.5, "text": "BRO YOU SAW THAT?!"}]
            return words, 0.0, 30.0

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
        # vad_filter=True removes background noise/silence hallucinations
        segments, _ = model.transcribe(
            audio_input,
            word_timestamps=True,
            language="en",
            condition_on_previous_text=False,
            vad_filter=True,
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

        # Strictly group transcript display into rows of max 4 words each
        transcript_display: List[Dict[str, Any]] = []
        for i in range(0, len(words), 4):
            chunk = words[i:i + 4]
            chunk_text = " ".join(w["word"] for w in chunk)
            transcript_display.append({
                "start": round(chunk[0]["start"], 1),
                "end": round(chunk[-1]["end"], 1),
                "text": chunk_text
            })

        state.current_transcript = transcript_display
        state.add_col3_log(f"Transcribed {len(words)} words ({state.censored_count} words censored in text, max 4 words/row)")

        # Snap boundaries to natural pauses
        snapped_start, snapped_end = self._calculate_snapped_boundaries(words)
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

    def _calculate_snapped_boundaries(self, words: List[Dict[str, Any]]) -> Tuple[float, float]:
        """
        Finds natural speech pause boundaries so clip doesn't cut mid-sentence.
        """
        if not words:
            return 0.0, settings.MAX_CLIP_DURATION

        start_time = words[0]["start"]
        max_duration = float(settings.MAX_CLIP_DURATION)
        target_end = min(words[-1]["end"], start_time + max_duration)

        # Look for pause > 0.3s or punctuation in the last 10 seconds of max duration
        best_end = target_end
        for i in range(len(words) - 1, 0, -1):
            w = words[i]
            if w["end"] <= start_time + max_duration:
                # Check if word ends with punctuation or followed by pause
                has_punct = w["raw_word"].endswith(('.', '!', '?', ','))
                if i < len(words) - 1:
                    pause = words[i+1]["start"] - w["end"]
                    if pause >= 0.3 or has_punct:
                        best_end = w["end"] + 0.15
                        break
                elif has_punct:
                    best_end = w["end"] + 0.15
                    break

        return start_time, best_end

transcriber = SpeechTranscriber()
