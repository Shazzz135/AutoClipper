import os
import re
import warnings
from typing import Dict, List, Any, Optional
from backend.core.config import settings
from backend.core.state import state

# Suppress library deprecation warning
warnings.filterwarnings("ignore", category=FutureWarning)

class TitleGenerator:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self._genai = None

    def _get_genai(self):
        if self._genai is None and self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._genai = genai
            except Exception:
                self._genai = False
        return self._genai if self._genai else None

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
            state.check_ai_rate_limit(settings.AI_MAX_CALLS_PER_MINUTE, settings.AI_MAX_CALLS_PER_DAY) and
            bool(self._get_genai())
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
        genai = self._get_genai()
        model = genai.GenerativeModel(model_name)
        streamer_tag = streamer.lower().replace(" ", "")

        prompt = f"""
You are an elite YouTube Shorts algorithm strategist and viral video producer for high-energy Twitch stream clips.
Streamer: {streamer}
Spoken Words: "{transcript[:500]}"
Chat Velocity: {peak_info.get('velocity', 25)} msgs/sec

The biggest gaming event in history is happening (GTA 6 / Grand Theft Auto VI launch).
Optimize this Short for maximum search volume and high-retention algorithmic push:

SEO STRATEGY:
- Title Formula: Combine an irresistible hook with high-volume search keywords (e.g. "GTA 6", "GTA VI", "Vice City", "Lucia & Jason", "PS5 Pro", "Police Chase", "Free Roam"). Max 60-70 characters. Include 1 emoji and #shorts.
- Description: 
  1. 2-3 punchy, hype sentences describing the streamer's reaction or gameplay moment.
  2. A direct viewer question to trigger the comment algorithm.
  3. A clean, high-ranking SEO keyword & search term block containing core launch queries (GTA 6 gameplay, Vice City, Leonida, Grand Theft Auto 6, Jason & Lucia).
  4. Top hashtags: #shorts #{streamer_tag} #GTA6 #GTAVI #GrandTheftAuto6 #gaming #viral
- Tags: 8-12 high-intent search tags targeting the game, streamer, and specific in-game moments.
- First Comment: An irresistible debate-sparking question or hot take designed to get pinned as the first comment and ignite comment wars (e.g. "Be honest... did he throw or clutch up?! 👇💀"). Max 200 characters.

Respond ONLY in this exact JSON format (no markdown, no code fences):
{{
  "title": "{streamer.upper()} INSANE GTA 6 MOMENT! 💀 #shorts",
  "description": "{streamer} experiences the craziest moment in GTA 6 live on stream! Did you expect this in Vice City? Comment below!\\n\\n🎮 Game: Grand Theft Auto VI (GTA 6)\\n📍 Location: Vice City, Leonida\\n\\n#{streamer_tag} #GTA6 #GTAVI #GrandTheftAuto6 #shorts #gaming #viral",
  "tags": ["{streamer_tag}", "gta 6", "gta vi", "grand theft auto 6", "gta 6 gameplay", "vice city", "leonida", "gta 6 ps5 pro", "shorts", "gaming", "viral"],
  "first_comment": "Be honest... was this a throw or did the game glitch? Drop your thoughts below! 👇💀"
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
                first_comment = str(data.get("first_comment", "")).strip()
                if not first_comment:
                    first_comment = f"Drop your thoughts below: Did {streamer} throw or clutch up?! 👇💀"
                return {
                    "title": str(data["title"]).strip(),
                    "description": str(data["description"]).strip(),
                    "tags": list(data.get("tags", [streamer_tag, "shorts", "twitch", "viral"])),
                    "first_comment": first_comment
                }

        raise ValueError("Invalid JSON received from Gemini")

    def _generate_offline_metadata(self, transcript: str, streamer: str, part: int) -> Dict[str, Any]:
        streamer_tag = streamer.lower().replace(" ", "")

        # Extract punchy words
        words = [w.strip(".,!?:;\"'").upper() for w in transcript.split() if len(w) > 3]
        sample_phrase = " ".join(words[:3]) if words else "HYPE MOMENT"

        title = f"{streamer.upper()} FIRST TIME PLAYING GTA 6! 💀 #shorts"
        if len(title) > 65:
            title = f"{streamer.upper()} INSANE GTA 6 MOMENT 💀 #shorts"

        description = (
            f"Watch {streamer}'s craziest reaction playing GTA 6 (Grand Theft Auto VI) live on stream!\n"
            f"Is GTA 6 game of the year already? W or L reaction? Drop your thoughts in the comments below!\n\n"
            f"🎮 Game: Grand Theft Auto VI (GTA 6)\n"
            f"📍 Map: Vice City & Leonida\n"
            f"🌴 Characters: Jason & Lucia\n\n"
            f"#{streamer_tag} #GTA6 #GTAVI #GrandTheftAuto6 #GTA6Gameplay #ViceCity #shorts #viral #gaming"
        )
        tags = [
            streamer_tag,
            "gta 6",
            "gta vi",
            "grand theft auto 6",
            "gta 6 gameplay",
            "gta 6 walkthrough",
            "gta 6 free roam",
            "vice city",
            "leonida",
            "jason and lucia",
            "gta 6 ps5 pro",
            "shorts",
            "gaming",
            "viral"
        ]

        first_comment = (
            f"Be honest... did {streamer} throw or clutch this GTA 6 moment? Drop your thoughts below! 👇💀"
        )

        return {
            "title": title,
            "description": description,
            "tags": tags,
            "first_comment": first_comment
        }

title_gen = TitleGenerator()
