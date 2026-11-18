# AutoClipper: Autonomous Twitch Stream Clipper & Shorts Pipeline

**AutoClipper** is a real-time autonomous video clipping, computer vision framing, speech transcription, and YouTube Shorts publishing pipeline engineered for high-energy Twitch broadcasts.

The system runs locally in the background on your hardware or in Docker, featuring a modern brutalist dashboard, an interactive 16:9 **Clip Studio** with dual-box framing, and a dedicated 9:16 vertical preview & scheduling interface.

---

## 🔒 Security & Privacy Architecture

AutoClipper is built with privacy-by-design to ensure your personal data, credentials, and channels are protected:
* **Zero Channel Leaks**: The frontend and API endpoints do not broadcast or display private channel account names, emails, or credentials to client browsers.
* **Strict `.gitignore` Protection**: Your `.env` files, Google OAuth secrets (`config/client_secrets.json`), refresh tokens (`config/token.json`), media chunks, and server logs are strictly excluded from git tracking.
* **Local-First Processing**: Ingestion, computer vision facecam tracking, Faster-Whisper audio transcription, and FFmpeg video compositing execute 100% locally on your machine.

---

## ⚡ Quick Start

### 1-Click Launch (Windows)
Double-click `start.bat` or run in PowerShell:
```powershell
.\start.bat
```
Then open your browser to:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 🚀 Key Features & Tools

### 1. 🎬 Interactive 16:9 Clip Studio (`ClipStudio.tsx`)
When a peak occurs or when browsing clips, AutoClipper loads the candidate footage into a studio workspace:
* **True 16:9 Video Canvas**: Pixel-accurate display matching source resolution (`frameDim.w / frameDim.h`) with zero black borders.
* **Dual-Box Visual Framing**:
  * 🔴 **Red Box (Facecam)**: Clamped to a 9:6.4 (40% canvas) aspect ratio for the top section.
  * 🔵 **Blue Box (Gameplay)**: Clamped to a 9:9.6 (60% canvas) aspect ratio for the bottom section.
  * Drag, resize, or reposition boxes with live coordinate tracking and edge snapping.
  * **Auto-Detect Facecam**: One-click MediaPipe/YOLO detection with room/border boundary awareness.
  * **CLEAR ALL**: Instant reset to custom-crop any scene from scratch.
* **4-Minute Extended Candidate Timeline (240s)**:
  * Automatically captures **3 minutes before the peak** and **1 minute after the peak**.
  * Built-in **4.5-second Twitch reaction delay compensation** so peak markers align with visual in-game moments rather than delayed chat reactions.
* **Modernized Scrubber & Trimming**:
  * **Dedicated Video Position Scrubber**: Seamless seeking across the entire 240 seconds with instant time readout.
  * **Thin Green Trim Handles**: Minimalist `w-1.5` green start and end vertical indicators with expanded grab targets and subtle hover glows.
  * **Peak Moment Marker**: Visual yellow badge pinned to the exact peak event on the timeline.
* **AI Metadata Suite**:
  * Automatic viral title, description, and tags generated on peak ingest.
  * **REGENERATE AI TITLE** button to generate fresh title variations instantly.
* **Single-Click "CONFIRM & CREATE CLIP"**:
  * Trims selected start and end timestamps.
  * Fires single-pass FFmpeg 40/60 vertical composite.
  * Runs Faster-Whisper transcription and burns karaoke subtitles.
  * Smoothly navigates to the 9:16 Preview & Post page.

---

### 2. ⚡ Rolling Ring Buffer & Anti-Freeze Video Engine
* **8-Minute Rolling Ring Buffer**: Uses Streamlink and FFmpeg MPEG-TS segmenting to continuously maintain the last 8 minutes of live stream footage.
* **Continuous Timestamp Engine**:
  * Omits `-reset_timestamps 1` so PTS/DTS timestamps remain strictly continuous across `.ts` chunks.
  * Uses byte-level MPEG-TS merging + single-pass remux (`-fflags +genpts+igndts -avoid_negative_ts make_zero -movflags +faststart`).
  * **Zero Playback Freeze**: Completely eliminates video playback freezing at ~60 seconds, enabling smooth scrub across all 240 seconds.
* **Post-Peak Reaction Accumulator**:
  * The orchestrator automatically pauses for up to 60 seconds after a peak event to allow the stream buffer to capture the full 1-minute aftermath before cutting the candidate file.

