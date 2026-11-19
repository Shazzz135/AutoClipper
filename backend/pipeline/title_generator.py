import os
import re
import random
import warnings
from collections import deque
from typing import Dict, List, Any, Optional
from backend.core.config import settings
from backend.core.state import state

# Suppress library deprecation warning
warnings.filterwarnings("ignore", category=FutureWarning)

# ==============================================================================
# 15 PRE-MADE UNIVERSAL GTA 6 TITLES
# Every title strictly includes "GTA 6" and works for any clip.
# ==============================================================================
GTA6_TITLES_15 = [
    "{streamer} FIRST TIME PLAYING GTA 6! 💀 #shorts",
    "{streamer} CANNOT BELIEVE THIS IN GTA 6! 😭 #shorts",
    "BRO DID NOT EXPECT THIS IN GTA 6 💀 #shorts",
    "{streamer} MOST INSANE GTA 6 MOMENT! 🚨 #shorts",
    "GTA 6 IS ALREADY OUT OF CONTROL 😭 #shorts",
    "{streamer} 5-STAR POLICE CHASE IN GTA 6! 🚨 #shorts",
    "HE REALLY THOUGHT HE SURVIVED GTA 6 💀 #shorts",
    "{streamer} LOST HIS MIND IN GTA 6 😭 #shorts",
    "GTA 6 GRAPHICS ARE ACTUALLY UNREAL 🤯 #shorts",
    "{streamer} CLUTCH OR CHOKE IN GTA 6?! 💀 #shorts",
    "THIS IS WHY GTA 6 TOOK 12 YEARS 💀 #shorts",
    "{streamer} EXPLORING VICE CITY IN GTA 6! 🌴 #shorts",
    "NO WAY THIS JUST HAPPENED IN GTA 6 💀 #shorts",
    "{streamer} PURE CHAOS IN GTA 6! 🚨 #shorts",
    "THE CRAZIEST THING YOU WILL SEE IN GTA 6 💀 #shorts"
]

# ==============================================================================
# 15 PRE-MADE UNIVERSAL DISCUSSION COMMENTS
# Designed to spark comment wars & debate. Works for any clip.
# ==============================================================================
GTA6_COMMENTS_15 = [
    "Be honest... did {streamer} throw or clutch this GTA 6 moment? Drop your thoughts below! 👇💀",
    "Is GTA 6 game of the year already or are people overhyping it? W or L reaction? 👇🔥",
    "Did you expect this to happen in Vice City?! Tell me in the comments! 👇😂",
    "Are you picking Jason or Lucia when you jump into GTA 6? Drop a comment! 👇🌴",
    "Rate this GTA 6 moment from 1 to 10 in the comments! 👇💀",
    "Bro really thought he had it under control 😭 W or L gameplay from {streamer}? 👇",
    "What would you have done in this GTA 6 situation? Comment below! 👇🚨",
    "Is GTA 6 living up to the 12-year wait so far? Drop your honest review below! 👇🎮",
    "Was this pure skill or did the GTA 6 physics save him? Let me know below! 👇🤯",
    "Who else is playing GTA 6 all night?! Drop a W in the comments! 👇🔥",
    "The police AI in GTA 6 is actually ruthless 😭 Did he deserve to get caught? 👇",
    "Best GTA 6 reaction so far? What do you think? Drop a comment! 👇💀",
    "Did {streamer} cook or sell here? Be 100% honest in the comments! 👇🍳",
    "The graphics in Vice City are insane! What console are you playing GTA 6 on? 👇📺",
    "Only in GTA 6 bro 💀 What has been your favorite moment in the game so far? 👇"
]

