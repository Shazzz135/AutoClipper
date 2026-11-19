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
from backend.core.scheduler import scheduler
from backend.ingestion.twitch_irc import TwitchIRCClient
from backend.ingestion.stream_buffer import StreamRollingBuffer
from backend.pipeline.peak_detector import PeakDetector
from backend.pipeline.clip_orchestrator import ClipOrchestrator
from backend.pipeline.facecam_cropper import facecam_cropper
from backend.uploader.youtube import uploader

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

                # Capture ONE frame once for Column 2 so it lasts the entire time without ever re-updating
                if not state.col2_has_preview and not state.layout_locked and not state.is_processing:
                    segments = sorted(settings.BUFFER_DIR.glob("seg_*.ts"), key=lambda x: x.stat().st_mtime)
                    if segments and segments[-1].stat().st_size > 30000:
                        await asyncio.to_thread(facecam_cropper.refresh_live_stream_frame)

                # Auto-process queued peaks if auto_process is toggled ON and no clip is active
                if state.auto_process and not state.is_processing and not orchestrator.is_processing and state.active_clip_id is None:
                    ready_peak = next((p for p in state.detected_peaks if p.get("status") == "READY"), None)
                    if ready_peak:
                        ready_peak["status"] = "PROCESSING"
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

def _cleanup_orphan_clip_files():
    """Purges any old orphaned clip files on startup to keep SSD clean."""
    for d in [settings.CLIPS_DIR, settings.BUFFER_DIR]:
        for pattern in ["Clip_*", "clip_*"]:
            for f in d.glob(pattern):
                try:
                    f.unlink()
                except Exception:
                    pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: clean orphaned clips & detect active YT account + streamer
    _cleanup_orphan_clip_files()
    active_acc = uploader.detect_active_account()
    if active_acc:
        mapped_streamer = uploader.get_streamer_for_account(active_acc)
        if mapped_streamer:
            settings.TWITCH_CHANNEL = mapped_streamer
            stream_buffer.channel = mapped_streamer
            twitch_irc.channel = mapped_streamer
        state.add_col1_log(f"Active YouTube account: {active_acc} -> Tracking Twitch streamer #{settings.TWITCH_CHANNEL}")
    else:
        state.add_col1_log("AutoClipper background engine starting...")

    # Load saved Red & Blue boxes for the tracked streamer if present
    saved_fb, saved_gb = facecam_cropper.load_streamer_boxes(settings.TWITCH_CHANNEL)
    if saved_fb and saved_gb:
        state.current_facecam_box = saved_fb
        state.current_gameplay_box = saved_gb
        state.layout_locked = True
        state.col2_status = "LOCKED"
        state.facecam_rule_applied = "SAVED STREAMER PROFILE"
        state.add_col2_log(f"Loaded saved Red/Blue crop boxes for #{settings.TWITCH_CHANNEL}.")

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

    # If user just toggled Auto-Upload ON while a clip is already active, auto-create (if needed) and upload it
    if state.auto_upload and state.active_clip_id and state.active_clip_id in state.clips:
        active_clip = state.clips[state.active_clip_id]
        if active_clip.get("status") in ["PENDING_REVIEW", "STUDIO_EDITING"]:
            state.add_col3_log(f"Auto-Upload triggered for active clip {state.active_clip_id}...")
            asyncio.create_task(orchestrator.dispatch_upload(state.active_clip_id, immediate=False))

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

