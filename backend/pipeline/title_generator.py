import os
import re
import warnings
from typing import Dict, List, Any, Optional
from backend.core.config import settings
from backend.core.state import state

# Suppress library deprecation warning
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

class TitleGenerator:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        if self.api_key and HAS_GENAI:
            try:
                genai.configure(api_key=self.api_key)
            except Exception:
                pass

    def generate_title_and_metadata(
        self,
        transcript_words: List[Dict[str, Any]],
        peak_info: Dict[str, Any],
        part: int = 1
    ) -> Dict[str, Any]:
        """
        Generates viral YouTube Shorts title, description, and tags from transcript words.
        """
        full_transcript = " ".join(w.get("word", "") for w in transcript_words).strip()
        return self.generate_metadata_from_text(full_transcript, peak_info, part)

    def generate_metadata_from_text(
        self,
        transcript: str,
        peak_info: Optional[Dict[str, Any]] = None,
        part: int = 1
    ) -> Dict[str, Any]:
        """
        Generates viral YouTube Shorts title, description, and tags using AI (Gemini).
        Enforces AI rate limits and falls back to offline heuristic if limits or connectivity fail.
        """
        info = peak_info or {}
        streamer = settings.TWITCH_CHANNEL.capitalize()

        can_call_ai = (
            bool(self.api_key) and
            HAS_GENAI and
            state.check_ai_rate_limit(settings.AI_MAX_CALLS_PER_MINUTE, settings.AI_MAX_CALLS_PER_DAY)
        )

        if can_call_ai:
            for model_name in ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]:
                try:
                    state.add_col3_log(f"Calling Gemini AI ({model_name}) for viral metadata...")
                    result = self._call_gemini_api(model_name, transcript, streamer, info, part)
                    state.record_ai_call()
                    state.add_col3_log(f"AI Metadata generated: \"{result['title']}\"")
                    return result
                except Exception as e:
                    state.add_col3_log(f"Gemini ({model_name}) failed: {str(e)[:80]}")

        # High-quality heuristic fallback generator if AI call is unavailable
        state.add_col3_log("Generating high-engagement heuristic metadata.")
        return self._generate_offline_metadata(transcript, streamer, part)

    def _call_gemini_api(
        self,
        model_name: str,
        transcript: str,
        streamer: str,
        peak_info: Dict[str, Any],
        part: int
    ) -> Dict[str, Any]:
        model = genai.GenerativeModel(model_name)
        streamer_tag = streamer.lower().replace(" ", "")

        prompt = f"""
You are an elite YouTube Shorts algorithm strategist and viral video producer for Twitch live stream highlights.
Streamer: {streamer}
Spoken Words: "{transcript[:500]}"
Chat Velocity: {peak_info.get('velocity', 25)} msgs/sec

Generate an ultra-clickable, high-retention YouTube Short package:
1. TITLE: Max 60 characters, ALL-CAPS or punchy title case, irresistible hook, includes 1 emoji and #shorts.
2. DESCRIPTION: 2-3 engaging sentences describing the moment, asking viewers a question to drive comments, followed by #shorts #{streamer_tag} #twitch.
3. TAGS: An array of 6-10 trending tags for search indexing.

Respond ONLY in this exact JSON format (no markdown, no code fences):
{{
  "title": "{streamer.upper()} CANNOT BELIEVE THIS HAPPENED 💀 #shorts",
  "description": "Watch what happens when {streamer} gets completely caught off guard live on stream! Did you expect this? Comment below!\\n\\n#{streamer_tag} #shorts #twitch #viral",
  "tags": ["{streamer_tag}", "twitch", "shorts", "gaming", "viral", "highlights", "funny"]
}}
"""
        response = model.generate_content(prompt)
        text = response.text.strip()

        # Clean markdown code fences if present
        text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)

        import json
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            if "title" in data and "description" in data:
                return {
                    "title": str(data["title"]).strip(),
                    "description": str(data["description"]).strip(),
                    "tags": list(data.get("tags", [streamer_tag, "shorts", "twitch", "viral"]))
                }

        raise ValueError("Invalid JSON received from Gemini")

    def _generate_offline_metadata(self, transcript: str, streamer: str, part: int) -> Dict[str, Any]:
        streamer_tag = streamer.lower().replace(" ", "")

        # Extract punchy words
        words = [w.strip(".,!?:;\"'").upper() for w in transcript.split() if len(w) > 3]
        sample_phrase = " ".join(words[:3]) if words else "HYPE MOMENT"

        title = f"{streamer.upper()}: \"{sample_phrase}\" 💀 #shorts"
        if len(title) > 65:
            title = f"{streamer.upper()} LOST HIS MIND LIVE 💀 #shorts"

        description = (
            f"Watch {streamer}'s craziest reaction live on Twitch!\n"
            f"Did you expect this to happen? Drop a comment below!\n\n"
            f"#{streamer_tag} #shorts #twitch #viral #reaction #highlights"
        )
        tags = [streamer_tag, "twitch", "shorts", "gaming", "viral", "reaction", "highlights", "streamer"]

        return {
            "title": title,
            "description": description,
            "tags": tags
        }

title_gen = TitleGenerator()