# ==============================================================================
# 15 PRE-MADE UNIVERSAL DESCRIPTIONS
# High-ranking SEO format, Vice City & Leonida tags, engagement calls. Works for any clip.
# ==============================================================================
GTA6_DESCRIPTIONS_15 = [
    # 1. Hype Vice City
    """Watch {streamer}'s craziest reaction playing Grand Theft Auto VI (GTA 6) live on stream!
The hype in Vice City is real... did you expect this to go down?!

🎮 Game: Grand Theft Auto VI (GTA 6)
📍 Map: Vice City, State of Leonida
🌴 Characters: Jason & Lucia

Drop your thoughts in the comments below! 👇

#{streamer_tag} #GTA6 #GTAVI #GrandTheftAuto6 #GTA6Gameplay #ViceCity #shorts #gaming #viral""",

    # 2. Chaos & Comedy
    """{streamer} experiences pure chaos exploring GTA 6 live on Twitch!
Did he throw or clutch up? You won't believe how this ended!

🎮 Game: Grand Theft Auto 6 / GTA VI
🌴 Location: Vice City & Leonida
📺 Platform: PS5 Pro 4K 60FPS

Leave a comment with your rating! 👇

#{streamer_tag} #GTA6 #GTAVI #GTA6Gameplay #GrandTheftAuto6 #PS5Pro #ViceCity #shorts #viral #gaming""",

    # 3. Free Roam & Walkthrough
    """Unfiltered GTA 6 gameplay and insane moments with {streamer} live in Vice City!
Exploring the full map of Leonida and finding crazy details in Grand Theft Auto VI.

🎮 Game: Grand Theft Auto VI (GTA 6)
🌴 Mission: Free Roam & Police Chase

Are you playing on PS5 Pro or Xbox Series X? Let us know below! 👇

#{streamer_tag} #GTA6 #GTAVI #GTA6Walkthrough #GTA6FreeRoam #ViceCity #GrandTheftAuto6 #shorts #gaming #viral""",

    # 4. Topics Checklist
    """{streamer} gets completely caught off guard in GTA 6! 
Watch the full reaction live from Vice City in Grand Theft Auto VI.

━━━━━━━━━━━━━━━━━━━━━━━━━
🔥 TOPICS COVERED:
• GTA 6 gameplay & free roam exploration
• {streamer} GTA 6 live stream moments & highlights
• Grand Theft Auto 6 police chase and secrets
• GTA 6 PS5 Pro graphics & Vice City map

#{streamer_tag} #GTA6 #GTAVI #GrandTheftAuto6 #GTA6Gameplay #ViceCity #Leonida #shorts #gaming #viral""",

    # 5. Game of the Year
    """Is GTA 6 already the greatest open-world game ever made?!
Watch {streamer} react to this unforgettable moment in Grand Theft Auto VI!

🎮 Game: Grand Theft Auto VI (GTA 6)
📍 Setting: Vice City & Leonida
🌴 Protagonists: Jason Duval & Lucia Caminos

Drop a W or L in the comments! 👇

#{streamer_tag} #GTA6 #GTAVI #GrandTheftAuto6 #GTA6Review #ViceCity #JasonAndLucia #shorts #viral #gaming""",

    # 6. Wild Stream Moments
    """Nobody expected this to happen during {streamer}'s GTA 6 stream!
Vice City has zero chill and the reactions are unbeatable.

🎮 Game: Grand Theft Auto 6 (GTA VI)
🌴 Map: State of Leonida

What would you have done here? Comment below! 👇

#{streamer_tag} #GTA6 #GTAVI #GTA6Clips #ViceCity #GamingMoments #shorts #viral""",

    # 7. First Look
    """First day in GTA 6 and {streamer} is already testing the limits of Vice City!
From high speed chases to wild physics, this game is next level.

🎮 Game: Grand Theft Auto VI
📺 Resolution: 4K 60FPS Gameplay

Is GTA 6 a 10/10 so far? Drop your verdict below! 👇

#{streamer_tag} #GTA6 #GTAVI #GrandTheftAuto6 #ViceCity #GTA6FirstLook #shorts #gaming #viral""",

    # 8. Police Chase
    """When a casual drive in GTA 6 turns into absolute madness for {streamer}!
The 5-star police aggression in Vice City is no joke.

🎮 Game: Grand Theft Auto VI (GTA 6)
🚨 Heat Level: Maximum Wanted Level

Did he survive this? Tell me in the comments! 👇

#{streamer_tag} #GTA6 #GTAVI #GTA6PoliceChase #ViceCity #GrandTheftAuto #shorts #viral""",

    # 9. Graphics Showcase
    """The visual details and graphics in GTA 6 are blowing everyone away!
Watch {streamer}'s genuine reaction to the Vice City world.

🎮 Title: Grand Theft Auto VI (GTA 6)
📍 Location: Leonida & Vice Beach

Are you picking up GTA 6 on PS5 Pro or Xbox? Let us know below! 👇

#{streamer_tag} #GTA6 #GTAVI #GTA6Graphics #PS5Pro #ViceCity #GrandTheftAuto6 #shorts #gaming""",

    # 10. Story & Characters
    """Exploring the story of Jason and Lucia in GTA 6 with {streamer}!
Every corner of Vice City has a new secret waiting to be found.

🎮 Game: Grand Theft Auto VI (GTA 6)
🌴 Duo: Jason & Lucia

Who is your favorite character so far? Drop your thoughts! 👇

#{streamer_tag} #GTA6 #GTAVI #JasonAndLucia #ViceCity #GTA6Story #shorts #gaming #viral""",

    # 11. Funny Fail
    """You cannot make this up... {streamer}'s reaction to this GTA 6 moment is priceless!
Drop a like and comment if you laughed! 💀

🎮 Game: Grand Theft Auto VI (GTA 6)
🌴 Location: Vice City

Did the game do him dirty? Be honest below! 👇

#{streamer_tag} #GTA6 #GTAVI #GTA6Fails #ViceCity #FunnyMoments #shorts #gaming #viral""",

    # 12. Highlights
    """Peak streaming energy as {streamer} dives headfirst into GTA 6!
Catch all the best Twitch highlights and unforgettable moments right here.

🎮 Game: Grand Theft Auto 6 / GTA VI
📍 World: Vice City & Leonida

Drop a comment with your favorite streamer playing GTA 6! 👇

#{streamer_tag} #GTA6 #GTAVI #TwitchClips #ViceCity #GTA6Highlights #shorts #gaming""",

    # 13. Open World Discovery
    """12 years in the making and GTA 6 did not disappoint!
Watch {streamer} discover something unbelievable in the heart of Vice City.

🎮 Game: Grand Theft Auto VI
🌴 Map: Leonida

Did you notice this in your own playthrough? Let me know below! 👇

#{streamer_tag} #GTA6 #GTAVI #GTA6Secrets #ViceCity #GrandTheftAuto6 #shorts #viral""",

    # 14. Clutch vs Choke
    """Was this an elite clutch or the biggest choke in GTA 6 history?!
Watch {streamer} battle it out on the streets of Vice City.

🎮 Game: Grand Theft Auto 6 (GTA VI)
🌴 Mission: High Stakes Free Roam

W or L gameplay? Cast your vote in the comments! 👇

#{streamer_tag} #GTA6 #GTAVI #GTA6Clutch #ViceCity #GrandTheftAuto #shorts #gaming""",

    # 15. Launch Day Hype
    """The launch of Grand Theft Auto VI is breaking the internet!
Join {streamer} for the most insane highlights from Vice City.

🎮 Game: Grand Theft Auto VI (GTA 6)
📺 Broadcast: Live on Twitch

Are you playing right now? Drop a 🔥 in the comments! 👇

#{streamer_tag} #GTA6 #GTAVI #GrandTheftAuto6 #ViceCity #GTA6Launch #shorts #viral #gaming"""
]