@app.post("/api/facecam/update_boxes")
async def update_crop_boxes(payload: dict):
    face_box = payload.get("face_box")
    game_box = payload.get("game_box")
    if not face_box or not game_box:
        raise HTTPException(status_code=400, detail="Missing face_box or game_box coordinates")

    try:
        crop_data = facecam_cropper.update_boxes_from_full_frame(face_box, game_box)
        state.facecam_rule_applied = "CUSTOM LOCKED BOXES"
        state.using_fallback = False
        state.layout_locked = True

        if state.active_clip_id and state.active_clip_id in state.clips:
            state.clips[state.active_clip_id]["crop_data"] = crop_data
            state.clips[state.active_clip_id]["base_face_box"] = crop_data["face_box"]

        fb = crop_data['face_box']
        gb = crop_data['game_crop']
        state.add_col2_log(
            f"Live Crop Boxes Applied & Locked: Red Face ({fb['w']}x{fb['h']} at {fb['x']},{fb['y']}), "
            f"Blue Game ({gb['w']}x{gb['h']} at {gb['x']},{gb['y']})."
        )
        await manager.broadcast(state.to_dict())
        return {"status": "UPDATED", "crop_data": crop_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/facecam/reset_ai")
async def reset_facecam_to_ai():
    try:
        crop_data = await asyncio.to_thread(facecam_cropper.reset_to_ai_guess)
        if state.active_clip_id and state.active_clip_id in state.clips:
            state.clips[state.active_clip_id]["crop_data"] = crop_data
            state.clips[state.active_clip_id]["base_face_box"] = crop_data["face_box"]
        state.col2_status = "LOCKED"
        state.add_col2_log("Re-ran 1-take AI layout guess and locked boxes.")
        await manager.broadcast(state.to_dict())
        return {"status": "RESET", "crop_data": crop_data, "col2": state.to_dict()["col2"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/facecam/init_preview")
async def init_facecam_preview():
    try:
        if not state.layout_locked or not state.col2_has_preview:
            crop_data = await asyncio.to_thread(facecam_cropper.reset_to_ai_guess)
            state.col2_status = "LOCKED"
        else:
            crop_data = {
                "face_box": state.current_facecam_box,
                "game_crop": state.current_gameplay_box
            }
        await manager.broadcast(state.to_dict())
        return {"status": "READY", "crop_data": crop_data, "col2": state.to_dict()["col2"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/youtube/status")
async def get_youtube_status():
    is_authed = uploader.is_authenticated()
    return {
        "authenticated": is_authed,
        "status": state.youtube_channel if is_authed else "NOT CONNECTED"
    }

@app.get("/api/youtube/accounts")
async def get_youtube_accounts():
    accounts = uploader.get_available_accounts()
    return {
        "accounts": accounts,
        "active_channel": state.youtube_channel,
        "tracked_streamer": settings.TWITCH_CHANNEL
    }

@app.get("/api/youtube/channel")
async def get_youtube_channel():
    accounts = uploader.get_available_accounts()
    active_acc = next((a for a in accounts if a.get("is_active")), None)
    channel_title = active_acc["name"] if active_acc else state.youtube_channel
    return {
        "authenticated": uploader.is_authenticated(),
        "channel_title": channel_title,
        "streamer": settings.TWITCH_CHANNEL
    }

@app.post("/api/youtube/switch")
async def switch_youtube_account(payload: dict):
    account_id = payload.get("account_id", "").strip()
    if not account_id:
        raise HTTPException(status_code=400, detail="Missing account_id")

    try:
        res = uploader.switch_account(account_id)
        target_streamer = res.get("streamer")
        if target_streamer and target_streamer.lower() != settings.TWITCH_CHANNEL.lower():
            await switch_channel({"channel": target_streamer})
        else:
            await manager.broadcast(state.to_dict())
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/youtube/reload")
async def reload_youtube_auth():
    try:
        uploader.reload_credentials()
        is_authed = uploader.is_authenticated()
    except Exception:
        is_authed = False
    active_acc = uploader.detect_active_account()
    state.youtube_channel = active_acc or ("CONNECTED" if is_authed else "NOT CONNECTED")
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
        return {"clip_id": clip_id, "status": "DISCARDED", "message": "Clip has been processed and discarded from SSD."}
    return clip

@app.post("/api/clips/{clip_id}/metadata")
async def update_clip_metadata(clip_id: str, payload: dict):
    clip = state.clips.get(clip_id)
    if not clip:
        return {"status": "DISCARDED", "message": "Clip already processed."}

    if "title" in payload and payload["title"] is not None:
        clip["title"] = str(payload["title"]).strip()
    if "description" in payload and payload["description"] is not None:
        clip["description"] = str(payload["description"]).strip()
    if "first_comment" in payload and payload["first_comment"] is not None:
        clip["first_comment"] = str(payload["first_comment"]).strip()

    state.add_col3_log(f"Metadata updated for {clip_id}: Title='{clip.get('title', '')[:30]}...'")
    return {"status": "UPDATED", "clip": clip}

@app.post("/api/clips/{clip_id}/approve")
async def approve_clip(clip_id: str):
    clip = state.clips.get(clip_id)
    if not clip:
        return {"status": "ALREADY_PROCESSED", "message": "Clip has already been approved and discarded."}
    if clip.get("status") in ["UPLOADING", "UPLOADED"]:
        return {"status": clip["status"], "youtube_url": clip.get("youtube_url")}
    clip["status"] = "APPROVED"
    asyncio.create_task(orchestrator.dispatch_upload(clip_id, immediate=False))
    return {"status": "APPROVED", "clip_id": clip_id}

@app.post("/api/clips/{clip_id}/upload_now")
async def upload_clip_now(clip_id: str):
    clip = state.clips.get(clip_id)
    if not clip:
        return {"status": "ALREADY_PROCESSED", "message": "Clip has already been uploaded and discarded."}
    if clip.get("status") in ["UPLOADING", "UPLOADED"]:
        return {"status": clip["status"], "youtube_url": clip.get("youtube_url")}
    clip["status"] = "UPLOADING"
    asyncio.create_task(orchestrator.dispatch_upload(clip_id, immediate=True))
    return {"status": "UPLOADING", "clip_id": clip_id}

@app.post("/api/clips/{clip_id}/create")
async def create_clip_from_studio_endpoint(clip_id: str, payload: dict):
    start_time = float(payload.get("start_time", 35.0))
    end_time = float(payload.get("end_time", 80.0))
    face_box = payload.get("face_box")
    game_box = payload.get("game_box")
    custom_title = payload.get("title")
    custom_first_comment = payload.get("first_comment")

    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="End time must be greater than start time")
    if (end_time - start_time) > 60.0:
        end_time = start_time + 60.0

    try:
        updated_clip = await orchestrator.create_clip_from_studio(
            clip_id=clip_id,
            start_time=start_time,
            end_time=end_time,
            face_box=face_box,
            game_box=game_box,
            custom_title=custom_title,
            custom_first_comment=custom_first_comment
        )
        await manager.broadcast(state.to_dict())
        return {"status": "SUCCESS", "clip": updated_clip}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/clips/{clip_id}/build_preview")
async def build_clip_2min_preview(clip_id: str):
    clip = state.clips.get(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    try:
        updated_clip = await orchestrator.create_clip_from_studio(
            clip_id=clip_id,
            start_time=float(clip.get("trim_start", 35.0)),
            end_time=float(clip.get("trim_end", 80.0)),
            custom_title=clip.get("title")
        )
        await manager.broadcast(state.to_dict())
        return {"status": "SUCCESS", "clip": updated_clip}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/clips/{clip_id}/retrim")
async def retrim_clip_endpoint(clip_id: str, payload: dict):
    start_time = float(payload.get("start_time", 0.0))
    end_time = float(payload.get("end_time", 45.0))
    zoom = float(payload.get("facecam_zoom", 1.0))
    pan_x = int(payload.get("facecam_pan_x", 0))
    pan_y = int(payload.get("facecam_pan_y", 0))
    custom_title = payload.get("title")

    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="End time must be greater than start time")

    # Automatically cap to 60 seconds max for YouTube Shorts
    if (end_time - start_time) > 60.0:
        end_time = start_time + 60.0

    try:
        updated_clip = await orchestrator.retrim_clip(
            clip_id=clip_id,
            new_start=start_time,
            new_end=end_time,
            facecam_zoom=zoom,
            facecam_pan_x=pan_x,
            facecam_pan_y=pan_y,
            custom_title=custom_title
        )
        await manager.broadcast(state.to_dict())
        return {"status": "SUCCESS", "clip": updated_clip}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/clips/{clip_id}/reject")
@app.delete("/api/clips/{clip_id}")
async def reject_clip(clip_id: str):
    orchestrator.reject_clip(clip_id)
    state.active_clip_id = None
    state.is_processing = False
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

    words = clip.get("all_words", [])
    t_start = float(clip.get("trim_start", 0.0))
    t_end = float(clip.get("trim_end", 120.0))
    window_words = [
        w for w in words
        if float(w.get("end", 0)) >= t_start and float(w.get("start", 0)) <= t_end
    ]
    transcript = " ".join(w.get("word", "") for w in (window_words or words)).strip()
    if not transcript:
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
    clip["first_comment"] = new_meta.get("first_comment", "")

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
    ch = channel.lower()
    existing = data.get(ch, {}) if isinstance(data.get(ch), dict) else {}
    existing.update(profile)
    data[ch] = existing
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

    # Load custom profile & saved Red/Blue boxes for this streamer if saved
    profile = load_streamer_profile(new_channel)
    saved_fb, saved_gb = facecam_cropper.load_streamer_boxes(new_channel)
    if saved_fb and saved_gb:
        state.current_facecam_box = saved_fb
        state.current_gameplay_box = saved_gb
        state.layout_locked = True
        state.col2_status = "LOCKED"
        state.facecam_rule_applied = "SAVED STREAMER PROFILE"
        state.add_col2_log(f"Loaded saved Red/Blue crop boxes for #{new_channel}.")

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

    # Also update active clip's all_words so any cut from the 2-minute clip uses the edited STT text
    if state.active_clip_id and state.active_clip_id in state.clips:
        clip = state.clips[state.active_clip_id]
        updated_words = []
        for row in new_transcript:
            r_start = float(row.get("start", 0.0))
            r_end = float(row.get("end", r_start + 1.0))
            tokens = str(row.get("text", "")).strip().split()
            if not tokens:
                continue
            step = max(0.05, (r_end - r_start) / len(tokens))
            for idx, tok in enumerate(tokens):
                w_s = round(r_start + idx * step, 2)
                w_e = round(min(r_end, w_s + step), 2)
                updated_words.append({
                    "word": tok,
                    "raw_word": tok,
                    "start": w_s,
                    "end": max(w_s + 0.05, w_e),
                    "probability": 1.0
                })
        if updated_words:
            clip["all_words"] = updated_words
            clip["transcript_text"] = " ".join(w["word"] for w in updated_words)

    state.add_col3_log(f"Transcript updated by user ({len(new_transcript)} lines synced to 2-minute STT).")
    await manager.broadcast(state.to_dict())
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

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_well_known():
    return {}

# Serve compiled frontend SPA at root AFTER all API and WebSocket routes
dist_dir = settings.BASE_DIR / "frontend" / "dist"
if dist_dir.exists():
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
