import asyncio
import time
import uuid
import shutil
import cv2
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

from backend.core.config import settings
from backend.core.state import state
from backend.core.scheduler import scheduler
from backend.pipeline.facecam_cropper import facecam_cropper
from backend.pipeline.transcription import transcriber
from backend.pipeline.subtitles import subtitles
from backend.pipeline.thumbnail import thumbnail_gen
from backend.pipeline.title_generator import title_gen
from backend.video.composer import composer
from backend.uploader.youtube import uploader

class ClipOrchestrator:
    def __init__(self, stream_buffer):
        self.stream_buffer = stream_buffer
        self.is_processing = False
        self._lock = asyncio.Lock()

    async def process_peak_event(self, peak_info: Dict[str, Any]):
        """
        Coordinates the complete pipeline from peak event to finished clip.
        Strictly enforces: only 1 clip at a time.
        """
        if self._lock.locked() or self.is_processing or state.is_processing or state.active_clip_id is not None:
            state.add_col1_log("Only 1 clip at a time permitted. A clip is currently processing or pending review.")
            return

        async with self._lock:
            if self.is_processing or state.is_processing or state.active_clip_id is not None:
                return

            self.is_processing = True
            state.is_processing = True
            peak_id = peak_info.get("peak_id")
            now = datetime.now()
            date_human = now.strftime("%b %d, %Y - %I:%M %p")
            date_short = now.strftime("%b %d, %I:%M %p")
            date_slug = now.strftime("%Y-%m-%d_%H-%M-%S")
            clip_id = f"Clip_{date_slug}"
            part = peak_info.get('part', 1)

            try:
                state.add_col1_log(f"--- STARTING PIPELINE EXECUTION FOR CLIP [{date_human}] ---")
                state.col1_status = "EXTRACTING"
                state.col2_status = "WAITING"
                state.col3_status = "WAITING"

                # Wait for rolling buffer to capture 1 minute (60s) after the peak moment so the clip is a full 4 minutes (3m before + 1m after)
                peak_timestamp = peak_info.get("timestamp", time.time())
                elapsed = time.time() - peak_timestamp
                if elapsed < 58.0:
                    wait_sec = int(60.0 - elapsed)
                    state.add_col1_log(f"Buffering {wait_sec}s to capture full 1 minute of stream reaction after peak (for 4-min clip: 3m before + 1m after)...")
                    await asyncio.sleep(wait_sec)

                raw_segment_path = settings.BUFFER_DIR / f"{clip_id}_raw.mp4"
                candidate_mp4_path = settings.CLIPS_DIR / f"{clip_id}_candidate.mp4"
                audio_path = settings.CLIPS_DIR / f"{clip_id}_audio.wav"
                ass_path = settings.CLIPS_DIR / f"{clip_id}_subtitles.ass"
                thumb_path = settings.CLIPS_DIR / f"{clip_id}_thumb.jpg"
                final_mp4_path = settings.CLIPS_DIR / f"{clip_id}.mp4"

                # 1. Extract full 4-minute (240s) 16:9 candidate footage (3 min before & 1 min after peak) anchored to peak_timestamp
                state.add_col1_log("Extracting 4-minute (240s) 16:9 stream footage (3m before & 1m after peak, accounting for reaction delay)...")
                success, computed_peak_offset = await asyncio.to_thread(
                    self.stream_buffer.extract_recent_segment,
                    240,
                    raw_segment_path,
                    peak_timestamp,
                    180.0,
                    60.0
                )
                if not success or not raw_segment_path.exists():
                    state.add_col1_log("Stream buffer is still accumulating footage. Please wait ~30s for buffer to fill.")
                    state.col1_status = "MONITORING"
                    state.col2_status = "IDLE"
                    state.col3_status = "IDLE"
                    return

                # Copy into clips dir so the 16:9 Studio can play the full 4-minute video immediately
                shutil.copy2(raw_segment_path, candidate_mp4_path)

                # Measure actual duration of the extracted candidate video
                candidate_duration = 240.0
                try:
                    cap = cv2.VideoCapture(str(candidate_mp4_path))
                    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
                    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    cap.release()
                    if fps > 0 and frames > 0:
                        candidate_duration = round(frames / fps, 1)
                except Exception:
                    pass

                peak_offset = round(min(candidate_duration - 2.0, max(2.0, float(computed_peak_offset or (candidate_duration * 0.75)))), 1)
                default_start = round(max(0.0, peak_offset - 25.0), 1)
                default_end = round(min(candidate_duration, default_start + 45.0), 1)
                if (default_end - default_start) < 5.0:
                    default_start = max(0.0, candidate_duration - 45.0)
                    default_end = candidate_duration

                state.col1_status = "OK"

                # 2. Load streamer's saved Red & Blue boxes (or run 1-take guess once and save to streamer profile)
                crop_data = await asyncio.to_thread(facecam_cropper.analyze_and_compute_crops, candidate_mp4_path)

                auto_process_active = bool(state.auto_process or settings.AUTO_PROCESS_PEAKS)
                auto_upload_active = bool(state.auto_upload or (settings.AUTO_UPLOAD_ENABLED and not settings.REQUIRE_MANUAL_APPROVAL))

                # 3. Calculate optimal YouTube scheduled slot (1-post-a-day, anti-duplicate)
                target_slot_dt = scheduler.get_next_available_slot()
                target_slot_iso = scheduler.format_iso(target_slot_dt)
                slot_info = scheduler.get_slot_info(target_slot_dt)
                countdown_seconds = settings.REVIEW_COUNTDOWN_MINUTES * 60

                if not auto_process_active and not auto_upload_active:
                    # MANUAL 16:9 STUDIO FLOW (Auto-Process OFF & Auto-Upload OFF):
                    # Loads 2-minute 16:9 video into Studio with an auto-generated title so user can adjust boxes/timestamps and click Confirm & Create Clip.
                    chat_sample = " ".join(c.get("msg", "") for c in state.recent_chat[-15:]).strip()
                    initial_context = chat_sample or f"{settings.TWITCH_CHANNEL} insane live stream peak reaction ({peak_info.get('intensity', 'HIGH')})"
                    initial_meta = await asyncio.to_thread(
                        title_gen.generate_metadata_from_text,
                        initial_context,
                        peak_info,
                        part
                    )

                    state.col3_status = "STUDIO_READY"
                    clip_size_mb = round(candidate_mp4_path.stat().st_size / (1024 * 1024), 2)
                    clip_record = {
                        "clip_id": clip_id,
                        "name": date_human,
                        "date": date_human,
                        "date_short": date_short,
                        "peak_info": peak_info,
                        "part": part,
                        "transcript_text": "",
                        "title": initial_meta["title"],
                        "description": initial_meta["description"],
                        "tags": initial_meta["tags"],
                        "first_comment": initial_meta.get("first_comment", ""),
                        "video_file": final_mp4_path.name,
                        "video_path": str(final_mp4_path),
                        "candidate_video_file": candidate_mp4_path.name,
                        "candidate_duration": candidate_duration,
                        "peak_offset_sec": peak_offset,
                        "trim_start": default_start,
                        "trim_end": default_end,
                        "duration_sec": round(default_end - default_start, 1),
                        "studio_ready": True,
                        "clip_created": False,
                        "thumbnail_file": None,
                        "size_mb": clip_size_mb,
                        "scheduled_slot_iso": target_slot_iso,
                        "scheduled_slot_display": f"{slot_info['display']} ({slot_info['description']})",
                        "scheduled_strategy": slot_info["description"],
                        "scheduled_window": slot_info["window"],
                        "status": "STUDIO_EDITING",
                        "review_expires_at": time.time() + countdown_seconds,
                        "raw_segment_path": str(raw_segment_path),
                        "created_at": date_human,
                        "all_words": [],
                        "crop_data": crop_data,
                        "base_face_box": crop_data.get("face_box", {}),
                        "version": 1
                    }
                    state.add_clip(clip_id, clip_record)
                    state.active_clip_id = clip_id
                    if peak_id:
                        state.remove_peak(peak_id)
                        state.add_col1_log(f"Peak {peak_id} loaded into 16:9 Studio with auto-generated title: \"{initial_meta['title']}\"")
                else:
                    # AUTO-PROCESS ON (or AUTO-UPLOAD ON):
                    # Automatically uses the streamer's saved Red & Blue boxes, transcribes the 45s peak window [35s - 80s],
                    # generates the AI title & captions, and renders the final 9:16 Short in one single pass.
                    clip_record = {
                        "clip_id": clip_id,
                        "name": date_human,
                        "date": date_human,
                        "date_short": date_short,
                        "peak_info": peak_info,
                        "part": part,
                        "video_file": final_mp4_path.name,
                        "video_path": str(final_mp4_path),
                        "candidate_video_file": candidate_mp4_path.name,
                        "candidate_duration": candidate_duration,
                        "peak_offset_sec": peak_offset,
                        "trim_start": default_start,
                        "trim_end": default_end,
                        "scheduled_slot_iso": target_slot_iso,
                        "scheduled_slot_display": f"{slot_info['display']} ({slot_info['description']})",
                        "scheduled_strategy": slot_info["description"],
                        "scheduled_window": slot_info["window"],
                        "status": "STUDIO_EDITING",
                        "review_expires_at": time.time() + countdown_seconds,
                        "raw_segment_path": str(raw_segment_path),
                        "created_at": date_human,
                        "crop_data": crop_data,
                        "base_face_box": crop_data.get("face_box", {}),
                        "version": 1
                    }
                    state.add_clip(clip_id, clip_record)
                    state.active_clip_id = clip_id
                    if peak_id:
                        state.remove_peak(peak_id)

                    await self.create_clip_from_studio(
                        clip_id=clip_id,
                        start_time=default_start,
                        end_time=default_end,
                        face_box=crop_data.get("face_box"),
                        game_box=crop_data.get("game_crop"),
                        custom_title=None
                    )

                    if auto_upload_active:
                        state.add_col3_log(f"Auto-Upload is ON: automatically dispatching clip [{date_short}] for scheduled YouTube upload...")
                        await self.dispatch_upload(clip_id, immediate=False)
                    else:
                        state.add_col3_log(f"Auto-Process is ON: 9:16 Short [{date_short}] rendered automatically and ready for review & upload!")

            except Exception as e:
                state.add_col3_log(f"Pipeline error: {str(e)}")
            finally:
                self.is_processing = False
                state.is_processing = False
                # If the peak was not removed (e.g. on pipeline error), reset its status so it can be re-run or deleted
                if peak_id:
                    target_peak = next((p for p in state.detected_peaks if p.get("peak_id") == peak_id), None)
                    if target_peak and target_peak.get("status") == "PROCESSING":
                        target_peak["status"] = "READY"
                    if target_peak and target_peak.get("status") == "PROCESSING":
                        target_peak["status"] = "READY"

    async def create_clip_from_studio(
        self,
        clip_id: str,
        start_time: float,
        end_time: float,
        face_box: Optional[Dict[str, Any]] = None,
        game_box: Optional[Dict[str, Any]] = None,
        custom_title: Optional[str] = None,
        custom_first_comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Single-pass clip creation from the 16:9 Studio:
        1. Persists Red (Facecam) and Blue (Gameplay) boxes for the current streamer.
        2. Extracts audio ONLY for the selected [start_time, end_time] (<60s) window and runs Faster-Whisper STT on that slice only.
        3. Uses user's custom title if entered, or auto-generates an AI viral title & description from the selected range's speech.
        4. Compiles ASS subtitles + temporary divider title and runs FFmpeg ONCE to create the final 1080x1920 9:16 Short.
        """
        clip = state.clips.get(clip_id)
        if not clip:
            raise ValueError(f"Clip {clip_id} not found")

        candidate_path = settings.CLIPS_DIR / f"{clip_id}_candidate.mp4"
        if not candidate_path.exists():
            raw_path = Path(clip.get("raw_segment_path", ""))
            if raw_path.exists():
                candidate_path = raw_path
            else:
                raise FileNotFoundError("2-minute candidate stream footage not found.")

        # 1. Enforce YouTube Shorts duration: max 60.0s, min 3.0s
        duration = min(60.0, max(3.0, float(end_time) - float(start_time)))
        safe_start = round(max(0.0, float(start_time)), 2)
        safe_end = round(safe_start + duration, 2)

        # 2. Compute and save Red/Blue boxes for this streamer
        fb = face_box or state.current_facecam_box or clip.get("crop_data", {}).get("face_box") or {"x": 0, "y": 0, "w": 400, "h": 284}
        gb = game_box or state.current_gameplay_box or clip.get("crop_data", {}).get("game_crop") or {"x": 302, "y": 0, "w": 675, "h": 720}
        orig_dim = state.frame_dimensions or {"w": 1280, "h": 720}
        crop_data = facecam_cropper.compute_custom_crop(
            face_box=fb,
            game_box=gb,
            orig_w=orig_dim.get("w", 1280),
            orig_h=orig_dim.get("h", 720)
        )
        state.current_facecam_box = crop_data["face_box"]
        state.current_gameplay_box = crop_data["game_crop"]
        state.layout_locked = True
        state.col2_status = "LOCKED"
        facecam_cropper.save_streamer_boxes(crop_data["face_box"], crop_data["game_crop"], settings.TWITCH_CHANNEL)

        audio_path = settings.CLIPS_DIR / f"{clip_id}_audio.wav"
        ass_path = settings.CLIPS_DIR / f"{clip_id}_subtitles.ass"
        thumb_path = settings.CLIPS_DIR / f"{clip_id}_thumb.jpg"
        final_mp4_path = settings.CLIPS_DIR / f"{clip_id}.mp4"

        # 3. Extract and transcribe ONLY the selected [safe_start, safe_end] audio range
        state.col3_status = "TRANSCRIBING"
        state.add_col3_log(f"Transcribing selected {duration:.1f}s clip range [{safe_start:.1f}s - {safe_end:.1f}s]...")
        await asyncio.to_thread(transcriber.extract_audio, candidate_path, audio_path, safe_start, duration)
        words, _, _ = await asyncio.to_thread(
            transcriber.transcribe_with_word_timestamps,
            audio_path,
            duration / 2.0
        )

        # 4. Generate metadata (use custom_title if provided, else AI title from the selected speech)
        peak_info = clip.get("peak_info") or {"velocity": 25.0}
        part = clip.get("part", 1)
        meta = await asyncio.to_thread(title_gen.generate_title_and_metadata, words, peak_info, part)
        final_title = custom_title.strip() if (custom_title and str(custom_title).strip()) else meta["title"]

        # 5. Compile ASS subtitles (words are already 0-based relative to safe_start because audio was sliced at safe_start)
        await asyncio.to_thread(
            subtitles.generate_ass_file,
            words,
            ass_path,
            0.0,
            duration,
            final_title
        )

        # 6. Render final 1080x1920 9:16 vertical Short in a single FFmpeg pass
        state.col3_status = "RENDERING"
        render_ok = await asyncio.to_thread(
            composer.render_final_vertical_clip,
            candidate_path,
            crop_data["filter_complex"],
            ass_path,
            safe_start,
            safe_end,
            final_mp4_path,
            60.0
        )

        if not render_ok or not final_mp4_path.exists():
            state.col3_status = "ERROR"
            raise RuntimeError("FFmpeg render failed while creating clip")

        await asyncio.to_thread(thumbnail_gen.extract_most_expressive_thumbnail, candidate_path, thumb_path)

        transcript_str = " ".join(w.get("word", "") for w in words).strip()
        final_comment = custom_first_comment.strip() if (custom_first_comment and str(custom_first_comment).strip()) else meta.get("first_comment", "")
        clip["title"] = final_title
        clip["description"] = meta["description"]
        clip["tags"] = meta["tags"]
        clip["first_comment"] = final_comment
        clip["transcript_text"] = transcript_str
        clip["all_words"] = words
        clip["trim_start"] = safe_start
        clip["trim_end"] = safe_end
        clip["duration_sec"] = round(duration, 1)
        clip["is_full_2min_preview"] = False
        clip["clip_created"] = True
        clip["status"] = "PENDING_REVIEW"
        clip["thumbnail_file"] = thumb_path.name if thumb_path.exists() else None
        clip["size_mb"] = round(final_mp4_path.stat().st_size / (1024 * 1024), 2)
        clip["crop_data"] = crop_data
        clip["base_face_box"] = crop_data["face_box"]
        clip["version"] = clip.get("version", 1) + 1

        state.col3_status = "COMPLETED"
        state.add_col3_log(f"Created 9:16 Short [{final_title}] ({duration:.1f}s, {clip['size_mb']} MB) in single pass!")
        return clip

    async def retrim_clip(
        self,
        clip_id: str,
        new_start: float,
        new_end: float,
        facecam_zoom: float = 1.0,
        facecam_pan_x: int = 0,
        facecam_pan_y: int = 0,
        custom_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Re-trims a clip from its 2-minute candidate footage to the user's exact pinpoint boundaries,
        adjusts facecam zoom/pan framing, updates the temporary hook title between facecam & gameplay,
        and re-renders the 1080x1920 vertical Short.
        """
        clip = state.clips.get(clip_id)
        if not clip:
            raise ValueError(f"Clip {clip_id} not found")

        candidate_path = settings.CLIPS_DIR / f"{clip_id}_candidate.mp4"
        if not candidate_path.exists():
            raw_path = Path(clip.get("raw_segment_path", ""))
            if raw_path.exists():
                candidate_path = raw_path
            else:
                raise FileNotFoundError("Candidate stream footage file not found.")

        # Update title if supplied
        if custom_title:
            clip["title"] = custom_title.strip()

        # Strictly enforce YouTube Shorts duration: max 60.0s, min 3.0s
        duration = min(60.0, max(3.0, new_end - new_start))
        safe_start = round(new_start, 2)
        safe_end = round(new_start + duration, 2)

        clip_name = clip.get("date_short") or clip.get("name") or clip_id
        state.add_col3_log(f"Re-trimming [{clip_name}] to [{safe_start:.1f}s - {safe_end:.1f}s] ({duration:.1f}s Short, zoom {facecam_zoom:.1f}x)...")
        state.col3_status = "RENDERING"

        final_mp4_path = settings.CLIPS_DIR / f"{clip_id}.mp4"
        ass_path = settings.CLIPS_DIR / f"{clip_id}_subtitles.ass"
        thumb_path = settings.CLIPS_DIR / f"{clip_id}_thumb.jpg"

        # Re-generate dynamic ASS subtitles from the full 2-minute STT word list for the cut [safe_start, safe_end] window
        words = clip.get("all_words", [])
        subtitles.generate_ass_file(words, ass_path, offset_start=safe_start, clip_duration=duration, title=clip.get("title"))

        # Update transcript text for this cut range while keeping full 2-minute all_words intact
        cut_words = [
            w for w in words
            if float(w.get("end", 0)) > safe_start and float(w.get("start", 0)) < safe_end
        ]
        if cut_words:
            clip["cut_transcript_text"] = " ".join(w.get("word", "") for w in cut_words).strip()
            clip["transcript_text"] = clip["cut_transcript_text"]

        # Use locked Red (Facecam) and Blue (Gameplay) crop boxes so layout never changes back
        face_box = state.current_facecam_box or clip.get("crop_data", {}).get("face_box") or clip.get("base_face_box") or {"x": 0, "y": 0, "w": 400, "h": 284}
        game_box = state.current_gameplay_box or clip.get("crop_data", {}).get("game_crop") or {"x": 302, "y": 0, "w": 675, "h": 720}
        orig_dim = state.frame_dimensions or {"w": 1280, "h": 720}
        crop_data = facecam_cropper.compute_custom_crop(
            face_box=face_box,
            game_box=game_box,
            orig_w=orig_dim.get("w", 1280),
            orig_h=orig_dim.get("h", 720)
        )

        render_ok = await asyncio.to_thread(
            composer.render_final_vertical_clip,
            candidate_path,
            crop_data["filter_complex"],
            ass_path,
            safe_start,
            safe_end,
            final_mp4_path
        )

        if not render_ok or not final_mp4_path.exists():
            state.col3_status = "ERROR"
            state.add_col3_log(f"Re-trim render failed for {clip_id}.")
            raise RuntimeError("FFmpeg render failed")

        # Update expressive thumbnail within newly pinpointed range
        thumbnail_gen.extract_most_expressive_thumbnail(candidate_path, thumb_path)

        # Update clip metadata
        clip["trim_start"] = safe_start
        clip["trim_end"] = safe_end
        clip["duration_sec"] = round(duration, 1)
        clip["is_full_2min_preview"] = False
        clip["size_mb"] = round(final_mp4_path.stat().st_size / (1024 * 1024), 2)
        clip["crop_data"] = crop_data
        clip["base_face_box"] = crop_data["face_box"]
        clip["facecam_zoom"] = facecam_zoom
        clip["facecam_pan_x"] = facecam_pan_x
        clip["facecam_pan_y"] = facecam_pan_y
        clip["version"] = clip.get("version", 1) + 1

        state.col3_status = "COMPLETED"
        state.add_col3_log(f"Clip [{clip_name}] successfully re-rendered ({duration:.1f}s YouTube Short). Preview updated!")
        return clip

    async def _auto_upload_countdown(self, clip_id: str, seconds: int):
        """Waits for review countdown; auto-uploads if not rejected or manually approved earlier."""
        await asyncio.sleep(seconds)
        clip = state.clips.get(clip_id)
        if clip and clip["status"] == "PENDING_REVIEW":
            state.add_col3_log(f"Review window expired for {clip_id}. Auto-approving for scheduled upload...")
            await self.dispatch_upload(clip_id)

    async def dispatch_upload(self, clip_id: str, immediate: bool = False):
        """Uploads clip to YouTube Shorts and immediately discards all files from SSD."""
        clip = state.clips.get(clip_id)
        if not clip:
            return

        clip_name = clip.get("date_short") or clip.get("name") or clip_id
        try:
            # If clip hasn't been created from the 16:9 Studio yet, create it now in a single pass before uploading
            if not clip.get("clip_created") or clip.get("is_full_2min_preview"):
                await self.create_clip_from_studio(
                    clip_id=clip_id,
                    start_time=float(clip.get("trim_start", 35.0)),
                    end_time=float(clip.get("trim_end", 80.0)),
                    custom_title=clip.get("title")
                )

            clip["status"] = "UPLOADING"
            video_path = Path(clip["video_path"])
            thumb_path = settings.CLIPS_DIR / clip["thumbnail_file"] if clip.get("thumbnail_file") else None

            schedule_time = None if immediate else clip["scheduled_slot_iso"]

            upload_result = await asyncio.to_thread(
                uploader.upload_short,
                video_path,
                thumb_path,
                clip["title"],
                clip["description"],
                clip["tags"],
                schedule_time
            )

            video_url = upload_result.get("url")
            video_id = upload_result.get("video_id")
            clip["status"] = "UPLOADED"
            clip["youtube_url"] = video_url
            state.add_col3_log(f"Clip [{clip_name}] published to YouTube Shorts: {video_url}")

            # Automatically post first discussion comment if configured
            comment_text = clip.get("first_comment")
            if comment_text and video_id:
                try:
                    await asyncio.to_thread(
                        uploader.post_comment,
                        video_id,
                        comment_text
                    )
                except Exception as e:
                    state.add_col3_log(f"Warning: Could not post first comment: {e}")

            # Once clip is posted, immediately discard all artifacts and clear from SSD
            raw_path = Path(clip["raw_segment_path"]) if clip.get("raw_segment_path") else None
            composer.purge_clip_artifacts(clip_id, raw_segment_path=raw_path)

            # Keep uploaded link in state briefly so frontend can display the success URL, then auto-clear
            async def _delayed_purge():
                await asyncio.sleep(3.5)
                state.remove_clip(clip_id)
                state.active_clip_id = None
                state.reset_columns_2_and_3()
                state.add_col3_log(f"Clip [{clip_name}] closed and SSD storage reclaimed. Ready for next peak.")

            asyncio.create_task(_delayed_purge())

        except Exception as e:
            clip["status"] = "UPLOAD_ERROR"
            state.add_col3_log(f"YouTube upload failed for {clip_id}: {str(e)}")

    def reject_clip(self, clip_id: str):
        clip = state.clips.get(clip_id)
        clip_name = clip.get("date_short") or clip.get("name") or clip_id if clip else clip_id
        raw_path = Path(clip["raw_segment_path"]) if clip and clip.get("raw_segment_path") else None
        
        # Always purge all disk artifacts
        composer.purge_clip_artifacts(clip_id, raw_segment_path=raw_path)
        
        # Clear clip from state and reset columns
        state.remove_clip(clip_id)
        state.active_clip_id = None
        self.is_processing = False
        state.is_processing = False

        # Reset any stuck processing peak in queue back to ready
        for p in state.detected_peaks:
            if p.get("status") == "PROCESSING":
                p["status"] = "READY"

        state.reset_columns_2_and_3()
        state.add_col3_log(f"Clip [{clip_name}] permanently rejected, all video files discarded, and SSD storage reclaimed.")
