import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from pydantic import BaseModel

class AppState:
    def __init__(self):
        # Overall Stream & System
        self.stream_online: bool = False
        self.stream_title: str = ""
        self.stream_uptime: str = "00:00:00"
        self.cpu_usage_pct: float = 0.0
        self.buffer_size_mb: float = 0.0
        self.youtube_channel: str = "CONNECTED"

        # Streamer & Viewers Info
        self.stream_viewers: int = 0
        self.stream_game: str = ""
        self.chat_hype_density: float = 0.0

        # Dynamic Peak Calibration
        self.peak_dynamic_mode: bool = True
        self.peak_streamer_tier: str = "AUTO" # AUTO, MEGA, LARGE, MEDIUM, SMALL
        self.peak_sensitivity: str = "NORMAL" # LOW, NORMAL, HIGH
        self.peak_base_z: float = 3.0
        self.peak_base_velocity: float = 10.0
        self.peak_audio_boost: bool = True
        self.peak_hype_boost: bool = True

        # Computed Live Requirements
        self.peak_active_tier: str = "MEGA"
        self.peak_req_velocity: float = 10.0
        self.peak_req_z_score: float = 3.0
        self.peak_detected_audio_loudness: float = -24.0

        # Automation Toggles
        self.auto_process: bool = False
        self.auto_upload: bool = False
        self.is_processing: bool = False
        self.is_monitoring: bool = True

        # AI Budget Tracker
        self.ai_calls_today: int = 0
        self.ai_calls_last_minute: List[float] = []
        self.last_ai_reset_day: int = datetime.now().day

        # Column 1: Peak Detection State
        self.col1_status: str = "INITIALIZING" # MONITORING, SPIKE_DETECTED, COOLDOWN
        self.msg_velocity: float = 0.0
        self.baseline_velocity: float = 0.0
        self.current_z_score: float = 0.0
        self.recent_chat: List[Dict[str, str]] = [] # [{'time': '14:20:01', 'user': 'w_user', 'msg': 'W'}]
        self.detected_peaks: List[Dict[str, Any]] = []
        self.col1_logs: List[str] = []

        # Column 2: Facecam & Framing State
        self.col2_status: str = "IDLE" # IDLE, DETECTING, LOCKED, CROPPING, OK
        self.last_known_facecam: Optional[Dict[str, int]] = None # {'x': 120, 'y': 40, 'w': 320, 'h': 240}
        self.current_facecam_box: Optional[Dict[str, int]] = None
        self.current_gameplay_box: Optional[Dict[str, int]] = None
        self.layout_locked: bool = False
        self.frame_dimensions: Dict[str, int] = {"w": 1280, "h": 720}
        self.facecam_mode: str = "AUTO" # AUTO, BACKGROUND, NO_BACKGROUND
        self.facecam_has_background: bool = True
        self.facecam_rule_applied: str = "RULE 1: FIT BOX" # "RULE 1: FIT BOX" or "RULE 2: 50% FACE"
        self.edge_confidence: float = 0.0
        self.using_fallback: bool = False
        self.col2_has_preview: bool = False
        self.preview_version: int = 1
        self.col2_logs: List[str] = []

        # Column 3: Speech & Rendering State
        self.col3_status: str = "IDLE" # IDLE, TRANSCRIBING, RENDERING, COMPLETED, OK
        self.current_transcript: List[Dict[str, Any]] = [] # [{'start': 0.0, 'end': 1.5, 'text': '...'}]
        self.censored_count: int = 0
        self.last_render_time_sec: float = 0.0
        self.col3_logs: List[str] = []

        # Clips & Review Queue
        self.clips: Dict[str, Dict[str, Any]] = {} # clip_id -> clip_data
        self.active_clip_id: Optional[str] = None # Current clip that finished and is ready for review

    def add_col1_log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.col1_logs.append(f"[{timestamp}] {msg}")
        if len(self.col1_logs) > 50:
            self.col1_logs.pop(0)

    def add_col2_log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.col2_logs.append(f"[{timestamp}] {msg}")
        if len(self.col2_logs) > 50:
            self.col2_logs.pop(0)

    def add_col3_log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.col3_logs.append(f"[{timestamp}] {msg}")
        if len(self.col3_logs) > 50:
            self.col3_logs.pop(0)

    def add_peak(self, peak_entry: Dict[str, Any]):
        self.detected_peaks.append(peak_entry)
        # Max 10 peaks in FIFO queue
        if len(self.detected_peaks) > 10:
            self.detected_peaks.pop(0)

    def remove_peak(self, peak_id: str):
        self.detected_peaks = [p for p in self.detected_peaks if p.get("peak_id") != peak_id]

    def clear_peaks(self):
        self.detected_peaks = []

    def add_clip(self, clip_id: str, clip_record: Dict[str, Any]):
        self.clips[clip_id] = clip_record
        # Max 10 clips in FIFO queue
        if len(self.clips) > 10:
            oldest_id = next(iter(self.clips))
            del self.clips[oldest_id]

    def remove_clip(self, clip_id: str):
        if clip_id in self.clips:
            del self.clips[clip_id]
        if self.active_clip_id == clip_id:
            self.active_clip_id = None
        self.reset_columns_2_and_3()

    def clear_active_clip(self):
        self.active_clip_id = None
        self.reset_columns_2_and_3()

    def reset_all_columns(self, channel_name: str = ""):
        """
        Completely clears all 3 columns (Peak Detection, Facecam/Framing, Speech/Rendering)
        when the target streamer is changed.
        """
        from backend.core.config import settings
        now_str = datetime.now().strftime('%H:%M:%S')
        streamer_label = f"#{channel_name}" if channel_name else "new streamer"

        # Column 1: Peak Detection & Chat State
        self.col1_status = "MONITORING" if self.is_monitoring else "PAUSED"
        self.msg_velocity = 0.0
        self.baseline_velocity = 0.0
        self.current_z_score = 0.0
        self.stream_viewers = 0
        self.chat_hype_density = 0.0
        self.peak_detected_audio_loudness = -24.0
        self.recent_chat = []
        self.detected_peaks = []
        self.col1_logs = [f"[{now_str}] Channel changed to {streamer_label}. Peak detector and chat cleared."]

        # Column 2: Facecam & Framing State
        self.col2_status = "IDLE"
        self.current_facecam_box = None
        self.current_gameplay_box = None
        self.layout_locked = False
        self.last_known_facecam = None
        self.edge_confidence = 0.0
        self.using_fallback = False
        self.col2_has_preview = False
        self.preview_version += 1
        self.col2_logs = [f"[{now_str}] Facecam cache and preview cleared for {streamer_label}."]

        # Column 3: Speech & Rendering State
        self.col3_status = "IDLE"
        self.current_transcript = []
        self.censored_count = 0
        self.last_render_time_sec = 0.0
        self.col3_logs = [f"[{now_str}] Speech & rendering transcript cleared for {streamer_label}."]

        # Active clip & review queue
        self.active_clip_id = None
        self.is_processing = False

        # Clean preview image files from disk
        for img_path in [settings.CLIPS_DIR / "preview_facecam.jpg", settings.CLIPS_DIR / "preview_gameplay.jpg", settings.CLIPS_DIR / "preview_full_frame.jpg"]:
            try:
                if img_path.exists():
                    img_path.unlink()
            except Exception:
                pass

    def reset_columns_2_and_3(self):
        """
        Resets Column 3 to clean IDLE state after a clip is discarded or uploaded.
        Preserves Column 2's locked 1-take layout & custom Red/Blue crop boxes so they never change back.
        """
        from backend.core.config import settings
        if self.layout_locked and self.current_facecam_box:
            self.col2_status = "LOCKED"
            self.col2_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Layout boxes locked & preserved for next clip.")
            if len(self.col2_logs) > 50:
                self.col2_logs.pop(0)
        else:
            self.col2_status = "IDLE"
            self.current_facecam_box = None
            self.current_gameplay_box = None
            self.last_known_facecam = None
            self.edge_confidence = 0.0
            self.using_fallback = False
            self.col2_has_preview = False
            self.preview_version += 1
            self.col2_logs = [f"[{datetime.now().strftime('%H:%M:%S')}] State reset. Waiting for peak selection."]
            for img_path in [settings.CLIPS_DIR / "preview_facecam.jpg", settings.CLIPS_DIR / "preview_gameplay.jpg", settings.CLIPS_DIR / "preview_full_frame.jpg"]:
                try:
                    if img_path.exists():
                        img_path.unlink()
                except Exception:
                    pass

        self.col3_status = "IDLE"
        self.current_transcript = []
        self.censored_count = 0
        self.last_render_time_sec = 0.0
        self.col3_logs = [f"[{datetime.now().strftime('%H:%M:%S')}] State reset. Ready for next clip."]
        self.active_clip_id = None

    def check_ai_rate_limit(self, max_per_min: int, max_per_day: int) -> bool:
        """Returns True if AI call is permitted under current limits."""
        now = time.time()
        current_day = datetime.now().day

        # Reset daily counter at midnight
        if current_day != self.last_ai_reset_day:
            self.ai_calls_today = 0
            self.last_ai_reset_day = current_day

        if self.ai_calls_today >= max_per_day:
            return False

        # Filter out calls older than 60s
        self.ai_calls_last_minute = [t for t in self.ai_calls_last_minute if now - t < 60.0]
        if len(self.ai_calls_last_minute) >= max_per_min:
            return False

        return True

    def record_ai_call(self):
        now = time.time()
        self.ai_calls_today += 1
        self.ai_calls_last_minute.append(now)

    def to_dict(self) -> Dict[str, Any]:
        from backend.core.config import settings
        return {
            "channel": settings.TWITCH_CHANNEL,
            "stream_online": self.stream_online,
            "stream_title": self.stream_title,
            "stream_uptime": self.stream_uptime,
            "stream_viewers": self.stream_viewers,
            "stream_game": self.stream_game,
            "chat_hype_density": round(self.chat_hype_density, 2),
            "cpu_usage_pct": self.cpu_usage_pct,
            "buffer_size_mb": self.buffer_size_mb,
            "youtube_channel": self.youtube_channel,
            "youtube_authenticated": bool(self.youtube_channel and self.youtube_channel != "NOT CONNECTED"),
            "youtube_status": self.youtube_channel,
            "auto_process": self.auto_process,
            "auto_upload": self.auto_upload,
            "is_processing": self.is_processing,
            "is_monitoring": self.is_monitoring,
            "ai_calls_today": self.ai_calls_today,
            "active_clip_id": self.active_clip_id,
            "active_clip": self.clips.get(self.active_clip_id),
            "peak_calibration": {
                "dynamic_mode": self.peak_dynamic_mode,
                "streamer_tier": self.peak_streamer_tier,
                "active_tier": self.peak_active_tier,
                "sensitivity": self.peak_sensitivity,
                "base_z": round(self.peak_base_z, 1),
                "base_velocity": round(self.peak_base_velocity, 1),
                "audio_boost": self.peak_audio_boost,
                "hype_boost": self.peak_hype_boost,
                "req_velocity": round(self.peak_req_velocity, 1),
                "req_z_score": round(self.peak_req_z_score, 2),
                "audio_loudness": self.peak_detected_audio_loudness
            },
            "all_processes_ok": (
                self.col1_status in ["MONITORING", "READY", "OK"] and
                self.col2_status in ["READY", "OK", "IDLE", "LOCKED"] and
                self.col3_status in ["COMPLETED", "OK", "IDLE"] and
                self.active_clip_id is not None
            ),
            "col1": {
                "status": self.col1_status,
                "msg_velocity": round(self.msg_velocity, 1),
                "baseline_velocity": round(self.baseline_velocity, 1),
                "current_z_score": round(self.current_z_score, 2),
                "recent_chat": self.recent_chat[-15:],
                "detected_peaks": self.detected_peaks[-10:],
                "logs": self.col1_logs[-15:]
            },
            "col2": {
                "status": self.col2_status,
                "current_facecam_box": self.current_facecam_box,
                "current_gameplay_box": self.current_gameplay_box,
                "layout_locked": self.layout_locked,
                "frame_dimensions": self.frame_dimensions,
                "last_known_facecam": self.last_known_facecam,
                "facecam_mode": self.facecam_mode,
                "has_background": self.facecam_has_background,
                "rule_applied": self.facecam_rule_applied,
                "edge_confidence": round(self.edge_confidence, 2),
                "using_fallback": self.using_fallback,
                "has_preview": bool(self.col2_has_preview and (settings.CLIPS_DIR / "preview_facecam.jpg").exists()),
                "preview_version": self.preview_version,
                "facecam_preview_url": "/media/preview_facecam.jpg" if (self.col2_has_preview and (settings.CLIPS_DIR / "preview_facecam.jpg").exists()) else None,
                "gameplay_preview_url": "/media/preview_gameplay.jpg" if (self.col2_has_preview and (settings.CLIPS_DIR / "preview_gameplay.jpg").exists()) else None,
                "full_frame_preview_url": "/media/preview_full_frame.jpg" if (self.col2_has_preview and (settings.CLIPS_DIR / "preview_full_frame.jpg").exists()) else None,
                "logs": self.col2_logs[-15:]
            },
            "col3": {
                "status": self.col3_status,
                "current_transcript": self.current_transcript,
                "censored_count": self.censored_count,
                "last_render_time_sec": round(self.last_render_time_sec, 1),
                "logs": self.col3_logs[-15:]
            },
            "clips_count": len(self.clips)
        }

state = AppState()