---

### 3. 📈 Real-Time Peak Detection & Twitch GQL Live Polling
* **Live Audience Polling**: Polls Twitch GQL every 15 seconds to fetch accurate live viewer counts without API keys.
* **Dynamic Velocity Tiers**: Calibrates chat message velocity and Z-score baselines dynamically according to streamer audience size (`MEGA`, `LARGE`, `MEDIUM`, `SMALL`).
* **Multi-Factor Scoring**:
  * **Audio Scream / Loudness Discount**: Decreases required Z-score by `-0.35` on audio decibel spikes (throttled to avoid event-loop blocking).
  * **Emote & Hype Density Discount**: Decreases required Z-score by `-0.25` when chat spam contains high caps or hype emote concentration.
* **Manual Peak Sensitivity Drawer**: Sliders in Column 1 allow adjusting Base Z-Score, chat velocity multiplier, and cooldown in real time.

---

### 4. 🤖 Fully Autonomous & Semi-Autonomous Modes
* **Auto-Process Mode**: Automatically captures, frames, transcribes, and renders detected peaks into vertical Shorts without manual clicks.
* **Auto-Upload Mode**: Dispatches finalized clips directly to YouTube according to scheduled publishing windows.
* **Manual Review Safe Mode**: Default mode lets you review, refine crop boxes, adjust trim points, edit titles, and approve uploads before publishing.

---

### 5. 🗣️ Faster-Whisper Audio Transcription & Karaoke Subtitles
* **Local Faster-Whisper**: Runs high-speed local audio transcription without external API costs or latency.
* **Word Limit Chunking**: Subtitles strictly enforce **maximum 4 words per row** for maximum readability on mobile screens.
* **Natural Pause Snapping**: Trims clip boundaries at natural speech silences ($>0.3\text{s}$) to avoid awkward mid-word cuts.
* **Dynamic Karaoke Styling**: Active spoken words glow red (`#FF1E1E`) with high-contrast outlines on white italicized text.
* **Smart Censorship**: Profanity is masked in subtitle text (`f***`) while audio remains 100% untouched.

---

### 6. 📱 Dedicated Preview & Scheduling Interface (`/preview`)
* **1080×1920 Vertical Player**: Immediate playback with native sound and subtitle inspection.
* **1-Post-A-Day Anti-Clustering Scheduler**: Automatically calculates optimal YouTube scheduled time slots (e.g. 12:00 PM, 3:30 PM, 7:00 PM) to maximize algorithm reach.
* **Direct Actions**:
  * `APPROVE & SCHEDULE`: Submits video to YouTube with privacy status set to `private` and `publishAt` set to the calculated time slot.
  * `UPLOAD NOW`: Immediately publishes to YouTube as public or unlisted.
  * `DOWNLOAD MP4`: Saves rendered short directly to your device.
  * `PURGE CLIP`: Instantly deletes video files, candidate clips, thumbnails, and temp artifacts to reclaim SSD space.

---

## 📋 Prerequisites

Before running AutoClipper, ensure you have the following installed:
1. **Python 3.11 – 3.13** (64-bit) with `pip` in your system `PATH`.
2. **Node.js 18+** & `npm` (for frontend building).
3. **FFmpeg** installed and accessible from your terminal (`ffmpeg -version`).
4. **Streamlink** installed (`pip install streamlink` or via package manager).

---

## 🛠️ Step-by-Step Setup Guide

### Step 1: Clone the Repository & Install Dependencies

```powershell
# Clone the repository
git clone https://github.com/Shazzz135/AutoClipper.git
cd AutoClipper

# Create and activate a Python virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install Python requirements
pip install -r requirements.txt

# Build the React/TypeScript frontend
npm --prefix frontend install
npm --prefix frontend run build
```

---

### Step 2: Configure Environment Variables (`.env`)

Copy the template file to create your local `.env`:
```powershell
copy .env.example .env
```

Open `.env` in any text editor and customize the parameters:

