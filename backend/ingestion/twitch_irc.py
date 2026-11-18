import asyncio
import re
import time
from datetime import datetime
import websockets
from backend.core.config import settings
from backend.core.state import state

# Regex for Twitch PRIVMSG
CHAT_MSG_REGEX = re.compile(r"^:(\w+)!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :(.*)$")

class TwitchIRCClient:
    def __init__(self, channel: str, on_message_callback=None):
        self.channel = channel.lower().lstrip("#")
        self.on_message_callback = on_message_callback
        self.ws_url = "wss://irc-ws.chat.twitch.tv:443"
        self.is_running = False
        self._task = None

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._listen_loop())
        state.add_col1_log(f"Twitch IRC client started for #{self.channel}")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
        state.add_col1_log("Twitch IRC client stopped")

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
