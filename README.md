# AutoClipper: Autonomous Twitch Stream Clipper & Shorts Pipeline

**AutoClipper** is a real-time autonomous video clipping, computer vision framing, speech transcription, and YouTube Shorts publishing pipeline engineered for high-energy Twitch broadcasts.

The system runs locally in the background on your hardware or in Docker, featuring a 3-column real-time web dashboard and dedicated clip review page.

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
git clone <your-repository-url>
cd AutoClipper

# Create and activate a Python virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install Python requirements
pip install -r requirements.txt

# (Optional) Rebuild the React frontend if modifying UI code
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
BUFFER_MINUTES=5

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
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_PORT=3000
```

---

### Step 3: Obtain a Free Gemini AI API Key

AutoClipper uses Google Gemini to generate viral titles, descriptions, and hashtag metadata from audio transcripts:

1. Visit [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google account.
3. Click **Get API key** and generate a new key.
4. Copy your key and paste it into `.env`:
   ```env
   GEMINI_API_KEY=AIzaSy...your_actual_key_here
   ```
*(Note: If no API key is provided or the 30 calls/day limit is reached, AutoClipper automatically falls back to an offline heuristic title generator so rendering never halts).*

---

### Step 4: Obtain YouTube Data API v3 OAuth Credentials

To enable automatic scheduling and direct Shorts publishing to your YouTube channel:

1. **Open Google Cloud Console**:
   Go to [https://console.cloud.google.com/](https://console.cloud.google.com/).
2. **Create a Project**:
   Click the project dropdown in the top bar and click **New Project** (e.g. name it `AutoClipper`).
3. **Enable YouTube Data API v3**:
   - Go to **APIs & Services** > **Library**.
   - Search for `YouTube Data API v3`.
   - Click on it and click **Enable**.
4. **Configure OAuth Consent Screen**:
   - Go to **APIs & Services** > **OAuth consent screen**.
   - Select **External** and click **Create**.
   - Fill in the required fields:
     - **App name**: `AutoClipper`
     - **User support email**: (Your personal Google email)
     - **Developer contact information**: (Your personal Google email)
   - Click **Save and Continue**.
   - **Scopes**: Click **Add or Remove Scopes**, select:
     - `.../auth/youtube.upload` (Upload YouTube videos)
     - `.../auth/youtube` (Manage your YouTube account)
   - Click **Save and Continue**.
   - **Test Users**: Under Test Users, click **Add Users** and enter the Google email address that owns your target YouTube channel.
   - Click **Save and Continue**.
5. **Create Desktop OAuth Client ID**:
   - Go to **APIs & Services** > **Credentials**.
   - Click **Create Credentials** > **OAuth client ID**.
   - For **Application type**, select **Desktop app**.
   - Set Name to `AutoClipper Desktop`.
   - Click **Create**.
6. **Download the Secrets File**:
   - Click the **Download JSON** button next to your new Client ID.
   - Rename the downloaded file to `client_secrets.json`.
   - Place this file in the `config/` directory:
     ```
     AutoClipper/config/client_secrets.json
     ```
7. **Authenticate Your Channel**:
   Run the one-click authentication script:
   ```powershell
   .\login_youtube.bat
   ```
   * A browser tab will open requesting permission.
   * Select your Google account and choose your YouTube channel.
   * Click **Continue** (or click Advanced > Go to AutoClipper if in Testing mode) and click **Allow**.
   * The script verifies your channel and saves an auto-refreshing authorization token to `config/token.json`.

---

## 🖥️ Using the Application

### Two-Tier Navbar Controls
* **Top Row**:
  * `AUTOCLIPPER`: Application brand.
  * `STREAM`: Click the pencil icon to switch target Twitch channels anytime.
  * Status Badge: Displays `720p60 LIVE`, `PAUSED (OFF)`, or `OFFLINE`.
  * System Telemetry: Live CPU utilization, buffer size in MB, daily AI call budget (`X / 30`), and clip count.
  * `YT: CONNECTED`: Confirms your YouTube channel is authenticated without leaking channel names.
* **Bottom Row**:
  * `[ENGINE: RUNNING / PAUSED]`: Master switch to halt or resume Twitch stream ingestion and IRC tracking.
  * `[AUTO-PROCESS: ON/OFF]`: Toggles automatic clipping of detected peak hype spikes.
  * `[AUTO-UPLOAD: ON/OFF]`: Toggles automatic dispatch to YouTube upon rendering.
  * `[🔊]`: Audio chime on chat hype spike.
  * Far-Right Triggers:
    * `TEST PEAK TRIGGER`: Simulates an artificial chat surge to test the entire pipeline.
    * `PREVIEW CLIP →`: Opens the active clip review page.

---

### Column 1: Peak Detection & Chat Stream
* **Multi-Factor Dynamic Requirements**:
  * Adapts baseline message velocity and Z-score thresholds based on streamer scale (`MEGA`, `LARGE`, `MEDIUM`, `SMALL`).
  * Live **Audio Scream Discount** (-0.35 Z on loud audio).
  * Live **Chat Hype Density Discount** (-0.25 Z on emote / all-caps surges).
  * Adjustable drawer to tune sensitivity, Base Z, and velocity targets.
* **Single-Clip Enforcement**: Strict mutex lock prevents concurrent processing—only 1 clip can process at a time.
* **Channel Switch Auto-Clear**: Changing the active streamer wipes all 3 columns and resets rolling buffers cleanly.

---

### Column 2: Facecam & Visual Framing
* **Primary Rule 1 (Webcam with Background / Border)**:
  * Detects the streamer's webcam overlay box and scales the entire section to measure just over $1080 \times 768$ (Top 40%).
  * Eliminates gameplay bleed and preserves full room/chair background without over-zooming.
* **Secondary Rule 2 (Cutout / Green Screen)**:
  * When no background or border exists, sizes the face to **exactly 50% of the 40% screen** ($384\text{px}$ tall) and centers it.
* **Interactive Mode Selector**: Toggle between `AUTO-DETECT`, `BOX (WITH BG)`, and `CUTOUT (NO BG)` in real time.

---

### Column 3: Speech, Subtitles & Rendering
* **Word Limit Chunking**: Subtitles and transcripts strictly enforce **maximum 4 words per row** with no character limits.
* **Natural Pause Snapping**: Cuts clip boundaries at natural speech silences ($>0.3\text{s}$) to avoid mid-sentence cutoffs.
* **Dynamic Karaoke Red Highlighting**: Active spoken words turn red (`#FF1E1E`) on white italicized text.
* **Text-Only Censorship**: Profanity is masked in subtitle text (`f***`) while audio remains 100% raw.

---

### Dedicated Preview & Review Page (`/preview`)
* Full $1080 \times 1920$ vertical player with instant playback.
* Direct **Download MP4** button.
* YouTube scheduled slot display with 1-post-a-day anti-clustering logic.
* **Manual Confirmation Safe Mode**: You explicitly approve or reject each clip before YouTube publishing.

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
├── frontend/           # React + Vite brutalist dashboard
│   └── src/components/ # Column1Peak, Column2Facecam, Column3Speech, Header, PreviewPage
├── config/             # client_secrets.json & token.json (Excluded by .gitignore)
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
