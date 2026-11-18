# AutoClipper: Tools, Libraries & Resource Directory

This document details every library, dependency, external API, container package, and algorithm needed to build and run the AutoClipper system.

---

## 1. Core Architecture Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend API & Orchestration** | **Python 3.11 + FastAPI + Uvicorn** | High-performance asynchronous REST API, WebSocket event broadcasting, and pipeline task coordinator |
| **Real-time Communication** | **WebSockets (`fastapi.WebSocket`)** | Low-latency bi-directional streaming of live chat velocity, process terminal logs, and queue timers to the dashboard |
| **Frontend Dashboard** | **React 18 + Vite + Tailwind CSS** | Single-page 3-lane visual interface with interactive clip player, live velocity charts, and approval controls |
| **UI Components & Icons** | **Lucide-React + Recharts** | Lightweight vector icons and responsive SVG charts for chat velocity sparklines and timeline markers |
| **Containerization** | **Docker + Docker Compose (ARM64)** | Multi-stage lightweight container configured for background execution on Windows ARM64 (Qualcomm Snapdragon X Plus) |

---

## 2. Pipeline Tools & Dependencies by Lane

### Lane 1: Stream Ingestion & Peak Detection
- **`streamlink` (`pip install streamlink`)**:
  - Live stream capture directly from Twitch with parameters: `--twitch-disable-ads`, `--twitch-low-latency`, `720p60`.
  - Pipes stream directly into a rolling circular buffer.
- **`websockets` / `aiohttp`**:
  - Connects to Twitch IRC via `wss://irc-ws.chat.twitch.tv:443`.
  - Anonymous read-only connection: `PASS SCHMOOPIE`, `NICK justinfan12345`, `JOIN #kaicenat`.
- **`numpy` & `scipy`**:
  - Fast rolling statistics ($\mu$, $\sigma$, Z-Score) on message frequency arrays to detect instant hype spikes without CPU thrashing.
- **Reference Model**:
  - [Digz0/TwitchPeakAnalyzer](https://github.com/Digz0/TwitchPeakAnalyzer): Chat velocity calculation methodology and spike clustering heuristics.

---

### Lane 2: Computer Vision, Facecam & 40/60 Layout
- **`face_recognition` (`pip install face_recognition`)** & **`dlib`**:
  - Wrapper repository: [ageitgey/face_recognition](https://github.com/ageitgey/face_recognition).
  - Uses the **HOG (Histogram of Oriented Gradients)** model for fast CPU inference on Snapdragon X Plus.
  - Locates face bounding box $[(y_{min}, x_{max}, y_{max}, x_{min})]$.
  - Facial landmarks (68 points) to compute Mouth Aspect Ratio (MAR) and Eye Aspect Ratio (EAR) for the **most exaggerated expression thumbnail**.
- **`opencv-python-headless` (`cv2`)**:
  - Video keyframe sampling, edge detection (`cv2.Canny`), and bounding contour detection to expand face bounds into the full rectangular facecam overlay.
  - Geometry calculations for the 40/60 split canvas ($1080 \times 1920$).
- **`ffmpeg` / `ffmpeg-python`**:
  - Slicing candidate segments from the circular buffer without re-encoding (`-c copy -ss ... -to ...`).
  - Complex filtergraph composition:
    - Top 40% Facecam crop ($1080 \times 768$).
    - Bottom 60% Gameplay crop ($1080 \times 1152$, centered horizontally).
    - Canvas stack: `vstack` filter.

---

### Lane 3: Audio Transcription, Captions & YouTube Publishing
- **Speech-to-Text Engine**:
  - Reference: [Kini218/speech-to-text](https://github.com/Kini218/speech-to-text) (uses `SpeechRecognition` and `pydub`).
  - Production Engine: **`faster-whisper`** (CTranslate2-based Whisper implementation):
    - Configured with `compute_type="int8"` and model `base.en` or `small.en` for fast, low-power CPU transcription on ARM64.
    - Yields precise word-level start and end timestamps.
- **Subtitle Generation (`pysubs2`)**:
  - Compiles structured **Advanced SubStation Alpha (`.ass`)** subtitle files:
    - Font: *Montserrat-BoldItalic* / *Arial-BoldItalic*.
    - Base Color: White (`&H00FFFFFF&`).
    - Outline: Black border (`&H00000000&`) with drop shadow.
    - Active Spoken Word Highlight: Vibrant Red (`&H001E1EFF&` in ASS format).
    - Chunking algorithm: Maximum 4 words and $\le 24$ characters per line.
    - Text Censorship filter: Regex-based masking for vulgarities (`f***`, `s***`, `b****`, `n****`), preserving raw audio.
- **`ffmpeg` Subtitle Burning**:
  - Burns `.ass` subtitles directly in the composition filterpass: `-vf "ass=subtitles.ass"`.
- **Title & Description Generation (AI Engine)**:
  - Supports Google Gemini API (`google-genai` / `google-generativeai`) or OpenAI API (`openai`), with an offline template fallback:
    - Uses transcript keywords + chat reactions to generate 3 punchy, high-CTR YouTube Shorts titles with `#shorts`.
- **YouTube Data API v3**:
  - Libraries: `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`.
  - Credentials: `client_secrets.json` and auto-refreshed `token.json`.
  - Upload parameters:
    - Title, Description, Tags, Category ID `20` (Gaming) or `24` (Entertainment).
    - Privacy: `private` or `unlisted` with scheduled `publishAt` timestamp (ISO 8601).
    - Thumbnail: Custom high-expression thumbnail upload via `thumbnails().set()`.

---

## 3. System & Docker Prerequisites (Snapdragon X Plus ARM64)

### Operating System & Docker Engine
- Windows 11 on ARM (with Docker Desktop running WSL2 Ubuntu or Hyper-V backend).
- Native ARM64 Linux container support enabled.

### Debian / Ubuntu System Packages (Dockerfile)
```dockerfile
# Multi-arch Debian Bookworm ARM64
apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    ffmpeg \
    fonts-montserrat \
    curl \
    git
```

### Complete Python Dependencies (`requirements.txt`)
```text
# Web Framework & Async
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
websockets>=12.0
aiofiles>=23.2.1
pydantic>=2.6.0

# Stream & Ingestion
streamlink>=6.6.0
yt-dlp>=2024.3.10

# Computer Vision & Face Detection
dlib>=19.24.2
face-recognition>=1.3.0
opencv-python-headless>=4.9.0.80
numpy>=1.26.4
scipy>=1.12.0
pillow>=10.2.0

# Audio & Speech-to-Text
faster-whisper>=1.0.1
pysubs2>=1.7.1

# AI & YouTube Publishing
google-api-python-client>=2.122.0
google-auth-oauthlib>=1.2.0
google-auth-httplib2>=0.2.0
google-generativeai>=0.4.1

# Utilities
python-dotenv>=1.0.1
```

---

## 4. External Credentials & Accounts Required

1. **Twitch**:
   - Zero credentials needed for reading live chat or stream video (public streamlink + anonymous IRC WebSocket `justinfan12345`).
2. **YouTube**:
   - Google Cloud Project with **YouTube Data API v3** enabled.
   - OAuth 2.0 Client ID (Web Application or Desktop App) delivering `client_secrets.json`.
3. **AI Title Model (Optional)**:
   - Free Google Gemini API key or OpenAI API key (an offline template generator will run if no key is entered).
