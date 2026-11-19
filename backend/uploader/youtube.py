import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import pytz

from backend.core.config import settings
from backend.core.state import state
from backend.core.scheduler import scheduler

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    HAS_GOOGLE_API = True
except ImportError:
    HAS_GOOGLE_API = False

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

class YouTubeUploader:
    def __init__(self):
        self.secrets_path = settings.BASE_DIR / settings.YOUTUBE_CLIENT_SECRETS_PATH
        self.token_path = settings.BASE_DIR / settings.YOUTUBE_TOKEN_PATH
        self._service = None

    def is_authenticated(self) -> bool:
        if not self.token_path.exists():
            return False
        # If we have cached health status, respect it
        health = getattr(self, "_cached_health", None)
        if health and health.get("status") == "EXPIRED":
            return False
        return True

    def check_health(self, force: bool = False) -> Dict[str, Any]:
        """
        Actively checks whether the active YouTube credentials are valid and can refresh,
        or whether they are expired (e.g. 7-day Google testing limit, revoked, or invalid_grant).
        Also inspects token age. Caches result for 30s to prevent spamming Google servers.
        """
        now = time.time()
        last_check = getattr(self, "_last_health_check", 0)
        cached = getattr(self, "_cached_health", None)
        if not force and cached and (now - last_check) < 30.0:
            return cached

        if not self.token_path.exists():
            res = {
                "status": "NOT_CONNECTED",
                "authenticated": False,
                "error": "No token.json found.",
                "days_old": 0.0,
                "channel_title": "Not Connected"
            }
            self._cached_health = res
            self._last_health_check = now
            return res

        # Check token file age (in days)
        mtime = self.token_path.stat().st_mtime
        days_old = round((now - mtime) / 86400.0, 1)

        try:
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            if not creds:
                res = {
                    "status": "EXPIRED",
                    "authenticated": False,
                    "error": "Token is empty or invalid format.",
                    "days_old": days_old,
                    "channel_title": "Invalid Token"
                }
                self._cached_health = res
                self._last_health_check = now
                return res

            # Attempt a refresh using Google's Request to verify token validity
            if creds.expired or not creds.valid:
                creds.refresh(Request())
                with open(self.token_path, "w") as f:
                    f.write(creds.to_json())

                # Also sync refreshed token to the named account token file if known
                active_stem = self.detect_active_account() or getattr(state, "youtube_channel", None)
                if active_stem and active_stem not in ("CONNECTED", "NOT CONNECTED"):
                    named_tok = settings.BASE_DIR / "config" / "tokens" / f"{active_stem}.json"
                    try:
                        with open(named_tok, "w") as nf:
                            nf.write(creds.to_json())
                    except Exception:
                        pass

            active_channel = self.detect_active_account() or "Connected Channel"
            res = {
                "status": "HEALTHY",
                "authenticated": True,
                "error": None,
                "days_old": days_old,
                "expiring_soon": days_old >= 6.0,
                "channel_title": active_channel
            }
            self._cached_health = res
            self._last_health_check = now
            return res

        except Exception as e:
            err_str = str(e)
            is_invalid_grant = "invalid_grant" in err_str.lower()
            active_stem = self.detect_active_account() or getattr(state, "youtube_channel", None)
            res = {
                "status": "EXPIRED",
                "authenticated": False,
                "error": "Google session expired (7-day testing limit or revoked). Re-authentication required." if is_invalid_grant else err_str,
                "days_old": days_old,
                "expiring_soon": False,
                "channel_title": f"{active_stem} (Expired)" if active_stem and active_stem not in ("CONNECTED", "NOT CONNECTED") else "Session Expired"
            }
            self._cached_health = res
            self._last_health_check = now
            return res

    def get_service(self):
        if self._service is not None:
            return self._service

        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif self.secrets_path.exists():
                flow = InstalledAppFlow.from_client_secrets_file(str(self.secrets_path), SCOPES)
                creds = flow.run_local_server(port=0)
            else:
                raise FileNotFoundError(f"YouTube client secrets file not found at {self.secrets_path}")

            with open(self.token_path, "w") as token:
                token.write(creds.to_json())

        self._service = build("youtube", "v3", credentials=creds)
        return self._service

    def reload_credentials(self):
        """Forces reload of service from token_path."""
        self._service = None
        return self.get_service()

    def get_streamer_for_account(self, account_id: str) -> str:
        """
        Maps a YouTube account ID (e.g. 'KaiClips', 'JynxziClips135') to its tracked Twitch streamer.
        """
        import re
        clean = account_id.lower().strip()
        profiles_file = settings.BASE_DIR / "config" / "streamer_profiles.json"
        if profiles_file.exists():
            try:
                data = json.loads(profiles_file.read_text())
                custom_map = data.get("_yt_account_map", {})
                if clean in custom_map and custom_map[clean]:
                    return custom_map[clean]
            except Exception:
                pass

        if "kai" in clean:
            return "kaicenat"
        if "jynxzi" in clean:
            return "jynxzi"
        if "speed" in clean:
            return "ishowspeed"
        if "caseoh" in clean:
            return "caseoh"
        if "xqc" in clean:
            return "xqc"
        if "plaqueboymax" in clean:
            return "plaqueboymax"
        if "stableronaldo" in clean or "ronaldo" in clean:
            return "stableronaldo"
        if "jasontheween" in clean:
            return "jasontheween"
        if "lacy" in clean:
            return "lacy"

        inferred = re.sub(r'(clips|clip|shorts|short|_\d+|\d+|_)', '', clean).strip()
        return inferred or settings.TWITCH_CHANNEL

    def detect_active_account(self) -> Optional[str]:
        """
        Checks config/token.json against config/tokens/*.json to identify the active YouTube account.
        Falls back to currently active state.youtube_channel if matching token file exists.
        """
        tokens_dir = settings.BASE_DIR / "config" / "tokens"
        tokens_dir.mkdir(parents=True, exist_ok=True)
        if not self.token_path.exists():
            curr = getattr(state, "youtube_channel", None)
            if curr and curr not in ("CONNECTED", "NOT CONNECTED") and (tokens_dir / f"{curr}.json").exists():
                return curr
            return None

        try:
            active_data = json.loads(self.token_path.read_text())
            active_rt = active_data.get("refresh_token")
        except Exception:
            active_rt = None

        for f in sorted(tokens_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                if active_rt and data.get("refresh_token") == active_rt:
                    state.youtube_channel = f.stem
                    return f.stem
            except Exception:
                pass

        curr = getattr(state, "youtube_channel", None)
        if curr and curr not in ("CONNECTED", "NOT CONNECTED") and (tokens_dir / f"{curr}.json").exists():
            return curr

        return None

    def get_available_accounts(self) -> list:
        """
        Lists all saved YouTube channel tokens from config/tokens/, plus any mapped profiles.
        """
        tokens_dir = settings.BASE_DIR / "config" / "tokens"
        tokens_dir.mkdir(parents=True, exist_ok=True)

        token_files = sorted(list(tokens_dir.glob("*.json")))
        detected_id = self.detect_active_account()
        active_channel = detected_id or getattr(state, "youtube_channel", "") or "CONNECTED"

        accounts = []
        for f in token_files:
            account_id = f.stem
            display_name = account_id.replace("_", " ")
            streamer = self.get_streamer_for_account(account_id)
            is_active = (
                account_id.lower() == active_channel.replace(" ", "").lower()
                or display_name.lower() == active_channel.lower()
            )

            accounts.append({
                "id": account_id,
                "name": display_name,
                "streamer": streamer,
                "file": f.name,
                "is_active": is_active
            })

        # Also discover any accounts registered in streamer_profiles._yt_account_map
        profiles_file = settings.BASE_DIR / "config" / "streamer_profiles.json"
        if profiles_file.exists():
            try:
                data = json.loads(profiles_file.read_text())
                custom_map = data.get("_yt_account_map", {})
                for acc_id, str_name in custom_map.items():
                    if not any(a["id"].lower() == acc_id.lower() for a in accounts):
                        accounts.append({
                            "id": acc_id,
                            "name": acc_id.replace("_", " "),
                            "streamer": str_name,
                            "file": f"{acc_id}.json",
                            "is_active": acc_id.lower() == active_channel.replace(" ", "").lower()
                        })
            except Exception:
                pass

        # If none matched active but accounts exist, mark the first one if active_channel is generic
        if accounts and not any(a["is_active"] for a in accounts):
            accounts[0]["is_active"] = True

        return accounts

    def switch_account(self, account_id: str) -> dict:
        """
        Dynamically switches active YouTube channel to the specified account token.
        Each account maintains its own unique token file in config/tokens/<account_id>.json.
        """
        import shutil
        tokens_dir = settings.BASE_DIR / "config" / "tokens"
        tokens_dir.mkdir(parents=True, exist_ok=True)

        target_file = tokens_dir / f"{account_id}.json"
        if not target_file.exists():
            target_file = tokens_dir / account_id

        account_stem = target_file.stem if target_file.exists() else account_id

        if target_file.exists():
            # Overwrite active token.json with target account's unique token
            shutil.copy(target_file, self.token_path)
        else:
            # Account doesn't have a token file yet; clear active token.json so previous credentials aren't mistakenly reused
            if self.token_path.exists():
                try:
                    self.token_path.unlink()
                except Exception:
                    pass

        # Invalidate service and health cache
        self._service = None
        self._cached_health = None
        target_streamer = self.get_streamer_for_account(account_stem)

        state.youtube_channel = account_stem

        # Immediately check health of the switched account
        health = self.check_health(force=True)
        state.youtube_auth_status = health.get("status", "NOT_CONNECTED")
        state.youtube_auth_error = health.get("error")
        state.youtube_token_days_old = health.get("days_old", 0.0)

        if health.get("status") == "HEALTHY":
            state.add_col3_log(f"Switched active YouTube account to: {account_stem} (Verified Healthy, Streamer: #{target_streamer})")
        elif health.get("status") == "EXPIRING_SOON":
            state.add_col3_log(f"Switched active YouTube account to: {account_stem} (Token ~{health.get('days_old', 0):.0f}d old, Streamer: #{target_streamer})")
        elif health.get("status") == "EXPIRED":
            state.add_col3_log(f"Switched active YouTube account to: {account_stem} (⚠️ Session Expired - click Reconnect to authorize, Streamer: #{target_streamer})")
        else:
            state.add_col3_log(f"Switched active YouTube account to: {account_stem} (Status: {health.get('status')}, Streamer: #{target_streamer})")

        # Refresh quota status for the newly active account
        state.youtube_quota = self.get_upload_quota()

        return {
            "status": "SWITCHED",
            "account_id": account_stem,
            "active_channel": account_stem,
            "streamer": target_streamer,
            "health": health,
            "quota": state.youtube_quota,
            "authenticated": health.get("authenticated", False)
        }

    def get_channel_info(self) -> Dict[str, Any]:
        """Returns details about the currently authenticated YouTube channel."""
        if not HAS_GOOGLE_API or not self.is_authenticated():
            return {"authenticated": False, "channel_title": "Not Connected", "channel_id": None}

        try:
            service = self.get_service()
            resp = service.channels().list(mine=True, part="snippet,statistics").execute()
            items = resp.get("items", [])
            if items:
                snippet = items[0].get("snippet", {})
                stats = items[0].get("statistics", {})
                return {
                    "authenticated": True,
                    "channel_title": snippet.get("title", "Unknown"),
                    "channel_id": items[0].get("id"),
                    "subscribers": stats.get("subscriberCount", "0"),
                    "custom_url": snippet.get("customUrl", "")
                }
        except Exception as e:
            return {"authenticated": False, "error": str(e), "channel_title": "Auth Error", "channel_id": None}

        return {"authenticated": False, "channel_title": "No Channel Found", "channel_id": None}

    def get_scheduled_videos_detailed(self) -> list:
        """
        Queries the authenticated YouTube channel for upcoming scheduled videos (publishAt).
        Returns a list of dicts: [{"video_id": ..., "title": ..., "publish_at_iso": ..., "dt": ...}]
        """
        if not HAS_GOOGLE_API or not self.is_authenticated():
            return []

        try:
            service = self.get_service()
            # 1. Fetch channel's uploads playlist ID
            ch_resp = service.channels().list(mine=True, part="contentDetails").execute()
            items = ch_resp.get("items", [])
            if not items:
                return []
            uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

            # 2. Fetch up to 50 recent videos from uploads playlist
            pl_resp = service.playlistItems().list(
                playlistId=uploads_id,
                part="contentDetails",
                maxResults=50
            ).execute()

            video_ids = [item["contentDetails"]["videoId"] for item in pl_resp.get("items", []) if "contentDetails" in item]
            if not video_ids:
                return []

            # 3. Query video status and snippet in batch
            videos_resp = service.videos().list(
                id=",".join(video_ids[:50]),
                part="status,snippet"
            ).execute()

            results = []
            now_utc = datetime.now(pytz.utc)
            for item in videos_resp.get("items", []):
                status = item.get("status", {})
                snippet = item.get("snippet", {})
                publish_at_str = status.get("publishAt")
                if publish_at_str:
                    try:
                        # ISO 8601 string, e.g. 2026-11-18T23:00:00Z
                        clean_str = publish_at_str.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(clean_str)
                        # Only count future scheduled videos
                        if dt > now_utc:
                            results.append({
                                "video_id": item.get("id"),
                                "title": snippet.get("title", "Untitled Short"),
                                "publish_at_iso": publish_at_str,
                                "dt": dt
                            })
                    except Exception:
                        pass

            return results
        except Exception as e:
            return []

    def get_recent_uploads_status(self, max_results: int = 15) -> list:
        """
        Queries recent channel uploads and returns live processing status, scheduled times,
        and ingestion health directly from Google's servers.
        """
        if not HAS_GOOGLE_API or not self.is_authenticated():
            return []

        try:
            service = self.get_service()
            ch_resp = service.channels().list(mine=True, part="contentDetails").execute()
            items = ch_resp.get("items", [])
            if not items:
                return []
            uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

            pl_resp = service.playlistItems().list(
                playlistId=uploads_id,
                part="contentDetails",
                maxResults=max_results
            ).execute()

            video_ids = [item["contentDetails"]["videoId"] for item in pl_resp.get("items", []) if "contentDetails" in item]
            if not video_ids:
                return []

            v_resp = service.videos().list(
                id=",".join(video_ids[:max_results]),
                part="snippet,status,processingDetails"
            ).execute()

            results = []
            for v in v_resp.get("items", []):
                vid = v.get("id")
                snippet = v.get("snippet", {})
                st = v.get("status", {})
                proc = v.get("processingDetails", {})

                upload_status = st.get("uploadStatus", "unknown")
                processing_status = proc.get("processingStatus", "unknown")
                privacy = st.get("privacyStatus", "private")
                publish_at = st.get("publishAt")

                is_ready = processing_status == "succeeded" or upload_status == "processed"

                if is_ready:
                    if publish_at:
                        status_display = "PROCESSED (SCHEDULED)"
                    else:
                        status_display = "PROCESSED (PUBLIC)"
                elif processing_status == "processing" or upload_status == "uploaded":
                    status_display = "PROCESSING (IN QUEUE)"
                elif processing_status == "failed" or upload_status in ("failed", "rejected"):
                    status_display = f"FAILED: {st.get('rejectionReason') or st.get('failureReason') or 'error'}"
                else:
                    status_display = upload_status.upper()

                results.append({
                    "video_id": vid,
                    "title": snippet.get("title", "Untitled Short"),
                    "url": f"https://youtube.com/shorts/{vid}",
                    "upload_status": upload_status,
                    "processing_status": processing_status,
                    "privacy_status": privacy,
                    "publish_at": publish_at,
                    "is_ready": is_ready,
                    "status_display": status_display
                })

            return results
        except Exception as e:
            return []

    def get_scheduled_publish_times(self) -> list:
        """
        Returns a list of datetime objects for all scheduled videos on YouTube.
        """
        details = self.get_scheduled_videos_detailed()
        return [d["dt"] for d in details]

    def _get_history_file(self) -> Path:
        hist_path = settings.BASE_DIR / "config" / "upload_history.json"
        hist_path.parent.mkdir(parents=True, exist_ok=True)
        return hist_path

    def load_upload_history(self) -> list:
        f = self._get_history_file()
        if not f.exists():
            return []
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            return data.get("uploads", [])
        except Exception:
            return []

    def save_upload_history(self, history: list):
        f = self._get_history_file()
        try:
            f.write_text(json.dumps({"uploads": history}, indent=2), encoding="utf-8")
        except Exception:
            pass

    def record_upload(self, video_id: str, account_id: str, title: str, scheduled: bool = False):
        history = self.load_upload_history()
        now_utc = datetime.now(pytz.utc)
        record = {
            "video_id": video_id,
            "account_id": account_id or self.detect_active_account() or "unknown",
            "title": title,
            "scheduled": scheduled,
            "timestamp": now_utc.timestamp(),
            "iso_time": now_utc.isoformat(),
            "status": "SUCCESS"
        }
        # Avoid duplicate records for same video_id
        if not any(h.get("video_id") == video_id for h in history):
            history.append(record)
            self.save_upload_history(history)

    def get_upload_quota(self) -> Dict[str, Any]:
        """
        Computes accurate daily upload budget and Google Cloud API unit quota.
        Google Cloud YouTube Data API quota resets daily at 12:00 AM Pacific Time.
        Total project budget: 6 uploads/day (1,600 units/upload out of 10,000 units/day).
        Optimal strategy: 3 uploads/day for Kai Cenat, 3 uploads/day for Jynxzi.
        """
        pt_tz = pytz.timezone("America/Los_Angeles")
        now_pt = datetime.now(pt_tz)
        today_midnight_pt = now_pt.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_ts = today_midnight_pt.timestamp()

        next_midnight_pt = (now_pt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_left = max(0, int((next_midnight_pt - now_pt).total_seconds()))
        hours_left = seconds_left // 3600
        mins_left = (seconds_left % 3600) // 60
        reset_display = f"{hours_left}h {mins_left}m"

        history = self.load_upload_history()

        # Count uploads today per account
        total_used_today = 0
        account_counts: Dict[str, int] = {}
        for h in history:
            ts = h.get("timestamp", 0)
            if ts >= today_start_ts:
                total_used_today += 1
                acc = (h.get("account_id") or "unknown").strip()
                account_counts[acc] = account_counts.get(acc, 0) + 1

        total_daily_limit = 6  # 10,000 quota units / 1,600 per video
        total_remaining = max(0, total_daily_limit - total_used_today)
        per_account_target = 3 # 3x daily schedule: Midday, Afternoon, Prime Evening

        active_account = self.detect_active_account() or getattr(state, "youtube_channel", "JynxziClips135")
        
        # Helper to match account counts case-insensitively
        def get_count_for(acc_name: str) -> int:
            clean = acc_name.lower().replace(" ", "").replace("_", "")
            for k, v in account_counts.items():
                if k.lower().replace(" ", "").replace("_", "") == clean or clean in k.lower():
                    return v
            return 0

        active_used = get_count_for(active_account)
        active_remaining = max(0, min(per_account_target - active_used, total_remaining))

        # Build status for all available accounts
        avail = self.get_available_accounts()
        accounts_quota = {}
        for a in avail:
            acc_id = a.get("id") or a.get("name")
            used = get_count_for(acc_id)
            rem = max(0, min(per_account_target - used, total_remaining))
            accounts_quota[acc_id] = {
                "name": a.get("name"),
                "streamer": a.get("streamer"),
                "is_active": a.get("is_active", False),
                "target": per_account_target,
                "used_today": used,
                "remaining_today": rem,
                "at_capacity": rem == 0
            }

        quota_data = {
            "total_daily_limit": total_daily_limit,
            "total_used_today": total_used_today,
            "total_remaining": total_remaining,
            "per_account_target": per_account_target,
            "active_account": active_account,
            "active_used": active_used,
            "active_remaining": active_remaining,
            "active_at_capacity": active_remaining == 0,
            "accounts": accounts_quota,
            "reset_display": reset_display,
            "reset_in_hours": round(seconds_left / 3600.0, 1),
            "next_reset_iso": next_midnight_pt.isoformat(),
            "strategy": "3x Daily Shorts (Midday, Afternoon, Prime Evening) per account (6 total across Google Cloud project)"
        }
        return quota_data

    def upload_short(
        self,
        video_path: Path,
        thumbnail_path: Optional[Path],
        title: str,
        description: str,
        tags: list,
        schedule_time_iso: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Uploads video to YouTube as a Short with scheduled publishing and custom thumbnail.
        """
        if not HAS_GOOGLE_API:
            state.add_col3_log("Warning: google-api-python-client not yet installed. Simulating YouTube upload.")
            return {
                "video_id": "test_mock_id",
                "url": "https://youtube.com/shorts/test_mock_id",
                "status": "UPLOADED (MOCK)",
                "publish_at": schedule_time_iso
            }

        service = self.get_service()
        state.add_col3_log(f"Uploading to YouTube Shorts: {title}...")

        # Enforce YouTube Shorts requirements:
        # 1. Title must include #Shorts or #shorts
        shorts_tag = "#shorts"
        if "#shorts" not in title.lower():
            if len(title) > 90:
                title = title[:90].rstrip() + f" {shorts_tag}"
            else:
                title = f"{title} {shorts_tag}"

        # 2. Description must include #shorts and trending hashtags
        if "#shorts" not in description.lower():
            description = f"{description}\n\n#shorts #youtubeshorts #gaming #viral"

        # Determine valid YouTube privacy status (must be private, public, or unlisted)
        privacy_setting = settings.YOUTUBE_DEFAULT_PRIVACY.lower()
        if privacy_setting not in ["private", "public", "unlisted"]:
            privacy_setting = "public" if not schedule_time_iso else "private"

        # If scheduling for future release, YouTube strictly requires privacyStatus = 'private'
        if schedule_time_iso:
            privacy_setting = "private"

        # Clean and deduplicate tags while respecting YouTube's 500-character total tag limit
        base_tags = [t.strip().lower() for t in tags if t and t.strip()]
        mandatory_tags = ["shorts", "youtubeshorts", "short", "gaming", "viral", "reaction", "highlights", "twitch", "streamer"]
        merged_tags = []
        char_count = 0
        for t in base_tags + mandatory_tags:
            t_clean = t.replace("#", "").strip()
            if t_clean and t_clean not in merged_tags:
                if char_count + len(t_clean) + 1 <= 450:
                    merged_tags.append(t_clean)
                    char_count += len(t_clean) + 1

        rec_date = datetime.now(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Setup complete metadata body complying with all YouTube Studio requirements
        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": merged_tags,
                "categoryId": "20",  # Gaming
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en"
            },
            "status": {
                "privacyStatus": privacy_setting,
                "selfDeclaredMadeForKids": False,  # COPPA Compliance: Not made for kids
                "license": "youtube",              # Standard YouTube License
                "embeddable": True,                # Allow embedding
                "publicStatsViewable": True        # Show like count / viewer engagement
            },
            "recordingDetails": {
                "recordingDate": rec_date          # Accurate recording timestamp
            }
        }

        # If scheduled time is provided, YouTube strictly requires privacyStatus = 'private' with publishAt
        if schedule_time_iso:
            body["status"]["privacyStatus"] = "private"
            body["status"]["publishAt"] = schedule_time_iso

        file_size_mb = round(video_path.stat().st_size / (1024 * 1024), 2)

        # Detailed live YouTube Data API logs
        state.add_col3_log(f"Configuring YouTube API v3 insert for: \"{title[:55]}...\"")
        state.add_col3_log(f"  • Category: Gaming (ID 20) | Language: English (en)")
        state.add_col3_log(f"  • Audience: Not Made for Kids (COPPA Compliant: selfDeclaredMadeForKids=False)")
        state.add_col3_log(f"  • License: Standard YouTube License | Embeds & Likes: Enabled")
        state.add_col3_log(f"  • Tags ({len(merged_tags)}): {', '.join(merged_tags[:6])}...")
        if schedule_time_iso:
            state.add_col3_log(f"  • Release: Scheduled for {schedule_time_iso} (Privacy: Private)")
        else:
            state.add_col3_log(f"  • Release: Immediate Publish (Privacy: {privacy_setting.upper()})")

        state.add_col3_log(f"Starting YouTube video upload: {file_size_mb} MB (5MB resumable chunks)...")

        # 5MB chunks (must be multiple of 256KB for Google API resumable upload)
        chunk_size = 5 * 1024 * 1024
        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            chunksize=chunk_size,
            resumable=True
        )

        request = service.videos().insert(
            part="snippet,status,recordingDetails",
            body=body,
            media_body=media
        )

        response = None
        retry_count = 0
        max_retries = 8
        last_pct = -1

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    if pct != last_pct and (pct % 25 == 0 or pct == 100 or pct == 50):
                        sent_mb = round(status.resumable_progress / (1024 * 1024), 1)
                        state.add_col3_log(f"YouTube upload progress: {pct}% ({sent_mb}/{file_size_mb} MB sent)")
                        last_pct = pct
                retry_count = 0  # Reset retry counter on every successful chunk
            except Exception as exc:
                err_text = str(exc)

                # Immediately halt on permanent API limits instead of retrying as network drops
                if "uploadLimitExceeded" in err_text:
                    limit_msg = "YouTube daily channel upload limit reached. YouTube enforces a rolling 24-hour limit on newer/unverified channels (~5-10 videos/day). Verify your channel with 'Advanced Features' in YouTube Studio to unlock 100 uploads/day, or switch to another YouTube account."
                    state.add_col3_log(f"⚠️ {limit_msg}")
                    raise RuntimeError(limit_msg)

                if "quotaExceeded" in err_text:
                    quota_msg = "Google Cloud YouTube Data API project quota exceeded (10,000 units/day limit). Resets daily at midnight PT. Request a free quota increase in Google Cloud Console or switch to another account."
                    state.add_col3_log(f"⚠️ {quota_msg}")
                    raise RuntimeError(quota_msg)

                retry_count += 1
                if retry_count > max_retries:
                    state.add_col3_log(f"Fatal YouTube upload error after {max_retries} attempts: {err_text}")
                    raise exc

                sleep_sec = min(2 ** retry_count, 15)
                state.add_col3_log(f"Network drop ({err_text}). Resuming upload from {last_pct if last_pct >= 0 else 0}% in {sleep_sec}s (retry {retry_count}/{max_retries})...")
                time.sleep(sleep_sec)

        video_id = response.get("id")
        video_url = f"https://youtube.com/shorts/{video_id}"
        state.add_col3_log(f"✅ UPLOAD SUCCESSFUL! Video ID: {video_id} ({video_url})")

        # Set custom thumbnail if available
        if thumbnail_path and thumbnail_path.exists() and video_id:
            try:
                state.add_col3_log("Setting custom expressive thumbnail...")
                thumb_media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
                service.thumbnails().set(
                    videoId=video_id,
                    media_body=thumb_media
                ).execute()
                state.add_col3_log("Thumbnail set successfully.")
            except Exception as e:
                state.add_col3_log(f"Warning: Could not set thumbnail ({str(e)})")

        # Record upload in persistent history and recompute remaining budget
        active_acc = self.detect_active_account() or getattr(state, "youtube_channel", "Connected Channel")
        self.record_upload(video_id, active_acc, title, bool(schedule_time_iso))
        state.youtube_quota = self.get_upload_quota()

        return {
            "video_id": video_id,
            "url": video_url,
            "status": "UPLOADED",
            "publish_at": schedule_time_iso
        }

    def post_comment(self, video_id: str, comment_text: str) -> Optional[str]:
        """
        Posts a top-level comment directly from the channel under the uploaded video.
        """
        if not comment_text or not comment_text.strip():
            return None
        if not HAS_GOOGLE_API or not self.is_authenticated():
            state.add_col3_log(f"Simulating YouTube comment post on {video_id}: \"{comment_text[:40]}...\"")
            return "mock_comment_id"

        try:
            state.add_col3_log(f"Posting first discussion comment on {video_id}...")
            service = self.get_service()
            body = {
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text.strip()
                        }
                    }
                }
            }
            res = service.commentThreads().insert(
                part="snippet",
                body=body
            ).execute()
            comment_id = res.get("id")
            state.add_col3_log(f"First comment posted successfully! (ID: {comment_id})")
            return comment_id
        except Exception as e:
            state.add_col3_log(f"Warning: Failed to post first comment ({str(e)})")
            return None

uploader = YouTubeUploader()
try:
    state.youtube_quota = uploader.get_upload_quota()
except Exception:
    pass
