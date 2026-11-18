import asyncio
import json
import re
import time
import urllib.request
from datetime import datetime
import websockets
from backend.core.config import settings
from backend.core.state import state

# Regex for Twitch PRIVMSG (supports optional IRCv3 @tags prefix and standard usernames)
CHAT_MSG_REGEX = re.compile(r"(?:^@\S+\s+)?:([a-zA-Z0-9_]+)![^@]+@[^\s]+\.tmi\.twitch\.tv\s+PRIVMSG\s+#\S+\s+:(.*)$")

# Public Twitch Web Client ID used by Twitch web player / streamlink for unauthenticated stream metadata
TWITCH_PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

class TwitchIRCClient:
    def __init__(self, channel: str, on_message_callback=None):
        self.channel = channel.lower().lstrip("#")
        self.on_message_callback = on_message_callback
        self.ws_url = "wss://irc-ws.chat.twitch.tv:443"
        self.is_running = False
        self._task = None
        self._metadata_task = None

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._listen_loop())
        self._metadata_task = asyncio.create_task(self._poll_stream_metadata_loop())
        state.add_col1_log(f"Twitch IRC & Live Viewer Tracker started for #{self.channel}")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
        if self._metadata_task:
            self._metadata_task.cancel()
        state.add_col1_log("Twitch IRC client stopped")

    def _fetch_live_stream_metadata_sync(self, channel_login: str):
        """Fetches real-time viewer count, stream title, and game from Twitch public GraphQL API."""
        query = {
            "query": """
            query($login: String!) {
              user(login: $login) {
                stream {
                  viewersCount
                  title
                  createdAt
                  game {
                    name
                  }
                }
              }
            }
            """,
            "variables": {"login": channel_login.lower().strip()}
        }
        req = urllib.request.Request(
            "https://gql.twitch.tv/gql",
            data=json.dumps(query).encode("utf-8"),
            headers={
                "Client-ID": TWITCH_PUBLIC_CLIENT_ID,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            user_data = (payload.get("data") or {}).get("user") or {}
            return user_data.get("stream")

    async def _poll_stream_metadata_loop(self):
        """Polls exact live viewer count every 15 seconds so peak detection scales accurately."""
        while self.is_running:
            try:
                stream_info = await asyncio.to_thread(self._fetch_live_stream_metadata_sync, self.channel)
                if stream_info:
                    viewers = int(stream_info.get("viewersCount") or 0)
                    if viewers > 0:
                        state.stream_viewers = viewers
                    state.stream_online = True
                    state.stream_title = str(stream_info.get("title") or "")
                    game_obj = stream_info.get("game") or {}
                    state.stream_game = str(game_obj.get("name") or "")
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            await asyncio.sleep(15)

    async def _listen_loop(self):
        while self.is_running:
            try:
                state.add_col1_log(f"Connecting to Twitch IRC WebSocket for #{self.channel}...")
                async with websockets.connect(self.ws_url) as ws:
                    # Anonymous authentication handshake
                    await ws.send("PASS SCHMOOPIE\r\n")
                    await ws.send("NICK justinfan12345\r\n")
                    await ws.send(f"JOIN #{self.channel}\r\n")
                    state.add_col1_log(f"Connected and joined #{self.channel}")

                    async for message in ws:
                        if not self.is_running:
                            break

                        # Handle Ping/Pong keepalive
                        if message.startswith("PING"):
                            await ws.send("PONG :tmi.twitch.tv\r\n")
                            continue

                        # Parse PRIVMSG
                        for line in message.split("\r\n"):
                            match = CHAT_MSG_REGEX.match(line)
                            if match:
                                username, text = match.groups()
                                now_str = datetime.now().strftime("%H:%M:%S")
                                chat_entry = {
                                    "time": now_str,
                                    "user": username,
                                    "msg": text
                                }
                                state.recent_chat.append(chat_entry)
                                if len(state.recent_chat) > 50:
                                    state.recent_chat.pop(0)

                                if self.on_message_callback:
                                    try:
                                        self.on_message_callback(text, username)
                                    except TypeError:
                                        self.on_message_callback(text)

            except asyncio.CancelledError:
                break
            except Exception as e:
                state.add_col1_log(f"Twitch IRC error: {str(e)}. Reconnecting in 5s...")
                await asyncio.sleep(5)