class TitleGenerator:
    def __init__(self):
        # Gemini is completely disabled per instructions. All metadata is picked from the 15 pre-made pools.
        self._recent_titles = deque(maxlen=8)
        self._recent_comments = deque(maxlen=8)
        self._recent_descriptions = deque(maxlen=8)

    def get_random_title(self, streamer: str) -> str:
        """Picks a unique pre-made GTA 6 title from the 15 available, avoiding recent repeats."""
        streamer_display = streamer.upper()
        available = [t for t in GTA6_TITLES_15 if t not in self._recent_titles]
        if not available:
            available = GTA6_TITLES_15
        chosen = random.choice(available)
        self._recent_titles.append(chosen)
        return chosen.format(streamer=streamer_display)

    def get_random_comment(self, streamer: str) -> str:
        """Picks a unique pre-made discussion comment from the 15 available, avoiding recent repeats."""
        available = [c for c in GTA6_COMMENTS_15 if c not in self._recent_comments]
        if not available:
            available = GTA6_COMMENTS_15
        chosen = random.choice(available)
        self._recent_comments.append(chosen)
        return chosen.format(streamer=streamer)

    def get_random_description(self, streamer: str) -> str:
        """Picks a unique pre-made GTA 6 description from the 15 available, avoiding recent repeats."""
        streamer_tag = streamer.lower().replace(" ", "")
        available = [d for d in GTA6_DESCRIPTIONS_15 if d not in self._recent_descriptions]
        if not available:
            available = GTA6_DESCRIPTIONS_15
        chosen = random.choice(available)
        self._recent_descriptions.append(chosen)
        return chosen.format(streamer=streamer, streamer_tag=streamer_tag)

    def generate_title_and_metadata(
        self,
        transcript_words: List[Dict[str, Any]],
        peak_info: Dict[str, Any],
        part: int = 1
    ) -> Dict[str, Any]:
        """
        Instant 0ms metadata generator selecting from the 15 pre-made pools without Gemini AI.
        """
        streamer = settings.TWITCH_CHANNEL.capitalize()
        return self._generate_offline_metadata("", streamer, part)

    def generate_metadata_from_text(
        self,
        transcript: str,
        peak_info: Optional[Dict[str, Any]] = None,
        part: int = 1
    ) -> Dict[str, Any]:
        """
        Instant 0ms metadata generator selecting from the 15 pre-made pools without Gemini AI.
        """
        streamer = settings.TWITCH_CHANNEL.capitalize()
        state.add_col3_log(f"Selecting unique pre-made GTA 6 viral metadata package for #{settings.TWITCH_CHANNEL}...")
        return self._generate_offline_metadata(transcript, streamer, part)

    def _generate_offline_metadata(self, transcript: str, streamer: str, part: int) -> Dict[str, Any]:
        streamer_tag = streamer.lower().replace(" ", "")

        title = self.get_random_title(streamer)
        first_comment = self.get_random_comment(streamer)
        description = self.get_random_description(streamer)

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

        return {
            "title": title,
            "description": description,
            "tags": tags,
            "first_comment": first_comment
        }

title_gen = TitleGenerator()
