import asyncio
import os
import json
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    import psutil
except ImportError:
    psutil = None

from backend.core.config import settings
from backend.core.state import state
from backend.core.events import manager
from backend.ingestion.twitch_irc import TwitchIRCClient
from backend.ingestion.stream_buffer import StreamRollingBuffer
from backend.pipeline.peak_detector import PeakDetector
from backend.pipeline.clip_orchestrator import ClipOrchestrator

# Global services
stream_buffer = StreamRollingBuffer(settings.TWITCH_CHANNEL)
orchestrator = ClipOrchestrator(stream_buffer)

def handle_peak_event(peak_info):
    asyncio.create_task(orchestrator.process_peak_event(peak_info))

peak_detector = PeakDetector(on_peak_detected_callback=handle_peak_event)
twitch_irc = TwitchIRCClient(settings.TWITCH_CHANNEL, on_message_callback=peak_detector.register_message)

async def background_tick_loop():
    """Runs periodic state updates and broadcasts to WebSocket clients."""
    while True:
        try:
            if state.is_monitoring:
                peak_detector.tick()

                # Auto-process queued peaks if auto_process is toggled ON and no clip is active
                if state.auto_process and not state.is_processing and not orchestrator.is_processing and state.active_clip_id is None:
                    ready_peak = next((p for p in state.detected_peaks if p.get("status") == "READY"), None)
                    if ready_peak:
                        ready_peak["status"] = "PROCESSING"
                        state.is_processing = True
                        state.add_col1_log(f"Auto-Processing queued peak: {ready_peak['peak_id']}")
                        asyncio.create_task(orchestrator.process_peak_event(ready_peak))

            # Sample system CPU usage if psutil is available
            if psutil is not None:
                state.cpu_usage_pct = psutil.cpu_percent(interval=None)
            else:
                state.cpu_usage_pct = 15.0
            # Broadcast state
            await manager.broadcast(state.to_dict())
        except Exception:
            pass
        await asyncio.sleep(0.5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    state.add_col1_log("AutoClipper background engine starting...")
    await stream_buffer.start()
    await twitch_irc.start()
    tick_task = asyncio.create_task(background_tick_loop())
    yield
    # Shutdown
    state.add_col1_log("AutoClipper background engine stopping...")
    tick_task.cancel()
    await twitch_irc.stop()
    await stream_buffer.stop()

app = FastAPI(title="AutoClipper API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount video files for frontend playback
app.mount("/media", StaticFiles(directory=str(settings.CLIPS_DIR)), name="media")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial state immediately
        await websocket.send_json(state.to_dict())
        while True:
            # Keep socket open and receive any ping or client messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

@app.get("/api/status")
async def get_status():
    return state.to_dict()

@app.get("/api/schedule/preview")
async def get_schedule_preview():
    return {
        "timezone": settings.YOUTUBE_TIMEZONE,
        "strategy": "1 post per day in peak engagement window",
        "calendar": scheduler.get_upcoming_schedule_preview(days=7)
    }

@app.post("/api/settings/auto_process")
async def toggle_auto_process(payload: dict = None):
    if payload and "enabled" in payload:
        state.auto_process = bool(payload["enabled"])
    else:
        state.auto_process = not state.auto_process
    settings.AUTO_PROCESS_PEAKS = state.auto_process
    status_str = "ENABLED" if state.auto_process else "DISABLED"
    state.add_col1_log(f"Auto-Process toggled {status_str} from navbar.")
    await manager.broadcast(state.to_dict())
    return {"auto_process": state.auto_process}

@app.post("/api/settings/auto_upload")
async def toggle_auto_upload(payload: dict = None):
    if payload and "enabled" in payload:
        state.auto_upload = bool(payload["enabled"])
    else:
        state.auto_upload = not state.auto_upload
    settings.AUTO_UPLOAD_ENABLED = state.auto_upload
    status_str = "ENABLED" if state.auto_upload else "DISABLED"
    state.add_col3_log(f"Auto-Upload toggled {status_str} from navbar.")
    await manager.broadcast(state.to_dict())
    return {"auto_upload": state.auto_upload}

@app.post("/api/settings/toggle_monitoring")
async def toggle_monitoring(payload: dict = None):
    target = bool(payload["enabled"]) if (payload and "enabled" in payload) else not state.is_monitoring
    state.is_monitoring = target
    if target:
        state.col1_status = "MONITORING"
        state.add_col1_log("Tracking engine STARTED (RUNNING).")
        await stream_buffer.start()
        await twitch_irc.start()
    else:
        state.col1_status = "PAUSED"
        state.stream_online = False
        state.msg_velocity = 0.0
        state.add_col1_log("Tracking engine PAUSED (OFF). Streamer and chat tracking stopped.")
        await twitch_irc.stop()
        await stream_buffer.stop()
    await manager.broadcast(state.to_dict())
    return {"is_monitoring": state.is_monitoring}

@app.post("/api/facecam/mode")
async def set_facecam_mode(payload: dict):
    mode = payload.get("mode", "AUTO").upper()
    if mode in ["AUTO", "BACKGROUND", "NO_BACKGROUND"]:
        state.facecam_mode = mode
        state.add_col2_log(f"Facecam framing mode switched to: {mode}")
        await manager.broadcast(state.to_dict())
    return {
        "facecam_mode": state.facecam_mode,
        "has_background": state.facecam_has_background,
        "rule_applied": state.facecam_rule_applied
    }

@app.get("/api/youtube/status")
async def get_youtube_status():
    from backend.uploader.youtube import uploader
    is_authed = uploader.is_authenticated()
    return {
        "authenticated": is_authed,
        "status": "CONNECTED" if is_authed else "NOT CONNECTED"
    }

@app.post("/api/youtube/reload")
async def reload_youtube_auth():
    from backend.uploader.youtube import uploader
    try:
        uploader.reload_credentials()
        is_authed = uploader.is_authenticated()
    except Exception:
        is_authed = False
    state.youtube_channel = "CONNECTED" if is_authed else "NOT CONNECTED"
    state.add_col3_log(f"Reloaded YouTube credentials. Status: {state.youtube_channel}")
    await manager.broadcast(state.to_dict())
    return {"status": "RELOADED", "authenticated": is_authed}

@app.get("/api/clips")
async def get_clips():
    return list(state.clips.values())

@app.get("/api/clips/{clip_id}")
async def get_clip_details(clip_id: str):
    clip = state.clips.get(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    return clip

@app.post("/api/clips/{clip_id}/metadata")
async def update_clip_metadata(clip_id: str, payload: dict):
    clip = state.clips.get(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    if "title" in payload and payload["title"] is not None:
        clip["title"] = str(payload["title"]).strip()
    if "description" in payload and payload["description"] is not None:
        clip["description"] = str(payload["description"]).strip()

    state.add_col3_log(f"Metadata updated for {clip_id}: Title='{clip.get('title', '')[:30]}...'")
    return {"status": "UPDATED", "clip": clip}

@app.post("/api/clips/{clip_id}/approve")
async def approve_clip(clip_id: str):
    clip = state.clips.get(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    clip["status"] = "APPROVED"
    asyncio.create_task(orchestrator.dispatch_upload(clip_id, immediate=False))
    return {"status": "APPROVED", "clip_id": clip_id}

@app.post("/api/clips/{clip_id}/upload_now")
async def upload_clip_now(clip_id: str):
    clip = state.clips.get(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    clip["status"] = "UPLOADING"
    asyncio.create_task(orchestrator.dispatch_upload(clip_id, immediate=True))
    return {"status": "UPLOADING", "clip_id": clip_id}

@app.post("/api/clips/{clip_id}/reject")
@app.delete("/api/clips/{clip_id}")
async def reject_clip(clip_id: str):
    orchestrator.reject_clip(clip_id)
    state.reset_columns_2_and_3()
    await manager.broadcast(state.to_dict())
    return {"status": "REJECTED", "clip_id": clip_id}

@app.post("/api/clips/{clip_id}/dismiss")
async def dismiss_clip(clip_id: str):
    if state.active_clip_id == clip_id:
        state.active_clip_id = None
    state.reset_columns_2_and_3()
    await manager.broadcast(state.to_dict())
    return {"status": "DISMISSED", "clip_id": clip_id}

@app.post("/api/clips/{clip_id}/generate_ai")
async def generate_clip_ai(clip_id: str):
    clip = state.clips.get(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    transcript = clip.get("transcript_text", "")
    if not transcript and state.current_transcript:
        transcript = " ".join(t.get("text", "") for t in state.current_transcript)
    if not transcript:
        transcript = "Insane hype moment live on Twitch"

    from backend.pipeline.title_generator import title_gen
    clip_display_name = clip.get("name") or clip.get("date") or clip_id
    state.add_col3_log(f"Triggering AI generation for clip [{clip_display_name}]...")
    new_meta = title_gen.generate_metadata_from_text(transcript, peak_info={"velocity": 25.0})

    clip["title"] = new_meta["title"]
    clip["description"] = new_meta["description"]
    clip["tags"] = new_meta["tags"]

    state.add_col3_log(f"AI details generated: \"{clip['title']}\"")
    await manager.broadcast(state.to_dict())
    return {"status": "SUCCESS", "clip": clip, "metadata": new_meta}

@app.delete("/api/peaks/{peak_id}")
@app.post("/api/peaks/{peak_id}/delete")
async def delete_peak(peak_id: str):
    state.remove_peak(peak_id)
    state.add_col1_log(f"Peak {peak_id} dismissed from queue.")
    await manager.broadcast(state.to_dict())
    return {"status": "DELETED", "peak_id": peak_id}

@app.delete("/api/peaks")
@app.post("/api/peaks/clear")
async def clear_all_peaks():
    count = len(state.detected_peaks)
    state.clear_peaks()
    state.add_col1_log(f"Cleared all {count} queued peaks.")
    await manager.broadcast(state.to_dict())
    return {"status": "CLEARED", "count": count}

PROFILES_FILE = settings.BASE_DIR / "config" / "streamer_profiles.json"

def load_streamer_profile(channel: str):
    if PROFILES_FILE.exists():
        try:
            with open(PROFILES_FILE, "r") as f:
                data = json.load(f)
                return data.get(channel.lower())
        except Exception:
            pass
    return None

def save_streamer_profile(channel: str, profile: dict):
    PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if PROFILES_FILE.exists():
        try:
            with open(PROFILES_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data[channel.lower()] = profile
    try:
        with open(PROFILES_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print("Failed to save streamer profile:", e)

@app.get("/api/settings/peak")
async def get_peak_settings():
    return {
        "channel": settings.TWITCH_CHANNEL,
        "calibration": state.to_dict()["peak_calibration"]
    }

@app.post("/api/settings/peak")
async def update_peak_settings(payload: dict):
    if "dynamic_mode" in payload and payload["dynamic_mode"] is not None:
        state.peak_dynamic_mode = bool(payload["dynamic_mode"])
    if "streamer_tier" in payload and payload["streamer_tier"]:
        state.peak_streamer_tier = str(payload["streamer_tier"]).upper()
    if "sensitivity" in payload and payload["sensitivity"]:
        state.peak_sensitivity = str(payload["sensitivity"]).upper()
    if "base_z" in payload and payload["base_z"] is not None:
        state.peak_base_z = float(payload["base_z"])
    if "base_velocity" in payload and payload["base_velocity"] is not None:
        state.peak_base_velocity = float(payload["base_velocity"])
    if "audio_boost" in payload and payload["audio_boost"] is not None:
        state.peak_audio_boost = bool(payload["audio_boost"])
    if "hype_boost" in payload and payload["hype_boost"] is not None:
        state.peak_hype_boost = bool(payload["hype_boost"])

    # Persist streamer-specific profile
    save_streamer_profile(settings.TWITCH_CHANNEL, {
        "dynamic_mode": state.peak_dynamic_mode,
        "streamer_tier": state.peak_streamer_tier,
        "sensitivity": state.peak_sensitivity,
        "base_z": state.peak_base_z,
        "base_velocity": state.peak_base_velocity,
        "audio_boost": state.peak_audio_boost,
        "hype_boost": state.peak_hype_boost,
    })

    mode_label = "DYNAMIC ADAPTIVE" if state.peak_dynamic_mode else "MANUAL FIXED"
    state.add_col1_log(
        f"Dynamic peak requirements updated for #{settings.TWITCH_CHANNEL}: {mode_label} "
        f"(Tier: {state.peak_streamer_tier}, Sens: {state.peak_sensitivity}, Base Z: {state.peak_base_z})"
    )
    await manager.broadcast(state.to_dict())
    return {"status": "UPDATED", "calibration": state.to_dict()["peak_calibration"]}

@app.post("/api/channel")
async def switch_channel(payload: dict):
    new_channel = payload.get("channel", "").strip().lower().lstrip("#")
    if not new_channel:
        raise HTTPException(status_code=400, detail="Channel name cannot be empty")

    settings.TWITCH_CHANNEL = new_channel

    # Reset chat velocity & history in peak detector for fair calibration
    peak_detector.reset()

    # Completely clear all 3 columns (peaks/chat, facecam/framing, speech/transcript)
    state.reset_all_columns(new_channel)
    state.add_col1_log(f"Switched target streamer to #{new_channel}. All 3 columns cleared.")

    # Clear old stream buffer segments from disk
    stream_buffer.clear_buffer()

    # Load custom profile for this streamer if saved, else default to auto dynamic
    profile = load_streamer_profile(new_channel)
    if profile:
        state.peak_dynamic_mode = profile.get("dynamic_mode", True)
        state.peak_streamer_tier = profile.get("streamer_tier", "AUTO")
        state.peak_sensitivity = profile.get("sensitivity", "NORMAL")
        state.peak_base_z = profile.get("base_z", 3.0)
        state.peak_base_velocity = profile.get("base_velocity", 10.0)
        state.peak_audio_boost = profile.get("audio_boost", True)
        state.peak_hype_boost = profile.get("hype_boost", True)
        state.add_col1_log(f"Loaded calibrated profile for #{new_channel} (Tier: {state.peak_streamer_tier}, Sens: {state.peak_sensitivity})")
    else:
        state.peak_dynamic_mode = True
        state.peak_streamer_tier = "AUTO"
        state.peak_sensitivity = "NORMAL"
        state.add_col1_log(f"Auto-calibrating dynamic requirements for #{new_channel} based on live stream baseline & chatters...")

    # Reconnect Twitch IRC
    await twitch_irc.stop()
    twitch_irc.channel = new_channel
    await twitch_irc.start()

    # Reconnect Stream Buffer
    await stream_buffer.stop()
    stream_buffer.channel = new_channel
    await stream_buffer.start()

    await manager.broadcast(state.to_dict())
    return {"status": "SWITCHED", "channel": new_channel}

@app.post("/api/peaks/{peak_id}/process")
async def process_specific_peak(peak_id: str):
    # Enforce only 1 clip at a time
    if state.active_clip_id is not None:
        active_clip_obj = state.clips.get(state.active_clip_id, {})
        clip_name = active_clip_obj.get("name") or active_clip_obj.get("date") or state.active_clip_id
        raise HTTPException(
            status_code=400,
            detail=f"Only 1 clip at a time permitted. Clip [{clip_name}] is currently pending review. Please review, upload, or discard it first."
        )

    if orchestrator.is_processing:
        raise HTTPException(status_code=400, detail="A clip is currently being processed. Please wait.")

    target_peak = next((p for p in state.detected_peaks if p.get("peak_id") == peak_id), None)
    if not target_peak:
        raise HTTPException(status_code=404, detail="Peak ID not found in queue")

    target_peak["status"] = "PROCESSING"
    state.add_col1_log(f"Processing user-selected peak: {peak_id}")
    asyncio.create_task(orchestrator.process_peak_event(target_peak))
    await manager.broadcast(state.to_dict())
    return {"status": "PROCESSING", "peak_id": peak_id}

@app.post("/api/transcript/update")
async def update_transcript(payload: dict):
    new_transcript = payload.get("transcript", [])
    state.current_transcript = new_transcript
    state.add_col3_log(f"Transcript updated by user ({len(new_transcript)} lines).")
    return {"status": "UPDATED"}

@app.post("/api/trigger_test_peak")
async def trigger_test_peak():
    """Manual trigger to add a test peak to the queue with a unique ID."""
    import time
    peak_detector.peak_counter += 1
    p_id = f"PK-{peak_detector.peak_counter}"
    peak_info = {
        "peak_id": p_id,
        "time": "MANUAL",
        "z_score": 3.8,
        "velocity": 92.0,
        "loudness_db": -14.2,
        "intensity": "HIGH (Scream/Hype)",
        "part": 1,
        "timestamp": time.time(),
        "status": "READY"
    }
    state.add_peak(peak_info)
    state.add_col1_log(f"Manual peak spike queued: {p_id} (Click Process to cut)")
    return {"status": "QUEUED", "peak_id": p_id}

@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)

# Serve compiled frontend SPA at root AFTER all API and WebSocket routes
dist_dir = settings.BASE_DIR / "frontend" / "dist"
if dist_dir.exists():
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
