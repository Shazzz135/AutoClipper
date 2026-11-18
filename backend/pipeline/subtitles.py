import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from backend.core.config import settings
from backend.core.state import state

class SubtitleGenerator:
    def __init__(self):
        self.max_words = 4 # Strictly max 4 words per row (no character limit)
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
        adjusted_words: List[Dict[str, Any]] = []
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
                adjusted_words.append({
                    "word": w["word"],
                    "start": rel_start,
                    "end": rel_end
                })

        if not adjusted_words:
            state.add_col3_log("Notice: No speech words fell within the selected clip window.")
            # Write empty valid ASS file (still includes hook title if present)
            self._write_empty_ass(output_path, title=title)
            return

        # ASS Header (Italic, centered at Y=830, bottom of facecam / top of gameplay)
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

        # Group words into chunks of max 4 words / <= 24 chars
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

        for chunk_idx, chunk in enumerate(chunks):
            if not chunk:
                continue

            chunk_start = chunk[0]["start"]
            # Chunk ends when the last word ends, or when the next chunk begins
            chunk_end = chunk[-1]["end"] + 0.3
            if chunk_idx < len(chunks) - 1:
                next_start = chunks[chunk_idx + 1][0]["start"]
                chunk_end = min(chunk_end, next_start)

            # Generate smooth events for each word in the chunk
            for word_idx, current_word in enumerate(chunk):
                # Active red window for this word:
                # Starts when this word is spoken
                w_active_start = current_word["start"]

                # Ends when the next word starts (or when the chunk ends if it's the last word)
                if word_idx < len(chunk) - 1:
                    w_active_end = chunk[word_idx + 1]["start"]
                else:
                    w_active_end = chunk_end

                if w_active_end <= w_active_start:
                    w_active_end = w_active_start + 0.15

                # Build line text: all words white italic, currently active word in vibrant red
                line_parts = []
                for idx, w in enumerate(chunk):
                    if idx == word_idx:
                        # Red active word
                        line_parts.append(f"{{\\c{self.active_color_ass}\\b1\\i1}}{w['word']}{{\\c{self.default_color_ass}\\b1\\i1}}")
                    else:
                        line_parts.append(f"{{\\b1\\i1}}{w['word']}{{\\b1\\i1}}")

                line_text = " ".join(line_parts)
                start_str = self._format_ass_time(w_active_start)
                end_str = self._format_ass_time(w_active_end)

                events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{line_text}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events) + "\n")

        state.add_col3_log(f"Subtitles compiled with {len(events)} synchronized word transitions.")

    def _chunk_words(self, words: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Strictly chunks words to max 4 words per row with no character limit."""
        chunks = []
        current_chunk = []

        for w in words:
            # Check pause gap to previous word (>0.6s pause starts a new line)
            gap = (w["start"] - current_chunk[-1]["end"]) if current_chunk else 0.0

            if len(current_chunk) >= self.max_words or gap > 0.6:
                if current_chunk:
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
