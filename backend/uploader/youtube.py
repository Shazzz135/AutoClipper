import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
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
            res = {
                "status": "EXPIRED",
                "authenticated": False,
                "error": "Google session expired (7-day testing limit or revoked). Re-authentication required." if is_invalid_grant else err_str,
                "days_old": days_old,
                "expiring_soon": False,
                "channel_title": "Session Expired"
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
        """
        tokens_dir = settings.BASE_DIR / "config" / "tokens"
        tokens_dir.mkdir(parents=True, exist_ok=True)
        if not self.token_path.exists():
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

        return None

    def get_available_accounts(self) -> list:
        """
        Lists all saved YouTube channel tokens from config/tokens/
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

        # If none matched active but accounts exist, mark the first one if active_channel is generic
        if accounts and not any(a["is_active"] for a in accounts):
            accounts[0]["is_active"] = True

        return accounts

    def switch_account(self, account_id: str) -> dict:
        """
        Dynamically switches active YouTube channel to the specified account token.
        """
        import shutil
        tokens_dir = settings.BASE_DIR / "config" / "tokens"
        target_file = tokens_dir / f"{account_id}.json"
        if not target_file.exists():
            target_file = tokens_dir / account_id
            if not target_file.exists():
                raise FileNotFoundError(f"Account token not found for: {account_id}")

        account_stem = target_file.stem

        # Overwrite current token.json with target account token
        shutil.copy(target_file, self.token_path)

        # Force reload service lazily on next API call
        self._service = None
        target_streamer = self.get_streamer_for_account(account_stem)

        state.youtube_channel = account_stem
        state.add_col3_log(f"Switched active YouTube account to: {account_stem} (Streamer: #{target_streamer})")

        return {
            "status": "SWITCHED",
            "account_id": account_stem,
            "active_channel": account_stem,
            "streamer": target_streamer
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

    def get_scheduled_publish_times(self) -> list:
        """
        Returns a list of datetime objects for all scheduled videos on YouTube.
        """
        details = self.get_scheduled_videos_detailed()
        return [d["dt"] for d in details]

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

        # Setup metadata body
        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": list(set(tags + ["shorts", "youtubeshorts", "short", "viral"])),
                "categoryId": "20" # Gaming category
            },
            "status": {
                "privacyStatus": privacy_setting,
                "selfDeclaredMadeForKids": False
            }
        }

        # If scheduled time is provided, YouTube strictly requires privacyStatus = 'private' with publishAt
        if schedule_time_iso:
            body["status"]["privacyStatus"] = "private"
            body["status"]["publishAt"] = schedule_time_iso

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            chunksize=-1,
            resumable=True
        )

        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                state.add_col3_log(f"YouTube upload progress: {int(status.progress() * 100)}%")

        video_id = response.get("id")
        video_url = f"https://youtube.com/shorts/{video_id}"
        state.add_col3_log(f"Uploaded successfully! Video ID: {video_id} ({video_url})")

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