```env
# ==========================================
# AutoClipper Configuration
# ==========================================

# Google Gemini AI (Title & Metadata Generation)
GEMINI_API_KEY=your_gemini_api_key_here
AI_MAX_CALLS_PER_MINUTE=10
AI_MAX_CALLS_PER_DAY=30
AI_FALLBACK_ON_LIMIT=true

# YouTube OAuth Paths
YOUTUBE_CLIENT_SECRETS_PATH=config/client_secrets.json
YOUTUBE_TOKEN_PATH=config/token.json

# Twitch Stream Ingestion
TWITCH_CHANNEL=jynxzi
STREAM_QUALITY=720p60
BUFFER_MINUTES=8

# Peak Detection & Clipping Defaults
MAX_CLIP_DURATION=45
PEAK_COOLDOWN_SECONDS=60
PEAK_Z_SCORE_THRESHOLD=3.0
PEAK_MIN_VELOCITY=10.0
AUTO_PROCESS_PEAKS=false

# 40/60 Split Canvas Dimensions
OUTPUT_WIDTH=1080
OUTPUT_HEIGHT=1920
LAYOUT_FACECAM_RATIO=0.40
LAYOUT_GAMEPLAY_RATIO=0.60

# Subtitle Specifications
SUBTITLE_MAX_WORDS=4
SUBTITLE_VERTICAL_POS_PCT=0.20
SUBTITLE_ACTIVE_COLOR=#FF1E1E
SUBTITLE_CENSOR_TEXT=true

# YouTube Scheduling & Publishing
YOUTUBE_SCHEDULE_SLOTS=12:00,15:30,19:00
YOUTUBE_TIMEZONE=America/New_York
YOUTUBE_DEFAULT_PRIVACY=scheduled
REQUIRE_MANUAL_APPROVAL=true
AUTO_UPLOAD_ENABLED=false
REVIEW_COUNTDOWN_MINUTES=10

# Server Binding
BACKEND_HOST=localhost
BACKEND_PORT=8000
FRONTEND_PORT=3000
```

---

### Step 3: Obtain a Free Gemini AI API Key

AutoClipper uses Google Gemini to generate viral titles, descriptions, and hashtag metadata:
1. Visit [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google account.
3. Click **Get API key** and generate a new key.
4. Paste the key into `.env`:
   ```env
   GEMINI_API_KEY=AIzaSy...your_actual_key_here
   ```
*(Note: If no API key is provided or the daily quota is reached, AutoClipper automatically falls back to an offline heuristic title generator).*

---

### Step 4: YouTube Data API v3 OAuth Credentials (Optional for Direct Uploads)

To enable automatic scheduling and direct Shorts publishing to your YouTube channel:
1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project (`AutoClipper`).
2. Enable **YouTube Data API v3**.
3. Configure the **OAuth Consent Screen** (User Type: External, Scopes: `youtube.upload` and `youtube`, add your email as a Test User).
4. Create an **OAuth Client ID** of type **Desktop app**.
5. Download the client secrets JSON, rename it to `client_secrets.json`, and place it in `config/client_secrets.json`.
6. Run the authentication script:
   ```powershell
   .\login_youtube.bat
   ```
7. Approve permissions in the browser. The token is saved to `config/token.json` and auto-refreshes.

---

## 📁 Repository Structure

```
AutoClipper/
├── backend/
│   ├── core/           # Config, state management, scheduler, events
│   ├── ingestion/      # Anonymous Twitch IRC client & streamlink rolling buffer
│   ├── pipeline/       # Peak detector, facecam cropper, transcription, subtitles, AI
│   ├── uploader/       # YouTube Data API v3 uploader & token switcher
│   ├── video/          # Single-pass FFmpeg compositor
│   └── main.py         # FastAPI application & WebSocket server
├── frontend/           # React 18 + TypeScript + Vite + Tailwind CSS
│   ├── src/
│   │   ├── components/ # ClipStudio, Column1Peak, Column2Facecam, Column3Speech, Header, PreviewPage
│   │   ├── services/   # Sound notification dispatcher
│   │   ├── App.tsx     # Main application layout & WebSocket listener
│   │   └── main.tsx    # Application entry point
│   └── package.json
├── config/             # client_secrets.json & token.json (Strictly ignored by .gitignore)
├── scripts/            # Standalone YouTube OAuth verification script
├── start.bat           # 1-Click native Windows startup script
├── login_youtube.bat   # 1-Click YouTube channel login script
├── .env.example        # Environment variable template
├── .gitignore          # Comprehensive credential & artifact exclusion rules
└── requirements.txt    # Python dependencies
```

---

## 📄 License
This software is provided for personal and educational use. Ensure compliance with Twitch and YouTube Terms of Service when ingesting and publishing stream content.
