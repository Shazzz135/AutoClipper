import time
import subprocess
import numpy as np
import re
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
from backend.core.config import settings
from backend.core.state import state

HYPE_TOKENS = {
    "w", "l", "clip", "omg", "wtf", "what", "kekw", "omegalul",
    "pog", "poggers", "lol", "lmao", "hype", "gg", "nooo",
    "insane", "crazy", "yoooo", "yo", "sheesh", "goat"
}

class PeakDetector:
    def __init__(self, on_peak_detected_callback=None):
        self.on_peak_detected_callback = on_peak_detected_callback
        self.timestamps: List[float] = [] # Timestamps of received chat messages
        self.chat_history: List[Dict[str, Any]] = [] # [{'time': float, 'text': str, 'user': str}]
        self.last_peak_time: float = 0.0
        self.peak_counter: int = 100

    def reset(self):
        """Resets chat history and rolling windows when switching streamers."""
        self.timestamps = []
        self.chat_history = []
        state.msg_velocity = 0.0
        state.baseline_velocity = 0.0
        state.current_z_score = 0.0
        state.chat_hype_density = 0.0

    def register_message(self, text: str, user: str = ""):
        """Called for every incoming chat message."""
        now = time.time()
        self.timestamps.append(now)
        self.chat_history.append({"time": now, "text": text, "user": user})
        if len(self.chat_history) > 200:
            self.chat_history.pop(0)

    def _calculate_hype_density(self) -> float:
        """Calculates proportion of recent messages with hype signals (emotes, caps, punctuation)."""
        if not self.chat_history:
            return 0.0
        recent = self.chat_history[-40:]
        hype_count = 0
        for item in recent:
            t = item.get("text", "").strip()
            if not t:
                continue
            lower_words = set(re.findall(r"\b\w+\b", t.lower()))
            has_token = bool(lower_words.intersection(HYPE_TOKENS))
            has_exclamation = ("!" in t or "?" in t)
            has_caps = len(t) >= 3 and sum(1 for c in t if c.isupper()) / max(1, len(t)) > 0.65
            if has_token or has_exclamation or has_caps:
                hype_count += 1
        return round(hype_count / len(recent), 2)

    def _compute_dynamic_requirements(self, baseline_velocity: float, loudness_db: float, hype_density: float):
        """
        Dynamically adjusts required velocity and Z-score based on streamer scale (viewers, baseline),
        audio loudness (screams), and chat sentiment (hype density).
        """
        # 1. Estimate viewers if not supplied from stream metadata
        now = time.time()
        recent_window_chatters = set(
            c.get("user") for c in self.chat_history
            if c.get("user") and (now - c.get("time", 0) <= 180.0)
        )
        if state.stream_viewers <= 0:
            estimated_viewers = max(50, len(recent_window_chatters) * 15)
            state.stream_viewers = estimated_viewers
        else:
            estimated_viewers = state.stream_viewers

        # 2. Determine Streamer Tier (Auto or User Selected)
        if state.peak_streamer_tier == "AUTO":
            if estimated_viewers >= 15000 or baseline_velocity >= 12.0:
                tier = "MEGA"
            elif estimated_viewers >= 4000 or baseline_velocity >= 4.0:
                tier = "LARGE"
            elif estimated_viewers >= 800 or baseline_velocity >= 1.5:
                tier = "MEDIUM"
            else:
                tier = "SMALL"
        else:
            tier = state.peak_streamer_tier
        state.peak_active_tier = tier

        # Sensitivity multipliers
        sens = state.peak_sensitivity
        if sens == "LOW":
            surge_mult = 2.4
            z_mod = 0.4
        elif sens == "HIGH":
            surge_mult = 1.35
            z_mod = -0.45
        else: # NORMAL
            surge_mult = 1.8
            z_mod = 0.0

        if not state.peak_dynamic_mode:
            # Manual Mode
            state.peak_req_velocity = state.peak_base_velocity
            state.peak_req_z_score = state.peak_base_z
            return

        # 3. Scale minimum velocity & Z-score by streamer tier
        if tier == "SMALL":
            # Small streams (<800 viewers) average 0.2 - 1.5 msg/s. A jump to 2.5 msg/s is huge.
            floor_vel = 1.2
            base_z = 2.3 + z_mod
            computed_vel = max(floor_vel, baseline_velocity * surge_mult)
        elif tier == "MEDIUM":
            # Medium streams (800 - 4k viewers) average 1.5 - 5 msg/s.
            floor_vel = 3.5
            base_z = 2.6 + z_mod
            computed_vel = max(floor_vel, baseline_velocity * surge_mult)
        elif tier == "LARGE":
            # Large streams (4k - 15k viewers) average 5 - 15 msg/s.
            floor_vel = 7.5
            base_z = 2.9 + z_mod
            computed_vel = max(floor_vel, baseline_velocity * surge_mult)
        else: # MEGA (Jynxzi, Kai Cenat, etc.)
            # Mega streams (15k+ viewers) average 15 - 50+ msg/s.
            floor_vel = 12.0
            base_z = 3.2 + z_mod
            computed_vel = max(floor_vel, baseline_velocity * surge_mult)

        # 4. Audio Scream Boost
        # If the streamer is screaming/laughing loudly (loudness > -17.5 dB), lower threshold requirements
        if state.peak_audio_boost and loudness_db > -17.5:
            base_z -= 0.35
            computed_vel *= 0.82

        # 5. Chat Hype & Emote Boost
        # If chat is collective pure hype (>= 50% hype/emote messages), lower threshold
        if state.peak_hype_boost and hype_density >= 0.50:
            base_z -= 0.25
            computed_vel *= 0.85

        state.peak_req_velocity = round(max(1.0, computed_vel), 1)
        state.peak_req_z_score = round(max(1.5, base_z), 2)

    def tick(self):
        """Called every second to calculate velocity, baseline, Z-score and check triggers."""
        now = time.time()

        # Purge message timestamps older than 180s (3 min window for baseline)
        self.timestamps = [t for t in self.timestamps if now - t <= 180.0]

        # Calculate instantaneous velocity: messages in the last 5 seconds (converted to msgs/sec)
        recent_count = sum(1 for t in self.timestamps if now - t <= 5.0)
        current_velocity = recent_count / 5.0
        state.msg_velocity = current_velocity

        # Compute chat hype density
        state.chat_hype_density = self._calculate_hype_density()

        # Compute 5-second bucket history across the 3-minute window
        if len(self.timestamps) > 10:
            bins = np.arange(now - 180.0, now, 5.0)
            hist, _ = np.histogram(self.timestamps, bins=bins)
            velocities = hist / 5.0

            if len(velocities) > 5:
                mean = float(np.mean(velocities))
                std = float(np.std(velocities))
                state.baseline_velocity = mean

                # Compute Z-score
                if std > 0.1:
                    z_score = (current_velocity - mean) / std
                else:
                    z_score = 0.0
                state.current_z_score = z_score

                # Calculate dynamic requirements based on streamer and live stream signals
                audio_loudness_db = self._analyze_recent_audio_loudness()
                state.peak_detected_audio_loudness = audio_loudness_db
                self._compute_dynamic_requirements(mean, audio_loudness_db, state.chat_hype_density)

                self._evaluate_trigger(now, z_score, current_velocity, audio_loudness_db)
            else:
                state.current_z_score = 0.0
        else:
            state.baseline_velocity = current_velocity
            state.current_z_score = 0.0
            # Update baseline requirements with default estimates
            self._compute_dynamic_requirements(current_velocity, -22.0, state.chat_hype_density)

    def _evaluate_trigger(self, now: float, z_score: float, velocity: float, audio_loudness_db: float):
        cooldown = settings.PEAK_COOLDOWN_SECONDS

        # Compare against dynamic stream-adaptive thresholds
        is_spike = (z_score >= state.peak_req_z_score) and (velocity >= state.peak_req_velocity)

        if is_spike and (now - self.last_peak_time >= cooldown):
            self.last_peak_time = now
            self._create_peak_entry(now, z_score, velocity, audio_loudness_db)

    def _analyze_recent_audio_loudness(self) -> float:
        """
        Samples the most recent buffer chunk to compute audio RMS decibel levels (screaming/laughing).
        """
        try:
            buffer_files = sorted(list(settings.BUFFER_DIR.glob("*.ts")), key=lambda p: p.stat().st_mtime)
            if not buffer_files:
                return -24.0

            latest_seg = buffer_files[-1]
            temp_wav = settings.BUFFER_DIR / "temp_loudness.wav"

            # Extract 2s audio to wav
            cmd = [
                "ffmpeg", "-y",
                "-i", str(latest_seg),
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                str(temp_wav)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if temp_wav.exists():
                import wave
                with wave.open(str(temp_wav), "rb") as wf:
                    frames = wf.readframes(wf.getnframes())
                    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                temp_wav.unlink()

                # Calculate RMS dB
                rms = np.sqrt(np.mean(audio**2))
                if rms > 0:
                    db = 20 * np.log10(rms)
                    return round(float(db), 1)
        except Exception:
            pass

        return -22.0

    def _create_peak_entry(self, timestamp: float, z_score: float, velocity: float, loudness_db: float):
        self.peak_counter += 1
        peak_id = f"PK-{self.peak_counter}"
        time_str = datetime.now().strftime("%H:%M:%S")

        # Classify audio intensity: High (Loud scream/laugh), Medium, Normal
        intensity = "HIGH (Scream/Hype)" if loudness_db > -17.5 else ("MEDIUM" if loudness_db > -24.0 else "NORMAL")

        peak_entry = {
            "peak_id": peak_id,
            "time": time_str,
            "z_score": round(z_score, 2),
            "req_z_score": state.peak_req_z_score,
            "velocity": round(velocity, 1),
            "req_velocity": state.peak_req_velocity,
            "streamer_tier": state.peak_active_tier,
            "hype_density": int(state.chat_hype_density * 100),
            "loudness_db": loudness_db,
            "intensity": intensity,
            "timestamp": timestamp,
            "status": "READY" # READY, PROCESSING, COMPLETED
        }

        # Hold max 10 peaks in a queue
        state.add_peak(peak_entry)
        state.add_col1_log(
            f"⚡ PEAK QUEUED: {peak_id} | {velocity:.1f} msg/s (req ≥{state.peak_req_velocity}) | "
            f"Z={z_score:.2f} (req ≥{state.peak_req_z_score}) | Tier: {state.peak_active_tier} | "
            f"Hype: {int(state.chat_hype_density*100)}% | Audio: {loudness_db}dB ({intensity})"
        )

        # Auto-process if enabled and no active clip is currently pending review/processing
        if (state.auto_process or settings.AUTO_PROCESS_PEAKS) and self.on_peak_detected_callback:
            if state.active_clip_id is None:
                peak_entry["status"] = "PROCESSING"
                self.on_peak_detected_callback(peak_entry)
