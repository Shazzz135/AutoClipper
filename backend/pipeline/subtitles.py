import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from backend.core.config import settings
from backend.core.state import state

class SubtitleGenerator:
    def __init__(self):
        self.max_words = 3 # Punchy 2-3 words per line for high-engagement Shorts
        # Position at 20% vertical height of 1920 canvas = 384px from bottom
        self.margin_v = int(settings.OUTPUT_HEIGHT * getattr(settings, 'SUBTITLE_VERTICAL_POS_PCT', 0.20))
        # ASS BGR format: #FF1E1E -> &H001E1EFF&
        self.active_color_ass = "&H001E1EFF&" # Vibrant Red
        self.default_color_ass = "&H00FFFFFF&" # Crisp White

    def generate_ass_file(
        self,
        words: List[Dict[str, Any]],
        output_path: Path,
        offset_start: float = 0.0,
        clip_duration: Optional[float] = None,
        title: Optional[str] = None
    ):
        """
        Creates an ASS subtitle file with:
        - Temporary hook title between facecam & gameplay (fades out at 3.8s)
        - Italic styling with max 4 words per line
        - Smooth word-by-word red karaoke transitions synchronized to audio
        """
        state.add_col3_log(f"Compiling synchronized subtitles (offset: -{offset_start:.2f}s)...")

        # 1. Offset words relative to the trimmed video start point
        raw_adjusted: List[Dict[str, Any]] = []
        for w in words:
            rel_start = float(w["start"]) - offset_start
            rel_end = float(w["end"]) - offset_start

            # Only include words that fall within the trimmed video window
            if rel_end <= 0.0:
                continue
            if clip_duration and rel_start >= clip_duration:
                continue

            rel_start = max(0.0, rel_start)
            if rel_end > rel_start:
                raw_adjusted.append({
                    "word": w["word"],
                    "start": rel_start,
                    "end": rel_end
                })

        if not raw_adjusted:
            state.add_col3_log("Notice: No speech words fell within the selected clip window.")
            # Write empty valid ASS file (still includes hook title if present)
            self._write_empty_ass(output_path, title=title)
            return

        # Normalize timestamps to guarantee positive duration & strict monotonic ordering
        adjusted_words: List[Dict[str, Any]] = []
        for w in raw_adjusted:
            start = max(0.0, float(w["start"]))
            end = max(start + 0.05, float(w["end"]))
            adjusted_words.append({"word": w["word"], "start": start, "end": end})

        for i in range(1, len(adjusted_words)):
            if adjusted_words[i]["start"] < adjusted_words[i - 1]["start"]:
                adjusted_words[i]["start"] = adjusted_words[i - 1]["start"]
            if adjusted_words[i]["end"] <= adjusted_words[i]["start"]:
                adjusted_words[i]["end"] = adjusted_words[i]["start"] + 0.05

        # ASS Header (Centered at Y=384 / bottom 20% of 1080x1920 portrait canvas)
        # DividerTitle is anchored at Y=745 (directly between facecam and gameplay) with smooth fade
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,68,{self.default_color_ass},&H000000FF&,&H00000000&,&H90000000&,-1,-1,0,0,100,100,0,0,1,6,3,2,40,40,{self.margin_v},1
Style: DividerTitle,Arial,52,&H00FFFFFF&,&H000000FF&,&H00000000&,&HD0000000&,-1,0,0,0,100,100,0,0,1,5,3,8,40,40,745,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        # Group words into chunks of max 3 words / pause-separated
        chunks = self._chunk_words(adjusted_words)
        events = []

        # Add temporary title between facecam & gameplay (fades in at 0.2s, fades out at 3.8s)
        # Strictly strip all hashtags (#shorts, #kai, #stream, etc.) from on-screen video title
        if title:
            clean_title = re.sub(r'#\S*', '', title).strip().upper()
            clean_title = re.sub(r'\s+', ' ', clean_title)
            if clean_title:
                if len(clean_title) > 36:
                    words_title = clean_title.split()
                    mid = len(words_title) // 2
                    clean_title = " ".join(words_title[:mid]) + "\\N" + " ".join(words_title[mid:])
                title_event = f"Dialogue: 1,0:00:00.20,0:00:03.80,DividerTitle,,0,0,0,,{{\\fad(250,400)\\b1}}{clean_title}"
                events.append(title_event)

        # Generate single-line subtitle events with word-by-word karaoke highlighting
        raw_events: List[Dict[str, Any]] = []
        for chunk_idx, chunk in enumerate(chunks):
            if not chunk:
                continue

            # Natural linger: chunk stays visible for 0.15s after last word ends, capped strictly by next chunk
            c_start = chunk[0]["start"]
            c_end = chunk[-1]["end"] + 0.15
            if chunk_idx < len(chunks) - 1 and len(chunks[chunk_idx + 1]) > 0:
                next_chunk_start = chunks[chunk_idx + 1][0]["start"]
                c_end = min(c_end, next_chunk_start)

            for word_idx, current_word in enumerate(chunk):
                w_start = current_word["start"]
                if word_idx < len(chunk) - 1:
                    w_end = chunk[word_idx + 1]["start"]
                else:
                    w_end = c_end

                if w_end <= w_start:
                    w_end = w_start + 0.05

                # Build line text: active word in red, remaining words in white
                line_parts = []
                for idx, w in enumerate(chunk):
                    if idx == word_idx:
                        line_parts.append(f"{{\\c{self.active_color_ass}\\b1\\i1}}{w['word']}{{\\c{self.default_color_ass}\\b1\\i1}}")
                    else:
                        line_parts.append(f"{{\\b1\\i1}}{w['word']}{{\\b1\\i1}}")

                raw_events.append({
                    "start": w_start,
                    "end": w_end,
                    "text": " ".join(line_parts)
                })

        # STRICT NON-OVERLAPPING PASS:
        # In libass, any time two Dialogue events overlap on the same layer/alignment, it stacks them.
        # By enforcing event[i].end <= event[i+1].start across all events, we guarantee mathematically
        # that EXACTLY ONE LINE appears on screen at any given moment.
        for i in range(len(raw_events)):
            ev = raw_events[i]
            e_start = ev["start"]
            e_end = ev["end"]
            if i < len(raw_events) - 1:
                next_start = raw_events[i + 1]["start"]
                if e_end > next_start:
                    e_end = next_start

            # Only emit events with positive visible duration (>= 30ms / ~2 frames at 60fps)
            if e_end > e_start + 0.03:
                start_str = self._format_ass_time(e_start)
                end_str = self._format_ass_time(e_end)
                events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{ev['text']}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events) + "\n")

        state.add_col3_log(f"Subtitles compiled: {len(events)} single-line synchronized events (zero overlap).")

    def _chunk_words(self, words: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        Chunks words so subtitles only appear when actively spoken:
        - Splits on speech pauses (> 0.35s silence between words)
        - Splits on punctuation marks (. , ! ? ; : - ...)
        - Capped at max 3 words per line
        - Capped at max 2.0s duration per chunk to prevent floating text
        """
        chunks = []
        current_chunk: List[Dict[str, Any]] = []

        PUNCTUATION_BREAKS = ('.', '!', '?', ',', ';', ':', '...', '—', '-', '"')

        for w in words:
            if not current_chunk:
                current_chunk = [w]
                continue

            prev_word = current_chunk[-1]
            prev_text = prev_word["word"].strip()
            prev_end = float(prev_word["end"])
            curr_start = float(w["start"])

            gap = curr_start - prev_end
            has_punct_break = any(prev_text.endswith(p) for p in PUNCTUATION_BREAKS)
            exceeds_duration = (float(w["end"]) - float(current_chunk[0]["start"])) > 2.0
            exceeds_word_count = len(current_chunk) >= self.max_words

            # Break into a new line whenever there is a pause, punctuation, duration cap, or word limit
            if gap > 0.35 or has_punct_break or exceeds_duration or exceeds_word_count:
                chunks.append(current_chunk)
                current_chunk = [w]
            else:
                current_chunk.append(w)

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _format_ass_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int(round((seconds - int(seconds)) * 100))
        if centisecs >= 100:
            centisecs = 99
        return f"{hours:01d}:{minutes:02d}:{secs:02d}.{centisecs:02d}"

    def _write_empty_ass(self, output_path: Path, title: Optional[str] = None):
        events = []
        if title:
            clean_title = re.sub(r'#\S*', '', title).strip().upper()
            clean_title = re.sub(r'\s+', ' ', clean_title)
            if clean_title:
                if len(clean_title) > 36:
                    words_title = clean_title.split()
                    mid = len(words_title) // 2
                    clean_title = " ".join(words_title[:mid]) + "\\N" + " ".join(words_title[mid:])
                events.append(f"Dialogue: 1,0:00:00.20,0:00:03.80,DividerTitle,,0,0,0,,{{\\fad(250,400)\\b1}}{clean_title}")

        content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,60,&H00FFFFFF&,&H000000FF&,&H00000000&,&H80000000&,-1,-1,0,0,100,100,0,0,1,5,2,2,40,40,830,1
Style: DividerTitle,Arial,52,&H00FFFFFF&,&H000000FF&,&H00000000&,&HD0000000&,-1,0,0,0,100,100,0,0,1,5,3,8,40,40,745,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

subtitles = SubtitleGenerator()
