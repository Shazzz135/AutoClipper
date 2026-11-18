import asyncio
import time
import uuid
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
                state.col1_status = "PROCESSING"
                state.col2_status = "PROCESSING"
                state.col3_status = "PROCESSING"

                raw_segment_path = settings.BUFFER_DIR / f"{clip_id}_raw.mp4"
                audio_path = settings.CLIPS_DIR / f"{clip_id}_audio.wav"
                ass_path = settings.CLIPS_DIR / f"{clip_id}_subtitles.ass"
                thumb_path = settings.CLIPS_DIR / f"{clip_id}_thumb.jpg"
                final_mp4_path = settings.CLIPS_DIR / f"{clip_id}.mp4"

                # 1. Extract raw candidate footage (60s candidate window to allow 50/50 context & snapping)
                success = self.stream_buffer.extract_recent_segment(60, raw_segment_path)
                if not success or not raw_segment_path.exists():
                    state.add_col1_log("Failed to extract video segment from buffer. Retrying next cycle.")
                    return

                state.col1_status = "OK"

                # 2. Lane 2: Facecam localization and 40/60 crop computation
                crop_data = facecam_cropper.analyze_and_compute_crops(raw_segment_path)
                state.col2_status = "OK"

                # 3. Lane 3: Audio extraction & speech-to-text
                transcriber.extract_audio(raw_segment_path, audio_path)
                words, snapped_start, snapped_end = transcriber.transcribe_with_word_timestamps(audio_path)

                # 4. Generate dynamic ASS subtitles synchronized to trimmed video
                clip_duration = snapped_end - snapped_start
                subtitles.generate_ass_file(words, ass_path, offset_start=snapped_start, clip_duration=clip_duration)

                # 5. Extract expressive thumbnail
                thumbnail_gen.extract_most_expressive_thumbnail(raw_segment_path, thumb_path)

                # 6. Generate viral title and description
                meta = title_gen.generate_title_and_metadata(words, peak_info, part=part)

                # 7. Render final vertical video
                render_ok = composer.render_final_vertical_clip(
                    raw_video_path=raw_segment_path,
                    filter_complex_str=crop_data["filter_complex"],
                    ass_subtitle_path=ass_path,
                    start_time=snapped_start,
                    end_time=snapped_end,
                    output_mp4_path=final_mp4_path
                )

                if not render_ok or not final_mp4_path.exists():
                    state.add_col3_log(f"Render failed for {clip_id}.")
                    return

                state.col3_status = "OK"

                # 8. Calculate optimal YouTube scheduled slot (1-post-a-day, anti-duplicate)
                target_slot_dt = scheduler.get_next_available_slot()
                target_slot_iso = scheduler.format_iso(target_slot_dt)
                slot_info = scheduler.get_slot_info(target_slot_dt)
                countdown_seconds = settings.REVIEW_COUNTDOWN_MINUTES * 60

                # Store clip record (only refer to clip name as the date and time)
                full_transcript_str = " ".join(w.get("word", "") for w in words).strip()
                clip_record = {
                    "clip_id": clip_id,
                    "name": date_human,
                    "date": date_human,
                    "date_short": date_short,
                    "transcript_text": full_transcript_str,
                    "title": meta["title"],
                    "description": meta["description"],
                    "tags": meta["tags"],
                    "video_file": final_mp4_path.name,
                    "video_path": str(final_mp4_path),
                    "thumbnail_file": thumb_path.name if thumb_path.exists() else None,
                    "duration_sec": round(snapped_end - snapped_start, 1),
                    "size_mb": round(final_mp4_path.stat().st_size / (1024 * 1024), 2),
                    "scheduled_slot_iso": target_slot_iso,
                    "scheduled_slot_display": f"{slot_info['display']} ({slot_info['description']})",
                    "scheduled_strategy": slot_info["description"],
                    "scheduled_window": slot_info["window"],
                    "status": "PENDING_REVIEW", # PENDING_REVIEW, APPROVED, REJECTED, UPLOADED
                    "review_expires_at": time.time() + countdown_seconds,
                    "raw_segment_path": str(raw_segment_path),
                    "created_at": date_human
                }

                state.add_clip(clip_id, clip_record)
                state.active_clip_id = clip_id
                state.add_col3_log(f"Clip [{date_short}] '{meta['title']}' ready for preview. Waiting for your manual confirmation before YouTube upload.")

                # Auto-remove peak from Column 1 queue since it is now converted into a finished clip
                if peak_id:
                    state.remove_peak(peak_id)
                    state.add_col1_log(f"Peak {peak_id} converted to clip and cleared from queue.")

                # Auto-upload if toggled ON via UI or settings
                if state.auto_upload or (settings.AUTO_UPLOAD_ENABLED and not settings.REQUIRE_MANUAL_APPROVAL):
                    state.add_col3_log(f"Auto-Upload is active: automatically dispatching clip [{date_short}] for scheduled YouTube upload...")
                    asyncio.create_task(self.dispatch_upload(clip_id, immediate=False))

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

    async def _auto_upload_countdown(self, clip_id: str, seconds: int):
        """Waits for review countdown; auto-uploads if not rejected or manually approved earlier."""
        await asyncio.sleep(seconds)
        clip = state.clips.get(clip_id)
        if clip and clip["status"] == "PENDING_REVIEW":
            state.add_col3_log(f"Review window expired for {clip_id}. Auto-approving for scheduled upload...")
            await self.dispatch_upload(clip_id)

    async def dispatch_upload(self, clip_id: str, immediate: bool = False):
        """Uploads clip to YouTube and auto-purges local artifacts."""
        clip = state.clips.get(clip_id)
        if not clip:
            return

        try:
            clip["status"] = "UPLOADING"
            video_path = Path(clip["video_path"])
            thumb_path = settings.CLIPS_DIR / clip["thumbnail_file"] if clip.get("thumbnail_file") else None

            schedule_time = None if immediate else clip["scheduled_slot_iso"]

            upload_result = uploader.upload_short(
                video_path=video_path,
                thumbnail_path=thumb_path,
                title=clip["title"],
                description=clip["description"],
                tags=clip["tags"],
                schedule_time_iso=schedule_time
            )

            clip["status"] = "UPLOADED"
            clip["youtube_url"] = upload_result["url"]
            state.add_col3_log(f"Clip {clip_id} successfully published to YouTube: {upload_result['url']}")

            # Auto-purge temporary files to reclaim SSD space
            raw_path = Path(clip["raw_segment_path"]) if clip.get("raw_segment_path") else None
            composer.purge_clip_artifacts(clip_id, raw_segment_path=raw_path)

        except Exception as e:
            clip["status"] = "UPLOAD_ERROR"
            state.add_col3_log(f"YouTube upload failed for {clip_id}: {str(e)}")

    def reject_clip(self, clip_id: str):
        clip = state.clips.get(clip_id)
        if clip:
            clip_name = clip.get("name") or clip.get("date") or clip_id
            clip["status"] = "REJECTED"
            raw_path = Path(clip["raw_segment_path"]) if clip.get("raw_segment_path") else None
            composer.purge_clip_artifacts(clip_id, raw_segment_path=raw_path)
            state.add_col3_log(f"Clip [{clip_name}] discarded and SSD storage reclaimed.")
        state.remove_clip(clip_id)
        state.reset_columns_2_and_3()
