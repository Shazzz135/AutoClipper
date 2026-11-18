import os
import json
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
        return self.token_path.exists()

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

    def get_available_accounts(self) -> list:
        """
        Lists all saved YouTube channel tokens from config/tokens/
        """
        import shutil
        tokens_dir = settings.BASE_DIR / "config" / "tokens"
        tokens_dir.mkdir(parents=True, exist_ok=True)

        current_token_path = settings.BASE_DIR / settings.YOUTUBE_TOKEN_PATH
        token_files = list(tokens_dir.glob("*.json"))

        active_channel = getattr(state, "youtube_channel", "") or "CONNECTED"
        accounts = []

        for f in token_files:
            account_id = f.stem
            display_name = account_id.replace("_", " ")
            is_active = (account_id.lower() == active_channel.replace(" ", "").lower()) or (display_name.lower() == active_channel.lower())

            accounts.append({
                "id": account_id,
                "name": display_name,
                "file": f.name,
                "is_active": is_active
            })

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

        # Overwrite current token.json with target account token
        shutil.copy(target_file, self.token_path)

        # Force reload service
        self.reload_credentials()
        new_name = account_id.replace("_", " ")
        try:
            info = self.get_channel_info()
            if info.get("channel_title") and info["channel_title"] not in ["Not Connected", "Auth Error", "No Channel Found"]:
                new_name = info["channel_title"]
        except Exception:
            info = {}

        state.youtube_channel = new_name
        state.add_col3_log(f"Switched active YouTube channel to: {new_name}")

        return {
            "status": "SWITCHED",
            "active_channel": new_name,
            "channel_info": info if 'info' in locals() else {}
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

        # Setup metadata body
        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags,
                "categoryId": "20" # Gaming category
            },
            "status": {
                "privacyStatus": settings.YOUTUBE_DEFAULT_PRIVACY,
                "selfDeclaredMadeForKids": False
            }
        }

        # If scheduled time is provided, YouTube requires privacyStatus = 'private' with publishAt
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

uploader = YouTubeUploader()
